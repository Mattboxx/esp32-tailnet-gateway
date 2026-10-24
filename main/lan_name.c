/* Per-board LAN name and mDNS responder (lwIP apps/mdns, uplink only).
 * SPDX-License-Identifier: MIT */
#include "lan_name.h"

#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "lwip/apps/mdns.h"
#include "lwip/tcpip.h"
#include "sdkconfig.h"
#include "first_boot.h"
#include "nvs_params.h"

/* The responder keeps its state in a netif client-data slot. */
#if CONFIG_LWIP_NUM_NETIF_CLIENT_DATA < 1
#error "Set CONFIG_LWIP_NUM_NETIF_CLIENT_DATA=1 in the active sdkconfig (see sdkconfig.defaults)"
#endif

static const char *TAG = "lan_name";

void lan_name_from(const char *configured, const uint8_t ap_mac[6], char *out, size_t cap)
{
    size_t n = configured ? strlen(configured) : 0;
    bool ok = n > 0 && n <= LAN_NAME_MAX && n < cap
        && configured[0] != '-' && configured[n - 1] != '-';
    for (size_t i = 0; ok && i < n; i++) {
        unsigned char c = (unsigned char)configured[i];
        ok = isalnum(c) || c == '-';
    }
    if (ok) {
        for (size_t i = 0; i < n; i++) out[i] = (char)tolower((unsigned char)configured[i]);
        out[n] = '\0';
        return;
    }
    snprintf(out, cap, "esp32-tailnet-%02x%02x", ap_mac[4], ap_mac[5]);
}

void lan_name_get(char *out, size_t cap)
{
    uint8_t mac[6] = {0};
    (void)esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    char *saved = nvs_param_get_str("hostname");
    lan_name_from(saved, mac, out, cap);
    free(saved);
}

static char s_name[LAN_NAME_MAX + 1];
static bool s_added;

void lan_name_default(char *out, size_t cap)
{
    uint8_t mac[6] = {0};
    (void)esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    lan_name_from(NULL, mac, out, cap);
}

void lan_name_active(char *out, size_t cap)
{
    /* s_name is written once, before the responder starts, and never again. */
    if (s_name[0] && cap > 0) snprintf(out, cap, "%s", s_name);
    else lan_name_get(out, cap);
}

static void name_result(struct netif *netif, u8_t result, s8_t slot)
{
    (void)netif; (void)slot;
    if (result == MDNS_PROBING_CONFLICT)
        ESP_LOGW(TAG, "%s.local is already used on this network; set a different hostname", s_name);
}

/* Runs in the TCPIP thread (core locking is off). */
static void mdns_on_uplink(void *arg)
{
    (void)arg;
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    struct netif *nif = sta ? esp_netif_get_netif_impl(sta) : NULL;
    if (!nif) return;
    if (s_added) {
        mdns_resp_restart(nif);     /* new address: probe and announce again */
        return;
    }
    mdns_resp_init();
    mdns_resp_register_name_result_cb(name_result);
    if (mdns_resp_add_netif(nif, s_name) == ERR_OK) {
        s_added = true;
        ESP_LOGW(TAG, "home network name: http://%s.local/", s_name);
    } else {
        ESP_LOGW(TAG, "mDNS responder not started");
    }
}

void lan_name_uplink_up(void)
{
    if (first_boot_active()) return;
    if (!s_name[0]) lan_name_get(s_name, sizeof s_name);
    if (tcpip_callback(mdns_on_uplink, NULL) != ERR_OK) ESP_LOGW(TAG, "mDNS start deferred: TCPIP queue full");
}
