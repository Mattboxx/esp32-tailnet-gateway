/* Deferred deletion for tasks created with xTaskCreate*WithCaps().
 *
 * The SDK's vTaskDeleteWithCaps(NULL) (a task deleting itself) creates a
 * temporary clean-up task with an internal-RAM stack at that moment and
 * calls abort() if that allocation fails. On a fragmented internal heap that
 * turns an ordinary worker exit into a device reset. These helpers hand the
 * exiting task to one persistent reaper created at boot instead, so a worker
 * exit needs no new allocation. Without the reaper they fall back to the SDK.
 * SPDX-License-Identifier: MIT */
#pragma once

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Create the reaper and its static queue once, early at boot. Idempotent. */
esp_err_t task_reaper_init(void);

/* Delete the calling WithCaps task; never returns. */
void task_reaper_self_delete(void) __attribute__((noreturn));

/* Drop-in for vTaskDeleteWithCaps(handle): NULL or the caller self-deletes
 * through the reaper, another task is deleted directly (no allocation). */
void task_reaper_delete(TaskHandle_t handle);

/* Tasks handed over but not yet deleted, and fallbacks to the SDK path. */
unsigned task_reaper_pending(void);
unsigned task_reaper_fallbacks(void);

#ifdef __cplusplus
}
#endif
