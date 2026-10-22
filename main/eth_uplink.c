/* Conditional SPI Ethernet uplink; see eth_uplink.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "eth_uplink.h"
#include "sdkconfig.h"
#include "json_guard.h"
#include "nvs.h"
#include "nvs_params.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "netif_hooks.h"
#include "portmap.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "lwip/netif.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if CONFIG_ETH_SPI_ETHERNET_W5500
#include "esp_eth.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#endif

#define TAG "eth_uplink"

/* --- eth core (begin) --- */
/* ESP32-S3 N16R8: GPIO26-37 belong to flash/octal PSRAM, 19/20 USB, 43/44
 * the console UART, 0/3/45/46 are strapping pins and 38-40 the microSD log. */
static bool eth_pin_allowed(int pin)
{
    static const int8_t allowed[] = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 41, 42, 47, 48};
    for (size_t i = 0; i < sizeof allowed; i++) if (allowed[i] == pin) return true;
    return false;
}

static bool eth_fail(char *why, size_t n, const char *text)
{
    if (why && n) snprintf(why, n, "%s", text);
    return false;
}

static bool eth_mask_valid(uint32_t mask_nbo)
{
    uint32_t m = ntohl(mask_nbo);
    return m && (~m & (~m + 1)) == 0 && m != UINT32_MAX;
}

bool eth_config_valid(const eth_config_t *c, char *why, size_t n)
{
    if (!c || c->enabled > 1 || c->ip_static > 1 || c->preference > ETH_PREF_ETHERNET_FIRST)
        return eth_fail(why, n, "invalid switch value");
    if (c->chip != ETH_CHIP_W5500) return eth_fail(why, n, "only the W5500 SPI module is supported");
    if (c->spi_host != 1 && c->spi_host != 2) return eth_fail(why, n, "SPI host must be SPI2 or SPI3");
    if (c->spi_mhz < 1 || c->spi_mhz > 40) return eth_fail(why, n, "SPI clock must be 1-40 MHz");
    int8_t pins[] = {c->sclk, c->mosi, c->miso, c->cs, c->intr, c->rst};
    for (unsigned i = 0; i < sizeof pins; i++) {
        if (pins[i] == -1 && i >= 4) continue;
        if (!eth_pin_allowed(pins[i])) return eth_fail(why, n, "pin not usable on this board (flash/PSRAM/USB/UART/strap/microSD)");
        for (unsigned j = 0; j < i; j++) if (pins[j] == pins[i]) return eth_fail(why, n, "pins must be distinct");
    }
    if (c->ip_static) {
        uint32_t ip = ntohl(c->ip), mask = ntohl(c->mask), gw = ntohl(c->gw);
        if (!eth_mask_valid(c->mask)) return eth_fail(why, n, "invalid netmask");
        if (!ip || (ip & ~mask) == 0 || (ip & ~mask) == ~mask || (ip >> 24) == 127 || (ip >> 28) >= 14)
            return eth_fail(why, n, "invalid static address");
        if (!gw || (gw & mask) != (ip & mask) || gw == ip) return eth_fail(why, n, "gateway must be another address in the same subnet");
    }
    return true;
}

int eth_uplink_choose(eth_selector_t *s, bool enabled, uint8_t preference, bool sta_ok, bool eth_ok)
{
    if (!enabled) {s->eth_streak = 0; return ETH_CHOICE_LEGACY;}
    if (!eth_ok) s->eth_streak = 0;
    else if (s->eth_streak < ETH_STABLE_SAMPLES) s->eth_streak++;
    bool eth_stable = s->eth_streak >= ETH_STABLE_SAMPLES;
    if (preference == ETH_PREF_ETHERNET_FIRST) return (eth_stable || (!sta_ok && eth_ok)) ? ETH_CHOICE_ETH : ETH_CHOICE_STA;
    return sta_ok ? ETH_CHOICE_STA : eth_ok ? ETH_CHOICE_ETH : ETH_CHOICE_STA;
}
/* --- eth core (end) --- */

#define ETH_MAGIC 0x45544831u /* ETH1 */
typedef struct {uint32_t magic, version; eth_config_t config; uint32_t checksum;} eth_record_t;

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static eth_config_t s_saved, s_running;
static eth_status_t s_status;
static atomic_bool s_link, s_has_ip;
static struct netif *s_lwip;           /* read in TCP/IP context only after start */
static eth_selector_t s_selector;      /* TCP/IP context only */
static esp_netif_t *s_netif;
static atomic_bool s_selected_eth;  /* last applied choice; drives listener rebinding */
#if CONFIG_ETH_SPI_ETHERNET_W5500
static esp_eth_handle_t s_handle;
#endif

static void defaults(eth_config_t *c)
{
    *c = (eth_config_t){.chip = ETH_CHIP_W5500, .spi_host = 1, .spi_mhz = 20,
        .sclk = 12, .mosi = 11, .miso = 13, .cs = 10, .intr = 14, .rst = 9};
}

static uint32_t record_checksum(const eth_record_t *r)
{
    uint32_t h = 2166136261u;
    const uint8_t *p = (const uint8_t *)r;
    for (size_t i = 0; i < offsetof(eth_record_t, checksum); i++) h = (h ^ p[i]) * 16777619u;
    return h;
}

static void load(eth_config_t *out)
{
    defaults(out);
    eth_record_t r;
    size_t size = sizeof r;
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) != ESP_OK) return;
    /* Invalid or foreign data means "Ethernet off", never a guessed pin map. */
    if (nvs_get_blob(nvs, "eth_cfg", &r, &size) == ESP_OK && size == sizeof r && r.magic == ETH_MAGIC
        && r.version == 1 && r.checksum == record_checksum(&r) && eth_config_valid(&r.config, NULL, 0))
        *out = r.config;
    nvs_close(nvs);
}

static void ensure_lock(void)
{
    static portMUX_TYPE init = portMUX_INITIALIZER_UNLOCKED;
    portENTER_CRITICAL(&init);
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    portEXIT_CRITICAL(&init);
}

static void set_error(const char *text)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    snprintf(s_status.error, sizeof s_status.error, "%s", text);
    xSemaphoreGive(s_lock);
}

/* Event-driven default-route application for when the route supervisor is
 * not running (Tailscale off). Never overrides an active exit-node route. */
static void apply_choice(void)
{
    if (tailscale_exit_node_ip != 0 || !s_netif) return;
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t info = {0};
    bool sta_ok = sta && esp_netif_is_netif_up(sta) && esp_netif_get_ip_info(sta, &info) == ESP_OK && info.ip.addr;
    bool eth_ok = atomic_load(&s_link) && atomic_load(&s_has_ip);
    eth_selector_t immediate = {.eth_streak = ETH_STABLE_SAMPLES};
    int choice = eth_uplink_choose(&immediate, true, s_running.preference, sta_ok, eth_ok);
    esp_netif_t *want = choice == ETH_CHOICE_ETH ? s_netif : sta_ok ? sta : NULL;
    if (want) esp_netif_set_default_netif(want);
    bool eth = choice == ETH_CHOICE_ETH;
    if (atomic_exchange(&s_selected_eth, eth) != eth || eth) portmap_install_all();
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
#if CONFIG_ETH_SPI_ETHERNET_W5500
    if (base == ETH_EVENT && (id == ETHERNET_EVENT_CONNECTED || id == ETHERNET_EVENT_DISCONNECTED)) {
        bool up = id == ETHERNET_EVENT_CONNECTED;
        atomic_store(&s_link, up);
        if (!up) atomic_store(&s_has_ip, false);
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_status.link_changes++;
        if (!up) {s_status.ip = s_status.mask = s_status.gw = 0;}
        xSemaphoreGive(s_lock);
        ESP_LOGI(TAG, "link %s", up ? "up" : "down");
    }
#endif
    if (base == IP_EVENT && (id == IP_EVENT_ETH_GOT_IP || id == IP_EVENT_ETH_LOST_IP)) {
        bool got = id == IP_EVENT_ETH_GOT_IP;
        atomic_store(&s_has_ip, got);
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (got) {
            const ip_event_got_ip_t *e = data;
            s_status.ip = e->ip_info.ip.addr; s_status.mask = e->ip_info.netmask.addr; s_status.gw = e->ip_info.gw.addr;
        } else s_status.ip = s_status.mask = s_status.gw = 0;
        xSemaphoreGive(s_lock);
    }
    apply_choice();
}

#if CONFIG_ETH_SPI_ETHERNET_W5500
static esp_err_t start_w5500(const eth_config_t *c)
{
    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;
    spi_host_device_t host = c->spi_host == 1 ? SPI2_HOST : SPI3_HOST;
    spi_bus_config_t bus = {.mosi_io_num = c->mosi, .miso_io_num = c->miso, .sclk_io_num = c->sclk,
                            .quadwp_io_num = -1, .quadhd_io_num = -1};
    err = spi_bus_initialize(host, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;
    spi_device_interface_config_t dev = {.mode = 0, .clock_speed_hz = c->spi_mhz * 1000000, .queue_size = 20,
                                         .spics_io_num = c->cs};
    eth_w5500_config_t w5500 = ETH_W5500_DEFAULT_CONFIG(host, &dev);
    w5500.int_gpio_num = c->intr;
    if (c->intr < 0) w5500.poll_period_ms = 10;
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.reset_gpio_num = c->rst;
    esp_eth_mac_t *mac = esp_eth_mac_new_w5500(&w5500, &mac_config);
    esp_eth_phy_t *phy = mac ? esp_eth_phy_new_w5500(&phy_config) : NULL;
    esp_eth_handle_t handle = NULL;
    esp_eth_netif_glue_handle_t glue = NULL;
    esp_eth_config_t config = ETH_DEFAULT_CONFIG(mac, phy);
    err = mac && phy ? esp_eth_driver_install(&config, &handle) : ESP_ERR_NO_MEM;
    if (err != ESP_OK) goto fail;
    uint8_t address[6];
    if ((err = esp_read_mac(address, ESP_MAC_ETH)) != ESP_OK
        || (err = esp_eth_ioctl(handle, ETH_CMD_S_MAC_ADDR, address)) != ESP_OK) goto fail_driver;
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&netif_config);
    if (!s_netif) {err = ESP_ERR_NO_MEM; goto fail_driver;}
    glue = esp_eth_new_netif_glue(handle);
    if (!glue) {err = ESP_ERR_NO_MEM; goto fail_netif;}
    if ((err = esp_netif_attach(s_netif, glue)) != ESP_OK) goto fail_netif;
    if (c->ip_static) {
        esp_netif_ip_info_t info = {.ip.addr = c->ip, .netmask.addr = c->mask, .gw.addr = c->gw};
        (void)esp_netif_dhcpc_stop(s_netif);
        if ((err = esp_netif_set_ip_info(s_netif, &info)) != ESP_OK) goto fail_netif;
        if (c->dns) {
            esp_netif_dns_info_t dns = {.ip.u_addr.ip4.addr = c->dns, .ip.type = ESP_IPADDR_TYPE_V4};
            (void)esp_netif_set_dns_info(s_netif, ESP_NETIF_DNS_MAIN, &dns);
        }
    }
    if ((err = esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, on_event, NULL)) != ESP_OK
        || (err = esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, on_event, NULL)) != ESP_OK) goto fail_netif;
    s_handle = handle;  /* started by eth_uplink_start() after the ACL hooks */
    return ESP_OK;
fail_netif:
    if (glue) esp_eth_del_netif_glue(glue);
    esp_netif_destroy(s_netif);
    s_netif = NULL;
fail_driver:
    esp_eth_driver_uninstall(handle);  /* MAC/PHY objects are still ours */
fail:
    if (phy) phy->del(phy);
    if (mac) mac->del(mac);
    spi_bus_free(host);
    return err;
}
#endif

void eth_uplink_init(void)
{
    ensure_lock();
    load(&s_saved);
    s_running = s_saved;
#if CONFIG_ETH_SPI_ETHERNET_W5500
    s_status.compiled = true;
#endif
    s_status.enabled_at_boot = s_running.enabled;
    if (!s_running.enabled) return;   /* WiFi-only path: no SPI/GPIO/netif touched */
#if CONFIG_ETH_SPI_ETHERNET_W5500
    esp_err_t err = start_w5500(&s_running);
    if (err != ESP_OK) {
        char text[64];
        snprintf(text, sizeof text, "driver start failed: %s", esp_err_to_name(err));
        set_error(text);
        ESP_LOGE(TAG, "%s (WiFi uplink unaffected)", text);
        return;
    }
#else
    set_error("Ethernet driver not compiled into this firmware");
#endif
}

void eth_uplink_start(void)
{
#if CONFIG_ETH_SPI_ETHERNET_W5500
    if (!s_handle) return;
    /* Fail closed: without the ACL hooks the interface never carries traffic. */
    if (!netif_hooks_eth_protected()) {set_error("not started: firewall hooks unavailable"); return;}
    esp_err_t err = esp_eth_start(s_handle);
    if (err != ESP_OK) {
        char text[64];
        snprintf(text, sizeof text, "start failed: %s", esp_err_to_name(err));
        set_error(text);
        return;
    }
    s_lwip = esp_netif_get_netif_impl(s_netif);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.driver_started = true;
    xSemaphoreGive(s_lock);
#endif
}

void eth_uplink_get_config(eth_config_t *out)
{
    ensure_lock();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_saved;
    xSemaphoreGive(s_lock);
}

esp_err_t eth_uplink_set_config(const eth_config_t *c, char *why, size_t n)
{
    ensure_lock();
    if (!eth_config_valid(c, why, n)) return ESP_ERR_INVALID_ARG;
    eth_record_t r = {.magic = ETH_MAGIC, .version = 1, .config = *c};
    r.checksum = record_checksum(&r);
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "eth_cfg", &r, sizeof r);
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err != ESP_OK) return err;   /* RAM keeps the previously saved value */
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_saved = *c;
    xSemaphoreGive(s_lock);
    return ESP_OK;
}

void eth_uplink_get_status(eth_status_t *out)
{
    ensure_lock();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_status;
    out->restart_required = memcmp(&s_saved, &s_running, sizeof s_saved) != 0;
    xSemaphoreGive(s_lock);
    out->link_up = atomic_load(&s_link);
    out->has_ip = atomic_load(&s_has_ip);
    esp_netif_t *def = esp_netif_get_default_netif();
    out->selected = s_netif && def == s_netif;
}

struct netif *eth_uplink_lwip_select(struct netif *sta)
{
    if (!s_running.enabled || !s_lwip) return NULL;
    bool sta_ok = sta && netif_is_up(sta) && netif_is_link_up(sta) && ip4_addr_get_u32(netif_ip4_addr(sta));
    bool eth_ok = netif_is_up(s_lwip) && netif_is_link_up(s_lwip) && ip4_addr_get_u32(netif_ip4_addr(s_lwip));
    int choice = eth_uplink_choose(&s_selector, true, s_running.preference, sta_ok, eth_ok);
    bool eth = choice == ETH_CHOICE_ETH;
    /* Already in TCP/IP context: rebind listeners in place, never queue-wait on ourselves. */
    if (atomic_exchange(&s_selected_eth, eth) != eth) portmap_install_now();
    return eth ? s_lwip : sta;
}

esp_netif_t *eth_uplink_service_netif(void)
{
    if (s_netif && atomic_load(&s_selected_eth) && atomic_load(&s_has_ip)) return s_netif;
    return esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
}

/* --- HTTP --- */
static esp_err_t send_json(httpd_req_t *req, cJSON *root)
{
    char *body = root ? cJSON_PrintUnformatted(root) : NULL;
    cJSON_Delete(root);
    if (!body) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, body);
    free(body);
    return err;
}

static void add_ip(cJSON *o, const char *name, uint32_t nbo)
{
    char text[16] = "";
    if (nbo) {struct in_addr a = {.s_addr = nbo}; inet_ntoa_r(a, text, sizeof text);}
    cJSON_AddStringToObject(o, name, text);
}

static cJSON *config_json(const eth_config_t *c)
{
    cJSON *o = cJSON_CreateObject();
    if (!o) return NULL;
    cJSON_AddBoolToObject(o, "enabled", c->enabled);
    cJSON_AddStringToObject(o, "chip", "w5500");
    cJSON_AddNumberToObject(o, "spi_host", c->spi_host == 1 ? 2 : 3);
    cJSON_AddNumberToObject(o, "spi_mhz", c->spi_mhz);
    cJSON_AddNumberToObject(o, "sclk", c->sclk); cJSON_AddNumberToObject(o, "mosi", c->mosi);
    cJSON_AddNumberToObject(o, "miso", c->miso); cJSON_AddNumberToObject(o, "cs", c->cs);
    cJSON_AddNumberToObject(o, "int", c->intr); cJSON_AddNumberToObject(o, "rst", c->rst);
    cJSON_AddBoolToObject(o, "static_ip", c->ip_static);
    add_ip(o, "ip", c->ip); add_ip(o, "netmask", c->mask); add_ip(o, "gateway", c->gw); add_ip(o, "dns", c->dns);
    cJSON_AddStringToObject(o, "preference", c->preference == ETH_PREF_ETHERNET_FIRST ? "ethernet_first" : "wifi_first");
    return o;
}

static esp_err_t get_ethernet(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    eth_config_t c; eth_status_t s;
    eth_uplink_get_config(&c);
    eth_uplink_get_status(&s);
    cJSON *root = cJSON_CreateObject(), *status = root ? cJSON_AddObjectToObject(root, "status") : NULL;
    cJSON *config = config_json(&c);
    if (!status || !config || !cJSON_AddItemToObject(root, "config", config)) {cJSON_Delete(config); cJSON_Delete(root); return send_json(req, NULL);}
    cJSON_AddBoolToObject(status, "compiled", s.compiled);
    cJSON_AddBoolToObject(status, "enabled_at_boot", s.enabled_at_boot);
    cJSON_AddBoolToObject(status, "driver_started", s.driver_started);
    cJSON_AddBoolToObject(status, "link_up", s.link_up);
    cJSON_AddBoolToObject(status, "has_ip", s.has_ip);
    cJSON_AddBoolToObject(status, "selected_uplink", s.selected);
    cJSON_AddBoolToObject(status, "restart_required", s.restart_required);
    cJSON_AddNumberToObject(status, "link_changes", s.link_changes);
    add_ip(status, "ip", s.ip); add_ip(status, "netmask", s.mask); add_ip(status, "gateway", s.gw);
    cJSON_AddStringToObject(status, "error", s.error);
    cJSON_AddStringToObject(status, "qualification", "not physically validated on this candidate");
    return send_json(req, root);
}

static bool json_int(const cJSON *root, const char *name, int lo, int hi, int *out)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(root, name);
    if (!cJSON_IsNumber(v) || !isfinite(v->valuedouble) || v->valuedouble < lo || v->valuedouble > hi
        || floor(v->valuedouble) != v->valuedouble) return false;
    *out = (int)v->valuedouble;
    return true;
}

static bool json_ip(const cJSON *root, const char *name, uint32_t *out)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(root, name);
    if (!cJSON_IsString(v)) return false;
    if (!v->valuestring[0]) {*out = 0; return true;}
    struct in_addr a;
    if (inet_pton(AF_INET, v->valuestring, &a) != 1) return false;
    *out = a.s_addr;
    return true;
}

static esp_err_t post_ethernet(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[512], why[96] = "invalid request";
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body size"); return ESP_FAIL;}
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) {httpd_resp_send_408(req); return ESP_FAIL;}
        received += n;
    }
    body[received] = 0;
    cJSON *root = json_guard_parse(body);
    eth_config_t c = {.chip = ETH_CHIP_W5500};
    int host = 0, mhz = 0, sclk, mosi, miso, cs, intr, rst;
    const cJSON *enabled = cJSON_GetObjectItemCaseSensitive(root, "enabled"), *st = cJSON_GetObjectItemCaseSensitive(root, "static_ip");
    const cJSON *pref = cJSON_GetObjectItemCaseSensitive(root, "preference"), *chip = cJSON_GetObjectItemCaseSensitive(root, "chip");
    bool parsed = cJSON_IsObject(root) && cJSON_IsBool(enabled) && cJSON_IsBool(st) && cJSON_IsString(pref)
        && cJSON_IsString(chip) && !strcmp(chip->valuestring, "w5500")
        && (!strcmp(pref->valuestring, "wifi_first") || !strcmp(pref->valuestring, "ethernet_first"))
        && json_int(root, "spi_host", 2, 3, &host) && json_int(root, "spi_mhz", 1, 40, &mhz)
        && json_int(root, "sclk", 0, 48, &sclk) && json_int(root, "mosi", 0, 48, &mosi) && json_int(root, "miso", 0, 48, &miso)
        && json_int(root, "cs", 0, 48, &cs) && json_int(root, "int", -1, 48, &intr) && json_int(root, "rst", -1, 48, &rst)
        && json_ip(root, "ip", &c.ip) && json_ip(root, "netmask", &c.mask) && json_ip(root, "gateway", &c.gw) && json_ip(root, "dns", &c.dns);
    if (parsed) {
        c.enabled = cJSON_IsTrue(enabled); c.ip_static = cJSON_IsTrue(st);
        c.preference = !strcmp(pref->valuestring, "ethernet_first") ? ETH_PREF_ETHERNET_FIRST : ETH_PREF_WIFI_FIRST;
        c.spi_host = (uint8_t)(host - 1); c.spi_mhz = (uint8_t)mhz;
        c.sclk = (int8_t)sclk; c.mosi = (int8_t)mosi; c.miso = (int8_t)miso; c.cs = (int8_t)cs; c.intr = (int8_t)intr; c.rst = (int8_t)rst;
        if (!c.ip_static) c.ip = c.mask = c.gw = c.dns = 0;
    }
    cJSON_Delete(root);
    esp_err_t err = parsed ? eth_uplink_set_config(&c, why, sizeof why) : ESP_ERR_INVALID_ARG;
    cJSON *reply = cJSON_CreateObject();
    if (err != ESP_OK) {
        httpd_resp_set_status(req, err == ESP_ERR_INVALID_ARG ? "400 Bad Request" : "500 Internal Server Error");
        if (reply) {cJSON_AddBoolToObject(reply, "ok", false); cJSON_AddStringToObject(reply, "error", err == ESP_ERR_INVALID_ARG ? why : esp_err_to_name(err));}
    } else if (reply) {cJSON_AddBoolToObject(reply, "ok", true); cJSON_AddBoolToObject(reply, "restart_required", true);}
    return send_json(req, reply);
}

esp_err_t eth_uplink_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/ethernet", .method = HTTP_GET, .handler = get_ethernet},
        {.uri = "/api/ethernet", .method = HTTP_POST, .handler = post_ethernet}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
