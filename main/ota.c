/* Local manual OTA upload. No release polling and no outbound HTTP. */
#include "ota.h"
#include "history.h"
#include "settings_snapshot.h"

#include <stdlib.h>
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define OTA_HTTP_RX_BUF 2048

static const char *TAG = "ota_local";
static portMUX_TYPE s_writer_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_writer_active;
bool ota_writer_try_acquire(void)
{
    portENTER_CRITICAL(&s_writer_lock);
    bool available = !s_writer_active;
    if (available) s_writer_active = true;
    portEXIT_CRITICAL(&s_writer_lock);
    return available;
}
void ota_writer_release(void)
{
    portENTER_CRITICAL(&s_writer_lock);
    s_writer_active = false;
    portEXIT_CRITICAL(&s_writer_lock);
}

esp_err_t ota_upload_handler(httpd_req_t *req)
{
    if (req->content_len <= 0) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "empty body");
        return ESP_FAIL;
    }
    const esp_partition_t *target = esp_ota_get_next_update_partition(NULL);
    if (!target) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            "no OTA partition available");
        return ESP_FAIL;
    }
    if ((size_t)req->content_len > target->size) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "image exceeds OTA partition");
        return ESP_FAIL;
    }
    if (!ota_writer_try_acquire()) {
        httpd_resp_set_status(req, "409 Conflict");
        httpd_resp_sendstr(req, "another firmware update is active");
        return ESP_FAIL;
    }
    settings_snapshot_before_update(SNAP_UPLOAD);   /* when switched on; never blocks the update */
    ESP_LOGI(TAG, "manual upload: %d bytes -> '%s' @0x%08lx",
             req->content_len, target->label, (unsigned long)target->address);

    esp_ota_handle_t handle = 0;
    /* The body size is known. Avoid erasing the unused tail of a large slot
     * while the browser is blocked behind the socket's send window. */
    esp_err_t err = esp_ota_begin(target, (size_t)req->content_len, &handle);
    if (err != ESP_OK) {
        ota_writer_release();
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            esp_err_to_name(err));
        return ESP_FAIL;
    }
    char *buffer = malloc(OTA_HTTP_RX_BUF);
    if (!buffer) {
        if (esp_ota_abort(handle) == ESP_OK) ota_writer_release();
        else ESP_LOGE(TAG, "OTA abort failed after allocation failure; restart before retrying");
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }
    int remaining = req->content_len;
    int64_t now = esp_timer_get_time();
    int64_t deadline = now + 600LL * 1000000;
    int64_t idle_deadline = now + 30LL * 1000000;
    bool paused = false, timed_out = false;
    const char *failure = "recv failed";
    while (remaining > 0) {
        now = esp_timer_get_time();
        if (now >= deadline || now >= idle_deadline) {
            timed_out = true;
            failure = now >= deadline ? "upload total time limit exceeded" :
                                       "upload stalled: no data for 30 seconds";
            ESP_LOGE(TAG, "%s after %d/%d bytes", failure,
                     req->content_len - remaining, req->content_len);
            goto upload_failed;
        }
        int wanted = remaining < OTA_HTTP_RX_BUF ? remaining : OTA_HTTP_RX_BUF;
        int received = httpd_req_recv(req, buffer, wanted);
        if (received == HTTPD_SOCK_ERR_TIMEOUT) {
            if (!paused) ESP_LOGW(TAG, "upload paused at %d/%d bytes; bounded receive retry",
                                  req->content_len - remaining, req->content_len);
            paused = true;
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (received <= 0) {
            ESP_LOGE(TAG, "upload receive failed (rc=%d) after %d/%d bytes",
                     received, req->content_len - remaining, req->content_len);
            failure = "upload connection ended before all bytes arrived";
            goto upload_failed;
        }
        now = esp_timer_get_time();
        if (now >= deadline) {
            timed_out = true; failure = "upload total time limit exceeded";
            goto upload_failed;
        }
        idle_deadline = now + 30LL * 1000000;
        paused = false;
        err = esp_ota_write(handle, buffer, received);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "upload flash write failed after %d/%d bytes: %s",
                     req->content_len - remaining, req->content_len, esp_err_to_name(err));
            failure = esp_err_to_name(err);
            goto upload_failed;
        }
        remaining -= received;
    }
    free(buffer);
    err = esp_ota_end(handle);
    if (err == ESP_OK) err = esp_ota_set_boot_partition(target);
    if (err != ESP_OK) {
        ota_writer_release();
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            esp_err_to_name(err));
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "manual upload complete; next boot partition is '%s'", target->label);
    history_event(HIST_EV_UPDATE, HIST_INFO, "Firmware uploaded from the browser (%d bytes); restart pending", req->content_len);
    httpd_resp_set_type(req, "application/json");
    (void)httpd_resp_sendstr(req, "{\"ok\":true,\"reboot_required\":true}");
    /* Boot partition is already committed: reboot even if the client left.
     * Keep writer ownership until reboot so no second OTA can overwrite it. */
    return ESP_OK;

upload_failed:
    free(buffer);
    if (esp_ota_abort(handle) == ESP_OK) ota_writer_release();
    else {
        /* An unacknowledged abort must not admit another writer over the
         * same SDK transaction. Preserve the running image; never reboot here. */
        failure = "OTA cleanup failed; restart before retrying";
        timed_out = false;
        ESP_LOGE(TAG, "%s", failure);
    }
    httpd_resp_send_err(req, timed_out ? HTTPD_408_REQ_TIMEOUT :
                                       HTTPD_500_INTERNAL_SERVER_ERROR, failure);
    return ESP_FAIL;
}
