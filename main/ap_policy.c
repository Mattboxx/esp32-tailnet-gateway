/* SPDX-License-Identifier: MIT */
#include "ap_policy.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_pending, s_shutdown, s_target;
static uint32_t s_generation;
static int64_t s_due;
static bool (*s_apply)(bool);
static bool s_initialized;
static TaskHandle_t s_worker;
static StaticTask_t s_tcb;
/* Internal, statically reserved: recovery can never fail to allocate an 8KB
 * contiguous stack after TLS has fragmented the runtime heap. */
static StackType_t s_stack[8192 / sizeof(StackType_t)] __attribute__((aligned(16)));

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
    if (s_worker) xTaskNotifyGive(s_worker);
}

static void worker(void *arg)
{
    (void)arg;
    for (;;) {
        taskENTER_CRITICAL(&s_lock);
        if (s_shutdown || !s_pending) {
            taskEXIT_CRITICAL(&s_lock);
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
            continue;
        }
        int64_t delay_us = s_due - esp_timer_get_time();
        if (delay_us > 0) {
            taskEXIT_CRITICAL(&s_lock);
            TickType_t ticks = pdMS_TO_TICKS((delay_us + 999) / 1000);
            ulTaskNotifyTake(pdTRUE, ticks ? ticks : 1);
            continue; /* a new request can shorten or replace the delay */
        }
        bool target = s_target;
        uint32_t generation = s_generation;
        s_pending = false;
        taskEXIT_CRITICAL(&s_lock);
        bool applied = s_apply(target);
        taskENTER_CRITICAL(&s_lock);
        if (!applied && !s_shutdown && generation == s_generation) {
            s_pending = true;
            s_due = esp_timer_get_time() + 1000000;
        }
        taskEXIT_CRITICAL(&s_lock);
    }
}

esp_err_t ap_policy_init(bool (*apply)(bool))
{
    if (!apply) return ESP_ERR_INVALID_ARG;
    if (s_initialized) return ESP_OK;
    s_apply = apply;
    /* Later-registered handlers run first: suppress recovery before the
     * WiFi shutdown handler raises STA/AP-down events during esp_restart. */
    esp_err_t err = esp_register_shutdown_handler(ap_policy_shutdown);
    if (err != ESP_OK) return err;
    s_worker = xTaskCreateStatic(worker, "ap_policy", 8192, NULL, 5, s_stack, &s_tcb);
    if (!s_worker) return ESP_ERR_NO_MEM;
    s_initialized = true;
    return ESP_OK;
}

void ap_policy_request_after(bool on, uint32_t delay_ms)
{
    int64_t due = esp_timer_get_time() + (int64_t)delay_ms * 1000;
    taskENTER_CRITICAL(&s_lock);
    if (!s_shutdown) {
        if (!(s_pending && s_target == on && s_due <= due)) {
            s_target = on;
            s_due = due;
            ++s_generation;
        }
        s_pending = true;
    }
    taskEXIT_CRITICAL(&s_lock);
    if (s_worker) xTaskNotifyGive(s_worker);
}

void ap_policy_request(bool on)
{
    ap_policy_request_after(on, on ? 100 : 1500);
}
