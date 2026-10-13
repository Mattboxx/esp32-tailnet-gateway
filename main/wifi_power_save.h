#pragma once
#include <stdbool.h>
#include "esp_err.h"

/* Mattboxx default remains OFF (low latency), including upgrades. */
esp_err_t wifi_power_save_init(void);
bool wifi_power_save_configured(void);
bool wifi_power_save_runtime(bool *enabled);
esp_err_t wifi_power_save_set(bool enabled);
