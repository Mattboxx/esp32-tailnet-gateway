/* WiFi modem-sleep policy, adapted from upstream v0.1.33.
 * Keep the fork's low-latency default and report driver/save failures honestly.
 * SPDX-License-Identifier: MIT
 */
#include "wifi_power_save.h"
#include "nvs_params.h"
#include "esp_wifi.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static StaticSemaphore_t s_storage;
static SemaphoreHandle_t s_lock;

bool wifi_power_save_configured(void)
{
    uint8_t saved = 0;
    (void)nvs_param_get_u8("wifi_ps", &saved);
    return saved != 0;
}

bool wifi_power_save_runtime(bool *enabled)
{
    wifi_ps_type_t mode;
    if (!enabled || esp_wifi_get_ps(&mode) != ESP_OK) return false;
    *enabled = mode != WIFI_PS_NONE;
    return true;
}

esp_err_t wifi_power_save_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_storage);
    if (!s_lock) return ESP_ERR_NO_MEM;
    return esp_wifi_set_ps(wifi_power_save_configured() ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE);
}

esp_err_t wifi_power_save_set(bool enabled)
{
    if (!s_lock) return ESP_ERR_INVALID_STATE;
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) return ESP_ERR_TIMEOUT;
    wifi_ps_type_t previous;
    esp_err_t err = esp_wifi_get_ps(&previous);
    if (err == ESP_OK) err = esp_wifi_set_ps(enabled ? WIFI_PS_MIN_MODEM : WIFI_PS_NONE);
    if (err == ESP_OK) {
        err = nvs_param_set_u8("wifi_ps", enabled ? 1 : 0);
        if (err != ESP_OK && esp_wifi_set_ps(previous) != ESP_OK)
            ESP_LOGE("wifi_ps", "Failed to restore modem-sleep state after save failure");
    }
    xSemaphoreGive(s_lock);
    return err;
}
