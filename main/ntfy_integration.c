/* Optional ntfy integration.
 *
 * No traffic is emitted unless explicitly enabled. The access token is never
 * returned by the web API, written to logs, or included in status replies.
 */
#include "ntfy_integration.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "runtime_metrics.h"
#include "snmp_agent.h"
#include "cJSON.h"
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
#include "log_capture.h"
#include "lwip/ip4_addr.h"
#include "microlink.h"
#include "mqtt_integration.h"
#include "nvs_params.h"
#include "nvs.h"
#include "tailscale_config.h"
#include "peer_dns.h"
#include "ota_remote.h"
#include "wol.h"
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

/* TLS certificate verification needs its own stack reserve. Keep the large
 * reporting/polling frames out of task_main: GCC otherwise inlines them and
 * permanently reserves their buffers even on a simple command poll. */
#define NTFY_TASK_STACK_BYTES 12288
#define NTFY_NOINLINE __attribute__((noinline))

extern bool wifi_ap_runtime_enabled(void);
extern bool wifi_ap_policy_auto_off(void);

typedef struct {
    char *data;
    size_t capacity;
    size_t used;
    bool overflow;
} response_buffer_t;

static esp_err_t http_event(esp_http_client_event_t *event)
{
    response_buffer_t *buffer = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && buffer && event->data_len > 0) {
        if (buffer->overflow || (size_t)event->data_len >= buffer->capacity - buffer->used) {
            buffer->overflow = true;
            return ESP_OK;
        }
        memcpy(buffer->data + buffer->used, event->data, event->data_len);
        buffer->used += event->data_len;
        buffer->data[buffer->used] = '\0';
    }
    return ESP_OK;
}

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

    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    wifi_ap_record_t ap = {0};
    bool uplink = sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr;
    bool have_ap = esp_wifi_sta_get_ap_info(&ap) == ESP_OK;
    appendf(text, 8192, "\nUplink: %s\nRSSI: %d dBm\n",
            uplink ? "connected" : "disconnected", have_ap ? ap.rssi : 0);
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
    } else if (strncasecmp(message, "wol ", 4) == 0) {
        err = wake_argument(c, message + 4);
        char reply[160];
        snprintf(reply, sizeof reply, "WOL %s: %s", message + 4,
                 err == ESP_OK ? "packet sent" : esp_err_to_name(err));
        (void)publish_message(c, "ESP32 WOL response", "mattboxx-response", reply);
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (err == ESP_OK) s_status.commands_received++;
    else if (strncasecmp(message, "wol ", 4) == 0 || strcasecmp(message, "info") == 0)
        s_status.command_errors++;
    xSemaphoreGive(s_lock);
}

static bool response_is_ours(cJSON *root)
{
    cJSON *title = cJSON_GetObjectItem(root, "title");
    return cJSON_IsString(title) && strncmp(title->valuestring, "ESP32 ", 6) == 0;
}

static bool config_equal(const ntfy_integration_config_t *a, const ntfy_integration_config_t *b)
{
    return a->enabled == b->enabled && a->tailscale_alerts == b->tailscale_alerts &&
           a->commands_enabled == b->commands_enabled &&
           a->commands_only_when_tailscale_down == b->commands_only_when_tailscale_down &&
           a->allow_direct_mac == b->allow_direct_mac && a->info_enabled == b->info_enabled &&
           a->info_include_details == b->info_include_details &&
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

static NTFY_NOINLINE void poll_commands(const ntfy_integration_config_t *c)
{
    char cursor[sizeof s_last_event_id];
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint64_t generation = s_config_generation;
    if (!poll_current_locked(c, generation)) { xSemaphoreGive(s_lock); return; }
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
    /* Keep the response off the task stack. An 8 KiB automatic buffer here
     * exhausted the ntfy task's entire 8 KiB stack on the first poll and
     * corrupted the TLSF heap, causing a reboot loop about 15 seconds after
     * enabling commands. */
    char url[352];
    char *response = calloc(1, 8192);
    if (!response) return;
    build_url(c, suffix, url, sizeof url);
    response_buffer_t rb = {.data=response,.capacity=8192};
    esp_http_client_config_t config = {.url=url,.method=HTTP_METHOD_GET,.timeout_ms=12000,
        .crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,
        .event_handler=http_event,.user_data=&rb};
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) { free(response); return; }
    esp_err_t err = set_auth(client, c);
    if (err == ESP_OK) err = esp_http_client_perform(client);
    int status = err == ESP_OK ? esp_http_client_get_status_code(client) : 0;
    esp_http_client_cleanup(client);
    if (err != ESP_OK || status != 200 || rb.overflow) {
        ESP_LOGW(TAG, "command poll failed: %s HTTP %d", esp_err_to_name(err), status);
        free(response);
        return;
    }
    char *save = NULL;
    for (char *line = strtok_r(response, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        cJSON *event = cJSON_Parse(line);
        if (!event) continue;
        cJSON *id = cJSON_GetObjectItem(event, "id");
        cJSON *kind = cJSON_GetObjectItem(event, "event");
        cJSON *msg = cJSON_GetObjectItem(event, "message");
        if (cJSON_IsString(kind) && strcmp(kind->valuestring, "message") == 0) {
            /* No ID means no durable replay protection. Reject IDs that could
             * truncate or inject additional query parameters into `since`. */
            if (!cJSON_IsString(id) || !event_id_valid(id->valuestring)) {
                cJSON_Delete(event); continue;
            }
            xSemaphoreTake(s_lock, portMAX_DELAY);
            if (!poll_current_locked(c, generation)) {
                xSemaphoreGive(s_lock); cJSON_Delete(event); break;
            }
            bool duplicate = strcmp(s_last_event_id, id->valuestring) == 0;
            /* Persist BEFORE dispatch; otherwise a flash error followed by a
             * reboot can replay WOL. Serialized with configuration saves so
             * an old poll cannot overwrite a new topic's cursor/settings. */
            esp_err_t saved = duplicate ? ESP_OK : save_state(c, id->valuestring);
            if (saved == ESP_OK && !duplicate)
                strlcpy(s_last_event_id, id->valuestring, sizeof s_last_event_id);
            xSemaphoreGive(s_lock);
            if (saved != ESP_OK) {
                ESP_LOGW(TAG, "Cannot persist command cursor; dispatch deferred");
                cJSON_Delete(event); break;
            }
            if (!duplicate && cJSON_IsString(msg) && !response_is_ours(event))
                handle_command(c, msg->valuestring);
        }
        cJSON_Delete(event);
    }
    free(response);
}

static bool uplink_connected(void)
{
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    return sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr != 0;
}

static NTFY_NOINLINE esp_err_t send_tailscale_alert(const ntfy_integration_config_t *c)
{
    char *logs = malloc(2300);
    char *message = malloc(2300);
    if (!logs || !message) { free(logs); free(message); return ESP_ERR_NO_MEM; }
    size_t n = log_capture_read(logs, 2300);
    const char *tail = logs;
    if (n > 1800) tail += n - 1800;
    snprintf(message, 2300, "Internet uplink is connected, but Tailscale has remained disconnected.\n\nRecent local log tail:\n%.1800s", tail);
    free(logs);
    esp_err_t err = publish_message(c, "ESP32 Tailscale problem", "warning,mattboxx-response", message);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (err == ESP_OK)
        s_status.alerts_sent++;
    xSemaphoreGive(s_lock);
    free(message);
    return err;
}

static void task_main(void *arg)
{
    (void)arg;
    uint32_t down_seconds = 0, poll_seconds = 0, retry_seconds = 0;
    bool alerted = false;
    bool could_poll_before = false;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        ntfy_integration_config_t c;
        snapshot(&c);
        if (!c.enabled || !uplink_connected()) {
            down_seconds = poll_seconds = retry_seconds = 0;
            alerted = false;
            could_poll_before = false;
            continue;
        }
        bool ts_down = tailscale_enabled && !tailscale_is_connected();
        if (ts_down) down_seconds++; else { down_seconds = 0; alerted = false; }
        if (retry_seconds) retry_seconds--;
        if (c.tailscale_alerts && ts_down && down_seconds >= c.failure_delay_seconds
            && !alerted && retry_seconds == 0) {
            alerted = send_tailscale_alert(&c) == ESP_OK;
            if (!alerted) retry_seconds = 60;
        }
        bool can_poll = c.commands_enabled
                     && (!c.commands_only_when_tailscale_down || ts_down);
        /* Arm immediately after enabling commands (or after the
         * Tailscale-down condition becomes true) instead of waiting one
         * complete poll interval before establishing the server cursor. */
        if (can_poll && !could_poll_before)
            poll_seconds = c.poll_interval_seconds;
        could_poll_before = can_poll;
        if (can_poll && ++poll_seconds >= c.poll_interval_seconds) {
            poll_seconds = 0; poll_commands(&c);
        } else if (!can_poll) poll_seconds = 0;
    }
}

void ntfy_integration_init(void)
{
    if (s_task) return;
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return;
    load_state(&s_config);
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
    esp_err_t e = save_state(c, endpoint_changed ? "" : s_last_event_id);
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
