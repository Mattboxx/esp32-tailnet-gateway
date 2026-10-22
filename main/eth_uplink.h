/* Conditional SPI Ethernet uplink (W5500) for explicitly wired ESP32-S3 boards.
 * OFF by default: a WiFi-only board never touches SPI/GPIO and keeps the STA
 * route path unchanged. Pins and IP settings apply at the next boot. This is
 * not a claim that any ESP32-S3 has Ethernet, and it is not physically
 * qualified. Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"

enum {ETH_CHIP_W5500 = 1};
enum {ETH_PREF_WIFI_FIRST = 0, ETH_PREF_ETHERNET_FIRST = 1};
enum {ETH_CHOICE_LEGACY = 0, ETH_CHOICE_STA = 1, ETH_CHOICE_ETH = 2};

typedef struct {
    uint8_t enabled, chip, spi_host, spi_mhz, ip_static, preference;
    int8_t sclk, mosi, miso, cs, intr, rst;  /* -1: not connected (intr/rst only) */
    uint32_t ip, mask, gw, dns;              /* network byte order, static mode */
} eth_config_t;

typedef struct {
    bool compiled, enabled_at_boot, driver_started, link_up, has_ip, selected, restart_required;
    uint32_t ip, mask, gw;                   /* network byte order */
    uint32_t link_changes;
    char error[64];
} eth_status_t;

/* Uplink selection with a short stability window before moving to Ethernet;
 * losing the Ethernet link falls back at once. */
typedef struct {uint8_t eth_streak;} eth_selector_t;
#define ETH_STABLE_SAMPLES 3

bool eth_config_valid(const eth_config_t *c, char *why, size_t why_size);
int eth_uplink_choose(eth_selector_t *s, bool enabled, uint8_t preference, bool sta_ok, bool eth_ok);

/* Boot: prepare (before netif_hooks_init), then start (after it). */
void eth_uplink_init(void);
void eth_uplink_start(void);
void eth_uplink_get_config(eth_config_t *out);
esp_err_t eth_uplink_set_config(const eth_config_t *c, char *why, size_t why_size);
void eth_uplink_get_status(eth_status_t *out);
/* TCP/IP context only (route supervisor). NULL: Ethernet disabled, keep the
 * legacy STA default; otherwise the lwIP netif to use as uplink. */
struct netif *eth_uplink_lwip_select(struct netif *sta);
esp_err_t eth_uplink_register_http(httpd_handle_t server);
