/* Opt-in layered evidence, not a connectivity guarantee. SPDX-License-Identifier: MIT */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "cJSON.h"
typedef struct {
    uint8_t enabled,notify,failure_threshold,reserved;
    uint16_t interval_s,gateway_port,internet_port,tailnet_port;
    char dns_name[96],internet_ip[16],tailnet_target[96];
} health_config_t;
void health_monitor_init(void);
bool health_monitor_enabled(void);
esp_err_t health_monitor_set(const health_config_t *config);
esp_err_t health_monitor_set_enabled(bool enabled);
/* Single optional ops worker only; no new task, timer, socket queue or reboot. */
void health_monitor_poll(void);
/* Detailed includes user targets; sanitized never includes those identifiers. */
cJSON *health_monitor_snapshot(bool detailed);
