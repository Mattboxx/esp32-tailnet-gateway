/* Local upload and shared OTA-writer exclusion. */
#pragma once

#include "esp_err.h"
#include "esp_http_server.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Stream an authenticated HTTP request into the inactive OTA partition and
 * mark it bootable. Outbound updates are handled by the opt-in remote module. */
esp_err_t ota_upload_handler(httpd_req_t *req);
bool ota_writer_try_acquire(void);
void ota_writer_release(void);
#ifdef __cplusplus
}
#endif
