/* Tailscale (microlink) manager — settings load and lifecycle.
 *
 * Phase 1.5b: connect path drives the public microlink_config_t with
 * auth_key, device_name, max_peers, ctrl_host (Headscale support), and
 * advertise_routes (Hostinfo.RoutableIPs subnet route advertisement).
 * The full set of NVS-backed values reaches microlink through this
 * struct; no internal NVS bridging needed.
 */

#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "lwip/ip4_addr.h"
#include <time.h>
#include <arpa/inet.h>
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "microlink.h"
#include "sdlog.h"
#include "tailscale_config.h"
#include "nvs_params.h"
#include "esp_sntp.h"
#include "fourvia6.h"
#include "upstream_validation.h"
#include "peer_dns.h"
#include "web_ui.h"

/* Local helper: load a string from NVS, defaulting to an empty heap
 * buffer when the key isn't there. Other modules assume non-NULL. */
static char *nvs_str_or_empty(const char *key)
{
    char *s = nvs_param_get_str(key);
    return s ? s : strdup("");
}

static const char *TAG = "tailscale_mgr";

int32_t tailscale_enabled = 0;
char* tailscale_auth_key = NULL;
char* tailscale_hostname = NULL;
char* tailscale_login_server = NULL;
char* tailscale_ipn_version = NULL;
int32_t tailscale_advertise_ap = 0;
char* tailscale_advertise_routes = NULL;
int32_t tailscale_advertise_exit_node = 0;
int32_t tailscale_max_peers = 16;
uint32_t tailscale_exit_node_ip = 0;
int32_t tailscale_netcheck_override = 0;          /* default: OFF — netcheck mis-selects regions (garbage STUN RTTs: picked London #8 for a HU node, fra/nue sometimes missing because probes tunnel through the exit netif) which destabilises DERP. Stay on the configured/echoed home region until the netcheck STUN path is fixed. Runtime-overridable via NVS. */
int32_t tailscale_netcheck_threshold_ms = 100;    /* default: 100 ms hysteresis (sticky — home routers rarely beat Frankfurt enough to be worth switching) */
int32_t tailscale_default_derp_region = 0;        /* 0 = unset → Frankfurt fallback in microlink */
int32_t tailscale_lan_bypass = 1;                  /* 1 = exit-node lets LAN egress via STA, like tailscale --exit-node-allow-lan-access */
int32_t tailscale_accept_routes = 0;               /* 0 = default; 1 = honour subnet routes advertised by peers (tailscale --accept-routes) */
int32_t tailscale_snat_subnet_routes = 0;          /* 0 = default OFF; 1 = SNAT tunnel→STA forwarded subnet-route/exit-node-server traffic to our STA IP (tailscale --snat-subnet-routes), so upstream hosts can reply without a route back to the tailnet */

/* Accepted-routes table — rebuilt by route_supervisor_task. Stored in host
 * byte order to match the route-hook arithmetic. */
tailscale_accepted_route_t tailscale_accepted_routes[TAILSCALE_ACCEPTED_ROUTES_MAX];
int tailscale_accepted_routes_count = 0;

bool tailscale_connected = false;
uint32_t tailscale_tunnel_ip = 0;

static uint32_t tailscale_subnet_ip = 0;
static uint32_t tailscale_subnet_mask = 0;

/* Microlink instance owned by this module. */
static microlink_t *s_microlink = NULL;
/* microlink retains these pointers for future registrations. Web saves may
 * replace/free the editable globals, so give the running instance immutable
 * boot-lifetime copies. New credentials/hostname take effect after restart. */
static char *s_active_auth_key;
static char *s_active_hostname;
static char *s_active_login_server;
static char *s_active_advertise_routes;
static char *s_active_ipn_version;
static char s_active_routes[640];
static char s_effective_ipn_version[64];
static bool s_routes_valid;
static StaticSemaphore_t s_lifecycle_storage;
static SemaphoreHandle_t s_lifecycle;
static portMUX_TYPE s_connect_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_connect_in_flight;
static uint32_t s_lifecycle_generation;
static bool s_exit_server_active;
static uint16_t s_peerapi_port = TAILSCALE_PEERAPI_PORT;

bool tailscale_lifecycle_try_acquire(void)
{
    return s_lifecycle && xSemaphoreTake(s_lifecycle, 0) == pdTRUE;
}

void tailscale_lifecycle_release(void) { xSemaphoreGive(s_lifecycle); }
uint32_t tailscale_lifecycle_generation(void) { return s_lifecycle_generation; }
bool tailscale_exit_server_active(void) { return s_exit_server_active; }
uint16_t tailscale_peerapi_port(void) { return s_peerapi_port; }

/* Read saved settings into caller-owned storage: no mutable static preview
 * shared between HTTP, MQTT and the connect task. Manual routes are untouched. */
bool tailscale_routes_preview(char *out, size_t capacity)
{
    if (!out || !capacity) return false;
    out[0] = '\0';
    int32_t enabled = tailscale_advertise_ap;
    (void)nvs_param_get_int("ts_adv_ap", &enabled);
    if (enabled) {
        char *ip_s = nvs_param_get_str("ap_ip");
        char *mask_s = nvs_param_get_str("ap_mask");
        ip4_addr_t ip, mask;
        bool valid = ip4addr_aton(ip_s && *ip_s ? ip_s : "192.168.4.1", &ip)
                  && ip4addr_aton(mask_s && *mask_s ? mask_s : "255.255.255.0", &mask);
        free(ip_s);
        free(mask_s);
        if (!valid) return false;
        uint32_t m = lwip_ntohl(mask.addr), host = lwip_ntohl(ip.addr) & m;
        if (!m || ((~m) & ((~m) + 1u))) return false;
        unsigned prefix = 0;
        for (uint32_t bit = m; bit & 0x80000000u; bit <<= 1) ++prefix;
        char cidr[32];
        snprintf(cidr, sizeof cidr, "%u.%u.%u.%u/%u",
                 (unsigned)(host >> 24), (unsigned)((host >> 16) & 255),
                 (unsigned)((host >> 8) & 255), (unsigned)(host & 255), prefix);
        if (!route_list_add(out, capacity, cidr)) return false;
    }
    char *manual = nvs_str_or_empty("ts_routes");
    if (!manual) return false;
    bool ok = strlen(manual) <= 400 && route_list_add(out, capacity, manual);
    free(manual);
    if (!ok) return false;
    fourvia6_status_t v6;
    fourvia6_get_status(&v6);
    if (v6.enabled && !route_list_add(out, capacity, v6.advertised_prefix)) return false;
    enabled = tailscale_advertise_exit_node;
    (void)nvs_param_get_int("ts_adv_exit", &enabled);
    return !enabled || route_list_add(out, capacity, "0.0.0.0/0\n::/0");
}

const char *tailscale_active_routes(void) { return s_routes_valid ? s_active_routes : ""; }

/* Start SNTP if it has not been started yet.  Called by tailscale_connect_task
 * (before the WireGuard handshake needs real wall-clock time) and by the WiFi
 * STA-got-IP event handler in esp32_nat_router.c. */
void init_sntp_if_needed(void)
{
    if (esp_sntp_enabled()) return;
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
}

void tailscale_init(void)
{
    int32_t v = 0;
    s_lifecycle = xSemaphoreCreateMutexStatic(&s_lifecycle_storage);
    /* Fresh installations follow upstream. Existing installations must opt in
     * explicitly so an upgrade cannot announce a previously private subnet. */
    tailscale_advertise_ap = nvs_param_get_int("ts_enabled", &v) == ESP_OK ? 0 : 1;
    if (nvs_param_get_int("ts_adv_ap", &v) == ESP_OK) tailscale_advertise_ap = v ? 1 : 0;
    else (void)nvs_param_set_int("ts_adv_ap", tailscale_advertise_ap);
    if (nvs_param_get_int("ts_enabled", &v) == ESP_OK) {
        tailscale_enabled = v;
    }
    tailscale_auth_key         = nvs_str_or_empty("ts_authkey");
    tailscale_hostname         = nvs_str_or_empty("ts_hostname");
    tailscale_login_server     = nvs_str_or_empty("ts_login");
    tailscale_ipn_version      = nvs_str_or_empty("ts_ipn_ver");
    s_active_ipn_version       = nvs_str_or_empty("ts_ipn_ver");
    tailscale_advertise_routes = nvs_str_or_empty("ts_routes");
    s_active_auth_key = nvs_str_or_empty("ts_authkey");
    s_active_hostname = nvs_str_or_empty("ts_hostname");
    s_active_login_server = nvs_str_or_empty("ts_login");
    s_active_advertise_routes = nvs_str_or_empty("ts_routes");
    if (nvs_param_get_int("ts_adv_exit", &v) == ESP_OK) {
        tailscale_advertise_exit_node = (v ? 1 : 0);
    }
    if (nvs_param_get_int("ts_maxpeers", &v) == ESP_OK && v >= 1 && v <= 64) {
        tailscale_max_peers = v;
    }
    /* Exit-node IP stored as i32 in NVS. Tailnet CGNAT (100.64.0.0/10) fits
     * comfortably below 2^31 so the signed/unsigned reinterpret is safe. */
    if (nvs_param_get_int("ts_exit_node", &v) == ESP_OK) {
        tailscale_exit_node_ip = (uint32_t)v;
    }
    if (nvs_param_get_int("ts_nc_ovr", &v) == ESP_OK) {
        tailscale_netcheck_override = (v ? 1 : 0);
    }
    if (nvs_param_get_int("ts_nc_thr", &v) == ESP_OK && v >= 0 && v <= 5000) {
        tailscale_netcheck_threshold_ms = v;
    }
    if (nvs_param_get_int("ts_def_derp", &v) == ESP_OK && v >= 0 && v <= 65535) {
        tailscale_default_derp_region = v;
    }
    if (nvs_param_get_int("ts_lan_bp", &v) == ESP_OK) {
        tailscale_lan_bypass = (v ? 1 : 0);
    }
    if (nvs_param_get_int("ts_acpt_rt", &v) == ESP_OK) {
        tailscale_accept_routes = (v ? 1 : 0);
    }
    if (nvs_param_get_int("ts_snat_sr", &v) == ESP_OK) {
        tailscale_snat_subnet_routes = (v ? 1 : 0);
    }
    if (tailscale_advertise_exit_node && tailscale_exit_node_ip != 0) {
        /* A node cannot safely be both an exit-node server and a client of a
         * different exit node: forwarded packets would loop into WireGuard.
         * Preserve the older client selection and clear the newer advert. */
        ESP_LOGW(TAG, "Conflicting exit-node modes; disabling exit-node advertisement");
        tailscale_advertise_exit_node = 0;
        (void)nvs_param_set_int("ts_adv_exit", 0);
    }
    s_exit_server_active = tailscale_enabled && tailscale_advertise_exit_node && !tailscale_exit_node_ip;
    /* Preserve every existing custom admin port, including 41180. PeerAPI
     * advertises its actual boot-selected port rather than assuming port 80. */
    s_peerapi_port = web_ui_configured_port() == TAILSCALE_PEERAPI_PORT
                  ? TAILSCALE_PEERAPI_PORT + 1 : TAILSCALE_PEERAPI_PORT;
    s_routes_valid = tailscale_routes_preview(s_active_routes, sizeof s_active_routes);
    ESP_LOGI(TAG, "Config loaded (enabled=%ld, max_peers=%ld, login_server=%s, exit_node=%lu.%lu.%lu.%lu)",
             (long)tailscale_enabled, (long)tailscale_max_peers,
             (tailscale_login_server && tailscale_login_server[0]) ? tailscale_login_server : "<saas>",
             (unsigned long)((tailscale_exit_node_ip >> 24) & 0xFF),
             (unsigned long)((tailscale_exit_node_ip >> 16) & 0xFF),
             (unsigned long)((tailscale_exit_node_ip >> 8) & 0xFF),
             (unsigned long)(tailscale_exit_node_ip & 0xFF));
}

struct microlink_s *tailscale_get_microlink(void)
{
    return s_microlink;
}

void tailscale_set_subnet(uint32_t ip, uint32_t mask)
{
    tailscale_subnet_ip = ip;
    tailscale_subnet_mask = mask;
}

bool tailscale_in_subnet(uint32_t ip)
{
    if (tailscale_subnet_mask == 0) return false;
    return (ip & tailscale_subnet_mask) == tailscale_subnet_ip;
}

static esp_err_t tailscale_connect_locked(void)
{
    if (!tailscale_enabled) {
        ESP_LOGI(TAG, "Tailscale not enabled");
        return ESP_ERR_INVALID_STATE;
    }
    if (!s_active_auth_key || !s_active_auth_key[0] || !s_active_hostname
        || !s_active_login_server || !s_active_advertise_routes) {
        ESP_LOGE(TAG, "Missing auth key (ts_authkey)");
        return ESP_ERR_INVALID_ARG;
    }

    if (s_microlink) {
        ESP_LOGW(TAG, "Already initialized; restart the device to reconnect safely");
        return ESP_ERR_INVALID_STATE;
    }

    if (!s_routes_valid || strlen(s_active_advertise_routes) > 400) {
        ESP_LOGE(TAG, "Advertised routes exceed the supported 400-byte limit");
        return ESP_ERR_INVALID_SIZE;
    }
    if (!ipn_version_valid(s_active_ipn_version)) {
        ESP_LOGE(TAG, "Invalid reported client version");
        return ESP_ERR_INVALID_ARG;
    }
    if (s_active_ipn_version[0]) {
        snprintf(s_effective_ipn_version, sizeof s_effective_ipn_version, "%s%s",
                 s_active_ipn_version, strchr(s_active_ipn_version, '-') ? "" : "-t00000000000-g00000000000");
    }

    /* Start before announcing PeerAPI; a failed listener must not be advertised.
     * This is the sole startup caller, serialized by the lifecycle mutex. */
    peer_dns_start();
    ++s_lifecycle_generation;
    microlink_config_t cfg = {
        .auth_key = s_active_auth_key,
        .device_name = s_active_hostname[0] ? s_active_hostname : NULL,
        .enable_derp = true,
        .enable_stun = true,
        .enable_disco = true,
        .max_peers = (uint8_t)tailscale_max_peers,
        .wifi_tx_power_dbm = 0,
        .priority_peer_ip = 0,
        .exit_node_ip = tailscale_exit_node_ip,
        .disco_heartbeat_ms = 0,
        .stun_interval_ms = 0,
        .ctrl_watchdog_ms = 0,
        .ctrl_host = s_active_login_server[0] ? s_active_login_server : NULL,
        .ipn_version = s_effective_ipn_version[0] ? s_effective_ipn_version : NULL,
        .advertise_routes = s_active_routes[0] ? s_active_routes : NULL,
        .peer_api_port = peer_dns_is_running() ? tailscale_peerapi_port() : 0,
        .netcheck_override_enabled = (tailscale_netcheck_override != 0),
        .netcheck_override_threshold_ms = (uint32_t)tailscale_netcheck_threshold_ms,
        .preferred_derp_region = (uint16_t)tailscale_default_derp_region,
    };

    microlink_t *instance = microlink_init(&cfg);
    if (!instance) {
        ESP_LOGE(TAG, "microlink_init failed");
        return ESP_FAIL;
    }

    /* Publish only a successfully started instance. Readers must never see
     * an object that the start-failure path is about to destroy. */
    esp_err_t err = microlink_start(instance);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "microlink_start failed: %s", esp_err_to_name(err));
        microlink_destroy(instance);
        return err;
    }

    s_microlink = instance;
    sdlog_set_microlink(instance);
    tailscale_connected = true;
    ESP_LOGI(TAG, "Tailscale started (device=%s, ctrl=%s, routes=%s, advertise_exit=%s, max_peers=%d)",
             cfg.device_name ? cfg.device_name : "<auto>",
             cfg.ctrl_host ? cfg.ctrl_host : "<saas>",
             (cfg.advertise_routes && cfg.advertise_routes[0]) ? cfg.advertise_routes : "<none>",
             tailscale_advertise_exit_node ? "yes" : "no",
             cfg.max_peers);
    return ESP_OK;
}

esp_err_t tailscale_connect(void)
{
    if (!s_lifecycle) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lifecycle, portMAX_DELAY);
    esp_err_t err = tailscale_connect_locked();
    xSemaphoreGive(s_lifecycle);
    return err;
}

void tailscale_disconnect(void)
{
    /* Other fork services retain the published handle. Keep restart-based
     * teardown until all consumers use a lifetime-safe accessor. */
    if (!s_lifecycle) return;
    xSemaphoreTake(s_lifecycle, portMAX_DELAY);
    if (s_microlink) {
        xSemaphoreGive(s_lifecycle);
        ESP_LOGW(TAG, "Use a device restart to disconnect the shared VPN instance safely");
        return;
    }
    tailscale_connected = false;
    tailscale_tunnel_ip = 0;
    ESP_LOGI(TAG, "Tailscale stopped");
    xSemaphoreGive(s_lifecycle);
}

bool tailscale_is_connected(void)
{
    if (!s_microlink) return false;
    bool connected = microlink_is_connected(s_microlink);
    if (connected) {
        /* microlink_get_vpn_ip returns host byte order; cache as network byte order
         * to match the existing VPN tunnel-IP convention used by netif hooks. */
        uint32_t host_ip = microlink_get_vpn_ip(s_microlink);
        if (host_ip) {
            tailscale_tunnel_ip = htonl(host_ip);
        }
    }
    return connected;
}

void tailscale_connect_task(void *pvParameters)
{
    taskENTER_CRITICAL(&s_connect_lock);
    bool duplicate = s_connect_in_flight;
    if (!duplicate) s_connect_in_flight = true;
    taskEXIT_CRITICAL(&s_connect_lock);
    if (duplicate) {
        vTaskDelete(NULL);
        return;
    }
    init_sntp_if_needed();

    /* Microlink's Noise handshake is timestamped; we need real wall-clock
     * before the first registration attempt, same as WireGuard's TAI64N. */
    const int max_retry = 60;
    int retry = 0;
    time_t now = 0;
    while (retry < max_retry) {
        time(&now);
        if (now > 1577836800) break;
        if (retry % 4 == 0) {
            ESP_LOGI(TAG, "Waiting for SNTP time sync... (%d/%ds)", retry / 2, max_retry / 2);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
        retry++;
    }
    if (now > 1577836800) {
        struct tm timeinfo;
        localtime_r(&now, &timeinfo);
        ESP_LOGI(TAG, "Time synchronized: %04d-%02d-%02d %02d:%02d:%02d",
                 timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                 timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    } else {
        ESP_LOGW(TAG, "SNTP timeout after %ds, attempting Tailscale connect anyway", max_retry / 2);
    }

    tailscale_connect();
    taskENTER_CRITICAL(&s_connect_lock);
    s_connect_in_flight = false;
    taskEXIT_CRITICAL(&s_connect_lock);
    vTaskDelete(NULL);
}
