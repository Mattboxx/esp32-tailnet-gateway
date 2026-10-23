/* Per-board name on the home network: DHCP hostname and mDNS
 * "<name>.local" on the Wi-Fi uplink, so a setup page can point to one
 * gateway even when several run the same firmware on one LAN.
 * SPDX-License-Identifier: MIT */
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LAN_NAME_MAX 32   /* characters, without ".local" */

/* A configured hostname that is a valid DNS label (letters, digits and
 * '-', 1..LAN_NAME_MAX, no leading or trailing '-') is used lowercased;
 * otherwise "esp32-tailnet-xxxx" from the last two AP MAC bytes, the same
 * suffix as the board's setup and default access point names. */
void lan_name_from(const char *configured, const uint8_t ap_mac[6], char *out, size_t cap);
/* This board's name, from the saved "hostname" and its MAC. */
void lan_name_get(char *out, size_t cap);
/* The uplink has an address: start the mDNS responder or announce the new
 * address. Does nothing while first-boot setup is active. */
void lan_name_uplink_up(void);

#ifdef __cplusplus
}
#endif
