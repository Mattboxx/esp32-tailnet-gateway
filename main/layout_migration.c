/* 2.x -> 3.x flash-layout migration; see layout_migration.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "layout_migration.h"
#include "ota.h"
#include "ota_remote.h"
#include "ota_validation.h"
#include "nvs.h"
#include "nvs_params.h"
#include "web_ui.h"
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_image_format.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_rom_crc.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/md5.h"
#include "mbedtls/sha256.h"
#include "sdkconfig.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#define TAG "migration"

/* --- migration core (begin) --- */
#define MIG_TABLE_OFFSET 0x8000u
#define MIG_TABLE_SIZE 0xC00u
#define MIG_BOOT_LIMIT 0x8000u          /* bootloader must end before the table */
#define MIG_V3_OTA1 0x3A0000u
#define MIG_V3_SLOT 0x380000u
#define MIG_OTADATA 0x19000u

typedef struct {const char *name; uint8_t type, subtype; uint32_t offset, size;} mig_expected_t;
static const mig_expected_t MIG_V2[] = {
    {"nvs", 1, 0x02, 0x9000, 0x10000}, {"otadata", 1, 0x00, 0x19000, 0x2000}, {"phy_init", 1, 0x01, 0x1b000, 0x1000},
    {"ota_0", 0, 0x10, 0x20000, 0x1E0000}, {"ota_1", 0, 0x11, 0x200000, 0x1E0000}, {"coredump", 1, 0x03, 0x3E0000, 0x10000}};
static const mig_expected_t MIG_V3[] = {
    {"nvs", 1, 0x02, 0x9000, 0x10000}, {"otadata", 1, 0x00, 0x19000, 0x2000}, {"phy_init", 1, 0x01, 0x1b000, 0x1000},
    {"ota_0", 0, 0x10, 0x20000, 0x380000}, {"ota_1", 0, 0x11, 0x3A0000, 0x380000}, {"coredump", 1, 0x03, 0x720000, 0x10000},
    {"storage", 1, 0x83, 0x730000, 0xD0000}};

static uint32_t mig_le32(const uint8_t *p) {return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;}
static void mig_put32(uint8_t *p, uint32_t v) {p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);}

/* ESP-IDF partition table: 32-byte entries (0x50AA magic), then an MD5
 * entry (0xEBEB) over the preceding entries, then 0xFF. */
int mig_parse_table(const uint8_t *bin, size_t len, mig_part_t *out, int max, int *md5_index)
{
    int count = 0;
    if (md5_index) *md5_index = -1;
    if (!bin || !out || max <= 0) return -1;
    for (size_t at = 0; at + 32 <= len; at += 32) {
        const uint8_t *e = bin + at;
        if (e[0] == 0xAA && e[1] == 0x50) {
            if (count == max) return -1;
            mig_part_t *p = &out[count++];
            p->type = e[2]; p->subtype = e[3];
            p->offset = mig_le32(e + 4); p->size = mig_le32(e + 8);
            memcpy(p->name, e + 12, 16); p->name[16] = 0;
            if (!memchr(e + 12, 0, 16)) return -1;   /* labels must be terminated */
            continue;
        }
        if (e[0] == 0xEB && e[1] == 0xEB) {if (md5_index) *md5_index = (int)(at / 32); return count;}
        bool blank = true;
        for (int i = 0; i < 32; i++) blank &= e[i] == 0xFF;
        return blank ? count : -1;
    }
    return -1;   /* no terminator inside the table area */
}

static bool mig_matches(const mig_part_t *parts, int count, const mig_expected_t *want, int wanted)
{
    if (count != wanted) return false;
    for (int i = 0; i < wanted; i++)
        if (strcmp(parts[i].name, want[i].name) || parts[i].type != want[i].type || parts[i].subtype != want[i].subtype
            || parts[i].offset != want[i].offset || parts[i].size != want[i].size) return false;
    return true;
}

int mig_layout_kind(const mig_part_t *parts, int count)
{
    if (mig_matches(parts, count, MIG_V2, (int)(sizeof MIG_V2 / sizeof MIG_V2[0]))) return MIG_LAYOUT_V2;
    if (mig_matches(parts, count, MIG_V3, (int)(sizeof MIG_V3 / sizeof MIG_V3[0]))) return MIG_LAYOUT_V3;
    return MIG_LAYOUT_UNKNOWN;
}

/* esp_image_header_t: magic, segment count, SPI mode, speed|size<<4, entry,
 * wp pin, drive strengths, chip id (offset 12, little endian). */
bool mig_bootloader_ok(const uint8_t *b, size_t len)
{
    return b && len >= 0x1000 && len <= MIG_BOOT_LIMIT && b[0] == 0xE9 && b[1] >= 1 && b[1] <= 16
        && (b[3] >> 4) == 3 /* 8 MB */ && (b[12] | b[13] << 8) == 9 /* ESP32-S3 */;
}

bool mig_app_ok(const uint8_t *b, size_t len, const char *project, const char *tag)
{
    const size_t desc = 24 + 8;   /* image header + first segment header */
    if (!b || !project || !tag || len < desc + 80) return false;
    if (b[0] != 0xE9 || (b[12] | b[13] << 8) != 9 || mig_le32(b + desc) != 0xABCD5432u) return false;
    const char *version = (const char *)b + desc + 16, *name = (const char *)b + desc + 48;
    if (!memchr(version, 0, 32) || !memchr(name, 0, 32) || strcmp(name, project)) return false;
    const char *expected = tag[0] == 'v' ? tag + 1 : tag;
    return !strcmp(version, expected) && version[0] >= '3' && version[0] <= '9' && version[1] == '.';
}

uint32_t mig_crc32_le(uint32_t crc, const uint8_t *buf, size_t len)
{
    crc = ~crc;
    for (size_t i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

/* esp_ota_select_entry_t: ota_seq, seq_label[20], ota_state, crc. */
static void mig_entry(uint8_t e[32], uint32_t seq, uint32_t state)
{
    memset(e, 0xFF, 32);
    mig_put32(e, seq);
    mig_put32(e + 24, state);
    mig_put32(e + 28, mig_crc32_le(UINT32_MAX, e, 4));
}

void mig_otadata(uint8_t first[32], uint8_t second[32])
{
    mig_entry(first, 2, 0x0 /* ESP_OTA_IMG_NEW: ota_1, confirmed by 3.x */);
    mig_entry(second, 1, 0x2 /* ESP_OTA_IMG_VALID: ota_0, the bridge */);
}

bool mig_pick_release(const cJSON *releases, bool beta, mig_target_t *out)
{
    static const char *const names[3] = MIG_ASSETS;
    static const uint32_t limits[3] = {MIG_V3_SLOT, MIG_BOOT_LIMIT, MIG_TABLE_SIZE};
    ota_version_t best = {0};
    bool found = false;
    const cJSON *release;
    if (!cJSON_IsArray(releases) || !out) return false;
    cJSON_ArrayForEach(release, releases) {
        const cJSON *name = cJSON_GetObjectItemCaseSensitive(release, "tag_name");
        const cJSON *pre = cJSON_GetObjectItemCaseSensitive(release, "prerelease");
        const cJSON *draft = cJSON_GetObjectItemCaseSensitive(release, "draft");
        const cJSON *assets = cJSON_GetObjectItemCaseSensitive(release, "assets");
        ota_version_t version;
        if (!cJSON_IsObject(release) || !cJSON_IsFalse(draft) || !cJSON_IsBool(pre) || (!beta && cJSON_IsTrue(pre))
            || !cJSON_IsString(name) || !ota_version_parse(name->valuestring, &version) || version.scheme != 1
            || version.upstream[0] < 3 || (version.stage < 4 && !cJSON_IsTrue(pre)) || !cJSON_IsArray(assets)
            || (found && ota_version_compare(&version, &best) <= 0)) continue;
        mig_target_t candidate = {0};
        int have = 0;
        for (int i = 0; i < 3; i++) {
            const cJSON *asset;
            cJSON_ArrayForEach(asset, assets) {
                const cJSON *an = cJSON_GetObjectItemCaseSensitive(asset, "name");
                const cJSON *as = cJSON_GetObjectItemCaseSensitive(asset, "state");
                const cJSON *az = cJSON_GetObjectItemCaseSensitive(asset, "size");
                const cJSON *ah = cJSON_GetObjectItemCaseSensitive(asset, "digest");
                if (!cJSON_IsString(an) || strcmp(an->valuestring, names[i]) || !cJSON_IsString(as)
                    || strcmp(as->valuestring, "uploaded") || !cJSON_IsNumber(az) || az->valuedouble < 32
                    || az->valuedouble > limits[i] || az->valuedouble != (double)(uint32_t)az->valuedouble
                    || !cJSON_IsString(ah) || !ota_digest_parse(ah->valuestring, candidate.digest[i])) continue;
                candidate.size[i] = (uint32_t)az->valuedouble;
                have |= 1 << i;
                break;
            }
        }
        if (have != 7) continue;
        snprintf(candidate.tag, sizeof candidate.tag, "%s", name->valuestring);
        *out = candidate; best = version; found = true;
    }
    return found;
}
/* --- migration core (end) --- */

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static mig_status_t s_status;

static void set_state(uint8_t state, unsigned progress, const char *error)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.state = state;
    s_status.progress = progress;
    if (error) snprintf(s_status.error, sizeof s_status.error, "%s", error);
    xSemaphoreGive(s_lock);
    if (error && error[0]) ESP_LOGW(TAG, "%s", error);
}

static int read_layout(void)
{
    uint8_t *table = malloc(MIG_TABLE_SIZE);
    mig_part_t parts[12];
    int md5 = -1, kind = MIG_LAYOUT_UNKNOWN;
    if (table && esp_flash_read(NULL, table, MIG_TABLE_OFFSET, MIG_TABLE_SIZE) == ESP_OK) {
        int count = mig_parse_table(table, MIG_TABLE_SIZE, parts, 12, &md5);
        if (count > 0) kind = mig_layout_kind(parts, count);
    }
    free(table);
    return kind;
}

void layout_migration_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    uint32_t physical = 0;
    (void)esp_flash_get_physical_size(NULL, &physical);
    int layout = read_layout();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.layout = (uint8_t)layout;
    s_status.physical_flash = physical;
    s_status.needed = layout == MIG_LAYOUT_V2;
#if CONFIG_TSR_MIGRATION_BRIDGE
    s_status.bridge = true;
    s_status.supported = layout == MIG_LAYOUT_V2 && physical >= 8u * 1024 * 1024;
#endif
    xSemaphoreGive(s_lock);
#if CONFIG_TSR_MIGRATION_BRIDGE
    /* After the bridge copied itself into ota_0 it continues by itself: the
     * owner already confirmed the migration before that restart. */
    nvs_handle_t nvs;
    uint8_t resume = 0;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs) == ESP_OK) {
        if (nvs_get_u8(nvs, "mig_resume", &resume) == ESP_OK) {nvs_erase_key(nvs, "mig_resume"); nvs_commit(nvs);}
        nvs_close(nvs);
    }
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (resume && running && running->address == 0x20000 && s_status.supported) {
        ESP_LOGW(TAG, "continuing the layout migration after the self-copy");
        (void)layout_migration_start();
    }
#endif
}

void layout_migration_get_status(mig_status_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_status;
    xSemaphoreGive(s_lock);
}

#if CONFIG_TSR_MIGRATION_BRIDGE
/* --- network --- */
typedef struct {
    uint8_t *buffer; size_t used, cap;               /* memory sink */
    uint32_t flash_at, flash_end;                    /* flash sink (firmware) */
    mbedtls_sha256_context sha;
    char *location;
} sink_t;

static bool test_source(void) {return CONFIG_TSR_MIGRATION_SOURCE_URL[0] != 0;}

static bool url_allowed(const char *url, const char *asset)
{
    if (test_source()) {
        size_t n = strlen(CONFIG_TSR_MIGRATION_SOURCE_URL);
        return !strncmp(url, CONFIG_TSR_MIGRATION_SOURCE_URL, n) && strlen(url) < 256;
    }
    return asset ? ota_download_url_allowed_for(url, asset) : false;
}

static esp_err_t http_event(esp_http_client_event_t *event)
{
    sink_t *s = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_HEADER && s->location && event->header_key && !strcasecmp(event->header_key, "Location")) {
        if (strlen(event->header_value) >= 2048) return ESP_FAIL;
        strcpy(s->location, event->header_value);
    }
    return ESP_OK;
}

/* Erase-as-you-go flash sink: sectors are erased right before first use. */
static esp_err_t sink_write(sink_t *s, const uint8_t *data, size_t n)
{
    mbedtls_sha256_update(&s->sha, data, n);
    if (s->buffer) {
        if (n > s->cap - s->used) return ESP_ERR_INVALID_SIZE;
        memcpy(s->buffer + s->used, data, n);
        s->used += n;
        return ESP_OK;
    }
    if (n > s->flash_end - s->flash_at) return ESP_ERR_INVALID_SIZE;
    uint32_t start = s->flash_at, end = start + (uint32_t)n;
    uint32_t first = (start + 0xFFFu) & ~0xFFFu;
    for (uint32_t sector = first; sector < end; sector += 0x1000) {
        esp_err_t err = esp_flash_erase_region(NULL, sector, 0x1000);
        if (err != ESP_OK) return err;
    }
    esp_err_t err = esp_flash_write(NULL, data, start, (uint32_t)n);
    s->flash_at = end;
    s->used += n;
    return err;
}

/* GET with up to three redirects inside the allow-list, exact size and SHA-256. */
static bool fetch(const char *url, const char *asset, uint32_t size, const unsigned char digest[32], sink_t *s, unsigned progress_base, unsigned progress_span)
{
    char *location = malloc(2048), *current = malloc(2048);
    uint8_t *chunk = malloc(2048);
    bool ok = false;
    esp_http_client_handle_t client = NULL;
    if (!location || !current || !chunk || strlen(url) >= 2048 || !url_allowed(url, asset)) goto done;
    strcpy(current, url);
    s->location = location;
    mbedtls_sha256_init(&s->sha);
    if (mbedtls_sha256_starts(&s->sha, 0) != 0) goto done;
    esp_http_client_config_t config = {
        .url = current, .disable_auto_redirect = true, .timeout_ms = 10000, .buffer_size = 2048, .buffer_size_tx = 1024,
        .event_handler = http_event, .user_data = s,
        .crt_bundle_attach = test_source() ? NULL : esp_crt_bundle_attach,
    };
    client = esp_http_client_init(&config);
    if (!client) goto done;
    esp_http_client_set_header(client, "User-Agent", "Mattboxx-ESP32-migration");
    esp_http_client_set_header(client, "Accept", "application/octet-stream");
    bool opened = false;
    for (int redirects = 0; redirects <= 3; redirects++) {
        location[0] = 0;
        if (esp_http_client_open(client, 0) != ESP_OK) break;
        int64_t length = esp_http_client_fetch_headers(client);
        int code = esp_http_client_get_status_code(client);
        if (code == 200 && length == (int64_t)size) {opened = true; break;}
        esp_http_client_close(client);
        if ((code != 301 && code != 302 && code != 303 && code != 307 && code != 308) || test_source()
            || !url_allowed(location, asset) || esp_http_client_set_url(client, location) != ESP_OK) break;
    }
    if (!opened) goto done;
    uint32_t got = 0;
    int64_t deadline = esp_timer_get_time() + 300LL * 1000000;
    while (got < size && esp_timer_get_time() < deadline) {
        int n = esp_http_client_read(client, (char *)chunk, size - got > 2048 ? 2048 : (int)(size - got));
        if (n <= 0 || sink_write(s, chunk, (size_t)n) != ESP_OK) goto done;
        got += (uint32_t)n;
        set_state(MIG_DOWNLOADING, progress_base + (unsigned)((uint64_t)got * progress_span / size), NULL);
    }
    unsigned char actual[32];
    ok = got == size && esp_http_client_is_complete_data_received(client)
        && mbedtls_sha256_finish(&s->sha, actual) == 0 && !memcmp(actual, digest, 32);
done:
    if (client) esp_http_client_cleanup(client);
    mbedtls_sha256_free(&s->sha);
    s->location = NULL;
    free(location); free(current); free(chunk);
    return ok;
}

/* Release list from GitHub (fallback to the previous repository name only on
 * 404), or migration.json of the bench source. */
/* The release list carries every release's notes and asset details: ten
 * releases measured 186 KB, twenty 285 KB (2026-10-25). Ask for ten and keep
 * room to grow; the buffer is PSRAM, freed right after. */
static bool find_target(mig_target_t *target, unsigned *answered, const char **why)
{
    enum {LIMIT = 512 * 1024};
    char *body = heap_caps_malloc(LIMIT + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!body) return false;
    bool found = false;
    for (unsigned repo = 0; repo < (test_source() ? 1u : OTA_REPO_COUNT) && !found; repo++) {
        char url[160];
        if (test_source()) snprintf(url, sizeof url, "%s/migration.json", CONFIG_TSR_MIGRATION_SOURCE_URL);
        else snprintf(url, sizeof url, "https://api.github.com/repos/%s/releases?per_page=10", ota_repo(repo));
        esp_http_client_config_t config = {.url = url, .timeout_ms = 10000, .buffer_size = 2048,
            .crt_bundle_attach = test_source() ? NULL : esp_crt_bundle_attach};
        esp_http_client_handle_t client = esp_http_client_init(&config);
        if (!client) break;
        esp_http_client_set_header(client, "User-Agent", "Mattboxx-ESP32-migration");
        esp_http_client_set_header(client, "Accept", "application/vnd.github+json");
        int code = 0, used = 0;
        if (esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0) {
            code = esp_http_client_get_status_code(client);
            int n;
            while (used < LIMIT && (n = esp_http_client_read(client, body + used, LIMIT - used)) > 0) used += n;
        }
        esp_http_client_cleanup(client);
        if (code == 404 && !test_source()) continue;
        if (code != 200) {*why = code == 403 || code == 429 ? "GitHub rate limit; retry later; nothing was changed"
                                                            : "GitHub releases could not be read; nothing was changed"; break;}
        if (used >= LIMIT) {*why = "GitHub release list too large to read; nothing was changed"; break;}
        body[used] = 0;
        cJSON *json = cJSON_ParseWithLength(body, (size_t)used);
        ota_remote_state_t updates; ota_remote_get_state(&updates);
        /* A bench source serves development builds: any channel. */
        found = mig_pick_release(json, test_source() || updates.config.beta_channel, target);
        cJSON_Delete(json);
        if (found) *answered = repo;   /* downloads use the repository that answered */
    }
    free(body);
    return found;
}

static void asset_url(char *out, size_t n, unsigned repo, const char *tag, const char *asset)
{
    if (test_source()) snprintf(out, n, "%s/%s", CONFIG_TSR_MIGRATION_SOURCE_URL, asset);
    else snprintf(out, n, "https://github.com/%s/releases/download/%s/%s", ota_repo(repo), tag, asset);
}

/* Erases and writes one region, then reads it back; retries a mismatch. */
static bool write_verified(uint32_t at, const uint8_t *data, size_t len)
{
    uint8_t *check = malloc(len);
    bool ok = false;
    for (int attempt = 0; check && attempt < 3 && !ok; attempt++) {
        uint32_t erase = (uint32_t)((len + 0xFFF) & ~(size_t)0xFFF);
        ok = esp_flash_erase_region(NULL, at, erase) == ESP_OK && esp_flash_write(NULL, data, at, (uint32_t)len) == ESP_OK
            && esp_flash_read(NULL, check, at, (uint32_t)len) == ESP_OK && !memcmp(check, data, len);
    }
    free(check);
    return ok;
}

static bool copy_self_to_ota0(void)
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    const esp_partition_t *ota0 = esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, NULL);
    esp_image_metadata_t meta = {0};
    const esp_partition_pos_t pos = {.offset = running->address, .size = running->size};
    if (!ota0 || esp_image_verify(ESP_IMAGE_VERIFY_SILENT, &pos, &meta) != ESP_OK) return false;
    esp_ota_handle_t ota;
    uint8_t *chunk = malloc(4096);
    bool ok = chunk && esp_ota_begin(ota0, meta.image_len, &ota) == ESP_OK;
    for (uint32_t at = 0; ok && at < meta.image_len; at += 4096) {
        uint32_t n = meta.image_len - at > 4096 ? 4096 : meta.image_len - at;
        ok = esp_partition_read(running, at, chunk, n) == ESP_OK && esp_ota_write(ota, chunk, n) == ESP_OK;
        set_state(MIG_COPYING_SELF, (unsigned)((uint64_t)at * 100 / meta.image_len), NULL);
    }
    free(chunk);
    if (!ok) return false;
    return esp_ota_end(ota) == ESP_OK && esp_ota_set_boot_partition(ota0) == ESP_OK;
}

static void migration_task(void *arg)
{
    (void)arg;
    mig_target_t target;
    uint8_t *boot = NULL, *table = NULL;
    const char *failure = NULL;
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (!running) {failure = "running partition unknown"; goto fail;}
    if (running->address != 0x20000) {
        /* Move out of the 2.x ota_1, which the 3.x ota_1 overlaps. */
        set_state(MIG_COPYING_SELF, 0, "");
        if (!copy_self_to_ota0()) {failure = "could not copy the bridge into ota_0; nothing was changed"; goto fail;}
        nvs_handle_t nvs;
        if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs) == ESP_OK) {nvs_set_u8(nvs, "mig_resume", 1); nvs_commit(nvs); nvs_close(nvs);}
        ota_writer_release();
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    }
    set_state(MIG_CHECKING, 0, "");
    /* After the self-copy restart this runs at boot: wait for the uplink
     * (bounded) instead of failing before WiFi has an address. */
    for (int i = 0; i < 120; i++) {
        esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        esp_netif_ip_info_t info = {0};
        if (sta && esp_netif_is_netif_up(sta) && esp_netif_get_ip_info(sta, &info) == ESP_OK && info.ip.addr) break;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    unsigned repo = 0;
    const char *why = NULL;
    if (!find_target(&target, &repo, &why)) {failure = why ? why : "no 3.x release with bootloader, partition table and image found on this update channel; nothing was changed"; goto fail;}
    xSemaphoreTake(s_lock, portMAX_DELAY);
    snprintf(s_status.target, sizeof s_status.target, "%s", target.tag);
    xSemaphoreGive(s_lock);
    char url[200];
    boot = heap_caps_malloc(target.size[1], MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    table = heap_caps_malloc(target.size[2], MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!boot || !table) {failure = "not enough memory; nothing was changed"; goto fail;}
    sink_t s = {.buffer = table, .cap = target.size[2]};
    asset_url(url, sizeof url, repo, target.tag, "partitions.bin");
    if (!fetch(url, "partitions.bin", target.size[2], target.digest[2], &s, 0, 2)) {failure = "partition table download or digest failed; nothing was changed"; goto fail;}
    mig_part_t parts[12];
    int md5_index = -1, count = mig_parse_table(table, target.size[2], parts, 12, &md5_index);
    if (count <= 0 || mig_layout_kind(parts, count) != MIG_LAYOUT_V3 || md5_index != count) {failure = "unexpected 3.x partition table; nothing was changed"; goto fail;}
    unsigned char md5[16];
    if (mbedtls_md5(table, (size_t)count * 32, md5) != 0 || memcmp(md5, table + md5_index * 32 + 16, 16)) {failure = "partition table checksum mismatch; nothing was changed"; goto fail;}
    s = (sink_t){.buffer = boot, .cap = target.size[1]};
    asset_url(url, sizeof url, repo, target.tag, "bootloader.bin");
    if (!fetch(url, "bootloader.bin", target.size[1], target.digest[1], &s, 2, 2) || !mig_bootloader_ok(boot, target.size[1])) {
        failure = "bootloader download, digest or header check failed; nothing was changed"; goto fail;
    }
    /* The 2.x bootloader header limits this session to 4 MB: open the
     * physical flash (checked >= 8 MB) for the new ota_1 above 4 MB. */
    uint32_t physical = 0;
    if (esp_flash_get_physical_size(NULL, &physical) != ESP_OK || physical < 8u * 1024 * 1024) {failure = "flash smaller than 8 MB; nothing was changed"; goto fail;}
    if (esp_flash_default_chip->size < 8u * 1024 * 1024) esp_flash_default_chip->size = 8u * 1024 * 1024;
    if (running->address + running->size > MIG_V3_OTA1) {failure = "bridge image overlaps the new slot; nothing was changed"; goto fail;}
    s = (sink_t){.flash_at = MIG_V3_OTA1, .flash_end = MIG_V3_OTA1 + target.size[0]};
    asset_url(url, sizeof url, repo, target.tag, "firmware.bin");
    if (!fetch(url, "firmware.bin", target.size[0], target.digest[0], &s, 4, 86)) {failure = "3.x image download or digest failed; the bridge keeps running"; goto fail;}
    set_state(MIG_VERIFYING, 90, NULL);
    /* Read back the written image: digest and app descriptor. */
    {
        uint8_t *chunk = malloc(4096);
        mbedtls_sha256_context sha; mbedtls_sha256_init(&sha);
        bool ok = chunk && mbedtls_sha256_starts(&sha, 0) == 0;
        unsigned char actual[32];
        for (uint32_t at = 0; ok && at < target.size[0]; at += 4096) {
            uint32_t n = target.size[0] - at > 4096 ? 4096 : target.size[0] - at;
            ok = esp_flash_read(NULL, chunk, MIG_V3_OTA1 + at, n) == ESP_OK && mbedtls_sha256_update(&sha, chunk, n) == 0;
            if (ok && at == 0) ok = mig_app_ok(chunk, n, esp_app_get_description()->project_name, target.tag);
        }
        ok = ok && mbedtls_sha256_finish(&sha, actual) == 0 && !memcmp(actual, target.digest[0], 32);
        mbedtls_sha256_free(&sha);
        free(chunk);
        if (!ok) {failure = "written 3.x image does not verify; the bridge keeps running"; goto fail;}
    }
    /* Point of no return, each step leaves a bootable device:
     * 1. 3.x bootloader (8 MB header) still boots the 2.x table and the bridge;
     * 2. 3.x table: ota_0 at 0x20000 is still the bridge;
     * 3. otadata: ota_1 (3.x, NEW) first, ota_0 (bridge, VALID) as fallback. */
    set_state(MIG_WRITING_BOOT, 92, "");
    uint8_t first[32], second[32];
    mig_otadata(first, second);
    uint8_t sector0[32], sector1[32];
    memcpy(sector0, first, 32); memcpy(sector1, second, 32);
    if (esp_rom_crc32_le(UINT32_MAX, sector0, 4) != mig_le32(sector0 + 28)) {failure = "otadata checksum self-test failed; nothing written"; goto fail;}
    if (!write_verified(0x0, boot, target.size[1])) {failure = "BOOTLOADER WRITE FAILED: do not power off; reinstall over USB if it does not start"; goto fail;}
    set_state(MIG_WRITING_BOOT, 95, NULL);
    if (!write_verified(MIG_TABLE_OFFSET, table, target.size[2])) {failure = "PARTITION TABLE WRITE FAILED: do not power off; reinstall over USB if it does not start"; goto fail;}
    set_state(MIG_WRITING_BOOT, 98, NULL);
    if (!write_verified(MIG_OTADATA, sector0, 32) || !write_verified(MIG_OTADATA + 0x1000, sector1, 32)) {
        failure = "otadata write failed: the next start may run the bridge again"; goto fail;
    }
    set_state(MIG_DONE, 100, "");
    ESP_LOGW(TAG, "layout migrated; restarting into %s", target.tag);
    free(boot); free(table);
    vTaskDelay(pdMS_TO_TICKS(3000));
    esp_restart();
fail:
    free(boot); free(table);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_status.busy = false;
    xSemaphoreGive(s_lock);
    set_state(MIG_FAILED, 0, failure ? failure : "failed");
    ota_writer_release();
    vTaskDelete(NULL);
}
#endif /* CONFIG_TSR_MIGRATION_BRIDGE */

esp_err_t layout_migration_start(void)
{
#if CONFIG_TSR_MIGRATION_BRIDGE
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool ok = s_status.supported && !s_status.busy;
    if (ok) {s_status.busy = true; s_status.error[0] = 0; s_status.state = MIG_CHECKING; s_status.progress = 0;}
    xSemaphoreGive(s_lock);
    if (!ok) return ESP_ERR_INVALID_STATE;
    ota_remote_state_t updates; ota_remote_get_state(&updates);
    /* One flash writer at a time: no update upload or GitHub install meanwhile. */
    if (updates.busy || !ota_writer_try_acquire()) {
        xSemaphoreTake(s_lock, portMAX_DELAY); s_status.busy = false; s_status.state = MIG_IDLE; xSemaphoreGive(s_lock);
        return ESP_ERR_INVALID_STATE;
    }
    /* Internal-RAM stack: this task writes flash. */
    if (xTaskCreate(migration_task, "migration", 8192, NULL, 4, NULL) != pdPASS) {
        ota_writer_release();
        xSemaphoreTake(s_lock, portMAX_DELAY); s_status.busy = false; s_status.state = MIG_IDLE; xSemaphoreGive(s_lock);
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
#else
    return ESP_ERR_NOT_SUPPORTED;
#endif
}

/* --- HTTP --- */
static const char *const STATE_NAMES[] = {"idle", "copying_self", "checking", "downloading", "verifying", "writing_boot", "done", "failed"};

static esp_err_t get_migration(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    mig_status_t s; layout_migration_get_status(&s);
    cJSON *root = cJSON_CreateObject();
    if (!root) {httpd_resp_send_500(req); return ESP_FAIL;}
    cJSON_AddStringToObject(root, "layout", s.layout == MIG_LAYOUT_V2 ? "2.x" : s.layout == MIG_LAYOUT_V3 ? "3.x" : "unknown");
    cJSON_AddBoolToObject(root, "bridge", s.bridge);
    cJSON_AddBoolToObject(root, "needed", s.needed);
    cJSON_AddBoolToObject(root, "supported", s.supported);
    cJSON_AddBoolToObject(root, "busy", s.busy);
    cJSON_AddNumberToObject(root, "physical_flash", s.physical_flash);
    cJSON_AddStringToObject(root, "state", s.state < sizeof STATE_NAMES / sizeof STATE_NAMES[0] ? STATE_NAMES[s.state] : "unknown");
    cJSON_AddNumberToObject(root, "progress", s.progress);
    cJSON_AddStringToObject(root, "target", s.target);
    cJSON_AddStringToObject(root, "error", s.error);
    char *body = cJSON_PrintUnformatted(root); cJSON_Delete(root);
    if (!body) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, body); free(body); return err;
}

static esp_err_t post_migration(httpd_req_t *req)
{
    /* Rewrites the bootloader: a password-backed session, like updates. */
    if (web_ui_require_password_session(req) != ESP_OK) return ESP_FAIL;
    char body[64] = "";
    int total = req->content_len;
    if (total <= 0 || total >= (int)sizeof body || httpd_req_recv(req, body, total) != total) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body"); return ESP_FAIL;}
    body[total] = 0;
    cJSON *json = cJSON_Parse(body);
    const cJSON *confirm = cJSON_GetObjectItemCaseSensitive(json, "confirm");
    bool confirmed = cJSON_IsString(confirm) && !strcmp(confirm->valuestring, "MIGRATE");
    cJSON_Delete(json);
    if (!confirmed) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "confirmation missing"); return ESP_FAIL;}
    esp_err_t err = layout_migration_start();
    httpd_resp_set_type(req, "application/json");
    if (err != ESP_OK) {
        httpd_resp_set_status(req, err == ESP_ERR_NOT_SUPPORTED ? "501 Not Implemented" : err == ESP_ERR_NO_MEM ? "503 Service Unavailable" : "409 Conflict");
        return httpd_resp_sendstr(req, "{\"ok\":false}");
    }
    httpd_resp_set_status(req, "202 Accepted");
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

esp_err_t layout_migration_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/system/migration", .method = HTTP_GET, .handler = get_migration},
        {.uri = "/api/system/migration", .method = HTTP_POST, .handler = post_migration}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
