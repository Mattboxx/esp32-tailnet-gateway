/* Opt-in GitHub release updates; no telemetry or credential upload. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "cJSON.h"

typedef struct {
    bool enabled, auto_install, beta_channel;
    int install_hour; /* -1 immediate, 0..23 local time */
} ota_remote_config_t;
typedef struct {
    ota_remote_config_t config;
    bool busy, checked, update_available;
    uint32_t last_check, asset_size;
    unsigned progress;
    char latest_version[32], status[96], release_url[192];
} ota_remote_state_t;

void ota_remote_init(void);
void ota_remote_get_state(ota_remote_state_t *out);
esp_err_t ota_remote_set_config(const ota_remote_config_t *config);
esp_err_t ota_remote_request(bool install);
/* Parser exposed to the real-C regression fixture, not to the network. */
bool ota_remote_select_release(const cJSON *releases, const char *running,
                               bool beta, uint32_t partition_size,
                               char tag[32], uint32_t *size, unsigned char digest[32]);
