/* Synchronous OTA work on the existing internal-stack admin server.
 * SPDX-License-Identifier: MIT */
#pragma once
#include "esp_ota_ops.h"
#include "esp_http_server.h"

/* Initialize once during boot, before optional network workers start. */
esp_err_t ota_flash_init(void);
/* Bind once to the lifetime-long internal-stack admin server. It must not be
 * stopped/replaced while the updater runs. Web port changes require reboot. */
esp_err_t ota_flash_bind_httpd(httpd_handle_t server);
const esp_partition_t *ota_flash_next_partition(void);
esp_err_t ota_flash_begin(const esp_partition_t *partition, size_t size, esp_ota_handle_t *handle);
esp_err_t ota_flash_write(esp_ota_handle_t handle, const void *data, size_t size);
/* Clear the handle only after SDK end actually consumed it. */
esp_err_t ota_flash_end(esp_ota_handle_t *handle);
esp_err_t ota_flash_abort(esp_ota_handle_t handle);
esp_err_t ota_flash_set_boot_partition(const esp_partition_t *partition);
void ota_flash_restart(void);
