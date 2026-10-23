/* Persistent reaper for WithCaps tasks; see task_reaper.h.
 * SPDX-License-Identifier: MIT */
#include "task_reaper.h"

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/idf_additions.h"
#include "freertos/queue.h"

#define REAPER_QUEUE_LEN 8
#define REAPER_STACK     2560

static const char *TAG = "task_reaper";

static StaticQueue_t s_queue_storage;
static uint8_t s_queue_buffer[REAPER_QUEUE_LEN * sizeof(TaskHandle_t)];
static QueueHandle_t s_queue;
static TaskHandle_t s_reaper;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static unsigned s_pending, s_fallbacks;

static void reaper_task(void *arg)
{
    (void)arg;
    for (;;) {
        TaskHandle_t victim = NULL;
        if (xQueueReceive(s_queue, &victim, portMAX_DELAY) != pdTRUE || !victim) continue;
        /* Deleting another task suspends it, waits until it is no longer
         * running on the other core, deletes it and frees its TCB and stack.
         * No allocation and no abort on this path. */
        vTaskDeleteWithCaps(victim);
        taskENTER_CRITICAL(&s_lock);
        if (s_pending) s_pending--;
        taskEXIT_CRITICAL(&s_lock);
    }
}

esp_err_t task_reaper_init(void)
{
    taskENTER_CRITICAL(&s_lock);
    bool ready = s_reaper != NULL;
    taskEXIT_CRITICAL(&s_lock);
    if (ready) return ESP_OK;
    if (!s_queue) {
        s_queue = xQueueCreateStatic(REAPER_QUEUE_LEN, sizeof(TaskHandle_t),
                                     s_queue_buffer, &s_queue_storage);
        if (!s_queue) return ESP_ERR_NO_MEM;
    }
    TaskHandle_t created = NULL;
    /* Above ordinary workers so exits are reclaimed promptly. */
    BaseType_t ok = pdFAIL;
#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    ok = xTaskCreateWithCaps(reaper_task, "task_reaper", REAPER_STACK, NULL, 6,
                             &created, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
#endif
    if (ok != pdPASS) {
        /* Boot-time internal stack is acceptable: created once, never freed. */
        ok = xTaskCreate(reaper_task, "task_reaper", REAPER_STACK, NULL, 6, &created);
    }
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "reaper not started; WithCaps exits use the SDK path");
        return ESP_ERR_NO_MEM;
    }
    taskENTER_CRITICAL(&s_lock);
    s_reaper = created;
    taskEXIT_CRITICAL(&s_lock);
    return ESP_OK;
}

void task_reaper_self_delete(void)
{
    TaskHandle_t self = xTaskGetCurrentTaskHandle();
    taskENTER_CRITICAL(&s_lock);
    bool usable = s_reaper != NULL && self != s_reaper;
    if (usable) s_pending++;
    taskEXIT_CRITICAL(&s_lock);
    if (usable && xQueueSend(s_queue, &self, 0) == pdTRUE) {
        /* The reaper deletes this task while it is suspended (or before it
         * gets here if the reaper preempts first). */
        for (;;) vTaskSuspend(NULL);
    }
    taskENTER_CRITICAL(&s_lock);
    if (usable && s_pending) s_pending--;
    s_fallbacks++;
    taskEXIT_CRITICAL(&s_lock);
    vTaskDeleteWithCaps(NULL);
    for (;;) vTaskSuspend(NULL); /* not reached */
}

void task_reaper_delete(TaskHandle_t handle)
{
    if (handle == NULL || handle == xTaskGetCurrentTaskHandle()) task_reaper_self_delete();
    vTaskDeleteWithCaps(handle);
}

unsigned task_reaper_pending(void)
{
    taskENTER_CRITICAL(&s_lock);
    unsigned n = s_pending;
    taskEXIT_CRITICAL(&s_lock);
    return n;
}

unsigned task_reaper_fallbacks(void)
{
    taskENTER_CRITICAL(&s_lock);
    unsigned n = s_fallbacks;
    taskEXIT_CRITICAL(&s_lock);
    return n;
}
