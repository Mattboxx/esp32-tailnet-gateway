/* Optional cellular (GSM/LTE) uplink over a UART modem; see cell_uplink.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "cell_uplink.h"
#include "eth_uplink.h"
#include "json_guard.h"
#include "netif_hooks.h"
#include "nvs.h"
#include "nvs_params.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_ppp.h"
#include "esp_netif_net_stack.h"
#include "lwip/inet.h"
#include "lwip/netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <ctype.h>
#include <math.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TAG "cell_uplink"

/* --- cell core (begin) --- */
/* Same usable set as the Ethernet pins on ESP32-S3 N8R8/N16R8: flash/octal
 * PSRAM, USB, console UART, strapping and microSD pins are excluded. */
static bool cell_pin_allowed(int pin)
{
    static const int8_t allowed[] = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 41, 42, 47, 48};
    for (size_t i = 0; i < sizeof allowed; i++) if (allowed[i] == pin) return true;
    return false;
}

static bool cell_fail(char *why, size_t n, const char *text)
{
    if (why && n) snprintf(why, n, "%s", text);
    return false;
}

/* Text sent inside a quoted AT argument: printable ASCII without quotes or
 * backslashes, so it can never end the argument or inject a command. */
static bool cell_text_ok(const char *s, size_t cap, bool allow_empty)
{
    size_t n = strnlen(s, cap);
    if (n == cap || (!n && !allow_empty)) return false;
    for (size_t i = 0; i < n; i++) {
        unsigned char ch = (unsigned char)s[i];
        if (ch < 0x20 || ch > 0x7e || ch == '"' || ch == '\\') return false;
    }
    return true;
}

bool cell_config_valid(const cell_config_t *c, char *why, size_t n)
{
    if (!c || c->enabled > 1 || c->mode > CELL_MODE_PRIMARY || c->roaming > 1 || c->data_ack > 1 || c->pwrkey_active_high > 1)
        return cell_fail(why, n, "invalid switch value");
    if (c->enabled && !c->data_ack) return cell_fail(why, n, "acknowledge the data-use notice before enabling");
    if (c->uart != 1 && c->uart != 2) return cell_fail(why, n, "UART must be UART1 or UART2");
    static const uint32_t bauds[] = {9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600};
    bool baud_ok = false;
    for (size_t i = 0; i < sizeof bauds / sizeof bauds[0]; i++) baud_ok |= c->baud == bauds[i];
    if (!baud_ok) return cell_fail(why, n, "unsupported baud rate");
    int8_t pins[] = {c->tx, c->rx, c->rts, c->cts, c->pwrkey};
    for (unsigned i = 0; i < sizeof pins; i++) {
        if (pins[i] == -1 && i >= 2) continue;
        if (!cell_pin_allowed(pins[i])) return cell_fail(why, n, "pin not usable on this board (flash/PSRAM/USB/UART/strap/microSD)");
        for (unsigned j = 0; j < i; j++) if (pins[j] == pins[i]) return cell_fail(why, n, "pins must be distinct");
    }
    if ((c->rts == -1) != (c->cts == -1)) return cell_fail(why, n, "hardware flow control needs both RTS and CTS");
    if (!cell_text_ok(c->apn, sizeof c->apn, !c->enabled)) return cell_fail(why, n, "APN required (letters, digits and dots; no quotes)");
    if (!cell_text_ok(c->user, sizeof c->user, true) || !cell_text_ok(c->password, sizeof c->password, true))
        return cell_fail(why, n, "user name and password: printable characters without quotes");
    size_t pin = strnlen(c->pin, sizeof c->pin);
    if (pin == sizeof c->pin || (pin && (pin < 4 || pin > 8))) return cell_fail(why, n, "SIM PIN: 4-8 digits or empty");
    for (size_t i = 0; i < pin; i++) if (!isdigit((unsigned char)c->pin[i])) return cell_fail(why, n, "SIM PIN: 4-8 digits or empty");
    return true;
}

int cell_csq_to_dbm(int csq)
{
    return csq >= 0 && csq <= 31 ? -113 + 2 * csq : 0;
}

/* Value after "<prefix>: " in a response, NULL when absent. */
static const char *cell_field(const char *response, const char *prefix)
{
    const char *p = response ? strstr(response, prefix) : NULL;
    if (!p) return NULL;
    p += strlen(prefix);
    if (*p != ':') return NULL;
    p++;
    while (*p == ' ') p++;
    return p;
}

int cell_parse_csq(const char *response)
{
    const char *p = cell_field(response, "+CSQ");
    if (!p || !isdigit((unsigned char)*p)) return -1;
    long v = strtol(p, NULL, 10);
    return v >= 0 && v <= 99 ? (int)v : -1;
}

/* "+CREG: <n>,<stat>[,...]" (query form) or "+CREG: <stat>" (URC form). */
int cell_parse_reg(const char *response, const char *prefix)
{
    const char *p = cell_field(response, prefix);
    if (!p || !isdigit((unsigned char)*p)) return -1;
    char *end;
    long first = strtol(p, &end, 10);
    long stat = first;
    if (*end == ',') {
        if (!isdigit((unsigned char)end[1])) return -1;
        stat = strtol(end + 1, NULL, 10);
    }
    return stat >= 0 && stat <= 10 ? (int)stat : -1;
}

int cell_parse_cpin(const char *response)
{
    const char *p = cell_field(response, "+CPIN");
    if (!p) return CELL_SIM_OTHER;
    if (!strncmp(p, "READY", 5)) return CELL_SIM_READY;
    if (!strncmp(p, "SIM PIN", 7) && strncmp(p, "SIM PIN2", 8)) return CELL_SIM_PIN;
    if (!strncmp(p, "SIM PUK", 7) && strncmp(p, "SIM PUK2", 8)) return CELL_SIM_PUK;
    return CELL_SIM_OTHER;
}

/* +COPS: 0,0,"Operator Name",7 -> Operator Name */
bool cell_parse_cops(const char *response, char *name, size_t n)
{
    const char *p = cell_field(response, "+COPS");
    const char *open = p ? strchr(p, '"') : NULL;
    const char *close = open ? strchr(open + 1, '"') : NULL;
    if (!close || !n) return false;
    size_t len = (size_t)(close - open - 1);
    if (len >= n) len = n - 1;
    for (size_t i = 0; i < len; i++) {
        unsigned char ch = (unsigned char)open[1 + i];
        name[i] = ch >= 0x20 && ch <= 0x7e ? (char)ch : '?';
    }
    name[len] = 0;
    return len > 0;
}

bool cell_registered(int stat, bool roaming)
{
    return stat == 1 || (stat == 5 && roaming);
}

bool cell_uplink_choose(cell_selector_t *s, uint8_t mode, bool other_ok, bool cell_ok)
{
    if (!cell_ok) {s->streak = 0; return false;}
    if (s->streak < CELL_STABLE_SAMPLES) s->streak++;
    if (mode == CELL_MODE_PRIMARY) return s->streak >= CELL_STABLE_SAMPLES || !other_ok;
    return !other_ok;
}
/* --- cell core (end) --- */

#define CELL_MAGIC 0x43454c31u /* CEL1 */
typedef struct {uint32_t magic, version; cell_config_t config; uint32_t checksum;} cell_record_t;

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static cell_config_t s_saved, s_running;
static cell_status_t s_status;
static atomic_bool s_has_ip, s_link_dead;
static esp_netif_t *s_netif;
static struct netif *s_lwip;           /* read in TCP/IP context only after creation */
static cell_selector_t s_selector;     /* TCP/IP context only */
static uart_port_t s_port;

static void defaults(cell_config_t *c)
{
    *c = (cell_config_t){.uart = 1, .baud = 115200, .tx = 17, .rx = 18, .rts = -1, .cts = -1, .pwrkey = -1};
}

static uint32_t record_checksum(const cell_record_t *r)
{
    uint32_t h = 2166136261u;
    const uint8_t *p = (const uint8_t *)r;
    for (size_t i = 0; i < offsetof(cell_record_t, checksum); i++) h = (h ^ p[i]) * 16777619u;
    return h;
}

static void load(cell_config_t *out)
{
    defaults(out);
    cell_record_t r;
    size_t size = sizeof r;
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) != ESP_OK) return;
    /* Invalid or foreign data means "cellular off", never a guessed modem. */
    if (nvs_get_blob(nvs, "cell_cfg", &r, &size) == ESP_OK && size == sizeof r && r.magic == CELL_MAGIC
        && r.version == 1 && r.checksum == record_checksum(&r) && cell_config_valid(&r.config, NULL, 0))
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

static void set_state(uint8_t state, const char *error)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.state = state;
    if (error) snprintf(s_status.error, sizeof s_status.error, "%s", error);
    xSemaphoreGive(s_lock);
    if (error && error[0]) ESP_LOGW(TAG, "%s", error);
}

/* --- AT command channel (modem task only) --- */
static char s_line[256];

/* Sends `command` and collects the response until OK/ERROR/`final` or the
 * timeout. 1: OK (or `final` seen), 0: ERROR, -1: timeout. */
static int at(const char *command, const char *final, char *response, size_t n, int timeout_ms)
{
    if (response && n) response[0] = 0;
    uart_flush_input(s_port);
    if (command) {
        uart_write_bytes(s_port, command, strlen(command));
        uart_write_bytes(s_port, "\r", 1);
    }
    size_t used = 0, line = 0;
    TickType_t end = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    while ((int32_t)(end - xTaskGetTickCount()) > 0) {
        uint8_t ch;
        if (uart_read_bytes(s_port, &ch, 1, pdMS_TO_TICKS(20)) != 1) continue;
        if (ch != '\r' && ch != '\n') {
            if (line < sizeof s_line - 1) s_line[line++] = (char)ch;
            continue;
        }
        if (!line) continue;
        s_line[line] = 0;
        line = 0;
        if (command && !strcmp(s_line, command)) continue;   /* echo before ATE0 */
        if (response && used + strlen(s_line) + 2 < n) {
            used += (size_t)snprintf(response + used, n - used, "%s\n", s_line);
        }
        if (!strcmp(s_line, "OK") || (final && strstr(s_line, final))) return 1;
        if (!strcmp(s_line, "ERROR") || !strncmp(s_line, "+CME ERROR", 10) || !strcmp(s_line, "NO CARRIER")
            || !strcmp(s_line, "BUSY") || !strcmp(s_line, "NO DIALTONE")) return 0;
    }
    return -1;
}

static bool at_sync(void)
{
    for (int i = 0; i < 30; i++) if (at("AT", NULL, NULL, 0, 1000) == 1) return true;
    return false;
}

static void modem_power_pulse(void)
{
    if (s_running.pwrkey < 0) return;
    gpio_reset_pin(s_running.pwrkey);
    gpio_set_direction(s_running.pwrkey, GPIO_MODE_OUTPUT);
    int active = s_running.pwrkey_active_high ? 1 : 0;
    gpio_set_level(s_running.pwrkey, !active);
    vTaskDelay(pdMS_TO_TICKS(100));
    gpio_set_level(s_running.pwrkey, active);
    vTaskDelay(pdMS_TO_TICKS(1200));
    gpio_set_level(s_running.pwrkey, !active);
    vTaskDelay(pdMS_TO_TICKS(8000));   /* typical modem boot before AT answers */
}

/* Leaves data mode after the PPP link ended: guard time, "+++", hang up. */
static void hang_up(void)
{
    vTaskDelay(pdMS_TO_TICKS(1100));
    uart_write_bytes(s_port, "+++", 3);
    vTaskDelay(pdMS_TO_TICKS(1100));
    (void)at("ATH", NULL, NULL, 0, 3000);
}

static void refresh_info(void)
{
    char response[160], name[32] = "";
    int csq = at("AT+CSQ", NULL, response, sizeof response, 2000) == 1 ? cell_parse_csq(response) : -1;
    bool have_name = at("AT+COPS?", NULL, response, sizeof response, 3000) == 1 && cell_parse_cops(response, name, sizeof name);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.rssi_dbm = (int16_t)cell_csq_to_dbm(csq);
    if (have_name) snprintf(s_status.operator_name, sizeof s_status.operator_name, "%s", name);
    xSemaphoreGive(s_lock);
}

static int registration(void)
{
    static const char *const queries[][2] = {{"AT+CEREG?", "+CEREG"}, {"AT+CGREG?", "+CGREG"}, {"AT+CREG?", "+CREG"}};
    char response[160];
    int best = -1;
    for (size_t i = 0; i < 3; i++) {
        if (at(queries[i][0], NULL, response, sizeof response, 2000) != 1) continue;
        int stat = cell_parse_reg(response, queries[i][1]);
        if (cell_registered(stat, s_running.roaming)) return stat;
        if (stat >= 0) best = stat;
    }
    return best;
}

/* --- PPP netif glue --- */
typedef struct {esp_netif_driver_base_t base;} cell_driver_t;
static cell_driver_t s_driver;

static esp_err_t cell_transmit(void *handle, void *buffer, size_t len)
{
    (void)handle;
    return uart_write_bytes(s_port, buffer, len) == (int)len ? ESP_OK : ESP_FAIL;
}

static esp_err_t cell_post_attach(esp_netif_t *netif, void *args)
{
    cell_driver_t *driver = args;
    driver->base.netif = netif;
    const esp_netif_driver_ifconfig_t ifconfig = {.handle = driver, .transmit = cell_transmit};
    return esp_netif_set_driver_config(netif, &ifconfig);
}

/* Event-driven default-route choice for when the route supervisor is not
 * running (Tailscale off). Never overrides an active exit-node route. */
static void apply_choice(void)
{
    if (tailscale_exit_node_ip != 0 || !s_netif) return;
    esp_netif_t *other = eth_uplink_service_netif();
    esp_netif_ip_info_t info = {0};
    bool other_ok = other && esp_netif_is_netif_up(other) && esp_netif_get_ip_info(other, &info) == ESP_OK && info.ip.addr;
    cell_selector_t immediate = {.streak = CELL_STABLE_SAMPLES};
    bool use = cell_uplink_choose(&immediate, s_running.mode, other_ok, atomic_load(&s_has_ip));
    esp_netif_t *want = use ? s_netif : other_ok ? other : NULL;
    if (want && esp_netif_get_default_netif() != want) esp_netif_set_default_netif(want);
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == NETIF_PPP_STATUS) {
        if (id > NETIF_PPP_ERRORNONE && id < NETIF_PP_PHASE_OFFSET) atomic_store(&s_link_dead, true);
        return;
    }
    if (base == IP_EVENT && (id == IP_EVENT_PPP_GOT_IP || id == IP_EVENT_PPP_LOST_IP)) {
        bool got = id == IP_EVENT_PPP_GOT_IP;
        atomic_store(&s_has_ip, got);
        if (!got) atomic_store(&s_link_dead, true);
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_status.ip = got ? ((const ip_event_got_ip_t *)data)->ip_info.ip.addr : 0;
        if (got) s_status.connects++;
        xSemaphoreGive(s_lock);
    }
    apply_choice();
}

static esp_err_t create_netif(void)
{
    esp_netif_inherent_config_t base = ESP_NETIF_INHERENT_DEFAULT_PPP();
    base.if_desc = "cell";
    base.route_prio = 5;   /* never the automatic default over WiFi or Ethernet */
    esp_netif_config_t config = {.base = &base, .driver = NULL, .stack = ESP_NETIF_NETSTACK_DEFAULT_PPP};
    s_netif = esp_netif_new(&config);
    if (!s_netif) return ESP_ERR_NO_MEM;
    s_driver.base.post_attach = cell_post_attach;
    esp_err_t err = esp_netif_attach(s_netif, &s_driver);
    esp_netif_ppp_config_t ppp = {.ppp_phase_event_enabled = false, .ppp_error_event_enabled = true};
    if (err == ESP_OK) err = esp_netif_ppp_set_params(s_netif, &ppp);
    if (err == ESP_OK && s_running.user[0])
        err = esp_netif_ppp_set_auth(s_netif, NETIF_PPP_AUTHTYPE_PAP, s_running.user, s_running.password);
    /* Fail closed: without the PPP ACL hooks the link never carries traffic. */
    struct netif *lwip = esp_netif_get_netif_impl(s_netif);
    if (err == ESP_OK && !netif_hooks_install_ppp(lwip)) err = ESP_ERR_INVALID_STATE;
    if (err == ESP_OK)
        err = esp_event_handler_register(NETIF_PPP_STATUS, ESP_EVENT_ANY_ID, on_event, NULL);
    if (err == ESP_OK)
        err = esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, on_event, NULL);
    if (err != ESP_OK) {esp_netif_destroy(s_netif); s_netif = NULL; return err;}
    s_lwip = lwip;
    return ESP_OK;
}

static esp_err_t open_uart(void)
{
    s_port = s_running.uart == 1 ? UART_NUM_1 : UART_NUM_2;
    uart_config_t config = {.baud_rate = (int)s_running.baud, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
                            .stop_bits = UART_STOP_BITS_1, .source_clk = UART_SCLK_DEFAULT,
                            .flow_ctrl = s_running.rts >= 0 ? UART_HW_FLOWCTRL_CTS_RTS : UART_HW_FLOWCTRL_DISABLE,
                            .rx_flow_ctrl_thresh = 100};
    esp_err_t err = uart_driver_install(s_port, 4096, 2048, 0, NULL, 0);
    if (err == ESP_OK) err = uart_param_config(s_port, &config);
    if (err == ESP_OK) err = uart_set_pin(s_port, s_running.tx, s_running.rx,
                                          s_running.rts >= 0 ? s_running.rts : UART_PIN_NO_CHANGE,
                                          s_running.cts >= 0 ? s_running.cts : UART_PIN_NO_CHANGE);
    return err;
}

/* Bounded retry: 30 s doubling to 10 min; a SIM PIN/PUK problem stops. */
static uint32_t backoff_s(unsigned failures)
{
    uint32_t s = 30u << (failures < 5 ? failures : 5);
    return s > 600 ? 600 : s;
}

static void cell_task(void *arg)
{
    (void)arg;
    unsigned failures = 0;
    /* PWRKEY toggles many modems: pulse only at start and after the modem
     * stopped answering AT, never after an ordinary end of the data call. */
    bool power_pulse = true, pin_sent = false;
    char response[192];
    uint8_t *buffer = heap_caps_malloc(512, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buffer) {set_state(CELL_STOPPED, "not enough memory for the modem buffer"); vTaskDelete(NULL); return;}
    for (;;) {
        if (power_pulse) {set_state(CELL_POWERING, NULL); modem_power_pulse(); power_pulse = false;}
        set_state(CELL_SYNC, NULL);
        if (!at_sync()) {
            power_pulse = true;
            set_state(CELL_BACKOFF, "modem does not answer AT: check wiring, baud rate and power");
            goto retry;
        }
        (void)at("ATE0", NULL, NULL, 0, 1000);
        (void)at("AT+CMEE=2", NULL, NULL, 0, 1000);
        if (at("AT+CGMM", NULL, response, sizeof response, 2000) == 1) {
            char *end = strchr(response, '\n');
            if (end) *end = 0;
            xSemaphoreTake(s_lock, portMAX_DELAY);
            snprintf(s_status.model, sizeof s_status.model, "%.31s", response);
            xSemaphoreGive(s_lock);
        }
        set_state(CELL_SIM, NULL);
        int sim = at("AT+CPIN?", "+CPIN", response, sizeof response, 5000) == 1 ? cell_parse_cpin(response) : CELL_SIM_OTHER;
        if (sim == CELL_SIM_PUK) {set_state(CELL_STOPPED, "SIM is PUK-locked: unlock it in a phone, then restart"); break;}
        if (sim == CELL_SIM_PIN) {
            /* One attempt per boot: a wrong PIN must never count down to PUK. */
            if (!s_running.pin[0]) {set_state(CELL_STOPPED, "SIM needs a PIN: enter it and restart"); break;}
            if (pin_sent) {set_state(CELL_STOPPED, "SIM PIN rejected: check it and restart"); break;}
            char command[32];
            snprintf(command, sizeof command, "AT+CPIN=\"%s\"", s_running.pin);
            pin_sent = true;
            if (at(command, NULL, NULL, 0, 10000) != 1) {set_state(CELL_STOPPED, "SIM PIN rejected: check it and restart"); break;}
            vTaskDelay(pdMS_TO_TICKS(5000));
            sim = at("AT+CPIN?", "+CPIN", response, sizeof response, 5000) == 1 ? cell_parse_cpin(response) : CELL_SIM_OTHER;
        }
        if (sim != CELL_SIM_READY) {set_state(CELL_BACKOFF, "SIM not ready (inserted?)"); goto retry;}
        set_state(CELL_REGISTERING, NULL);
        int stat = -1;
        for (int i = 0; i < 60 && !cell_registered(stat, s_running.roaming); i++) {
            stat = registration();
            if (!cell_registered(stat, s_running.roaming)) vTaskDelay(pdMS_TO_TICKS(2000));
        }
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_status.registration = stat < 0 ? 0xff : (uint8_t)stat;
        xSemaphoreGive(s_lock);
        refresh_info();
        if (!cell_registered(stat, s_running.roaming)) {
            set_state(CELL_BACKOFF, stat == 5 ? "roaming network: allow roaming to use it" : "not registered on a mobile network");
            goto retry;
        }
        set_state(CELL_DIALING, NULL);
        char command[96];
        snprintf(command, sizeof command, "AT+CGDCONT=1,\"IP\",\"%s\"", s_running.apn);
        if (at(command, NULL, NULL, 0, 5000) != 1) {set_state(CELL_BACKOFF, "APN rejected by the modem"); goto retry;}
        if (at("ATD*99#", "CONNECT", NULL, 0, 30000) != 1) {set_state(CELL_BACKOFF, "data call refused (APN, plan or coverage)"); goto retry;}
        atomic_store(&s_link_dead, false);
        set_state(CELL_CONNECTED, "");
        esp_netif_action_start(s_netif, 0, 0, 0);
        TickType_t last_choice = xTaskGetTickCount();
        while (!atomic_load(&s_link_dead)) {
            int n = uart_read_bytes(s_port, buffer, 512, pdMS_TO_TICKS(50));
            if (n > 0) esp_netif_receive(s_netif, buffer, (size_t)n, NULL);
            if (xTaskGetTickCount() - last_choice > pdMS_TO_TICKS(2000)) {apply_choice(); last_choice = xTaskGetTickCount();}
        }
        esp_netif_action_stop(s_netif, 0, 0, 0);
        atomic_store(&s_has_ip, false);
        apply_choice();
        hang_up();
        set_state(CELL_BACKOFF, "data link ended; reconnecting");
        failures = 0;
retry:
        if (++failures > 30) failures = 30;
        vTaskDelay(pdMS_TO_TICKS(backoff_s(failures - 1) * 1000));
    }
    free(buffer);
    vTaskDelete(NULL);
}

void cell_uplink_init(void)
{
    ensure_lock();
    load(&s_saved);
    s_running = s_saved;
    s_status.enabled_at_boot = s_running.enabled;
    s_status.registration = 0xff;
    if (!s_running.enabled) return;   /* nothing touched: no UART, GPIO or netif */
    esp_err_t err = open_uart();
    if (err == ESP_OK) err = create_netif();
    if (err != ESP_OK) {
        char text[80];
        snprintf(text, sizeof text, "not started: %s", esp_err_to_name(err));
        set_state(CELL_STOPPED, text);
        return;
    }
    /* PSRAM stack: the task never writes flash (no NVS access). */
    if (xTaskCreatePinnedToCoreWithCaps(cell_task, "cell_modem", 6144, NULL, 5, NULL, tskNO_AFFINITY,
                                        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) != pdPASS) {
        set_state(CELL_STOPPED, "not started: no memory for the modem task");
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.task_running = true;
    xSemaphoreGive(s_lock);
}

void cell_uplink_get_config(cell_config_t *out)
{
    ensure_lock();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_saved;
    xSemaphoreGive(s_lock);
}

esp_err_t cell_uplink_set_config(const cell_config_t *c, char *why, size_t n)
{
    ensure_lock();
    if (!cell_config_valid(c, why, n)) return ESP_ERR_INVALID_ARG;
    if (c->enabled) {
        /* Never share a pin with an enabled Ethernet module. */
        eth_config_t e;
        eth_uplink_get_config(&e);
        int8_t mine[] = {c->tx, c->rx, c->rts, c->cts, c->pwrkey}, theirs[] = {e.sclk, e.mosi, e.miso, e.cs, e.intr, e.rst};
        for (unsigned i = 0; e.enabled && i < sizeof mine; i++)
            for (unsigned j = 0; mine[i] >= 0 && j < sizeof theirs; j++)
                if (mine[i] == theirs[j]) {snprintf(why, n, "pin %d is used by the Ethernet module", mine[i]); return ESP_ERR_INVALID_ARG;}
    }
    cell_record_t r = {.magic = CELL_MAGIC, .version = 1, .config = *c};
    r.checksum = record_checksum(&r);
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "cell_cfg", &r, sizeof r);
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err != ESP_OK) return err;   /* RAM keeps the previously saved value */
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_saved = *c;
    xSemaphoreGive(s_lock);
    return ESP_OK;
}

void cell_uplink_get_status(cell_status_t *out)
{
    ensure_lock();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_status;
    out->restart_required = memcmp(&s_saved, &s_running, sizeof s_saved) != 0;
    xSemaphoreGive(s_lock);
    out->has_ip = atomic_load(&s_has_ip);
    out->selected = s_netif && esp_netif_get_default_netif() == s_netif;
    out->bytes_in = netif_hooks_get_ppp_bytes_in();
    out->bytes_out = netif_hooks_get_ppp_bytes_out();
}

struct netif *cell_uplink_lwip_select(struct netif *current)
{
    if (!s_running.enabled || !s_lwip) return NULL;
    bool other_ok = current && netif_is_up(current) && netif_is_link_up(current) && ip4_addr_get_u32(netif_ip4_addr(current));
    bool cell_ok = netif_is_up(s_lwip) && ip4_addr_get_u32(netif_ip4_addr(s_lwip));
    return cell_uplink_choose(&s_selector, s_running.mode, other_ok, cell_ok) ? s_lwip : NULL;
}

/* --- HTTP --- */
static const char *const STATE_NAMES[] = {"off", "powering", "sync", "sim", "registering", "dialing", "connected", "backoff", "stopped"};

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

static esp_err_t get_cellular(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    cell_config_t c; cell_status_t s;
    cell_uplink_get_config(&c);
    cell_uplink_get_status(&s);
    cJSON *root = cJSON_CreateObject();
    cJSON *config = root ? cJSON_AddObjectToObject(root, "config") : NULL;
    cJSON *status = root ? cJSON_AddObjectToObject(root, "status") : NULL;
    if (!config || !status) {cJSON_Delete(root); return send_json(req, NULL);}
    cJSON_AddBoolToObject(config, "enabled", c.enabled);
    cJSON_AddStringToObject(config, "mode", c.mode == CELL_MODE_PRIMARY ? "primary" : "failover");
    cJSON_AddBoolToObject(config, "roaming", c.roaming);
    cJSON_AddBoolToObject(config, "data_ack", c.data_ack);
    cJSON_AddNumberToObject(config, "uart", c.uart);
    cJSON_AddNumberToObject(config, "baud", c.baud);
    cJSON_AddNumberToObject(config, "tx", c.tx); cJSON_AddNumberToObject(config, "rx", c.rx);
    cJSON_AddNumberToObject(config, "rts", c.rts); cJSON_AddNumberToObject(config, "cts", c.cts);
    cJSON_AddNumberToObject(config, "pwrkey", c.pwrkey);
    cJSON_AddBoolToObject(config, "pwrkey_active_high", c.pwrkey_active_high);
    cJSON_AddStringToObject(config, "apn", c.apn);
    cJSON_AddStringToObject(config, "user", c.user);
    /* Write-only secrets: presence only. */
    cJSON_AddBoolToObject(config, "has_password", c.password[0] != 0);
    cJSON_AddBoolToObject(config, "has_pin", c.pin[0] != 0);
    cJSON_AddBoolToObject(status, "enabled_at_boot", s.enabled_at_boot);
    cJSON_AddBoolToObject(status, "task_running", s.task_running);
    cJSON_AddStringToObject(status, "state", s.state < sizeof STATE_NAMES / sizeof STATE_NAMES[0] ? STATE_NAMES[s.state] : "unknown");
    if (s.registration == 0xff) cJSON_AddNullToObject(status, "registration");
    else cJSON_AddNumberToObject(status, "registration", s.registration);
    if (s.rssi_dbm) cJSON_AddNumberToObject(status, "rssi_dbm", s.rssi_dbm);
    else cJSON_AddNullToObject(status, "rssi_dbm");
    cJSON_AddStringToObject(status, "model", s.model);
    cJSON_AddStringToObject(status, "operator", s.operator_name);
    char ip[16] = "";
    if (s.ip) {struct in_addr a = {.s_addr = s.ip}; inet_ntoa_r(a, ip, sizeof ip);}
    cJSON_AddStringToObject(status, "ip", ip);
    cJSON_AddBoolToObject(status, "has_ip", s.has_ip);
    cJSON_AddBoolToObject(status, "selected_uplink", s.selected);
    cJSON_AddBoolToObject(status, "restart_required", s.restart_required);
    cJSON_AddNumberToObject(status, "connects", s.connects);
    cJSON_AddNumberToObject(status, "bytes_in", (double)s.bytes_in);
    cJSON_AddNumberToObject(status, "bytes_out", (double)s.bytes_out);
    cJSON_AddStringToObject(status, "error", s.error);
    cJSON_AddStringToObject(status, "qualification", "experimental: not physically validated with a modem");
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

static bool json_text(const cJSON *root, const char *name, char *out, size_t cap)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(root, name);
    if (!cJSON_IsString(v) || strlen(v->valuestring) >= cap) return false;
    snprintf(out, cap, "%s", v->valuestring);
    return true;
}

/* A write-only secret: absent or "" keeps the saved value, clear_<name>
 * removes it, any other string replaces it. */
static bool json_secret(const cJSON *root, const char *name, const char *clear, const char *saved, char *out, size_t cap)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(root, name);
    const cJSON *drop = cJSON_GetObjectItemCaseSensitive(root, clear);
    if (drop && !cJSON_IsBool(drop)) return false;
    snprintf(out, cap, "%s", saved);
    if (cJSON_IsTrue(drop)) out[0] = 0;
    if (!v) return true;
    if (!cJSON_IsString(v) || strlen(v->valuestring) >= cap) return false;
    if (v->valuestring[0]) snprintf(out, cap, "%s", v->valuestring);
    return true;
}

static esp_err_t post_cellular(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[768], why[96] = "invalid request";
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body size"); return ESP_FAIL;}
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) {httpd_resp_send_408(req); return ESP_FAIL;}
        received += n;
    }
    body[received] = 0;
    cell_config_t saved, c = {0};
    cell_uplink_get_config(&saved);
    cJSON *root = json_guard_parse(body);
    int uart = 0, baud = 0, tx, rx, rts, cts, pwrkey;
    const cJSON *enabled = cJSON_GetObjectItemCaseSensitive(root, "enabled"), *mode = cJSON_GetObjectItemCaseSensitive(root, "mode");
    const cJSON *roaming = cJSON_GetObjectItemCaseSensitive(root, "roaming"), *ack = cJSON_GetObjectItemCaseSensitive(root, "data_ack");
    const cJSON *high = cJSON_GetObjectItemCaseSensitive(root, "pwrkey_active_high");
    bool parsed = cJSON_IsObject(root) && cJSON_IsBool(enabled) && cJSON_IsBool(roaming) && cJSON_IsBool(ack) && cJSON_IsBool(high)
        && cJSON_IsString(mode) && (!strcmp(mode->valuestring, "failover") || !strcmp(mode->valuestring, "primary"))
        && json_int(root, "uart", 1, 2, &uart) && json_int(root, "baud", 9600, 921600, &baud)
        && json_int(root, "tx", 0, 48, &tx) && json_int(root, "rx", 0, 48, &rx)
        && json_int(root, "rts", -1, 48, &rts) && json_int(root, "cts", -1, 48, &cts) && json_int(root, "pwrkey", -1, 48, &pwrkey)
        && json_text(root, "apn", c.apn, sizeof c.apn) && json_text(root, "user", c.user, sizeof c.user)
        && json_secret(root, "password", "clear_password", saved.password, c.password, sizeof c.password)
        && json_secret(root, "pin", "clear_pin", saved.pin, c.pin, sizeof c.pin);
    if (parsed) {
        c.enabled = cJSON_IsTrue(enabled); c.roaming = cJSON_IsTrue(roaming); c.data_ack = cJSON_IsTrue(ack);
        c.pwrkey_active_high = cJSON_IsTrue(high);
        c.mode = !strcmp(mode->valuestring, "primary") ? CELL_MODE_PRIMARY : CELL_MODE_FAILOVER;
        c.uart = (uint8_t)uart; c.baud = (uint32_t)baud;
        c.tx = (int8_t)tx; c.rx = (int8_t)rx; c.rts = (int8_t)rts; c.cts = (int8_t)cts; c.pwrkey = (int8_t)pwrkey;
    }
    cJSON_Delete(root);
    esp_err_t err = parsed ? cell_uplink_set_config(&c, why, sizeof why) : ESP_ERR_INVALID_ARG;
    memset(&c, 0, sizeof c);
    memset(&saved, 0, sizeof saved);
    memset(body, 0, sizeof body);   /* the request carried the secrets */
    cJSON *reply = cJSON_CreateObject();
    if (err != ESP_OK) {
        httpd_resp_set_status(req, err == ESP_ERR_INVALID_ARG ? "400 Bad Request" : "500 Internal Server Error");
        if (reply) {cJSON_AddBoolToObject(reply, "ok", false); cJSON_AddStringToObject(reply, "error", err == ESP_ERR_INVALID_ARG ? why : esp_err_to_name(err));}
    } else if (reply) {cJSON_AddBoolToObject(reply, "ok", true); cJSON_AddBoolToObject(reply, "restart_required", true);}
    return send_json(req, reply);
}

esp_err_t cell_uplink_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/cellular", .method = HTTP_GET, .handler = get_cellular},
        {.uri = "/api/cellular", .method = HTTP_POST, .handler = post_cellular}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
