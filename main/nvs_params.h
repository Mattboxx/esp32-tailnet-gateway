/* Small wrapper around the ESP-IDF NVS API for the single project
 * namespace ("tsr"). Every other module in the firmware talks to NVS
 * through these helpers so the namespace + read/write conventions live
 * in exactly one place.
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* NVS namespace shared by every module. Keep it short — NVS imposes a
 * 15-character limit. */
#define NVS_NAMESPACE "tsr"

/* String params. nvs_param_get_str() allocates the returned buffer with
 * malloc(); caller frees. Returns NULL if the key doesn't exist. */
char       *nvs_param_get_str(const char *key);
esp_err_t   nvs_param_set_str(const char *key, const char *value);

/* Read a string into a caller-supplied buffer. out_len is in/out: pass
 * the buffer size in, get the actual stored length back (including
 * null terminator). Returns ESP_OK / ESP_ERR_NVS_NOT_FOUND. */
esp_err_t   nvs_param_get_str_buf(const char *key, char *out, size_t *out_len);

/* Integer params. The signed variant covers ints, the unsigned variant
 * covers u8/u16/u32 stored under the same key — pick the one that
 * matches what was written. */
esp_err_t   nvs_param_get_int(const char *key, int32_t *out);
esp_err_t   nvs_param_set_int(const char *key, int32_t value);
esp_err_t   nvs_param_get_u8 (const char *key, uint8_t  *out);
esp_err_t   nvs_param_set_u8 (const char *key, uint8_t   value);
esp_err_t   nvs_param_get_u16(const char *key, uint16_t *out);
esp_err_t   nvs_param_set_u16(const char *key, uint16_t  value);
esp_err_t   nvs_param_get_u32(const char *key, uint32_t *out);
esp_err_t   nvs_param_set_u32(const char *key, uint32_t  value);

/* Erase a single key. ESP_OK or ESP_ERR_NVS_NOT_FOUND. */
esp_err_t   nvs_param_erase(const char *key);

/* Erase every key in the namespace (factory-reset style). */
esp_err_t   nvs_param_erase_all(void);

/* Binary params. get: out_len is in/out like nvs_get_blob; out may be NULL
 * to query the stored size. */
esp_err_t   nvs_param_get_blob(const char *key, void *out, size_t *out_len);
esp_err_t   nvs_param_set_blob(const char *key, const void *data, size_t len);

/* Settings transactions: make a save that touches several keys all or
 * nothing. Between begin and end, every nvs_param_set_* / nvs_param_erase
 * made by the calling task first records the key's previous value (or its
 * absence) in an undo journal stored in NVS, then writes. end(true) drops
 * the journal; end(false), or any failed write inside the transaction,
 * restores every recorded key. A journal left by a power loss is undone by
 * nvs_param_txn_recover() at the next boot.
 *
 * Nesting by the owning task is allowed (only the outermost end decides).
 * Writes from other tasks are not journaled and do not wait. Bounded: at
 * most NVS_PARAM_TXN_MAX_BYTES of previous values; a write that would not
 * fit fails (ESP_ERR_NO_MEM) and so rolls the transaction back. Only keys
 * of this namespace written through this API are covered. */
#define NVS_PARAM_TXN_MAX_BYTES 6144
esp_err_t   nvs_param_txn_begin(void);
esp_err_t   nvs_param_txn_end(bool keep);
/* Mark the current transaction failed (e.g. a non-NVS step failed). */
void        nvs_param_txn_fail(void);
/* Call once at boot after nvs_flash_init(), before settings are read. */
esp_err_t   nvs_param_txn_recover(void);

#ifdef __cplusplus
}
#endif
