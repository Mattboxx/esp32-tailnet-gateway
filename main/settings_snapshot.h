/* Settings copies: raw copies of the NVS partition in three slots of the
 * 3.x storage partition (see storage_store.h).
 *
 * A copy is taken on demand and, when switched on, before each firmware
 * update. A restore is requested at run time and applied at the next boot,
 * before NVS is opened: the request survives a power cut and is retried at
 * most SNAP_RESTORE_ATTEMPTS times. Copies hold the same secrets as NVS
 * (WiFi password, Tailscale keys, admin password) with the same protection:
 * they are never downloadable, a restore or delete needs the admin password
 * and a factory reset erases them. Restoring also brings back the admin
 * password of that moment.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "storage_store.h"

#define SNAP_MAGIC 0x31504E53u          /* "SNP1" */
#define SNAP_CONTROL_MAGIC 0x31545352u  /* "RST1" */
#define SNAP_NVS_MAX 0x10000u
#define SNAP_RESTORE_ATTEMPTS 3

enum {SNAP_MANUAL = 1, SNAP_UPDATE, SNAP_UPLOAD, SNAP_BEFORE_RESTORE};
typedef enum {SNAP_BOOT_NONE, SNAP_BOOT_RESTORED, SNAP_BOOT_INVALID, SNAP_BOOT_FAILED, SNAP_BOOT_GAVE_UP} snap_boot_t;

typedef struct {
    uint32_t magic, version, seq, wall, size, data_crc;
    uint8_t reason, pad[3];
    char firmware[32];
    uint32_t header_crc;
} snap_header_t;

/* Core (host-tested): `storage` is the storage partition, `nvs` the NVS one. */
bool snap_read_header(const store_flash_t *storage, unsigned slot, snap_header_t *out);
int snap_take(const store_flash_t *storage, const store_flash_t *nvs, uint32_t nvs_size, uint8_t reason,
              const char *firmware, uint32_t wall, int exclude_slot, uint8_t *buffer);   /* slot, or -1 */
esp_err_t snap_request_restore(const store_flash_t *storage, unsigned slot, uint8_t *buffer);
bool snap_restore_pending(const store_flash_t *storage);
esp_err_t snap_cancel_restore(const store_flash_t *storage);
snap_boot_t snap_boot_restore(const store_flash_t *storage, const store_flash_t *nvs, uint32_t nvs_size,
                              uint8_t *buffer, unsigned *slot);
esp_err_t snap_delete(const store_flash_t *storage, unsigned slot);

/* Firmware. */
void settings_snapshot_boot(void);       /* app_main, before nvs_flash_init */
void settings_snapshot_log_boot(void);   /* after history_init: report a restore */
/* Takes a copy on an internal-RAM stack; any caller. Returns the slot or -1. */
int settings_snapshot_take(uint8_t reason);
/* Before an update, when switched on; never blocks the update on failure. */
void settings_snapshot_before_update(uint8_t reason);
#include "esp_http_server.h"
esp_err_t settings_snapshot_register_http(httpd_handle_t server);
