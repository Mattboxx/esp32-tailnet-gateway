/* Flash mapping/erase/verification must not run on the HTTPS worker's PSRAM
 * stack: ESP-IDF freezes caches and requires the current stack in internal RAM.
 * SPDX-License-Identifier: MIT */
#include "ota_flash.h"
#include <stdbool.h>
#include <stdint.h>
#include "esp_attr.h"
#include "esp_cpu.h"
#include "esp_memory_utils.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

typedef enum { NEXT, BEGIN, WRITE, END, ABORT, SET_BOOT, RESTART } operation_t;
typedef struct {
    operation_t operation;
    const esp_partition_t *partition;
    const void *data;
    size_t size;
    esp_ota_handle_t handle;
    esp_err_t result;
    bool completed;
} flash_job_t;

/* Reuse the permanent admin server's 12 KiB internal stack, as local uploads
 * already do. Reserving a separate stack can prevent WireGuard from starting.
 * Only SDK flash work is dispatched: TLS/downloads never block this server. */
static DRAM_ATTR StaticSemaphore_t s_mutex_storage, s_done_storage;
static DRAM_ATTR flash_job_t s_job;
static SemaphoreHandle_t s_mutex, s_done;
static httpd_handle_t s_server;
static TaskHandle_t s_httpd_task;

/* httpd_queue_work() delivers a loopback datagram to the server's control
 * socket. lwIP drops it silently when the receive buffer cannot be allocated
 * (low internal RAM) or the socket mailbox is full, although the send already
 * succeeded. The server therefore claims a job before running it; a job still
 * unclaimed after START_WAIT_MS is withdrawn and sent once more, then reported
 * as a timeout. A claimed job is always awaited: flash work and its borrowed
 * buffer cannot be abandoned. A late delivery finds nothing to claim. */
#ifndef START_WAIT_MS
#define START_WAIT_MS 15000
#endif
#define DELIVERIES 2
enum { JOB_IDLE, JOB_QUEUED, JOB_RUNNING };
static uint32_t s_state;

static bool job_transition(uint32_t from, uint32_t to)
{
    return __atomic_compare_exchange_n(&s_state, &from, to, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
}

static void identify_httpd(void *unused)
{
    (void)unused;
    __atomic_store_n(&s_httpd_task, xTaskGetCurrentTaskHandle(), __ATOMIC_RELEASE);
}

static void flash_work(void *unused)
{
    (void)unused;
    if (!job_transition(JOB_QUEUED, JOB_RUNNING)) return;   /* withdrawn or duplicate delivery */
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
            s_job.completed = true;
            break;
        case WRITE:
            s_job.result = esp_ota_write(s_job.handle, s_job.data, s_job.size);
            break;
        case END:
            s_job.result = esp_ota_end(s_job.handle);
            s_job.completed = true;
            break;
        case ABORT: s_job.result = esp_ota_abort(s_job.handle); break;
        case SET_BOOT: s_job.result = esp_ota_set_boot_partition(s_job.partition); break;
        case RESTART: esp_restart(); break;
        }
    }
    xSemaphoreGive(s_done);
}

esp_err_t ota_flash_init(void)
{
    if (s_mutex && s_done) return ESP_OK;
    s_mutex = xSemaphoreCreateMutexStatic(&s_mutex_storage);
    s_done = xSemaphoreCreateBinaryStatic(&s_done_storage);
    if (!s_mutex || !s_done) return ESP_ERR_NO_MEM;
    return ESP_OK;
}

esp_err_t ota_flash_bind_httpd(httpd_handle_t server)
{
    if (!server) return ESP_ERR_INVALID_ARG;
    if (!s_mutex || !s_done) return ESP_ERR_INVALID_STATE;
    /* The web server is started once and never stopped at runtime. Refuse
     * replacement rather than invalidating an already queued callback. */
    httpd_handle_t expected = NULL;
    if (!__atomic_compare_exchange_n(&s_server, &expected, server, false,
                                     __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return expected == server ? ESP_OK : ESP_ERR_INVALID_STATE;
    /* Learn the server's identity before accepting requests. An early call
     * from the HTTP thread then fails instead of waiting on its own queue. */
    esp_err_t result = httpd_queue_work(server, identify_httpd, NULL);
    if (result != ESP_OK) __atomic_store_n(&s_server, NULL, __ATOMIC_RELEASE);
    return result;
}

static esp_err_t execute(flash_job_t *job)
{
    httpd_handle_t server = __atomic_load_n(&s_server, __ATOMIC_ACQUIRE);
    TaskHandle_t owner = __atomic_load_n(&s_httpd_task, __ATOMIC_ACQUIRE);
    if (!server || !owner || xTaskGetCurrentTaskHandle() == owner)
        return ESP_ERR_INVALID_STATE;
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
    esp_err_t result = ESP_ERR_TIMEOUT;
    bool ran = false;
    for (int delivery = 0; delivery < DELIVERIES && !ran; delivery++) {
        __atomic_store_n(&s_state, JOB_QUEUED, __ATOMIC_RELEASE);
        esp_err_t queued = httpd_queue_work(server, flash_work, NULL);
        if (queued == ESP_OK && xSemaphoreTake(s_done, pdMS_TO_TICKS(START_WAIT_MS)) == pdTRUE) {
            ran = true;
        } else if (!job_transition(JOB_QUEUED, JOB_IDLE)) {
            /* An earlier, delayed delivery claimed it: let the flash work end. */
            while (xSemaphoreTake(s_done, portMAX_DELAY) != pdTRUE) { }
            ran = true;
        } else if (queued != ESP_OK) {
            result = queued;
            break;
        }
    }
    if (ran) {
        *job = s_job;
        result = job->result;
    }
    __atomic_store_n(&s_state, JOB_IDLE, __ATOMIC_RELEASE);
    xSemaphoreGive(s_mutex);
    return result;
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
    /* The SDK can publish a handle before failing its erase. Preserve it for
     * abort even on that error, but never invent one for a rejected dispatch. */
    if (job.completed) *handle = job.handle;
    return result;
}

esp_err_t ota_flash_write(esp_ota_handle_t handle, const void *data, size_t size)
{
    if (!data || !size) return ESP_ERR_INVALID_ARG;
    flash_job_t job = {.operation = WRITE, .handle = handle, .data = data, .size = size};
    return execute(&job);
}

esp_err_t ota_flash_end(esp_ota_handle_t *handle)
{
    if (!handle) return ESP_ERR_INVALID_ARG;
    flash_job_t job = {.operation = END, .handle = *handle};
    esp_err_t result = execute(&job);
    if (job.completed) *handle = 0;
    return result;
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
