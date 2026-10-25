/* See nvs_params.h. Boilerplate that opens the project namespace and
 * forwards to the underlying ESP-IDF NVS calls, plus the settings undo
 * journal that makes multi-key saves all or nothing.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdlib.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "nvs_params.h"
#ifdef CONFIG_SPIRAM
#include "esp_heap_caps.h"
#endif

static const char *TAG = "nvs_params";

static esp_err_t open_handle(nvs_open_mode_t mode, nvs_handle_t *out)
{
    esp_err_t err = nvs_open(NVS_NAMESPACE, mode, out);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "nvs_open(%s) failed: %s", NVS_NAMESPACE, esp_err_to_name(err));
    }
    return err;
}

/* ---- undo journal (settings transactions) ----
 * Blob "txn_undo": magic u32, entry count u16, reserved u16, entries,
 * CRC-32 of everything before it. Entry: type u8, present u8, key length
 * u8, key (no NUL), value length u16 LE, value (strings keep their NUL).
 * Only the first write of a key inside a transaction is recorded, so the
 * journal always holds the values from before the transaction. */
#define TXN_KEY    "txn_undo"
#define TXN_MAGIC  0x314E5854u               /* "TXN1" */
#define TXN_HEADER 8
#define TXN_CAP    (TXN_HEADER + NVS_PARAM_TXN_MAX_BYTES + 4)
enum { T_I32 = 1, T_U8, T_U16, T_U32, T_STR, T_BLOB };

static SemaphoreHandle_t s_txn_lock;
static StaticSemaphore_t s_txn_lock_storage;
static TaskHandle_t volatile s_txn_owner;
static int s_txn_depth;
static bool s_txn_failed;
static bool s_txn_stale;                     /* a journal could not be undone */
static uint8_t *s_txn_buf;
static size_t s_txn_used;                    /* header + entries */
static uint16_t s_txn_count;

static uint32_t crc32_le(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *p++;
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

static bool txn_mine(void)
{
    TaskHandle_t owner = s_txn_owner;
    return owner && owner == xTaskGetCurrentTaskHandle();
}

static esp_err_t txn_note(esp_err_t err)
{
    if (err != ESP_OK && txn_mine()) s_txn_failed = true;
    return err;
}

static size_t entry_size(const uint8_t *e)
{
    return 5u + e[2] + (size_t)(e[3 + e[2]] | (e[4 + e[2]] << 8));
}

static bool txn_recorded(const char *key)
{
    size_t klen = strlen(key);
    size_t off = TXN_HEADER;
    for (uint16_t i = 0; i < s_txn_count; i++) {
        const uint8_t *e = s_txn_buf + off;
        if (e[2] == klen && memcmp(e + 3, key, klen) == 0) return true;
        off += entry_size(e);
    }
    return false;
}

/* Value size per type; 0 for variable-length types. */
static size_t fixed_size(uint8_t type)
{
    switch (type) {
    case T_I32: case T_U32: return 4;
    case T_U16: return 2;
    case T_U8:  return 1;
    default:    return 0;
    }
}

static void journal_seal(void)
{
    s_txn_buf[4] = (uint8_t)s_txn_count;
    s_txn_buf[5] = (uint8_t)(s_txn_count >> 8);
    uint32_t crc = crc32_le(s_txn_buf, s_txn_used);
    memcpy(s_txn_buf + s_txn_used, &crc, 4);
}

static esp_err_t journal_persist(nvs_handle_t h)
{
    journal_seal();
    esp_err_t err = nvs_set_blob(h, TXN_KEY, s_txn_buf, s_txn_used + 4);
    if (err == ESP_OK) err = nvs_commit(h);
    return err;
}

/* Before the owning task writes or erases `key`, record its previous value
 * (whatever type is stored) and persist the journal. */
static esp_err_t journal_before(nvs_handle_t h, const char *key)
{
    if (!txn_mine()) return ESP_OK;
    size_t klen = strlen(key);
    if (klen == 0 || klen > 15 || !strcmp(key, TXN_KEY)) return ESP_ERR_INVALID_ARG;
    if (txn_recorded(key)) return ESP_OK;

    nvs_type_t stored = NVS_TYPE_ANY;
    esp_err_t err = nvs_find_key(h, key, &stored);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) return err;
    uint8_t present = err == ESP_OK, type = 0;
    if (present) {
        switch (stored) {
        case NVS_TYPE_I32:  type = T_I32;  break;
        case NVS_TYPE_U8:   type = T_U8;   break;
        case NVS_TYPE_U16:  type = T_U16;  break;
        case NVS_TYPE_U32:  type = T_U32;  break;
        case NVS_TYPE_STR:  type = T_STR;  break;
        case NVS_TYPE_BLOB: type = T_BLOB; break;
        default: return ESP_ERR_NOT_SUPPORTED;
        }
    }
    size_t room = TXN_HEADER + NVS_PARAM_TXN_MAX_BYTES - s_txn_used;
    if (room < 5 + klen) return ESP_ERR_NO_MEM;
    uint8_t *e = s_txn_buf + s_txn_used;
    uint8_t *v = e + 5 + klen;
    size_t vlen = 0, cap = room - 5 - klen;
    if (present) {
        vlen = fixed_size(type);
        if (vlen > cap) return ESP_ERR_NO_MEM;
        switch (type) {
        case T_I32: { int32_t x = 0;  err = nvs_get_i32(h, key, &x); memcpy(v, &x, 4); break; }
        case T_U32: { uint32_t x = 0; err = nvs_get_u32(h, key, &x); memcpy(v, &x, 4); break; }
        case T_U16: { uint16_t x = 0; err = nvs_get_u16(h, key, &x); memcpy(v, &x, 2); break; }
        case T_U8:  err = nvs_get_u8(h, key, v); break;
        default: {
            size_t n = 0;
            err = type == T_STR ? nvs_get_str(h, key, NULL, &n) : nvs_get_blob(h, key, NULL, &n);
            if (err != ESP_OK) break;
            if (n > cap || n > 0xFFFF) return ESP_ERR_NO_MEM;
            err = type == T_STR ? nvs_get_str(h, key, (char *)v, &n) : nvs_get_blob(h, key, v, &n);
            vlen = n;
            break;
        }
        }
        if (err != ESP_OK) return err;
    }
    e[0] = type;
    e[1] = present;
    e[2] = (uint8_t)klen;
    memcpy(e + 3, key, klen);
    e[3 + klen] = (uint8_t)vlen;
    e[4 + klen] = (uint8_t)(vlen >> 8);
    s_txn_used += 5 + klen + vlen;
    s_txn_count++;
    err = journal_persist(h);
    if (err != ESP_OK) {             /* the key is not written: forget it */
        s_txn_used -= 5 + klen + vlen;
        s_txn_count--;
    }
    return err;
}

/* Check a journal image and, when apply is set, put every recorded key back
 * (or erase it if it did not exist). Returns ESP_ERR_INVALID_CRC for an
 * image that must not be trusted; nothing is applied then. */
static esp_err_t journal_apply(nvs_handle_t h, const uint8_t *buf, size_t len, bool apply)
{
    if (len < TXN_HEADER + 4) return ESP_ERR_INVALID_CRC;
    uint32_t magic, crc;
    memcpy(&magic, buf, 4);
    memcpy(&crc, buf + len - 4, 4);
    if (magic != TXN_MAGIC || crc != crc32_le(buf, len - 4)) return ESP_ERR_INVALID_CRC;
    uint16_t count = (uint16_t)(buf[4] | (buf[5] << 8));
    size_t off = TXN_HEADER, end = len - 4;
    for (uint16_t i = 0; i < count; i++) {
        if (end - off < 5) return ESP_ERR_INVALID_CRC;
        const uint8_t *e = buf + off;
        size_t klen = e[2];
        if (klen == 0 || klen > 15 || end - off - 5 < klen) return ESP_ERR_INVALID_CRC;
        size_t vlen = (size_t)(e[3 + klen] | (e[4 + klen] << 8));
        if (end - off - 5 - klen < vlen) return ESP_ERR_INVALID_CRC;
        uint8_t type = e[0], present = e[1];
        if (present > 1 || (!present && vlen) || (present && (type < T_I32 || type > T_BLOB)))
            return ESP_ERR_INVALID_CRC;
        if (present && fixed_size(type) && vlen != fixed_size(type)) return ESP_ERR_INVALID_CRC;
        if (present && type == T_STR && (vlen == 0 || e[5 + klen + vlen - 1] != '\0'))
            return ESP_ERR_INVALID_CRC;
        off += 5 + klen + vlen;
    }
    if (off != end) return ESP_ERR_INVALID_CRC;
    if (!apply) return ESP_OK;

    esp_err_t first = ESP_OK;
    off = TXN_HEADER;
    for (uint16_t i = 0; i < count; i++) {
        const uint8_t *e = buf + off;
        size_t klen = e[2];
        size_t vlen = (size_t)(e[3 + klen] | (e[4 + klen] << 8));
        const uint8_t *v = e + 5 + klen;
        char key[16];
        memcpy(key, e + 3, klen);
        key[klen] = '\0';
        esp_err_t err;
        if (!e[1]) {
            err = nvs_erase_key(h, key);
            if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
        } else {
            switch (e[0]) {
            case T_I32: { int32_t x;  memcpy(&x, v, 4); err = nvs_set_i32(h, key, x); break; }
            case T_U32: { uint32_t x; memcpy(&x, v, 4); err = nvs_set_u32(h, key, x); break; }
            case T_U16: { uint16_t x; memcpy(&x, v, 2); err = nvs_set_u16(h, key, x); break; }
            case T_U8:  err = nvs_set_u8(h, key, v[0]); break;
            case T_STR: err = nvs_set_str(h, key, (const char *)v); break;
            default:    err = nvs_set_blob(h, key, v, vlen); break;
            }
        }
        if (err != ESP_OK && first == ESP_OK) first = err;
        off += 5 + klen + vlen;
    }
    esp_err_t err = nvs_commit(h);
    return first != ESP_OK ? first : err;
}

static esp_err_t journal_drop(nvs_handle_t h)
{
    esp_err_t err = nvs_erase_key(h, TXN_KEY);
    if (err == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (err == ESP_OK) err = nvs_commit(h);
    return err;
}

static void txn_lock_init(void)
{
    if (!s_txn_lock) s_txn_lock = xSemaphoreCreateMutexStatic(&s_txn_lock_storage);
}

esp_err_t nvs_param_txn_recover(void)
{
    txn_lock_init();
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READWRITE, &h);
    if (err != ESP_OK) {
        s_txn_stale = true;
        return err;
    }
    size_t len = 0;
    err = nvs_get_blob(h, TXN_KEY, NULL, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        s_txn_stale = false;
        nvs_close(h);
        return ESP_OK;
    }
    uint8_t *buf = NULL;
    if (err == ESP_OK && len > TXN_CAP) err = ESP_ERR_INVALID_CRC;
    if (err == ESP_OK && !(buf = malloc(len ? len : 1))) err = ESP_ERR_NO_MEM;
    if (err == ESP_OK) err = nvs_get_blob(h, TXN_KEY, buf, &len);
    if (err == ESP_OK) err = journal_apply(h, buf, len, true);
    free(buf);
    if (err == ESP_ERR_INVALID_CRC || err == ESP_ERR_NVS_INVALID_LENGTH) {
        /* Not a journal this firmware wrote completely: never apply it. */
        ESP_LOGE(TAG, "discarding an unreadable settings undo journal");
        err = journal_drop(h);
    } else if (err == ESP_OK) {
        ESP_LOGW(TAG, "an interrupted settings save was undone");
        err = journal_drop(h);
    }
    s_txn_stale = err != ESP_OK;
    if (err != ESP_OK) ESP_LOGE(TAG, "settings undo journal: %s", esp_err_to_name(err));
    nvs_close(h);
    return err;
}

esp_err_t nvs_param_txn_begin(void)
{
    if (txn_mine()) {
        s_txn_depth++;
        return ESP_OK;
    }
    txn_lock_init();
    if (!s_txn_lock) return ESP_ERR_NO_MEM;
    if (xSemaphoreTake(s_txn_lock, pdMS_TO_TICKS(5000)) != pdTRUE) return ESP_ERR_TIMEOUT;
    /* An earlier journal that could not be undone must not be overwritten. */
    esp_err_t err = s_txn_stale ? nvs_param_txn_recover() : ESP_OK;
    if (err == ESP_OK) {
#ifdef CONFIG_SPIRAM
        s_txn_buf = heap_caps_malloc(TXN_CAP, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!s_txn_buf)
#endif
        s_txn_buf = malloc(TXN_CAP);
        if (!s_txn_buf) err = ESP_ERR_NO_MEM;
    }
    if (err != ESP_OK) {
        xSemaphoreGive(s_txn_lock);
        return err;
    }
    uint32_t magic = TXN_MAGIC;
    memcpy(s_txn_buf, &magic, 4);
    memset(s_txn_buf + 4, 0, 4);
    s_txn_used = TXN_HEADER;
    s_txn_count = 0;
    s_txn_failed = false;
    s_txn_depth = 1;
    s_txn_owner = xTaskGetCurrentTaskHandle();
    return ESP_OK;
}

void nvs_param_txn_fail(void)
{
    if (txn_mine()) s_txn_failed = true;
}

esp_err_t nvs_param_txn_end(bool keep)
{
    if (!txn_mine()) return ESP_ERR_INVALID_STATE;
    if (!keep) s_txn_failed = true;
    if (--s_txn_depth > 0) return ESP_OK;

    bool restore = s_txn_failed;
    esp_err_t err = ESP_OK;
    if (s_txn_count) {
        nvs_handle_t h;
        err = open_handle(NVS_READWRITE, &h);
        if (err == ESP_OK) {
            /* A journal that cannot be dropped would undo the save at the
             * next boot: undo it now so the result is the same. */
            if (!restore && journal_drop(h) != ESP_OK) restore = true;
            if (restore) {
                journal_seal();
                err = journal_apply(h, s_txn_buf, s_txn_used + 4, true);
                if (err == ESP_OK) err = journal_drop(h);
            }
            nvs_close(h);
        } else {
            restore = true;
        }
        if (restore && err != ESP_OK) {
            s_txn_stale = true;      /* retried at the next begin or boot */
            ESP_LOGE(TAG, "settings rollback incomplete: %s", esp_err_to_name(err));
        }
    }
    free(s_txn_buf);
    s_txn_buf = NULL;
    s_txn_owner = NULL;
    xSemaphoreGive(s_txn_lock);
    if (!restore) return ESP_OK;
    return err != ESP_OK ? err : ESP_ERR_INVALID_STATE;
}

/* ---- accessors ---- */

char *nvs_param_get_str(const char *key)
{
    nvs_handle_t h;
    if (open_handle(NVS_READONLY, &h) != ESP_OK) return NULL;
    size_t len = 0;
    esp_err_t err = nvs_get_str(h, key, NULL, &len);
    if (err != ESP_OK || len == 0) {
        nvs_close(h);
        return NULL;
    }
    char *buf = malloc(len);
    if (!buf) {
        nvs_close(h);
        return NULL;
    }
    err = nvs_get_str(h, key, buf, &len);
    nvs_close(h);
    if (err != ESP_OK) {
        free(buf);
        return NULL;
    }
    return buf;
}

esp_err_t nvs_param_set_str(const char *key, const char *value)
{
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READWRITE, &h);
    if (err != ESP_OK) return txn_note(err);
    err = journal_before(h, key);
    if (err == ESP_OK) err = nvs_set_str(h, key, value ? value : "");
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return txn_note(err);
}

esp_err_t nvs_param_get_str_buf(const char *key, char *out, size_t *out_len)
{
    if (!out || !out_len || *out_len == 0) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READONLY, &h);
    if (err != ESP_OK) return err;
    err = nvs_get_str(h, key, out, out_len);
    nvs_close(h);
    return err;
}

#define NVS_PARAM_INT_FN(suffix, type, getter, setter)                   \
    esp_err_t nvs_param_get_##suffix(const char *key, type *out)         \
    {                                                                    \
        if (!out) return ESP_ERR_INVALID_ARG;                            \
        nvs_handle_t h;                                                  \
        esp_err_t err = open_handle(NVS_READONLY, &h);                   \
        if (err != ESP_OK) return err;                                   \
        err = getter(h, key, out);                                       \
        nvs_close(h);                                                    \
        return err;                                                      \
    }                                                                    \
    esp_err_t nvs_param_set_##suffix(const char *key, type value)        \
    {                                                                    \
        nvs_handle_t h;                                                  \
        esp_err_t err = open_handle(NVS_READWRITE, &h);                  \
        if (err != ESP_OK) return txn_note(err);                         \
        err = journal_before(h, key);                                    \
        if (err == ESP_OK) err = setter(h, key, value);                  \
        if (err == ESP_OK) err = nvs_commit(h);                          \
        nvs_close(h);                                                    \
        return txn_note(err);                                            \
    }

NVS_PARAM_INT_FN(int, int32_t,  nvs_get_i32, nvs_set_i32)
NVS_PARAM_INT_FN(u8,  uint8_t,  nvs_get_u8,  nvs_set_u8)
NVS_PARAM_INT_FN(u16, uint16_t, nvs_get_u16, nvs_set_u16)
NVS_PARAM_INT_FN(u32, uint32_t, nvs_get_u32, nvs_set_u32)

esp_err_t nvs_param_get_blob(const char *key, void *out, size_t *out_len)
{
    if (!out_len) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READONLY, &h);
    if (err != ESP_OK) return err;
    err = nvs_get_blob(h, key, out, out_len);
    nvs_close(h);
    return err;
}

esp_err_t nvs_param_set_blob(const char *key, const void *data, size_t len)
{
    if (!data && len) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READWRITE, &h);
    if (err != ESP_OK) return txn_note(err);
    err = journal_before(h, key);
    if (err == ESP_OK) err = nvs_set_blob(h, key, data, len);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return txn_note(err);
}

esp_err_t nvs_param_erase(const char *key)
{
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READWRITE, &h);
    if (err != ESP_OK) return txn_note(err);
    err = journal_before(h, key);
    if (err == ESP_OK) err = nvs_erase_key(h, key);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    return txn_note(err);
}

esp_err_t nvs_param_erase_all(void)
{
    nvs_handle_t h;
    esp_err_t err = open_handle(NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_erase_all(h);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}
