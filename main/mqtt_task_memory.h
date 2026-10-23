/* Project-scoped allocation adapter for the pinned ESP-IDF esp-mqtt component.
 * No SDK files are modified. Include before that component's source only.
 * SPDX-License-Identifier: MIT */
#pragma once
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "esp_heap_caps.h"

#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
/* The SDK still allocates TCBs internally. Do not consume a 6 KiB internal
 * stack at first runtime enable; keep the configured stack size unchanged.
 * The reviewed SDK component deletes only its own task, so the allocator and
 * deleter must be switched together, including the core-pinned build path. */
/* Self-deletion goes through the project reaper: the SDK's own self-delete
 * allocates an internal clean-up stack at exit and aborts if it cannot. */
void task_reaper_delete(TaskHandle_t handle);
#undef xTaskCreate
#undef xTaskCreatePinnedToCore
#undef vTaskDelete
#define xTaskCreate(fn, name, size, arg, priority, handle) \
    xTaskCreateWithCaps(fn, name, size, arg, priority, handle, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
#define xTaskCreatePinnedToCore(fn, name, size, arg, priority, handle, core) \
    xTaskCreatePinnedToCoreWithCaps(fn, name, size, arg, priority, handle, core, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
#define vTaskDelete(handle) task_reaper_delete(handle)
#endif
