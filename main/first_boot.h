/* First-boot setup over the device's own access point (captive portal).
 * See first_boot_core.h for the pairing and confidentiality design.
 * SPDX-License-Identifier: MIT */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { FB_WIFI_IDLE = 0, FB_WIFI_TESTING, FB_WIFI_OK, FB_WIFI_FAILED } fb_wifi_state_t;

/* Decide once per boot, after NVS, the Wi-Fi table and the tailnet settings
 * are loaded and before the access point starts. */
void first_boot_init(void);
bool first_boot_active(void);
/* "Tailnet-Gateway-Setup-XXXX" (setup) and "Tailnet-Gateway-XXXX" (proposed
 * protected access point after setup); XXXX from the AP MAC. */
void first_boot_setup_ssid(char *out, size_t cap);
void first_boot_default_ssid(char *out, size_t cap);
/* After the AP is up: captive DNS, BOOT-button watcher, serial setup code. */
void first_boot_start(void);
esp_err_t first_boot_register_http(httpd_handle_t server);
/* Redirect unknown paths to the setup page while setup is active (404 hook);
 * returns ESP_FAIL after sending a normal 404 otherwise. */
esp_err_t first_boot_not_found(httpd_req_t *req, httpd_err_code_t err);
/* Setup-AP isolation for the AP input hook; always true outside setup. */
bool first_boot_ap_frame_allowed(const uint8_t *frame, size_t len);

/* Implemented in main.c: trial association used by the setup wizard. */
esp_err_t wifi_setup_test_start(const char *ssid, const char *password);
void wifi_setup_test_get(fb_wifi_state_t *state, uint32_t *ip_nbo, uint32_t *mask_nbo, int *reason);

#ifdef __cplusplus
}
#endif
