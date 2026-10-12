/* SPDX-License-Identifier: MIT */
#include "ap_policy.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_pending, s_active, s_shutdown, s_target;
static uint32_t s_generation;
static int64_t s_due;
static bool (*s_apply)(bool);
static bool s_initialized;
static const char *TAG = "ap_policy";

bool ap_policy_is_shutdown(void)
{
    taskENTER_CRITICAL(&s_lock);
    bool shutdown = s_shutdown;
    taskEXIT_CRITICAL(&s_lock);
    return shutdown;
}

void ap_policy_shutdown(void)
{
    taskENTER_CRITICAL(&s_lock);
    s_shutdown = true;
    s_pending = false;
    taskEXIT_CRITICAL(&s_lock);
}

static void worker(void *arg)
{
    (void)arg;
    taskENTER_CRITICAL(&s_lock);
    bool apply = !s_shutdown && s_pending && esp_timer_get_time() >= s_due;
    bool target = s_target;
    uint32_t generation = s_generation;
    if (apply) {
        s_pending = false;
    }
    taskEXIT_CRITICAL(&s_lock);
    bool applied = !apply || s_apply(target);
    taskENTER_CRITICAL(&s_lock);
    if (!applied && !s_shutdown && generation == s_generation) {
        s_pending = true;
        s_due = esp_timer_get_time() + 1000000;
    }
    s_active = false;
    taskEXIT_CRITICAL(&s_lock);
    vTaskDelete(NULL);
}

static void try_start(void)
{
    taskENTER_CRITICAL(&s_lock);
    bool start = s_apply && s_pending && !s_active && !s_shutdown && esp_timer_get_time() >= s_due;
    if (start) s_active = true;
    uint32_t generation = s_generation;
    taskEXIT_CRITICAL(&s_lock);
    if (!start) return;
    /* WiFi mode changes stay on the original roomy stack, never on the
     * event/timer task. One worker handles all pending generations. */
    size_t free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    size_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    /* Total free RAM is not enough: the stack needs one contiguous block,
     * plus room for the TCB and concurrent network allocations. */
    if (free < 10240 || largest < 9216 ||
        xTaskCreate(worker, "ap_policy", 8192, NULL, 5, NULL) != pdPASS) {
        taskENTER_CRITICAL(&s_lock);
        s_active = false;
        if (generation == s_generation) s_due = esp_timer_get_time() + 1000000;
        taskEXIT_CRITICAL(&s_lock);
        ESP_LOGW(TAG, "Worker allocation deferred; retry pending (free=%u largest=%u)",
                 (unsigned)free, (unsigned)largest);
    }
}

void ap_policy_poll(void)
{
    try_start();
}

esp_err_t ap_policy_init(bool (*apply)(bool))
{
    if (!apply) return ESP_ERR_INVALID_ARG;
    if (s_initialized) return ESP_OK;
    s_apply = apply;
    /* Later-registered handlers run first: suppress recovery before the
     * WiFi shutdown handler raises STA/AP-down events during esp_restart. */
    esp_err_t err = esp_register_shutdown_handler(ap_policy_shutdown);
    if (err == ESP_OK) s_initialized = true;
    return err;
}

void ap_policy_request(bool on)
{
    int64_t due = esp_timer_get_time() + (on ? 100000 : 1500000);
    taskENTER_CRITICAL(&s_lock);
    if (!s_shutdown) {
        s_target = on;
        s_due = due;
        ++s_generation;
        s_pending = true;
    }
    taskEXIT_CRITICAL(&s_lock);
    try_start();
}
