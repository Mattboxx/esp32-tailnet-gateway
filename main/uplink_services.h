/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once

#include "esp_netif.h"

/* IPv4 readiness of a physical LAN or Internet uplink. */
static inline bool uplink_address(esp_netif_t *netif, esp_netif_ip_info_t *ip)
{
    return netif && esp_netif_is_netif_up(netif) &&
           esp_netif_get_ip_info(netif, ip) == ESP_OK && ip->ip.addr;
}

/* PPP is an Internet uplink. Keep LAN listeners on Ethernet/Wi-Fi. */
esp_netif_t *uplink_internet_netif(void);
esp_netif_t *uplink_local_netif(void);
static inline bool uplink_internet_ready(void)
{
    esp_netif_ip_info_t info = {0};
    return uplink_address(uplink_internet_netif(), &info);
}
void uplink_services_refresh(bool lost_link);
void uplink_services_schedule_refresh(void);
