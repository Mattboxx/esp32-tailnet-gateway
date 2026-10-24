/* Record rings and fixed slots in the 3.x "storage" data partition (832 KiB).
 *
 * No filesystem: each ring is a run of 4 KiB sectors used round-robin. A
 * sector starts with a header (magic, sequence); records follow back to back
 * (length, type, wall clock, uptime, payload, CRC32) until 0xFF. Appending a
 * record that does not fit moves to the next sector, erasing the oldest one,
 * so each sector is erased once per lap (flash wear bounded by the ring
 * size). A record cut by a power loss fails its CRC and ends that sector.
 *
 *   0x00000  events     64 sectors (256 KiB)   event history
 *   0x40000  metrics    64 sectors (256 KiB)   history samples
 *   0x80000  snapshots  3 x 68 KiB             NVS copies (settings)
 *   0xB3000  control    4 KiB                  pending restore request
 *   0xB4000  free       112 KiB
 *
 * The ring core is not thread-safe: firmware callers hold storage_store_lock().
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define STORE_SECTOR 4096u
#define STORE_RECORD_MAX 512u   /* payload bytes */

/* Flash access, so the ring core runs on a host fixture too. */
typedef struct {
    void *ctx;
    esp_err_t (*read)(void *ctx, uint32_t offset, void *out, size_t len);
    esp_err_t (*write)(void *ctx, uint32_t offset, const void *data, size_t len);
    esp_err_t (*erase_sector)(void *ctx, uint32_t offset);
} store_flash_t;

typedef struct {
    const store_flash_t *flash;
    uint32_t base, sectors;      /* region in the partition */
    uint32_t sector, offset;     /* write position: sector index, byte offset in it */
    uint32_t seq;                /* sequence of the current sector */
    bool ready;
} store_ring_t;

typedef struct {
    uint16_t type;
    uint32_t wall;               /* Unix time, 0 when the clock was not set */
    uint32_t uptime;             /* seconds since boot */
    uint16_t len;
    uint8_t payload[STORE_RECORD_MAX];
} store_record_t;

/* Core (host-tested). */
esp_err_t store_ring_open(store_ring_t *ring, const store_flash_t *flash, uint32_t base, uint32_t sectors);
esp_err_t store_ring_append(store_ring_t *ring, uint16_t type, uint32_t wall, uint32_t uptime, const void *payload, uint16_t len);
/* Newest first; the callback returns false to stop. Returns records visited. */
typedef bool (*store_visit_t)(const store_record_t *record, void *arg);
unsigned store_ring_walk(const store_ring_t *ring, store_visit_t visit, void *arg);
uint32_t store_crc32(uint32_t crc, const void *data, size_t len);

/* Firmware: the "storage" partition (any data subtype, found by label). */
#define STORE_EVENTS_BASE 0x00000u
#define STORE_EVENTS_SECTORS 64u
#define STORE_METRICS_BASE 0x40000u
#define STORE_METRICS_SECTORS 64u
#define STORE_SNAPSHOT_BASE 0x80000u
#define STORE_SNAPSHOT_SLOT 0x11000u    /* 4 KiB header + 64 KiB NVS copy */
#define STORE_SNAPSHOT_SLOTS 3u
#define STORE_CONTROL_BASE 0xB3000u
bool storage_store_available(void);   /* false on the 2.x layout (no storage partition) */
const store_flash_t *storage_store_flash(void);
void storage_store_lock(void);
void storage_store_unlock(void);
/* Factory reset: erases the settings copies first, then the history. */
esp_err_t storage_store_erase_all(void);
