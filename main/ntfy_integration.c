/* Optional ntfy integration.
 *
 * No traffic is emitted unless explicitly enabled. The access token is never
 * returned by the web API, written to logs, or included in status replies.
 */
#include "ntfy_integration.h"
#include "ntfy_json_stream.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "runtime_metrics.h"
#include "snmp_agent.h"
#include "dhcps_ext.h"
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "fourvia6.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/ip4_addr.h"
#include "microlink.h"
#include "mqtt_integration.h"
#include "nvs_params.h"
#include "wifi_power_save.h"
#include "nvs.h"
#include "tailscale_config.h"
#include "peer_dns.h"
#include "ota_remote.h"
#include "wol.h"
#include "homelab_ops.h"
#include "service_lease.h"
#include "service_retry.h"
#include "ntfy_events.h"
#include "tailnet_forward.h"
#include "web_ui.h"

static const char *TAG = "ntfy";
static ntfy_integration_config_t s_config;
static ntfy_integration_status_t s_status;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;
static char s_last_event_id[48];
/* Changes invalidate queued replies, including a disable/re-enable cycle. */
static uint64_t s_config_generation;
static char s_operational_event[160];
static uint64_t s_operational_generation;

bool ntfy_integration_queue_event(const char *message)
{
    if(!s_lock || !message || strlen(message)>=sizeof s_operational_event)return false;
    xSemaphoreTake(s_lock,portMAX_DELAY);
    bool accepted=s_config.enabled && !s_operational_event[0];
    if(accepted){strlcpy(s_operational_event,message,sizeof s_operational_event);s_operational_generation=s_config_generation;}
    xSemaphoreGive(s_lock);return accepted;
}

/* TLS certificate verification needs its own stack reserve. Keep the large
 * reporting/polling frames out of task_main: GCC otherwise inlines them and
 * permanently reserves their buffers even on a simple command poll. */
#define NTFY_TASK_STACK_BYTES 12288
#define NTFY_NOINLINE __attribute__((noinline))

extern bool wifi_ap_runtime_enabled(void);
extern bool wifi_ap_policy_auto_off(void);

#define NTFY_POLL_BATCH 32
typedef struct {
    ntfy_json_parser_t parser;
    ntfy_json_event_t events[NTFY_POLL_BATCH];
    size_t count;
    char read_buffer[512];
} command_batch_t;

static void defaults(ntfy_integration_config_t *c)
{
    memset(c, 0, sizeof *c);
    strlcpy(c->server, "https://ntfy.sh", sizeof c->server);
    c->failure_delay_seconds = 120;
    c->poll_interval_seconds = 15;
    c->commands_only_when_tailscale_down = true;
    c->info_enabled = true;
}

static bool load_string(const char *key, char *out, size_t size)
{
    /* Distinguish a missing optional key from a read/allocation/type error.
     * Never turn a failed token read into an anonymous configuration. */
    size_t length = size;
    esp_err_t err = nvs_param_get_str_buf(key, out, &length);
    return err == ESP_OK || err == ESP_ERR_NVS_NOT_FOUND;
}

static bool load_config(ntfy_integration_config_t *c)
{
    defaults(c);
    bool valid = true;
#define LOAD_U8(key, field) do { uint8_t b; esp_err_t err = nvs_param_get_u8((key), &b); \
    if (err == ESP_OK && b <= 1) (field) = b != 0; \
    else if (err != ESP_ERR_NVS_NOT_FOUND) valid = false; } while (0)
#define LOAD_U16(key, field) do { uint16_t n; esp_err_t err = nvs_param_get_u16((key), &n); \
    if (err == ESP_OK) (field) = n; \
    else if (err != ESP_ERR_NVS_NOT_FOUND) valid = false; } while (0)
    LOAD_U8("ntfy_en", c->enabled); LOAD_U8("ntfy_alert", c->tailscale_alerts);
    LOAD_U8("ntfy_cmd", c->commands_enabled);
    LOAD_U8("ntfy_down", c->commands_only_when_tailscale_down);
    LOAD_U8("ntfy_mac", c->allow_direct_mac); LOAD_U8("ntfy_info", c->info_enabled);
    LOAD_U8("ntfy_infdet", c->info_include_details);
    LOAD_U16("ntfy_delay", c->failure_delay_seconds);
    LOAD_U16("ntfy_poll", c->poll_interval_seconds);
#undef LOAD_U8
#undef LOAD_U16
    valid = load_string("ntfy_srv", c->server, sizeof c->server) && valid;
    valid = load_string("ntfy_topic", c->topic, sizeof c->topic) && valid;
    valid = load_string("ntfy_token", c->token, sizeof c->token) && valid;
    return valid;
}

static bool topic_valid(const char *topic)
{
    if (!topic || !topic[0]) return false;
    for (const unsigned char *p = (const unsigned char *)topic; *p; p++)
        if (!isalnum(*p) && *p != '-' && *p != '_') return false;
    return true;
}

static bool token_header_valid(const char *token)
{
    if (!token) return false;
    for (const unsigned char *p = (const unsigned char *)token; *p; ++p)
        if (*p <= 32 || *p >= 127) return false;
    return true; /* Empty token is valid for explicitly anonymous topics. */
}

static bool config_valid(const ntfy_integration_config_t *c)
{
    if (!c || !memchr(c->server, 0, sizeof c->server) ||
        !memchr(c->topic, 0, sizeof c->topic) ||
        !memchr(c->token, 0, sizeof c->token) || !token_header_valid(c->token)) return false;
    bool server_ok = strncmp(c->server, "https://", 8) == 0
                   || strncmp(c->server, "http://", 7) == 0;
    /* Topic is appended as a path segment, so query/fragment syntax has no
     * valid role in the base URL. Reject whitespace/control characters and
     * URI user-info as well: tokens use the write-only Authorization field
     * and must never become part of a URL that may be logged or returned. */
    if (strpbrk(c->server, "@?#\r\n\t ") != NULL) server_ok = false;
    for (const unsigned char *p = (const unsigned char *)c->server; *p; ++p)
        if (*p <= 32 || *p >= 127 || *p == '\\') server_ok = false;
    return (!c->enabled || (server_ok && topic_valid(c->topic)))
        && c->failure_delay_seconds >= 15 && c->failure_delay_seconds <= 3600
        && c->poll_interval_seconds >= 5 && c->poll_interval_seconds <= 300;
}

/* Configuration and its endpoint-bound replay cursor are one versioned NVS
 * value. Writing individual keys can leave a partially updated configuration
 * after a flash allocation failure or reset. Never serialize native bools:
 * validate an explicit bitset before decoding untrusted persisted bytes. */
typedef struct {
    uint32_t schema;
    uint32_t flags;
    uint16_t delay, poll;
    char server[160], topic[96], token[160], cursor[48];
} saved_ntfy_state_t;

static bool event_id_valid(const char *id)
{
    size_t length = 0;
    if (!id || !id[0]) return false;
    for (const unsigned char *p = (const unsigned char *)id; *p; ++p) {
        if (++length >= sizeof s_last_event_id ||
            !((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '-' || *p == '_')) return false;
    }
    return true;
}

/* Caller holds s_lock (or runs before the worker is started). This lock is
 * held only for short NVS operations, never across HTTP/TLS or command work. */
static NTFY_NOINLINE esp_err_t save_state(const ntfy_integration_config_t *c,
                                        const char *cursor)
{
    saved_ntfy_state_t saved = {0};
    saved.schema = 1;
    saved.flags = (c->enabled ? 1U : 0) | (c->tailscale_alerts ? 2U : 0) |
        (c->commands_enabled ? 4U : 0) | (c->commands_only_when_tailscale_down ? 8U : 0) |
        (c->allow_direct_mac ? 16U : 0) | (c->info_enabled ? 32U : 0) |
        (c->info_include_details ? 64U : 0);
    saved.delay = c->failure_delay_seconds; saved.poll = c->poll_interval_seconds;
    strlcpy(saved.server, c->server, sizeof saved.server);
    strlcpy(saved.topic, c->topic, sizeof saved.topic);
    strlcpy(saved.token, c->token, sizeof saved.token);
    strlcpy(saved.cursor, cursor, sizeof saved.cursor);
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "ntfy_state_v1", &saved, sizeof saved);
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    return err;
}

static void load_state(ntfy_integration_config_t *c)
{
    defaults(c);
    s_last_event_id[0] = 0;
    saved_ntfy_state_t saved;
    size_t length = sizeof saved;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (err == ESP_OK) {
        err = nvs_get_blob(nvs, "ntfy_state_v1", &saved, &length);
        nvs_close(nvs);
    }
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        /* One-time migration. Keep legacy values untouched for recovery;
         * after success the new record is authoritative, even if corrupt. */
        bool legacy_valid = load_config(c);
        if (!load_string("ntfy_last", s_last_event_id, sizeof s_last_event_id))
            s_last_event_id[0] = 0;
        if (!event_id_valid(s_last_event_id)) s_last_event_id[0] = 0;
        if (legacy_valid && config_valid(c) && save_state(c, s_last_event_id) == ESP_OK) return;
    } else if (err == ESP_OK && length == sizeof saved && saved.schema == 1 &&
               (saved.flags & ~127U) == 0 &&
               memchr(saved.server, 0, sizeof saved.server) &&
               memchr(saved.topic, 0, sizeof saved.topic) &&
               memchr(saved.token, 0, sizeof saved.token) &&
               memchr(saved.cursor, 0, sizeof saved.cursor) &&
               (!saved.cursor[0] || event_id_valid(saved.cursor))) {
        c->enabled = (saved.flags & 1U) != 0;
        c->tailscale_alerts = (saved.flags & 2U) != 0;
        c->commands_enabled = (saved.flags & 4U) != 0;
        c->commands_only_when_tailscale_down = (saved.flags & 8U) != 0;
        c->allow_direct_mac = (saved.flags & 16U) != 0;
        c->info_enabled = (saved.flags & 32U) != 0;
        c->info_include_details = (saved.flags & 64U) != 0;
        c->failure_delay_seconds = saved.delay; c->poll_interval_seconds = saved.poll;
        strlcpy(c->server, saved.server, sizeof c->server);
        strlcpy(c->topic, saved.topic, sizeof c->topic);
        strlcpy(c->token, saved.token, sizeof c->token);
        if (config_valid(c)) {
            strlcpy(s_last_event_id, saved.cursor, sizeof s_last_event_id);
            return;
        }
    }
    /* Never fall back to an old enabled configuration on corruption/errors. */
    defaults(c); s_last_event_id[0] = 0;
    ESP_LOGW(TAG, "Stored settings unavailable or invalid; integration disabled");
}

static void snapshot(ntfy_integration_config_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(out, &s_config, sizeof *out);
    xSemaphoreGive(s_lock);
}

static void build_url(const ntfy_integration_config_t *c, const char *suffix,
                      char *out, size_t out_size)
{
    size_t n = strlen(c->server);
    while (n > 0 && c->server[n - 1] == '/') n--;
    snprintf(out, out_size, "%.*s/%s%s", (int)n, c->server, c->topic,
             suffix ? suffix : "");
}

static esp_err_t set_auth(esp_http_client_handle_t client,
                     const ntfy_integration_config_t *c)
{
    if (!memchr(c->token, 0, sizeof c->token) || !token_header_valid(c->token))
        return ESP_ERR_INVALID_ARG;
    if (!c->token[0]) return ESP_OK;
    char value[176];
    snprintf(value, sizeof value, "Bearer %s", c->token);
    return esp_http_client_set_header(client, "Authorization", value);
}

static NTFY_NOINLINE esp_err_t publish_message(const ntfy_integration_config_t *c,
                                 const char *title, const char *tags,
                                 const char *message)
{
    if(!homelab_ops_admit())return ESP_ERR_NO_MEM;
    char url[288];
    build_url(c, NULL, url, sizeof url);
    esp_http_client_config_t config = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 12000,
        .crt_bundle_attach = esp_crt_bundle_attach,
        /* SDK redirection retains manually installed Authorization headers
         * and POST data. Never replay the token or private info to a new
         * origin (or silently downgrade HTTPS). Configure the final URL. */
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return ESP_ERR_NO_MEM;
    esp_err_t err = set_auth(client, c);
    esp_http_client_set_header(client, "Content-Type", "text/plain; charset=utf-8");
    if (title) esp_http_client_set_header(client, "Title", title);
    if (tags) esp_http_client_set_header(client, "Tags", tags);
    esp_http_client_set_post_field(client, message, strlen(message));
    if (err == ESP_OK) err = esp_http_client_perform(client);
    int status = err == ESP_OK ? esp_http_client_get_status_code(client) : 0;
    esp_http_client_cleanup(client);
    bool ok = err == ESP_OK && status >= 200 && status < 300;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.last_publish_ok = ok;
    xSemaphoreGive(s_lock);
    if (!ok) ESP_LOGW(TAG, "publish failed: %s HTTP %d", esp_err_to_name(err), status);
    return ok ? ESP_OK : (err == ESP_OK ? ESP_FAIL : err);
}

static void appendf(char *out, size_t size, const char *fmt, ...)
{
    size_t used = strlen(out);
    if (used >= size - 1) return;
    va_list args;
    va_start(args, fmt);
    vsnprintf(out + used, size - used, fmt, args);
    va_end(args);
}

static NTFY_NOINLINE esp_err_t send_info(const ntfy_integration_config_t *c)
{
    char *text = calloc(1, 8192);
    if (!text) return ESP_ERR_NO_MEM;
    const esp_app_desc_t *app = esp_app_get_description();
    runtime_metrics_t cpu = runtime_metrics_get();
    if (cpu.valid)
        appendf(text, 8192, "CPU: %u%% (core 0: %u%%, core 1: %u%%)\n",
                cpu.load_pct, cpu.core_pct[0], cpu.core_pct[1]);
    else
        appendf(text, 8192, "CPU: sample not available yet\n");
    appendf(text, 8192, "Firmware: %s\nUptime: %llu s\nFree heap: %lu B (minimum %lu B)\nReset reason: %d\nWeb UI port: %u\n",
            app ? app->version : "unknown", esp_timer_get_time() / 1000000ULL,
            (unsigned long)esp_get_free_heap_size(),
            (unsigned long)esp_get_minimum_free_heap_size(), (int)esp_reset_reason(),
            (unsigned)web_ui_configured_port());
    appendf(text, 8192, "Socket limit: %d\nSNMP: %s (%s)\n",
            CONFIG_LWIP_MAX_SOCKETS, snmp_agent_is_enabled() ? "enabled" : "disabled",
            snmp_agent_is_running() ? "running" : "stopped");
    ops_resources_t resources;homelab_ops_resources(&resources);
    appendf(text,8192,"Operational resources: sockets %d/%d, internal min %lu B, largest block %lu B\n",
        resources.sockets_used,resources.socket_limit,(unsigned long)resources.internal_min,(unsigned long)resources.internal_largest);
    cJSON *operations=homelab_ops_snapshot(false);
    if(operations){
        const cJSON *state=cJSON_GetObjectItemCaseSensitive(operations,"recovery_state");
        appendf(text,8192,"Recovery/check: %s (sending WoL is not proof of boot)\n",cJSON_IsString(state)?state->valuestring:"unavailable");
        const cJSON *health=cJSON_GetObjectItemCaseSensitive(operations,"health"),*check;
        cJSON_ArrayForEach(check,cJSON_GetObjectItemCaseSensitive(health,"checks")){
            const cJSON *role=cJSON_GetObjectItemCaseSensitive(check,"role"),*status=cJSON_GetObjectItemCaseSensitive(check,"state");
            appendf(text,8192,"Configured %s: %s\n",cJSON_IsString(role)?role->valuestring:"check",cJSON_IsString(status)?status->valuestring:"unknown");
        }
        cJSON_Delete(operations);
    }
    cJSON *leases=service_lease_snapshot();
    if(leases){const cJSON *lease;cJSON_ArrayForEach(lease,leases){
        const cJSON *status=cJSON_GetObjectItemCaseSensitive(lease,"status"),*index=cJSON_GetObjectItemCaseSensitive(lease,"index"),*remaining=cJSON_GetObjectItemCaseSensitive(lease,"remaining_s");
        appendf(text,8192,"LAN→Tailnet rule %d lease: %s, %.0f seconds remaining\n",cJSON_IsNumber(index)?index->valueint+1:0,cJSON_IsString(status)?status->valuestring:"unknown",cJSON_IsNumber(remaining)?remaining->valuedouble:0);
    }cJSON_Delete(leases);}

    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    wifi_ap_record_t ap = {0};
    bool uplink = sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr;
    bool have_ap = esp_wifi_sta_get_ap_info(&ap) == ESP_OK;
    appendf(text, 8192, "\nUplink: %s\nRSSI: %d dBm\n",
            uplink ? "connected" : "disconnected", have_ap ? ap.rssi : 0);
    bool wifi_ps_active = false;
    bool wifi_ps_known = wifi_power_save_runtime(&wifi_ps_active);
    appendf(text, 8192, "WiFi power save: %s (runtime: %s)\n",
            wifi_power_save_configured() ? "on" : "off",
            wifi_ps_known ? (wifi_ps_active ? "on" : "off") : "unknown");
    if (c->info_include_details) {
        appendf(text, 8192, "WiFi SSID: %s\nLocal IP: " IPSTR
                "\nNetmask: " IPSTR "\nGateway: " IPSTR "\n",
                have_ap ? (char *)ap.ssid : "", IP2STR(&ip.ip),
                IP2STR(&ip.netmask), IP2STR(&ip.gw));
    }

    bool ts = tailscale_is_connected();
    ip4_addr_t ts_ip = {.addr = tailscale_tunnel_ip};
    appendf(text, 8192, "\nTailscale: %s (enabled: %s)\nAdvertise as exit node: %s\n",
            ts ? "connected" : "disconnected", tailscale_enabled ? "yes" : "no",
            tailscale_advertise_exit_node ? "yes" : "no");
    microlink_t *ml = tailscale_get_microlink();
    ota_remote_state_t update; ota_remote_get_state(&update);
    appendf(text, 8192, "GitHub updates: checks %s, automatic install %s, channel %s\nUpdate: %s (%s)\n",
            update.config.enabled ? "on" : "off", update.config.auto_install ? "on" : "off",
            update.config.beta_channel ? "stable + beta" : "stable only",
            update.latest_version[0] ? update.latest_version : "none", update.status);
    appendf(text, 8192, "Exit-node server (this boot): %s\nExit-node DNS: %s (port %u)\n",
            tailscale_exit_server_active() ? "active" : "inactive",
            peer_dns_is_running() ? "running" : "stopped", (unsigned)tailscale_peerapi_port());
    appendf(text, 8192, "Exit-node server configured: %s (manual default route: %s)\n",
            tailscale_exit_server_configured() ? "yes" : "no",
            tailscale_manual_exit_configured() ? "yes" : "no");
    appendf(text, 8192, "Automatic AP advertisement (configured): %s\n",
            tailscale_advertise_ap ? "yes" : "no");
    int peers = ml ? microlink_get_peer_count(ml) : 0;
    appendf(text, 8192, "Peers (%d):\n", peers);
    if (c->info_include_details) {
        appendf(text, 8192, "Tailscale IP: " IPSTR
                "\nActive advertised routes: %s\nAccept peer routes: %s\nSource NAT: %s\n",
                IP2STR(&ts_ip), tailscale_active_routes(),
                tailscale_accept_routes ? "yes" : "no", tailscale_snat_subnet_routes ? "yes" : "no");
        for (int i = 0; i < peers; i++) {
            microlink_peer_info_t p = {0};
            if (microlink_get_peer_info(ml, i, &p) != ESP_OK) continue;
            appendf(text, 8192, "- %s %u.%u.%u.%u %s via %s\n", p.hostname,
                    (p.vpn_ip >> 24) & 255, (p.vpn_ip >> 16) & 255,
                    (p.vpn_ip >> 8) & 255, p.vpn_ip & 255,
                    p.online ? "online" : "offline", p.direct_path ? "direct" : "DERP");
        }
    }

    fourvia6_status_t v6;
    fourvia6_get_status(&v6);
    appendf(text, 8192, "\n4via6: %s\nFlows: %lu\n",
            v6.enabled ? "enabled" : "disabled", (unsigned long)v6.active_flows);
    if (c->info_include_details) {
        appendf(text, 8192, "LAN: %s\nSite ID: %u\nPrefix: %s\n",
                v6.lan_cidr, v6.site_id, v6.advertised_prefix);
    }
    wifi_sta_list_t clients = {0};
    int clients_n = wifi_ap_runtime_enabled() && esp_wifi_ap_get_sta_list(&clients) == ESP_OK
                    ? clients.num : 0;
    appendf(text, 8192, "\nAccess point: %s (policy: %s)\nConnected AP devices: %d\n",
            wifi_ap_runtime_enabled() ? "enabled" : "disabled",
            wifi_ap_policy_auto_off() ? "standby while uplink is connected" : "always available", clients_n);
    if (c->info_include_details) {
        for (int i = 0; i < clients_n; i++) {
            uint8_t *m = clients.sta[i].mac;
            appendf(text, 8192, "- %02x:%02x:%02x:%02x:%02x:%02x RSSI %d dBm\n",
                    m[0],m[1],m[2],m[3],m[4],m[5], clients.sta[i].rssi);
        }
    }
    uint32_t tf_enabled=0,tf_installed=0,tf_accepted=0,tf_blocked=0;
    tailnet_forward_totals(&tf_enabled,&tf_installed,&tf_accepted,&tf_blocked);
    appendf(text,8192,"\nLAN -> Tailnet forwarding: %lu configured, %lu enabled, %lu active\nAccepted/blocked packets: %lu/%lu\n",
            (unsigned long)tailnet_forward_count(),(unsigned long)tf_enabled,(unsigned long)tf_installed,
            (unsigned long)tf_accepted,(unsigned long)tf_blocked);
    if(c->info_include_details){for(int i=0;i<tailnet_forward_count();i++){tailnet_forward_rule_t r;tailnet_forward_runtime_t rt;if(!tailnet_forward_get(i,&r,&rt))continue;char cidr[32];tailnet_forward_format_cidr(r.source_network,r.source_prefix,cidr,sizeof cidr);appendf(text,8192,"- %s: %s/%u -> %s:%u, source %s [%s]\n",r.name[0]?r.name:"unnamed",r.proto==17?"UDP":"TCP",r.listen_port,r.destination,r.destination_port,cidr,rt.installed?"active":(rt.error[0]?rt.error:"inactive"));}}

    mqtt_integration_config_t mqtt;
    mqtt_integration_get_config(&mqtt);
    appendf(text, 8192, "\nMQTT: %s / %s\nSaved WOL devices: %d\n",
            mqtt_integration_connected() ? "connected" : "disconnected",
            mqtt.enabled ? "enabled" : "disabled", wol_count());
    for (int i = 0; i < wol_count(); i++) {
        wol_device_t w;
        if (!wol_get(i, &w)) continue;
        appendf(text, 8192, "- %s", w.name[0] ? w.name : "unnamed");
        if (c->info_include_details) {
            char mac[18]; wol_format_mac(w.mac, mac); appendf(text, 8192, " (%s)", mac);
        }
        appendf(text, 8192, "\n");
    }
    /* ntfy messages are limited in size. Send deterministic chunks; no chunk
     * contains passwords, WiFi keys, Tailscale keys, or broker/ntfy tokens. */
    size_t length = strlen(text), offset = 0;
    unsigned part = 1, parts = (unsigned)((length + 3499) / 3500);
    esp_err_t result = ESP_OK;
    while (offset < length) {
        size_t take = length - offset > 3500 ? 3500 : length - offset;
        char saved = text[offset + take]; text[offset + take] = '\0';
        char title[64];
        if (parts > 1) snprintf(title, sizeof title, "ESP32 router info %u/%u", part, parts);
        else strlcpy(title, "ESP32 router info", sizeof title);
        esp_err_t err = publish_message(c, title, "information,mattboxx-response", text + offset);
        if (err != ESP_OK) result = err;
        text[offset + take] = saved; offset += take; part++;
    }
    free(text);
    return result;
}

static esp_err_t wake_argument(const ntfy_integration_config_t *c, const char *argument)
{
    while (*argument == ' ') argument++;
    for (int i = 0; i < wol_count(); i++) {
        wol_device_t d;
        if (wol_get(i, &d) && d.name[0] && strcasecmp(d.name, argument) == 0)
            return wol_send_index(i);
    }
    uint8_t mac[6];
    if (!wol_parse_mac(argument, mac)) return ESP_ERR_NOT_FOUND;
    if (wol_send_saved_mac_text(argument) == ESP_OK) return ESP_OK;
    return c->allow_direct_mac ? wol_send_mac(mac, NULL, 9) : ESP_ERR_INVALID_STATE;
}

static NTFY_NOINLINE void handle_command(const ntfy_integration_config_t *c, const char *message)
{
    while (*message && isspace((unsigned char)*message)) message++;
    /* Mobile clients often append a newline. Trim edges without changing
     * spaces within a saved WOL device name; reject oversized commands. */
    size_t length = strlen(message);
    while (length && isspace((unsigned char)message[length - 1])) length--;
    char command[128];
    if (!length || length >= sizeof command) return;
    memcpy(command, message, length);
    command[length] = '\0';
    message = command;
    esp_err_t err = ESP_ERR_INVALID_ARG;
    if (c->info_enabled && strcasecmp(message, "info") == 0) {
        err = send_info(c);
    } else if (strncasecmp(message,"recover ",8)==0 || strncasecmp(message,"check ",6)==0) {
        bool wake=strncasecmp(message,"recover ",8)==0;
        const char *selector=message+(wake?8:6);uint8_t mac[6];
        if(wol_parse_mac(selector,mac))err=homelab_ops_command(selector,wake);
        else for(int i=0;i<wol_count();i++){
            wol_device_t d;if(wol_get(i,&d)&&d.name[0]&&!strcasecmp(selector,d.name)){
                char address[18];wol_format_mac(d.mac,address);err=homelab_ops_command(address,wake);break;
            }
        }
        (void)publish_message(c,"ESP32 recovery response","mattboxx-response",
            err==ESP_OK?"Recovery/check accepted; completion must be verified in Devices & Recovery.":"Recovery/check rejected; verify target, remote-command permission, cooldown and resources.");
    } else if (strncasecmp(message, "wol ", 4) == 0) {
        err = wake_argument(c, message + 4);
        char reply[160];
        snprintf(reply, sizeof reply, "WOL %s: %s", message + 4,
                 err == ESP_OK ? "packet sent" : esp_err_to_name(err));
        (void)publish_message(c, "ESP32 WOL response", "mattboxx-response", reply);
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (err == ESP_OK) s_status.commands_received++;
    else if (strncasecmp(message, "wol ", 4) == 0 || strcasecmp(message, "info") == 0
        || strncasecmp(message,"recover ",8)==0 || strncasecmp(message,"check ",6)==0)
        s_status.command_errors++;
    xSemaphoreGive(s_lock);
}

static void collect_line(command_batch_t *batch)
{
    ntfy_json_parser_t *p = &batch->parser;
    if (batch->count < NTFY_POLL_BATCH && ntfy_json_finish(p) &&
        strcmp(p->event.event, "message") == 0 && event_id_valid(p->event.id))
        batch->events[batch->count++] = p->event;
    ntfy_json_reset(p);
}

static void collect_bytes(command_batch_t *batch, const char *bytes, size_t length)
{
    for (size_t i = 0; i < length && batch->count < NTFY_POLL_BATCH; ++i) {
        unsigned char b = (unsigned char)bytes[i];
        if (b == '\n') collect_line(batch);
        else ntfy_json_feed(&batch->parser, b);
    }
}

static NTFY_NOINLINE esp_err_t read_command_batch(esp_http_client_handle_t client,
                                                command_batch_t *batch)
{
    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) return err;
    if (esp_http_client_fetch_headers(client) < 0 ||
        esp_http_client_get_status_code(client) != 200) return ESP_FAIL;
    int64_t deadline = esp_timer_get_time() + 30000000;
    while (batch->count < NTFY_POLL_BATCH) {
        if (esp_timer_get_time() >= deadline) return ESP_ERR_TIMEOUT;
        int n = esp_http_client_read(client, batch->read_buffer, sizeof batch->read_buffer);
        if (n < 0) return ESP_FAIL;
        if (!n) {
            if (!esp_http_client_is_complete_data_received(client)) return ESP_FAIL;
            /* A final valid JSON object may omit its newline. A truncated or
             * malformed object never advances the cursor or runs a command. */
            collect_line(batch);
            return ESP_OK;
        }
        collect_bytes(batch, batch->read_buffer, (size_t)n);
    }
    /* Deliberately close after a complete bounded prefix. The next poll
     * resumes at its last durable ID; unread commands are not skipped. */
    return ESP_OK;
}

static bool config_equal(const ntfy_integration_config_t *a, const ntfy_integration_config_t *b)
{
    return a->enabled == b->enabled && a->tailscale_alerts == b->tailscale_alerts &&
           a->commands_enabled == b->commands_enabled &&
           a->commands_only_when_tailscale_down == b->commands_only_when_tailscale_down &&
           a->allow_direct_mac == b->allow_direct_mac && a->info_enabled == b->info_enabled &&
           a->info_include_details == b->info_include_details &&
           a->system_events == b->system_events &&
           a->failure_delay_seconds == b->failure_delay_seconds &&
           a->poll_interval_seconds == b->poll_interval_seconds &&
           strcmp(a->server, b->server) == 0 && strcmp(a->topic, b->topic) == 0 &&
           strcmp(a->token, b->token) == 0;
}

static bool poll_current_locked(const ntfy_integration_config_t *c, uint64_t generation)
{
    return generation == s_config_generation && config_equal(c, &s_config) &&
           c->enabled && c->commands_enabled &&
           (!c->commands_only_when_tailscale_down ||
            (tailscale_enabled && !tailscale_is_connected()));
}

static NTFY_NOINLINE bool poll_commands(const ntfy_integration_config_t *c)
{
    if(!homelab_ops_admit())return false;
    char cursor[sizeof s_last_event_id];
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint64_t generation = s_config_generation;
    if (!poll_current_locked(c, generation)) { xSemaphoreGive(s_lock); return false; }
    strlcpy(cursor, s_last_event_id, sizeof cursor);
    xSemaphoreGive(s_lock);

    /* The old fixed `since=10s` window was shorter than the default
     * 15-second polling interval.  Commands landing in that gap were lost
     * forever.  Cover one complete interval plus network/TLS scheduling
     * jitter until ntfy gives us a durable message-id cursor. */
    char since[48];
    if (cursor[0]) strlcpy(since, cursor, sizeof since);
    else snprintf(since, sizeof since, "%us", (unsigned)c->poll_interval_seconds + 30U);
    char suffix[96];
    snprintf(suffix, sizeof suffix, "/json?poll=1&since=%s", since);
    /* Fixed heap batch, allocation-free JSON projection. Neither total
     * response size nor individual notification text grows the task stack. */
    char url[352];
    command_batch_t *batch = calloc(1, sizeof *batch);
    if (!batch) return false;
    build_url(c, suffix, url, sizeof url);
    esp_http_client_config_t config = {.url=url,.method=HTTP_METHOD_GET,.timeout_ms=12000,
        .crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true};
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) { free(batch); return false; }
    esp_err_t err = set_auth(client, c);
    if (err == ESP_OK) err = read_command_batch(client, batch);
    int status = err == ESP_OK ? esp_http_client_get_status_code(client) : 0;
    esp_http_client_cleanup(client);
    if (err != ESP_OK || status != 200) {
        ESP_LOGW(TAG, "command poll failed: %s HTTP %d", esp_err_to_name(err), status);
        free(batch);
        return false;
    }
    bool completed = true;
    for (size_t i = 0; i < batch->count; ++i) {
            const ntfy_json_event_t *event = &batch->events[i];
            xSemaphoreTake(s_lock, portMAX_DELAY);
            if (!poll_current_locked(c, generation)) {
                xSemaphoreGive(s_lock); completed = false; break;
            }
            bool duplicate = strcmp(s_last_event_id, event->id) == 0;
            /* Persist BEFORE dispatch; otherwise a flash error followed by a
             * reboot can replay WOL. Serialized with configuration saves so
             * an old poll cannot overwrite a new topic's cursor/settings. */
            esp_err_t saved = duplicate ? ESP_OK : save_state(c, event->id);
            if (saved == ESP_OK && !duplicate)
                strlcpy(s_last_event_id, event->id, sizeof s_last_event_id);
            xSemaphoreGive(s_lock);
            if (saved != ESP_OK) {
                ESP_LOGW(TAG, "Cannot persist command cursor; dispatch deferred");
                completed = false;
                break;
            }
            if (!duplicate && event->has_message && !event->message_too_long &&
                strncmp(event->title, "ESP32 ", 6) != 0)
                handle_command(c, event->message);
    }
    free(batch);
    return completed;
}

static bool uplink_connected(void)
{
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    return sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr != 0;
}

static NTFY_NOINLINE esp_err_t send_tailscale_alert(const ntfy_integration_config_t *c)
{
    /* Alerts report connectivity, never export the local log buffer. Private
     * details for an explicitly requested info reply are a separate policy. */
    static const char message[] =
        "Internet uplink is connected, but Tailscale has remained disconnected.\n"
        "Open the local Diagnostics page to inspect logs.";
    esp_err_t err = publish_message(c, "ESP32 Tailscale problem", "warning,mattboxx-response", message);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (err == ESP_OK)
        s_status.alerts_sent++;
    xSemaphoreGive(s_lock);
    return err;
}

/* Kept out of task_main's frame: the OTA state copy is several hundred bytes. */
static NTFY_NOINLINE uint32_t available_update_id(void)
{
    ota_remote_state_t update;
    ota_remote_get_state(&update);
    if (!update.update_available || !update.latest_version[0]) return 0;
    uint32_t hash = 2166136261u;
    for (const char *p = update.latest_version; *p; p++) hash = (hash ^ (uint8_t)*p) * 16777619u;
    return hash | 1u;
}

static NTFY_NOINLINE esp_err_t send_system_event(const ntfy_integration_config_t *c, unsigned event,
                                                uint32_t outage_seconds)
{
    char message[192];
    const char *title = "ESP32 gateway event";
    if (event == NTFY_EVENT_BOOT) {
        const esp_app_desc_t *app = esp_app_get_description();
        snprintf(message, sizeof message, "Gateway started: firmware %s, reset reason %d.",
                 app ? app->version : "unknown", (int)esp_reset_reason());
        title = "ESP32 gateway started";
    } else if (event == NTFY_EVENT_RESTORED) {
        snprintf(message, sizeof message, "Tailscale control connection restored after about %lu s. "
                 "This does not prove every peer or service is reachable.", (unsigned long)outage_seconds);
        title = "ESP32 Tailscale restored";
    } else {
        ota_remote_state_t update;
        ota_remote_get_state(&update);
        snprintf(message, sizeof message, "Firmware %.31s is available. Nothing was installed; review the release and update from the Web UI.",
                 update.latest_version);
        title = "ESP32 firmware update available";
    }
    return publish_message(c, title, "mattboxx-response", message);
}

static void task_main(void *arg)
{
    (void)arg;
    uint32_t down_seconds = 0, retry_seconds = 0;
    service_retry_t polling = {0};
    uint64_t polling_generation = 0;
    bool alerted = false;
    bool could_poll_before = false;
    ntfy_events_t events;
    ntfy_events_init(&events);
    uint32_t restored_after = 0;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        ntfy_integration_config_t c;
        snapshot(&c);
        if (!c.enabled || !c.system_events) ntfy_events_tick(&events, false, false, 0);
        if (!c.enabled || !uplink_connected()) {
            down_seconds = retry_seconds = 0;
            service_retry_reset(&polling);
            alerted = false;
            could_poll_before = false;
            continue;
        }
        char operational[160]={0};
        xSemaphoreTake(s_lock,portMAX_DELAY);
        if(s_operational_generation==s_config_generation)strlcpy(operational,s_operational_event,sizeof operational);
        s_operational_event[0]=0;
        xSemaphoreGive(s_lock);
        if(operational[0])(void)publish_message(&c,"ESP32 operational result","mattboxx-response",operational);
        bool ts_down = tailscale_enabled && !tailscale_is_connected();
        bool restored = alerted && !ts_down;
        if (restored) restored_after = down_seconds;
        if (ts_down) down_seconds++; else { down_seconds = 0; alerted = false; }
        if (c.system_events) {
            ntfy_events_tick(&events, true, restored, available_update_id());
            unsigned due = ntfy_events_due(&events);
            if (due) ntfy_events_result(&events, due, send_system_event(&c, due, restored_after) == ESP_OK);
        }
        if (retry_seconds) retry_seconds--;
        if (c.tailscale_alerts && ts_down && down_seconds >= c.failure_delay_seconds
            && !alerted && retry_seconds == 0) {
            alerted = send_tailscale_alert(&c) == ESP_OK;
            if (!alerted) retry_seconds = 60;
        }
        bool can_poll = c.commands_enabled
                     && (!c.commands_only_when_tailscale_down || ts_down);
        xSemaphoreTake(s_lock,portMAX_DELAY);
        uint64_t generation = s_config_generation;
        xSemaphoreGive(s_lock);
        /* Arm immediately after enabling commands (or after the
         * Tailscale-down condition becomes true) instead of waiting one
         * complete poll interval before establishing the server cursor. */
        if (can_poll && (!could_poll_before || generation != polling_generation))
            service_retry_reset(&polling);
        polling_generation = generation;
        could_poll_before = can_poll;
        uint64_t now = (uint64_t)esp_timer_get_time()/1000;
        if (can_poll && service_retry_due(&polling,now)) {
            bool ok = poll_commands(&c);
            now = (uint64_t)esp_timer_get_time()/1000;
            if(ok){service_retry_reset(&polling);polling.next_ms=now+(uint64_t)c.poll_interval_seconds*1000;}
            else {
                service_retry_failed(&polling,now);
                uint64_t configured_min=now+(uint64_t)c.poll_interval_seconds*1000;
                if(polling.next_ms<configured_min)polling.next_ms=configured_min;
            }
        } else if (!can_poll) service_retry_reset(&polling);
    }
}

void ntfy_integration_init(void)
{
    if (s_task) return;
    /* Retry-safe: the module supervisor may call this again after a failed start. */
    if (!s_lock) s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return;
    load_state(&s_config);
    uint8_t system_events = 0;
    s_config.system_events = nvs_param_get_u8("ntfy_sysev", &system_events) == ESP_OK && system_events == 1;
    if (xTaskCreate(task_main, "ntfy", NTFY_TASK_STACK_BYTES, NULL, 3, &s_task) != pdPASS) {
        s_task = NULL;
        ESP_LOGE(TAG, "Cannot allocate ntfy worker stack");
    }
}

void ntfy_integration_get_config(ntfy_integration_config_t *out)
{
    if (!out) return;
    if (!s_lock) { defaults(out); return; }
    snapshot(out);
}

void ntfy_integration_get_status(ntfy_integration_status_t *out)
{
    if (!out) return;
    if (!s_lock) { memset(out, 0, sizeof *out); return; }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(out, &s_status, sizeof *out);
    xSemaphoreGive(s_lock);
    out->task_running = s_task != NULL;
    /* ESP-IDF reports the high-water mark in bytes, not FreeRTOS words. */
    out->stack_min_free_bytes = s_task ? uxTaskGetStackHighWaterMark(s_task) : 0;
}

esp_err_t ntfy_integration_set_config(const ntfy_integration_config_t *c)
{
    if (!config_valid(c)) return ESP_ERR_INVALID_ARG;
    if (!s_lock || !s_task) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool endpoint_changed = strcmp(s_config.server, c->server) != 0
                         || strcmp(s_config.topic, c->topic) != 0;
    /* Separate key: older firmware ignores it and keeps the main record valid. */
    bool events_changed = c->system_events != s_config.system_events;
    esp_err_t e = events_changed ? nvs_param_set_u8("ntfy_sysev", c->system_events ? 1 : 0) : ESP_OK;
    if (e != ESP_OK) {xSemaphoreGive(s_lock); return e;}
    e = save_state(c, endpoint_changed ? "" : s_last_event_id);
    if (e != ESP_OK && events_changed) (void)nvs_param_set_u8("ntfy_sysev", s_config.system_events ? 1 : 0);
    if (e == ESP_OK) {
        memcpy(&s_config, c, sizeof *c);
        s_config_generation++;
        if (endpoint_changed) s_last_event_id[0] = '\0';
    }
    xSemaphoreGive(s_lock);
    return e;
}

esp_err_t ntfy_integration_send_test(void)
{
    if (!s_lock || !s_task) return ESP_ERR_INVALID_STATE;
    ntfy_integration_config_t c;
    snapshot(&c);
    if (!c.enabled) return ESP_ERR_INVALID_STATE;
    return publish_message(&c, "ESP32 router test", "white_check_mark,mattboxx-response",
                           "ntfy integration is working.");
}
