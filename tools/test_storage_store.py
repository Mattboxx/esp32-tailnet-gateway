"""Actual record-ring core of main/storage_store.c on a simulated NOR flash.

The fake flash keeps NOR semantics (a write can only clear bits, erase sets a
4 KiB sector to 0xFF) and counts erases. Covered: fresh/garbage regions,
newest-first walk, wrap-around with the oldest sector dropped, reopen after a
restart, torn writes (power cut), failing writes/erases, limits and invalid
arguments. The esp_partition backend and real flash timing are NOT covered.
STORE_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/storage_store.c').read_text(encoding='utf-8')
core = source.split('/* --- store core (begin) --- */', 1)[1].split('/* --- store core (end) --- */', 1)[0]

ESP_ERR = r'''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
'''

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "storage_store.h"
''' + core + r'''
#define REGION (8u * STORE_SECTOR)
static uint8_t flash[REGION + STORE_SECTOR];      /* one guard sector after the ring */
static unsigned erases[REGION / STORE_SECTOR + 1];
static int fail_write, fail_erase, cut_after;      /* cut_after: bytes written before a "power cut" */

static esp_err_t f_read(void *ctx, uint32_t at, void *out, size_t n){(void)ctx;assert(at + n <= sizeof flash);memcpy(out, flash + at, n);return ESP_OK;}
static esp_err_t f_write(void *ctx, uint32_t at, const void *data, size_t n){
    (void)ctx;assert(at + n <= sizeof flash);
    assert(at / STORE_SECTOR == (at + n - 1) / STORE_SECTOR);       /* never crosses a sector */
    if (fail_write) return ESP_FAIL;
    size_t keep = n;
    if (cut_after > 0 && (size_t)cut_after < n) keep = (size_t)cut_after;
    for (size_t i = 0; i < keep; i++) flash[at + i] &= ((const uint8_t *)data)[i];   /* NOR: clear bits only */
    if (keep < n) {cut_after = -1; return ESP_FAIL;}
    return ESP_OK;
}
static esp_err_t f_erase(void *ctx, uint32_t at){
    (void)ctx;assert(at % STORE_SECTOR == 0 && at < REGION);
    if (fail_erase) return ESP_FAIL;
    memset(flash + at, 0xFF, STORE_SECTOR);erases[at / STORE_SECTOR]++;return ESP_OK;
}
static const store_flash_t dev = {NULL, f_read, f_write, f_erase};

typedef struct {unsigned n; uint32_t ids[4096]; uint16_t lens[4096]; unsigned stop;} seen_t;
static bool collect(const store_record_t *r, void *arg){
    seen_t *s = arg;
    uint32_t id = 0;
    if (r->len >= 4) memcpy(&id, r->payload, 4);
    for (unsigned i = 4; i < r->len; i++) assert(r->payload[i] == (uint8_t)(id + i));   /* payload intact */
    assert(r->type == (uint16_t)(id % 7) && r->uptime == id * 2 && r->wall == (id ? 1700000000u + id : 0));
    s->ids[s->n] = id; s->lens[s->n] = r->len; s->n++;
    return !s->stop || s->n < s->stop;
}
static esp_err_t put(store_ring_t *r, uint32_t id, uint16_t len){
    uint8_t p[STORE_RECORD_MAX];
    memset(p, 0, sizeof p);
    if (len >= 4) memcpy(p, &id, 4);
    for (unsigned i = 4; i < len; i++) p[i] = (uint8_t)(id + i);
    return store_ring_append(r, (uint16_t)(id % 7), id ? 1700000000u + id : 0, id * 2, p, len);
}
static seen_t seen;
static unsigned walk(const store_ring_t *r){memset(&seen, 0, sizeof seen);return store_ring_walk(r, collect, &seen);}
static void newest_first(uint32_t newest){for (unsigned i = 0; i < seen.n; i++) assert(seen.ids[i] == newest - i);}

int main(void){
    store_ring_t r;
    /* CRC-32 (IEEE) reference value and chaining. */
    assert(store_crc32(0, "123456789", 9) == 0xCBF43926u);
    assert(store_crc32(store_crc32(0, "1234", 4), "56789", 5) == 0xCBF43926u);

    /* Invalid arguments and the closed state. */
    assert(store_ring_open(&r, NULL, 0, 8) == ESP_ERR_INVALID_ARG && !r.ready);
    assert(store_ring_open(&r, &dev, 0, 1) == ESP_ERR_INVALID_ARG && !r.ready);
    assert(store_ring_append(&r, 1, 0, 0, "x", 1) == ESP_ERR_INVALID_ARG && store_ring_walk(&r, collect, &seen) == 0);
    assert(store_ring_append(NULL, 1, 0, 0, "x", 1) == ESP_ERR_INVALID_ARG && store_ring_walk(NULL, collect, &seen) == 0);

    /* Fresh erased region: the first sector is started, nothing to walk. */
    memset(flash, 0xFF, sizeof flash);
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_OK && r.ready && r.sector == 0 && r.seq == 1 && erases[0] == 1);
    assert(walk(&r) == 0 && store_ring_walk(&r, NULL, NULL) == 0);
    assert(store_ring_append(&r, 1, 0, 0, NULL, 4) == ESP_ERR_INVALID_ARG);
    assert(store_ring_append(&r, 1, 0, 0, "x", STORE_RECORD_MAX + 1) == ESP_ERR_INVALID_ARG);

    /* Empty and maximal payloads; newest first. */
    assert(put(&r, 0, 0) == ESP_OK && put(&r, 1, 5) == ESP_OK && put(&r, 2, STORE_RECORD_MAX) == ESP_OK);
    assert(walk(&r) == 3 && seen.ids[0] == 2 && seen.lens[0] == STORE_RECORD_MAX && seen.ids[1] == 1 && seen.lens[1] == 5 && seen.lens[2] == 0);
    seen.n = 0; seen.stop = 1; assert(store_ring_walk(&r, collect, &seen) == 1);          /* the callback stops the walk */

    /* Many records across sectors, then a restart: position and order kept. */
    for (uint32_t id = 3; id < 60; id++) assert(put(&r, id, (uint16_t)(40 + id % 90)) == ESP_OK);
    assert(r.sector > 0);
    store_ring_t again;
    assert(store_ring_open(&again, &dev, 0, 8) == ESP_OK && again.sector == r.sector && again.offset == r.offset && again.seq == r.seq);
    assert(walk(&again) == 60); newest_first(59);
    assert(put(&again, 60, 100) == ESP_OK && walk(&again) == 61 && seen.ids[0] == 60);

    /* Wrap-around: the oldest sector is erased, the newest records stay, wear is even. */
    for (uint32_t id = 61; id < 2000; id++) assert(put(&again, id, (uint16_t)(60 + id % 300)) == ESP_OK);
    unsigned kept = walk(&again);
    assert(kept > 7 * 9 && kept < 8 * STORE_SECTOR / 16); newest_first(1999);
    assert(seen.ids[kept - 1] > 61);                                                        /* the oldest records are gone */
    unsigned lo = erases[0], hi = erases[0];
    for (unsigned i = 1; i < 8; i++) {if (erases[i] < lo) lo = erases[i]; if (erases[i] > hi) hi = erases[i];}
    assert(hi - lo <= 1 && hi > 2 && erases[8] == 0);                                       /* never outside the region */
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_OK && walk(&r) == kept); newest_first(1999);

    /* Torn write (power cut mid-record): the record is dropped, earlier ones
     * kept, and the next record goes to a fresh sector, never over the debris. */
    uint32_t id = 2000;
    while (r.offset + 16 + 200 > STORE_SECTOR) assert(put(&r, id++, 10) == ESP_OK);   /* the torn record fits here */
    uint32_t newest = id - 1, sector = r.sector;
    kept = walk(&r);
    cut_after = 9; assert(put(&r, id++, 200) == ESP_FAIL);
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_OK && r.sector == sector && r.offset == STORE_SECTOR);
    assert(walk(&r) == kept); newest_first(newest);
    assert(put(&r, id, 50) == ESP_OK && r.sector == (sector + 1) % 8 && r.offset == 8 + 16 + 52);
    walk(&r); assert(seen.ids[0] == id && seen.ids[1] == newest);

    /* A record whose CRC does not match (bit rot) ends that sector on reopen. */
    uint32_t at = r.base + r.sector * STORE_SECTOR + 8;
    assert(put(&r, ++id, 10) == ESP_OK);
    flash[at + 16 + 5] &= 0x0F;
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_OK && r.offset == STORE_SECTOR);
    walk(&r); assert(seen.ids[0] == newest);

    /* Failing write or erase: reported, the ring stays usable afterwards. */
    fail_write = 1; assert(put(&r, ++id, 10) == ESP_FAIL); fail_write = 0;
    fail_erase = 1; assert(put(&r, ++id, 10) == ESP_FAIL); fail_erase = 0;
    assert(put(&r, ++id, 10) == ESP_OK); walk(&r); assert(seen.ids[0] == id && seen.ids[1] == newest);
    /* A failed open on an unerasable fresh region leaves the ring closed. */
    memset(flash, 0x00, REGION); fail_erase = 1;
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_FAIL && !r.ready); fail_erase = 0;

    /* Garbage (non-ring data) in the region is treated as empty: started fresh. */
    for (unsigned i = 0; i < REGION; i++) flash[i] = (uint8_t)(i * 31 + 7);
    assert(store_ring_open(&r, &dev, 0, 8) == ESP_OK && r.sector == 0 && r.seq == 1 && walk(&r) == 0);
    assert(put(&r, 7, 30) == ESP_OK && walk(&r) == 1);

    /* Stale sectors from an older lap (lower sequence) are not walked twice. */
    memset(flash, 0xFF, sizeof flash);
    assert(store_ring_open(&r, &dev, 0, 2) == ESP_OK);
    for (uint32_t id = 1; id < 200; id++) assert(put(&r, id, 300) == ESP_OK);
    unsigned two = walk(&r); newest_first(199);
    assert(two <= 2 * (STORE_SECTOR / (16 + 300)) && two >= STORE_SECTOR / (16 + 300));
    /* A region at a non-zero base inside a larger partition. */
    store_ring_t other;
    assert(store_ring_open(&other, &dev, 2 * STORE_SECTOR, 3) == ESP_OK && walk(&other) == 0);
    assert(put(&other, 9, 20) == ESP_OK && walk(&other) == 1 && walk(&r) == two);
    puts("storage_store core: ok");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='store-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
        (path / 'store.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('store.exe' if os.name == 'nt' else 'store')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('STORE_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'store.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
