/* Local manual OTA upload. No release polling and no outbound HTTP. */
#include "ota.h"
#include "history.h"
#include "settings_snapshot.h"

#include <stdlib.h>
#include "esp_log.h"
#include "esp_ota_ops.h"
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
    esp_err_t err = esp_ota_begin(target, OTA_SIZE_UNKNOWN, &handle);
    if (err != ESP_OK) {
        ota_writer_release();
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            esp_err_to_name(err));
        return ESP_FAIL;
    }
    char *buffer = malloc(OTA_HTTP_RX_BUF);
    if (!buffer) {
        esp_ota_abort(handle);
        ota_writer_release();
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }
    int remaining = req->content_len;
    while (remaining > 0) {
        int wanted = remaining < OTA_HTTP_RX_BUF ? remaining : OTA_HTTP_RX_BUF;
        int received = httpd_req_recv(req, buffer, wanted);
        if (received <= 0) {
            free(buffer);
            esp_ota_abort(handle);
            ota_writer_release();
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "recv failed");
            return ESP_FAIL;
        }
        err = esp_ota_write(handle, buffer, received);
        if (err != ESP_OK) {
            free(buffer);
            esp_ota_abort(handle);
            ota_writer_release();
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                                esp_err_to_name(err));
            return ESP_FAIL;
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
}
