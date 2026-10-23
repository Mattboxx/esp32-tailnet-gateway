/* Flash mapping/erase/verification must not run on the HTTPS worker's PSRAM
 * stack: ESP-IDF freezes caches and requires the current stack in internal RAM.
 * SPDX-License-Identifier: MIT */
#include "ota_flash.h"
#include <stdbool.h>
#include "esp_attr.h"
#include "esp_cpu.h"
#include "esp_memory_utils.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define FLASH_STACK_BYTES 4096
typedef enum { NEXT, BEGIN, WRITE, END, ABORT, SET_BOOT, RESTART } operation_t;
typedef struct {
    operation_t operation;
    const esp_partition_t *partition;
    const void *data;
    size_t size;
    esp_ota_handle_t handle;
    esp_err_t result;
} flash_job_t;

/* Reserve at link time, not when an update meets a fragmented runtime heap.
 * ESP-IDF's task stack depth is in bytes, unlike upstream FreeRTOS. */
static DRAM_ATTR StackType_t s_stack[FLASH_STACK_BYTES / sizeof(StackType_t)] __attribute__((aligned(16)));
static DRAM_ATTR StaticTask_t s_tcb;
static DRAM_ATTR StaticSemaphore_t s_mutex_storage, s_done_storage;
static DRAM_ATTR flash_job_t s_job;
static SemaphoreHandle_t s_mutex, s_done;
static TaskHandle_t s_task;

static void flash_worker(void *unused)
{
    (void)unused;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        s_job.result = ESP_ERR_INVALID_STATE;
        /* No fallback to the external caller stack if initialization/domain is
         * wrong. This also makes every failure acknowledge its borrowed data. */
        if (esp_ptr_in_dram((const void *)esp_cpu_get_sp())) {
            switch (s_job.operation) {
            case NEXT:
                s_job.partition = esp_ota_get_next_update_partition(NULL);
                s_job.result = s_job.partition ? ESP_OK : ESP_ERR_NOT_FOUND;
                break;
            case BEGIN:
                s_job.result = esp_ota_begin(s_job.partition, s_job.size, &s_job.handle);
                break;
            case WRITE:
                s_job.result = esp_ota_write(s_job.handle, s_job.data, s_job.size);
                break;
            case END: s_job.result = esp_ota_end(s_job.handle); break;
            case ABORT: s_job.result = esp_ota_abort(s_job.handle); break;
            case SET_BOOT: s_job.result = esp_ota_set_boot_partition(s_job.partition); break;
            case RESTART: esp_restart(); break;
            }
        }
        xSemaphoreGive(s_done);
    }
}

esp_err_t ota_flash_init(void)
{
    if (s_task) return ESP_OK;
    s_mutex = xSemaphoreCreateMutexStatic(&s_mutex_storage);
    s_done = xSemaphoreCreateBinaryStatic(&s_done_storage);
    if (!s_mutex || !s_done) return ESP_ERR_NO_MEM;
    s_task = xTaskCreateStatic(flash_worker, "ota_flash", FLASH_STACK_BYTES,
                             NULL, 4, s_stack, &s_tcb);
    return s_task ? ESP_OK : ESP_ERR_NO_MEM;
}

static esp_err_t execute(flash_job_t *job)
{
    if (!s_task || xTaskGetCurrentTaskHandle() == s_task) return ESP_ERR_INVALID_STATE;
    /* One mailbox, no allocated jobs or unbounded queue. Admission may time
     * out; an admitted operation cannot: the caller owns its buffer until ACK.
     * Never abandon an in-flight flash call or free its data on a timeout. */
    /* END consumes the SDK handle even on verification failure; ABORT must
     * finish before its owner releases the writer lock. Never skip either on
     * admission timeout and accidentally leak an active SDK transaction. */
    TickType_t admission = job->operation == END || job->operation == ABORT || job->operation == RESTART
                         ? portMAX_DELAY : pdMS_TO_TICKS(1000);
    if (xSemaphoreTake(s_mutex, admission) != pdTRUE) return ESP_ERR_TIMEOUT;
    s_job = *job;
    xTaskNotifyGive(s_task);
    while (xSemaphoreTake(s_done, portMAX_DELAY) != pdTRUE) { }
    *job = s_job;
    xSemaphoreGive(s_mutex);
    return job->result;
}

const esp_partition_t *ota_flash_next_partition(void)
{
    flash_job_t job = {.operation = NEXT};
    return execute(&job) == ESP_OK ? job.partition : NULL;
}

esp_err_t ota_flash_begin(const esp_partition_t *partition, size_t size, esp_ota_handle_t *handle)
{
    if (!partition || !handle) return ESP_ERR_INVALID_ARG;
    *handle = 0;
    flash_job_t job = {.operation = BEGIN, .partition = partition, .size = size};
    esp_err_t result = execute(&job);
    if (result == ESP_OK) *handle = job.handle;
    return result;
}

esp_err_t ota_flash_write(esp_ota_handle_t handle, const void *data, size_t size)
{
    if (!data || !size) return ESP_ERR_INVALID_ARG;
    flash_job_t job = {.operation = WRITE, .handle = handle, .data = data, .size = size};
    return execute(&job);
}

esp_err_t ota_flash_end(esp_ota_handle_t handle)
{
    flash_job_t job = {.operation = END, .handle = handle};
    return execute(&job);
}

esp_err_t ota_flash_abort(esp_ota_handle_t handle)
{
    flash_job_t job = {.operation = ABORT, .handle = handle};
    return execute(&job);
}

esp_err_t ota_flash_set_boot_partition(const esp_partition_t *partition)
{
    if (!partition) return ESP_ERR_INVALID_ARG;
    flash_job_t job = {.operation = SET_BOOT, .partition = partition};
    return execute(&job);
}

void ota_flash_restart(void)
{
    flash_job_t job = {.operation = RESTART};
    (void)execute(&job);
}
