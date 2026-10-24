/* Optional cellular (GSM/LTE) data uplink through an external UART modem
 * (for example SIMCom SIM7600/A7670 or Quectel EC2x) with a SIM card.
 * AT commands bring the modem up (SIM PIN, registration, APN) and the data
 * call runs as PPP over the UART through the ESP-IDF PPP netif.
 * OFF by default: nothing dials until it is enabled, configured and the data
 * notice is acknowledged. It is the Internet uplink only (primary or
 * failover); LAN-side services stay on WiFi or Ethernet. Settings apply at
 * the next boot. Not physically qualified on any modem yet.
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"

enum {CELL_MODE_FAILOVER = 0, CELL_MODE_PRIMARY = 1};
enum {CELL_SIM_READY = 0, CELL_SIM_PIN = 1, CELL_SIM_PUK = 2, CELL_SIM_OTHER = 3};
enum {CELL_OFF, CELL_POWERING, CELL_SYNC, CELL_SIM, CELL_REGISTERING, CELL_DIALING,
      CELL_CONNECTED, CELL_BACKOFF, CELL_STOPPED};

typedef struct {
    uint8_t enabled, uart, mode, roaming, data_ack, pwrkey_active_high;
    int8_t tx, rx, rts, cts, pwrkey;      /* rts/cts/pwrkey: -1 not connected */
    uint32_t baud;
    char apn[64], user[32], password[64], pin[9];
} cell_config_t;

typedef struct {
    bool compiled, enabled_at_boot, task_running, has_ip, selected, restart_required;
    uint8_t state, registration;          /* registration: 3GPP stat, 0xff unknown */
    int16_t rssi_dbm;                     /* 0: unknown */
    uint32_t ip, connects;
    uint64_t bytes_in, bytes_out;
    char model[32], operator_name[32], error[80];
} cell_status_t;

/* Core (pure, host-tested). */
bool cell_config_valid(const cell_config_t *c, char *why, size_t why_size);
int cell_csq_to_dbm(int csq);                  /* 0..31 -> -113..-51 dBm, else 0 */
int cell_parse_csq(const char *response);      /* "+CSQ: n,m" -> n, -1 */
int cell_parse_reg(const char *response, const char *prefix);  /* stat or -1 */
int cell_parse_cpin(const char *response);     /* CELL_SIM_* */
bool cell_parse_cops(const char *response, char *name, size_t n);
bool cell_registered(int stat, bool roaming);  /* 1 home; 5 roaming only if allowed */
typedef struct {uint8_t streak;} cell_selector_t;
#define CELL_STABLE_SAMPLES 3
/* true: route Internet traffic over cellular. Failover takes it only while
 * the WiFi/Ethernet uplink is down; primary after a short stable window. */
bool cell_uplink_choose(cell_selector_t *s, uint8_t mode, bool other_ok, bool cell_ok);

/* Boot: after netif_hooks_init (the ACL hooks are a start condition). */
void cell_uplink_init(void);
/* Secrets (password, PIN) are never returned by the HTTP API. */
void cell_uplink_get_config(cell_config_t *out);
esp_err_t cell_uplink_set_config(const cell_config_t *c, char *why, size_t why_size);
void cell_uplink_get_status(cell_status_t *out);
/* TCP/IP context only (route supervisor): the cellular netif when it should
 * carry the Internet uplink instead of `current`, otherwise NULL. */
struct netif *cell_uplink_lwip_select(struct netif *current);
esp_err_t cell_uplink_register_http(httpd_handle_t server);
