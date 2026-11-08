/* Mattboxx Edition changes: Copyright (C) 2026 Mattboxx, GPL-3.0-only (LICENSE,
 * LICENSE-EXCEPTION.md). Ported from Csontikka/esp32-tailscale-subnet-router, whose
 * code keeps its MIT licence (licenses/upstream/, NOTICE.md). */
#pragma once
#include <stdbool.h>
#include "esp_err.h"

/* Mattboxx default remains OFF (low latency), including upgrades. */
esp_err_t wifi_power_save_init(void);
bool wifi_power_save_configured(void);
bool wifi_power_save_runtime(bool *enabled);
esp_err_t wifi_power_save_set(bool enabled);
