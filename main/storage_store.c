/* Record rings in the "storage" partition; see storage_store.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "storage_store.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#endif

/* --- store core (begin) --- */
#ifndef EXT_RAM_BSS_ATTR
#define EXT_RAM_BSS_ATTR
#endif
/* Scratch buffers in PSRAM: no internal RAM is used while history is off. */
EXT_RAM_BSS_ATTR static store_record_t s_scratch;
EXT_RAM_BSS_ATTR static uint16_t s_offsets[STORE_SECTOR / 16u];
#define STORE_MAGIC 0x474E5252u        /* "RRNG" */
#define STORE_HEADER 8u                /* sector: magic, sequence */
#define STORE_RECORD_HEADER 16u        /* record: len, type, wall, uptime, crc */
#define STORE_FREE 0xFFFFu

uint32_t store_crc32(uint32_t crc, const void *data, size_t len)
{
    const uint8_t *p = data;
    crc = ~crc;
    for (size_t i = 0; i < len; i++) {
        crc ^= p[i];
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static uint32_t rd32(const uint8_t *p) {return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;}
static void wr32(uint8_t *p, uint32_t v) {p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);}
static uint32_t record_size(uint16_t len) {return STORE_RECORD_HEADER + ((len + 3u) & ~3u);}

static bool sector_header(const store_ring_t *r, uint32_t index, uint32_t *seq)
{
    uint8_t h[STORE_HEADER];
    if (r->flash->read(r->flash->ctx, r->base + index * STORE_SECTOR, h, sizeof h) != 0 || rd32(h) != STORE_MAGIC) return false;
    *seq = rd32(h + 4);
    return *seq != 0xFFFFFFFFu;
}

static esp_err_t start_sector(store_ring_t *r, uint32_t index, uint32_t seq)
{
    uint8_t h[STORE_HEADER];
    wr32(h, STORE_MAGIC); wr32(h + 4, seq);
    esp_err_t err = r->flash->erase_sector(r->flash->ctx, r->base + index * STORE_SECTOR);
    if (!err) err = r->flash->write(r->flash->ctx, r->base + index * STORE_SECTOR, h, sizeof h);
    if (!err) {r->sector = index; r->seq = seq; r->offset = STORE_HEADER;}
    return err;
}

/* Reads one record at `offset`; false at the end of the valid records. */
static bool read_record(const store_ring_t *r, uint32_t index, uint32_t offset, store_record_t *out, uint32_t *next)
{
    uint8_t h[STORE_RECORD_HEADER];
    if (offset + STORE_RECORD_HEADER > STORE_SECTOR) return false;
    uint32_t at = r->base + index * STORE_SECTOR + offset;
    if (r->flash->read(r->flash->ctx, at, h, sizeof h) != 0) return false;
    uint16_t len = (uint16_t)(h[0] | h[1] << 8);
    if (len == STORE_FREE || len > STORE_RECORD_MAX || offset + record_size(len) > STORE_SECTOR) return false;
    out->len = len; out->type = (uint16_t)(h[2] | h[3] << 8);
    out->wall = rd32(h + 4); out->uptime = rd32(h + 8);
    if (len && r->flash->read(r->flash->ctx, at + STORE_RECORD_HEADER, out->payload, len) != 0) return false;
    uint32_t crc = store_crc32(0, h, 12);
    if (store_crc32(crc, out->payload, len) != rd32(h + 12)) return false;   /* torn write: the sector ends here */
    *next = offset + record_size(len);
    return true;
}

esp_err_t store_ring_open(store_ring_t *r, const store_flash_t *flash, uint32_t base, uint32_t sectors)
{
    memset(r, 0, sizeof *r);
    if (!flash || sectors < 2) return ESP_ERR_INVALID_ARG;
    r->flash = flash; r->base = base; r->sectors = sectors;
    uint32_t best = 0, best_seq = 0;
    bool any = false;
    for (uint32_t i = 0; i < sectors; i++) {
        uint32_t seq;
        if (sector_header(r, i, &seq) && (!any || seq > best_seq)) {best = i; best_seq = seq; any = true;}
    }
    if (!any) {
        esp_err_t err = start_sector(r, 0, 1);
        r->ready = !err;
        return err;
    }
    r->sector = best; r->seq = best_seq; r->offset = STORE_HEADER;
    uint32_t next;
    while (read_record(r, best, r->offset, &s_scratch, &next)) r->offset = next;
    /* Anything but erased flash after the last valid record (a torn
     * write): never write over it, continue in the next sector. */
    uint8_t probe[4] = {0};
    if (r->offset + 4 <= STORE_SECTOR) flash->read(flash->ctx, base + best * STORE_SECTOR + r->offset, probe, sizeof probe);
    if (r->offset + 4 > STORE_SECTOR || rd32(probe) != 0xFFFFFFFFu) r->offset = STORE_SECTOR;
    r->ready = true;
    return ESP_OK;
}

esp_err_t store_ring_append(store_ring_t *r, uint16_t type, uint32_t wall, uint32_t uptime, const void *payload, uint16_t len)
{
    if (!r || !r->ready || len > STORE_RECORD_MAX || (len && !payload)) return ESP_ERR_INVALID_ARG;
    uint32_t size = record_size(len);
    if (r->offset + size > STORE_SECTOR) {
        esp_err_t err = start_sector(r, (r->sector + 1) % r->sectors, r->seq + 1);
        if (err) {r->offset = STORE_SECTOR; return err;}
    }
    /* Header first, then the payload (the padding stays erased): a cut
     * between the two leaves a header whose CRC fails, ending the sector. */
    uint8_t h[STORE_RECORD_HEADER];
    h[0] = (uint8_t)len; h[1] = (uint8_t)(len >> 8);
    h[2] = (uint8_t)type; h[3] = (uint8_t)(type >> 8);
    wr32(h + 4, wall); wr32(h + 8, uptime);
    wr32(h + 12, store_crc32(store_crc32(0, h, 12), payload, len));
    uint32_t at = r->base + r->sector * STORE_SECTOR + r->offset;
    esp_err_t err = r->flash->write(r->flash->ctx, at, h, sizeof h);
    if (!err && len) err = r->flash->write(r->flash->ctx, at + STORE_RECORD_HEADER, payload, len);
    r->offset = err ? STORE_SECTOR : r->offset + size;   /* a failed write ends the sector */
    return err;
}

unsigned store_ring_walk(const store_ring_t *r, store_visit_t visit, void *arg)
{
    if (!r || !r->ready || !visit) return 0;
    store_record_t *record = &s_scratch;                   /* callers serialize (storage_store_lock) */
    uint16_t *offsets = s_offsets;
    unsigned visited = 0;
    for (uint32_t i = 0; i < r->sectors; i++) {
        uint32_t index = (r->sector + r->sectors - i) % r->sectors, seq;
        if (!sector_header(r, index, &seq) || seq != r->seq - i || (i && seq == 0)) break;
        unsigned count = 0;
        uint32_t offset = STORE_HEADER, next;
        while (count < sizeof s_offsets / sizeof s_offsets[0] && read_record(r, index, offset, record, &next)) {
            offsets[count++] = (uint16_t)offset;
            offset = next;
        }
        while (count--) {
            if (!read_record(r, index, offsets[count], record, &next)) continue;
            visited++;
            if (!visit(record, arg)) return visited;
        }
    }
    return visited;
}
/* --- store core (end) --- */

#ifdef ESP_PLATFORM
#include "esp_partition.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

/* Flash operations disable the cache: every caller runs on an internal-RAM
 * stack (the storage task, httpd, app_main), never a PSRAM-stack worker. */
static const esp_partition_t *s_part;
static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;

static esp_err_t part_read(void *ctx, uint32_t at, void *out, size_t n) {(void)ctx; return esp_partition_read(s_part, at, out, n);}
static esp_err_t part_write(void *ctx, uint32_t at, const void *data, size_t n) {(void)ctx; return esp_partition_write(s_part, at, data, n);}
static esp_err_t part_erase(void *ctx, uint32_t at) {(void)ctx; return esp_partition_erase_range(s_part, at, STORE_SECTOR);}
static const store_flash_t s_flash = {NULL, part_read, part_write, part_erase};

bool storage_store_available(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    if (!s_part) {
        const esp_partition_t *p = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "storage");
        /* Only the 3.x layout: the regions below must fit. */
        if (p && p->size >= STORE_CONTROL_BASE + STORE_SECTOR && !p->encrypted) s_part = p;
    }
    return s_part && s_lock;
}

const store_flash_t *storage_store_flash(void) {return storage_store_available() ? &s_flash : NULL;}
void storage_store_lock(void) {if (storage_store_available()) xSemaphoreTake(s_lock, portMAX_DELAY);}
void storage_store_unlock(void) {if (s_lock) xSemaphoreGive(s_lock);}

esp_err_t storage_store_erase_all(void)
{
    if (!storage_store_available()) return ESP_ERR_NOT_FOUND;
    storage_store_lock();
    /* Secrets first: the settings copies, then the control sector and history. */
    esp_err_t err = esp_partition_erase_range(s_part, STORE_SNAPSHOT_BASE, STORE_CONTROL_BASE + STORE_SECTOR - STORE_SNAPSHOT_BASE);
    if (!err) err = esp_partition_erase_range(s_part, 0, STORE_SNAPSHOT_BASE);
    storage_store_unlock();
    return err;
}
#endif
