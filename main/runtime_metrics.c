/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* One sampler for UI, MQTT and ntfy; no request-time task-list allocation. */
#include "runtime_metrics.h"
#include "control_validation.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static runtime_metrics_t s_metrics;
static int64_t s_sample_time;
static TaskHandle_t s_task;

static void sample_task(void *arg)
{
    (void)arg;
    configRUN_TIME_COUNTER_TYPE previous[configNUMBER_OF_CORES];
    for (int i = 0; i < configNUMBER_OF_CORES; ++i)
        previous[i] = ulTaskGetIdleRunTimeCounterForCore(i);
    int64_t last = esp_timer_get_time();
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        int64_t now = esp_timer_get_time();
        uint64_t elapsed = (uint64_t)(now - last);
        runtime_metrics_t result = {0};
        uint64_t idle_sum = 0;
        for (int i = 0; i < configNUMBER_OF_CORES; ++i) {
            configRUN_TIME_COUNTER_TYPE current = ulTaskGetIdleRunTimeCounterForCore(i);
            /* Modular subtraction per core handles 32-bit counter rollover. */
            configRUN_TIME_COUNTER_TYPE delta = current - previous[i];
            previous[i] = current;
            uint64_t idle = delta > elapsed ? elapsed : delta;
            idle_sum += idle;
            if (i < 2) result.core_pct[i] = control_cpu_pct(elapsed, idle);
        }
        result.valid = elapsed > 0 && elapsed < UINT32_MAX;
        result.load_pct = control_cpu_pct(elapsed * configNUMBER_OF_CORES, idle_sum);
        taskENTER_CRITICAL(&s_lock);
        s_metrics = result;
        s_sample_time = now;
        taskEXIT_CRITICAL(&s_lock);
        last = now;
    }
}

void runtime_metrics_init(void)
{
    if (!s_task && xTaskCreate(sample_task, "cpu_metrics", 2048, NULL, 1, &s_task) != pdPASS)
        ESP_LOGE("cpu_metrics", "Unable to start CPU sampler");
}

runtime_metrics_t runtime_metrics_get(void)
{
    taskENTER_CRITICAL(&s_lock);
    runtime_metrics_t result = s_metrics;
    int64_t sampled = s_sample_time;
    taskEXIT_CRITICAL(&s_lock);
    if (esp_timer_get_time() - sampled > 10000000) result.valid = false;
    return result;
}
