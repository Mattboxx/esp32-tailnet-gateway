/* Settings copies; see settings_snapshot.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "settings_snapshot.h"
#include <stdio.h>
#include <string.h>

/* --- snapshot core (begin) --- */
#define SNAP_DATA 0x1000u                 /* data after the header sector */
#define SNAP_COPY_TRIES 3
#define ATTEMPTS_AT 64u                   /* control: one cleared byte per restore attempt */

typedef struct {uint32_t magic, slot, seq, data_crc, crc;} snap_control_t;

static uint32_t slot_base(unsigned slot) {return STORE_SNAPSHOT_BASE + slot * STORE_SNAPSHOT_SLOT;}
static uint32_t header_crc(const snap_header_t *h) {return store_crc32(0, h, offsetof(snap_header_t, header_crc));}

bool snap_read_header(const store_flash_t *storage, unsigned slot, snap_header_t *out)
{
    if (!storage || slot >= STORE_SNAPSHOT_SLOTS) return false;
    if (storage->read(storage->ctx, slot_base(slot), out, sizeof *out) != 0) return false;
    return out->magic == SNAP_MAGIC && out->version == 1 && out->size && out->size <= SNAP_NVS_MAX &&
           !(out->size % STORE_SECTOR) && out->header_crc == header_crc(out) &&
           memchr(out->firmware, 0, sizeof out->firmware);
}

static esp_err_t erase(const store_flash_t *f, uint32_t at, uint32_t len)
{
    for (uint32_t o = 0; o < len; o += STORE_SECTOR) {
        esp_err_t err = f->erase_sector(f->ctx, at + o);
        if (err) return err;
    }
    return ESP_OK;
}

static esp_err_t crc_of(const store_flash_t *f, uint32_t at, uint32_t len, uint8_t *buffer, uint32_t *crc)
{
    *crc = 0;
    for (uint32_t o = 0; o < len; o += STORE_SECTOR) {
        esp_err_t err = f->read(f->ctx, at + o, buffer, STORE_SECTOR);
        if (err) return err;
        *crc = store_crc32(*crc, buffer, STORE_SECTOR);
    }
    return ESP_OK;
}

/* Copies `len` bytes and returns the CRC of what was read. */
static esp_err_t copy(const store_flash_t *from, uint32_t src, const store_flash_t *to, uint32_t dst,
                      uint32_t len, uint8_t *buffer, uint32_t *crc)
{
    *crc = 0;
    for (uint32_t o = 0; o < len; o += STORE_SECTOR) {
        esp_err_t err = from->read(from->ctx, src + o, buffer, STORE_SECTOR);
        if (!err) err = to->write(to->ctx, dst + o, buffer, STORE_SECTOR);
        if (err) return err;
        *crc = store_crc32(*crc, buffer, STORE_SECTOR);
    }
    return ESP_OK;
}

int snap_take(const store_flash_t *storage, const store_flash_t *nvs, uint32_t nvs_size, uint8_t reason,
              const char *firmware, uint32_t wall, int exclude, uint8_t *buffer)
{
    if (!storage || !nvs || !buffer || !nvs_size || nvs_size > SNAP_NVS_MAX || nvs_size % STORE_SECTOR) return -1;
    /* An empty slot first, otherwise the oldest copy. */
    int slot = -1;
    uint32_t oldest = UINT32_MAX, newest = 0;
    for (unsigned i = 0; i < STORE_SNAPSHOT_SLOTS; i++) {
        snap_header_t h;
        bool valid = snap_read_header(storage, i, &h);
        if (valid && h.seq > newest) newest = h.seq;
        if ((int)i == exclude) continue;
        uint32_t rank = valid ? h.seq : 0;
        if (slot < 0 || rank < oldest) {slot = (int)i; oldest = rank;}
    }
    if (slot < 0) return -1;
    uint32_t base = slot_base((unsigned)slot);
    /* Header sector first: the slot is invalid until the copy is verified. */
    if (erase(storage, base, SNAP_DATA + nvs_size)) return -1;
    uint32_t crc = 0, again = 0;
    bool stable = false;
    for (int t = 0; t < SNAP_COPY_TRIES && !stable; t++) {
        if (t && erase(storage, base + SNAP_DATA, nvs_size)) return -1;
        if (copy(nvs, 0, storage, base + SNAP_DATA, nvs_size, buffer, &crc)) return -1;
        /* NVS stays live: an identical second read proves no write ran
         * during the copy, so the copy is one consistent state. */
        if (crc_of(nvs, 0, nvs_size, buffer, &again)) return -1;
        stable = crc == again;
    }
    uint32_t stored;
    if (!stable || crc_of(storage, base + SNAP_DATA, nvs_size, buffer, &stored) || stored != crc) {
        erase(storage, base, STORE_SECTOR);
        return -1;
    }
    snap_header_t h;
    memset(&h, 0, sizeof h);
    h.magic = SNAP_MAGIC; h.version = 1; h.seq = newest + 1; h.wall = wall; h.size = nvs_size;
    h.data_crc = crc; h.reason = reason;
    if (firmware) strncpy(h.firmware, firmware, sizeof h.firmware - 1);
    h.header_crc = header_crc(&h);
    if (storage->write(storage->ctx, base, &h, sizeof h)) return -1;
    snap_header_t check;
    return snap_read_header(storage, (unsigned)slot, &check) && check.seq == h.seq ? slot : -1;
}

static bool read_control(const store_flash_t *storage, snap_control_t *c)
{
    return storage->read(storage->ctx, STORE_CONTROL_BASE, c, sizeof *c) == 0 &&
           c->magic == SNAP_CONTROL_MAGIC && c->crc == store_crc32(0, c, offsetof(snap_control_t, crc)) &&
           c->slot < STORE_SNAPSHOT_SLOTS;
}

bool snap_restore_pending(const store_flash_t *storage)
{
    snap_control_t c;
    return storage && read_control(storage, &c);
}

esp_err_t snap_cancel_restore(const store_flash_t *storage)
{
    return storage ? storage->erase_sector(storage->ctx, STORE_CONTROL_BASE) : ESP_ERR_INVALID_ARG;
}

static bool slot_intact(const store_flash_t *storage, unsigned slot, snap_header_t *h, uint8_t *buffer)
{
    uint32_t crc;
    return snap_read_header(storage, slot, h) &&
           crc_of(storage, slot_base(slot) + SNAP_DATA, h->size, buffer, &crc) == 0 && crc == h->data_crc;
}

esp_err_t snap_request_restore(const store_flash_t *storage, unsigned slot, uint8_t *buffer)
{
    snap_header_t h;
    if (!storage || !buffer || slot >= STORE_SNAPSHOT_SLOTS) return ESP_ERR_INVALID_ARG;
    if (!slot_intact(storage, slot, &h, buffer)) return ESP_ERR_INVALID_CRC;
    snap_control_t c = {SNAP_CONTROL_MAGIC, slot, h.seq, h.data_crc, 0};
    c.crc = store_crc32(0, &c, offsetof(snap_control_t, crc));
    esp_err_t err = storage->erase_sector(storage->ctx, STORE_CONTROL_BASE);
    if (!err) err = storage->write(storage->ctx, STORE_CONTROL_BASE, &c, sizeof c);
    return err ? err : snap_restore_pending(storage) ? ESP_OK : ESP_FAIL;
}

snap_boot_t snap_boot_restore(const store_flash_t *storage, const store_flash_t *nvs, uint32_t nvs_size,
                              uint8_t *buffer, unsigned *slot_out)
{
    snap_control_t c;
    if (!storage || !nvs || !buffer) return SNAP_BOOT_NONE;
    uint32_t magic = 0;
    if (storage->read(storage->ctx, STORE_CONTROL_BASE, &magic, sizeof magic) || magic == 0xFFFFFFFFu) return SNAP_BOOT_NONE;
    if (!read_control(storage, &c)) {snap_cancel_restore(storage); return SNAP_BOOT_INVALID;}
    if (slot_out) *slot_out = c.slot;
    uint8_t attempts[SNAP_RESTORE_ATTEMPTS];
    storage->read(storage->ctx, STORE_CONTROL_BASE + ATTEMPTS_AT, attempts, sizeof attempts);
    unsigned used = 0;
    while (used < SNAP_RESTORE_ATTEMPTS && attempts[used] != 0xFF) used++;
    if (used >= SNAP_RESTORE_ATTEMPTS) {snap_cancel_restore(storage); return SNAP_BOOT_GAVE_UP;}
    /* Count the attempt before touching NVS: a cut retries a bounded number of times. */
    uint8_t zero = 0;
    if (storage->write(storage->ctx, STORE_CONTROL_BASE + ATTEMPTS_AT + used, &zero, 1)) return SNAP_BOOT_FAILED;
    snap_header_t h;
    /* Fail closed: a changed or damaged copy never reaches NVS. */
    if (!slot_intact(storage, c.slot, &h, buffer) || h.seq != c.seq || h.data_crc != c.data_crc || h.size != nvs_size) {
        snap_cancel_restore(storage);
        return SNAP_BOOT_INVALID;
    }
    uint32_t crc, written;
    if (erase(nvs, 0, nvs_size) || copy(storage, slot_base(c.slot) + SNAP_DATA, nvs, 0, nvs_size, buffer, &crc) ||
        crc != h.data_crc || crc_of(nvs, 0, nvs_size, buffer, &written) || written != h.data_crc)
        return SNAP_BOOT_FAILED;          /* the request stays: retried at the next boot */
    snap_cancel_restore(storage);
    return SNAP_BOOT_RESTORED;
}

esp_err_t snap_delete(const store_flash_t *storage, unsigned slot)
{
    if (!storage || slot >= STORE_SNAPSHOT_SLOTS) return ESP_ERR_INVALID_ARG;
    snap_control_t c;
    if (read_control(storage, &c) && c.slot == slot) snap_cancel_restore(storage);
    return erase(storage, slot_base(slot), STORE_SNAPSHOT_SLOT);   /* the secrets too, not just the header */
}
/* --- snapshot core (end) --- */

#ifdef ESP_PLATFORM
#include "history.h"
#include "json_guard.h"
#include "reset_history.h"
#include "web_ui.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <time.h>

static const char *TAG = "snapshot";
static const esp_partition_t *s_nvs;
static snap_boot_t s_boot_result = SNAP_BOOT_NONE;
static unsigned s_boot_slot;

static esp_err_t nvs_read(void *ctx, uint32_t at, void *out, size_t n) {(void)ctx; return esp_partition_read(s_nvs, at, out, n);}
static esp_err_t nvs_write(void *ctx, uint32_t at, const void *data, size_t n) {(void)ctx; return esp_partition_write(s_nvs, at, data, n);}
static esp_err_t nvs_erase(void *ctx, uint32_t at) {(void)ctx; return esp_partition_erase_range(s_nvs, at, STORE_SECTOR);}
static const store_flash_t s_nvs_flash = {NULL, nvs_read, nvs_write, nvs_erase};

static const store_flash_t *nvs_flash(void)
{
    if (!s_nvs) s_nvs = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_NVS, "nvs");
    return s_nvs && s_nvs->size <= SNAP_NVS_MAX && !(s_nvs->size % STORE_SECTOR) && !s_nvs->encrypted ? &s_nvs_flash : NULL;
}

static uint32_t wall_now(void) {time_t t = time(NULL); return t > 1700000000 ? (uint32_t)t : 0;}

void settings_snapshot_boot(void)
{
    const store_flash_t *storage = storage_store_flash();
    if (!storage) return;
    uint32_t magic = 0;
    if (storage->read(storage->ctx, STORE_CONTROL_BASE, &magic, sizeof magic) || magic == 0xFFFFFFFFu) return;
    const store_flash_t *nvs = nvs_flash();
    uint8_t *buffer = malloc(STORE_SECTOR);
    if (!nvs || !buffer) {free(buffer); s_boot_result = SNAP_BOOT_FAILED; return;}
    storage_store_lock();
    s_boot_result = snap_boot_restore(storage, nvs, s_nvs->size, buffer, &s_boot_slot);
    storage_store_unlock();
    free(buffer);
    ESP_LOGW(TAG, "settings restore from copy %u: %d", s_boot_slot + 1, (int)s_boot_result);
}

void settings_snapshot_log_boot(void)
{
    static const char *const text[] = {"", "Settings restored from copy %u", "Settings copy %u was damaged or changed: not restored",
                                       "Settings restore from copy %u failed, retrying at the next start",
                                       "Settings restore from copy %u abandoned after repeated failures"};
    if (s_boot_result != SNAP_BOOT_NONE)
        history_event(HIST_EV_SETTINGS, s_boot_result == SNAP_BOOT_RESTORED ? HIST_INFO : HIST_ERROR,
                      text[s_boot_result], s_boot_slot + 1);
}

typedef struct {uint8_t reason; int exclude; int slot;} take_t;

static esp_err_t take_job(void *arg)
{
    take_t *t = arg;
    const store_flash_t *storage = storage_store_flash(), *nvs = nvs_flash();
    uint8_t *buffer = heap_caps_malloc(STORE_SECTOR, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    t->slot = -1;
    if (storage && nvs && buffer) {
        storage_store_lock();
        t->slot = snap_take(storage, nvs, s_nvs->size, t->reason, esp_app_get_description()->version, wall_now(), t->exclude, buffer);
        storage_store_unlock();
    }
    free(buffer);
    return t->slot >= 0 ? ESP_OK : ESP_FAIL;
}

static int take(uint8_t reason, int exclude)
{
    if (!storage_store_available() || !nvs_flash()) return -1;
    take_t t = {reason, exclude, -1};
    history_run_job(take_job, &t);
    if (t.slot >= 0) history_event(HIST_EV_SETTINGS, HIST_INFO, "Settings copy %d saved", t.slot + 1);
    else history_event(HIST_EV_SETTINGS, HIST_WARN, "Settings copy could not be saved");
    return t.slot;
}

int settings_snapshot_take(uint8_t reason) {return take(reason, -1);}

void settings_snapshot_before_update(uint8_t reason)
{
    if (history_snapshots_before_update() && take(reason, -1) < 0)
        ESP_LOGW(TAG, "no settings copy before the update; continuing");
}

/* --- HTTP --- */
static const char *reason_name(uint8_t r)
{
    return r == SNAP_MANUAL ? "manual" : r == SNAP_UPDATE ? "update" : r == SNAP_UPLOAD ? "upload" : r == SNAP_BEFORE_RESTORE ? "before_restore" : "other";
}

static esp_err_t get_snapshots(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    const store_flash_t *storage = storage_store_flash();
    char out[768];
    int n = snprintf(out, sizeof out, "{\"available\":%s,\"before_update\":%s,\"restore_pending\":%s,\"slots\":[",
                     storage && nvs_flash() ? "true" : "false", history_snapshots_before_update() ? "true" : "false",
                     storage && snap_restore_pending(storage) ? "true" : "false");
    for (unsigned i = 0; storage && i < STORE_SNAPSHOT_SLOTS && n > 0 && n < (int)sizeof out; i++) {
        snap_header_t h;
        storage_store_lock();
        bool valid = snap_read_header(storage, i, &h);
        storage_store_unlock();
        char firmware[sizeof h.firmware * 2];
        firmware[0] = 0;
        if (valid) history_json_escape(firmware, sizeof firmware, h.firmware);
        n += snprintf(out + n, sizeof out - n, "%s{\"slot\":%u,\"valid\":%s,\"seq\":%lu,\"t\":%lu,\"reason\":\"%s\",\"firmware\":\"%s\"}",
                      i ? "," : "", i + 1, valid ? "true" : "false", valid ? (unsigned long)h.seq : 0ul,
                      valid ? (unsigned long)h.wall : 0ul, valid ? reason_name(h.reason) : "", firmware);
    }
    if (n > 0 && n < (int)sizeof out) n += snprintf(out + n, sizeof out - n, "]}");
    if (n <= 0 || n >= (int)sizeof out) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, out);
}

static void restart_task(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(1500));
    reset_history_note_restart("settings restore");
    esp_restart();
}

typedef struct {unsigned slot; esp_err_t err;} restore_t;
static esp_err_t restore_job(void *arg)
{
    restore_t *r = arg;
    uint8_t *buffer = heap_caps_malloc(STORE_SECTOR, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    const store_flash_t *storage = storage_store_flash();
    r->err = ESP_ERR_NO_MEM;
    if (buffer && storage) {
        storage_store_lock();
        r->err = snap_request_restore(storage, r->slot, buffer);
        storage_store_unlock();
    }
    free(buffer);
    return r->err;
}
static esp_err_t delete_job(void *arg)
{
    restore_t *r = arg;
    storage_store_lock();
    r->err = snap_delete(storage_store_flash(), r->slot);
    storage_store_unlock();
    return r->err;
}

static esp_err_t reply(httpd_req_t *req, const char *status, bool ok, const char *reason)
{
    char out[160];
    if (status) httpd_resp_set_status(req, status);
    httpd_resp_set_type(req, "application/json");
    snprintf(out, sizeof out, "{\"ok\":%s%s%s%s}", ok ? "true" : "false", reason ? ",\"reason\":\"" : "", reason ? reason : "", reason ? "\"" : "");
    return httpd_resp_sendstr(req, out);
}

static esp_err_t post_snapshots(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[128];
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body size"); return ESP_FAIL;}
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) {httpd_resp_send_408(req); return ESP_FAIL;}
        received += n;
    }
    body[received] = 0;
    cJSON *root = json_guard_parse(body);
    const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action"), *slot = cJSON_GetObjectItemCaseSensitive(root, "slot");
    const cJSON *confirm = cJSON_GetObjectItemCaseSensitive(root, "confirm");
    char name[12] = "";
    if (cJSON_IsString(action)) strncpy(name, action->valuestring, sizeof name - 1);
    bool has_slot = cJSON_IsNumber(slot) && slot->valuedouble >= 1 && slot->valuedouble <= STORE_SNAPSHOT_SLOTS &&
                    slot->valuedouble == (int)slot->valuedouble;
    restore_t r = {has_slot ? (unsigned)slot->valuedouble - 1 : 0, ESP_OK};
    bool confirmed = cJSON_IsTrue(confirm);
    cJSON_Delete(root);
    if (!storage_store_available() || !nvs_flash()) return reply(req, "409 Conflict", false, "needs the 3.x flash layout");
    if (!strcmp(name, "take")) {
        int taken = settings_snapshot_take(SNAP_MANUAL);
        return taken >= 0 ? reply(req, NULL, true, NULL) : reply(req, "500 Internal Server Error", false, "copy failed");
    }
    if (!strcmp(name, "cancel")) {
        if (web_ui_require_password_session(req) != ESP_OK) return ESP_FAIL;
        storage_store_lock();
        esp_err_t err = snap_cancel_restore(storage_store_flash());
        storage_store_unlock();
        return reply(req, NULL, err == ESP_OK, err ? esp_err_to_name(err) : NULL);
    }
    if ((strcmp(name, "restore") && strcmp(name, "delete")) || !has_slot || !confirmed) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "expected action take, cancel, or restore/delete with slot 1-3 and confirm");
        return ESP_FAIL;
    }
    /* Both replace or destroy settings: the admin password, not just a session. */
    if (web_ui_require_password_session(req) != ESP_OK) return ESP_FAIL;
    if (!strcmp(name, "delete")) {
        history_run_job(delete_job, &r);
        if (!r.err) history_event(HIST_EV_SETTINGS, HIST_INFO, "Settings copy %u deleted", r.slot + 1);
        return reply(req, r.err ? "500 Internal Server Error" : NULL, !r.err, r.err ? esp_err_to_name(r.err) : NULL);
    }
    /* Keep the current settings in another slot so the restore can be undone. */
    if (take(SNAP_BEFORE_RESTORE, (int)r.slot) < 0) return reply(req, "500 Internal Server Error", false, "could not save the current settings first");
    history_run_job(restore_job, &r);
    if (r.err) return reply(req, r.err == ESP_ERR_INVALID_CRC ? "409 Conflict" : "500 Internal Server Error", false,
                            r.err == ESP_ERR_INVALID_CRC ? "copy damaged" : esp_err_to_name(r.err));
    history_event(HIST_EV_SETTINGS, HIST_WARN, "Restore of settings copy %u requested; restarting", r.slot + 1);
    esp_err_t err = reply(req, NULL, true, NULL);
    if (xTaskCreate(restart_task, "snap_restart", 2048, NULL, 5, NULL) != pdPASS) esp_restart();
    return err;
}

esp_err_t settings_snapshot_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/system/snapshots", .method = HTTP_GET, .handler = get_snapshots},
        {.uri = "/api/system/snapshots", .method = HTTP_POST, .handler = post_snapshots}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
