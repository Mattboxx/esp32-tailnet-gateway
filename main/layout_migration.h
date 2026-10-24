/* 2.x -> 3.x flash-layout migration over the network (the 2.1 bridge).
 *
 * 2.x gateways have a 4 MB layout (two 1920 KiB app slots); 3.x needs the
 * 8 MB layout of partitions.csv. The 2.1 bridge release installs through
 * the 2.x updater, then on the owner's request downloads the 3.x bootloader,
 * partition table and image from GitHub, verifies their SHA-256 digests and
 * contents, writes the image into the new ota_1 slot (outside its own code),
 * and finally rewrites bootloader, partition table and otadata. NVS keeps
 * its offset and size, so every setting survives. The bridge sits at
 * 0x20000, ota_0 in both layouts: if 3.x does not confirm itself, rollback
 * returns to the bridge. Power loss while the bootloader or the partition
 * table is being rewritten (well under a second) needs a USB reinstall.
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "cJSON.h"
#include "esp_err.h"
#include "esp_http_server.h"

typedef struct {char name[17]; uint8_t type, subtype; uint32_t offset, size;} mig_part_t;
enum {MIG_LAYOUT_UNKNOWN = 0, MIG_LAYOUT_V2 = 2, MIG_LAYOUT_V3 = 3};
enum {MIG_IDLE, MIG_COPYING_SELF, MIG_CHECKING, MIG_DOWNLOADING, MIG_VERIFYING, MIG_WRITING_BOOT, MIG_DONE, MIG_FAILED};

typedef struct {
    char tag[32];
    uint32_t size[3];            /* firmware.bin, bootloader.bin, partitions.bin */
    unsigned char digest[3][32];
} mig_target_t;
#define MIG_ASSETS {"firmware.bin", "bootloader.bin", "partitions.bin"}

/* Core (pure, host-tested). */
int mig_parse_table(const uint8_t *bin, size_t len, mig_part_t *out, int max, int *md5_index);
int mig_layout_kind(const mig_part_t *parts, int count);
bool mig_bootloader_ok(const uint8_t *image, size_t len);
bool mig_app_ok(const uint8_t *image, size_t len, const char *project, const char *tag);
uint32_t mig_crc32_le(uint32_t crc, const uint8_t *buf, size_t len);
/* otadata after migration: entry A boots ota_1 (3.x, ESP_OTA_IMG_NEW so an
 * unconfirmed start rolls back), entry B keeps ota_0 (the bridge) valid. */
void mig_otadata(uint8_t first[32], uint8_t second[32]);
/* Newest release with major version >= 3 on the selected channel that has
 * all three assets with digests and plausible sizes. */
bool mig_pick_release(const cJSON *releases, bool beta, mig_target_t *out);

typedef struct {
    bool bridge, needed, supported, busy;
    uint8_t layout, state;
    unsigned progress;
    uint32_t physical_flash;
    char target[32], error[96];
} mig_status_t;

void layout_migration_init(void);
void layout_migration_get_status(mig_status_t *out);
esp_err_t layout_migration_start(void);
esp_err_t layout_migration_register_http(httpd_handle_t server);
