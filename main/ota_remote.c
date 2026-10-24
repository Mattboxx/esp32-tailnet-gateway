/* User-authorized GitHub updates for the Mattboxx edition only.
 * No telemetry, arbitrary update URL, token, NVS upload or plaintext TLS fallback.
 * SPDX-License-Identifier: MIT */
#include "ota_remote.h"
#include "ota_validation.h"
#include "ota.h"
#include "ota_flash.h"
#include "nvs_params.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "nvs.h"

#define CHECK_BIT 1U
#define INSTALL_BIT 2U
#define CONFIG_BIT 4U
#define JSON_LIMIT (256U * 1024U)
#define DAILY_US (24LL * 3600 * 1000000)
#define WORKER_STACK 16384
#define OTA_NOINLINE __attribute__((noinline))
static StaticSemaphore_t s_lock_storage;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;
static bool s_flash_ready;
static ota_remote_state_t s_state;
static unsigned char s_digest[32];
typedef struct { uint8_t schema, enabled, automatic, beta; int32_t hour; } saved_config_t;

static void status_set(const char *status)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    strlcpy(s_state.status, status, sizeof s_state.status);
    xSemaphoreGive(s_lock);
}

void ota_remote_get_state(ota_remote_state_t *out)
{
    if (!out) return;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_state;
    xSemaphoreGive(s_lock);
}

bool ota_remote_select_release(const cJSON *releases, const char *running,
                               bool beta, const char *asset_name, bool reinstall, uint32_t partition_size,
                               char tag[32], uint32_t *size, unsigned char digest[32])
{
    ota_version_t current, best;
    if (!cJSON_IsArray(releases) || !asset_name || !ota_version_parse(running, &current)) return false;
    best = current;
    bool found = false;
    const cJSON *release;
    cJSON_ArrayForEach(release, releases) {
        const cJSON *name = cJSON_GetObjectItemCaseSensitive(release, "tag_name");
        const cJSON *pre = cJSON_GetObjectItemCaseSensitive(release, "prerelease");
        const cJSON *draft = cJSON_GetObjectItemCaseSensitive(release, "draft");
        ota_version_t version;
        if (!cJSON_IsObject(release) || !cJSON_IsFalse(draft) || !cJSON_IsBool(pre) ||
            (!beta && cJSON_IsTrue(pre)) || !cJSON_IsString(name) ||
            !ota_version_parse(name->valuestring, &version) ||
            (version.stage < 4 && !cJSON_IsTrue(pre))) continue;
        /* Newer only; the running version itself only for another language. */
        int order = ota_version_compare(&version, &best);
        if (order < 0 || (order == 0 && (found || !reinstall))) continue;
        const cJSON *assets = cJSON_GetObjectItemCaseSensitive(release, "assets"), *asset;
        if (!cJSON_IsArray(assets)) continue;
        cJSON_ArrayForEach(asset, assets) {
            const cJSON *an = cJSON_GetObjectItemCaseSensitive(asset, "name");
            const cJSON *az = cJSON_GetObjectItemCaseSensitive(asset, "size");
            const cJSON *ah = cJSON_GetObjectItemCaseSensitive(asset, "digest");
            const cJSON *as = cJSON_GetObjectItemCaseSensitive(asset, "state");
            unsigned char hash[32];
            if (!cJSON_IsString(an) || strcmp(an->valuestring, asset_name) ||
                !cJSON_IsString(as) || strcmp(as->valuestring, "uploaded") ||
                !cJSON_IsNumber(az) || az->valuedouble < 288 || az->valuedouble > partition_size ||
                az->valuedouble != (double)(uint32_t)az->valuedouble ||
                !cJSON_IsString(ah) || !ota_digest_parse(ah->valuestring, hash)) continue;
            best = version; found = true;
            strlcpy(tag, name->valuestring, 32);
            *size = (uint32_t)az->valuedouble;
            memcpy(digest, hash, sizeof hash);
            break;
        }
    }
    return found;
}

typedef struct { char *body; size_t used; bool overflow; char *location; } http_buffer_t;
static esp_err_t http_event(esp_http_client_event_t *event)
{
    http_buffer_t *b = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && b->body && event->data_len > 0) {
        if ((size_t)event->data_len > JSON_LIMIT - b->used) { b->overflow = true; return ESP_FAIL; }
        memcpy(b->body + b->used, event->data, event->data_len);
        b->used += (size_t)event->data_len; b->body[b->used] = '\0';
    }
    if (event->event_id == HTTP_EVENT_ON_HEADER && b->location && event->header_key &&
        !strcasecmp(event->header_key, "Location")) {
        size_t n = strlen(event->header_value);
        if (n >= 2048) return ESP_FAIL;
        memcpy(b->location, event->header_value, n + 1);
    }
    return ESP_OK;
}

static esp_http_client_handle_t http_client(const char *url, http_buffer_t *buffer)
{
    esp_http_client_config_t config = {
        .url = url, .crt_bundle_attach = esp_crt_bundle_attach,
        .disable_auto_redirect = true, .timeout_ms = 5000,
        .buffer_size = 2048, .buffer_size_tx = 1024,
        .event_handler = http_event, .user_data = buffer,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client) {
        esp_http_client_set_header(client, "User-Agent", "Mattboxx-ESP32-updater");
        esp_http_client_set_header(client, "Accept", buffer->body ? "application/vnd.github+json" : "application/octet-stream");
    }
    return client;
}

static OTA_NOINLINE bool check_release(void)
{
    /* A failed refresh invalidates the cached candidate: never auto-install
     * stale release metadata after a transport/parsing error. */
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool beta = s_state.config.beta_channel;
    const char *asset = ota_asset_for(s_state.config.language);
    bool reinstall = strcmp(s_state.config.language, OTA_UI_LANGUAGE) != 0;
    s_state.checked = false; s_state.update_available = false; s_state.asset[0] = 0;
    s_state.latest_version[0] = s_state.release_url[0] = 0; s_state.asset_size = 0;
    xSemaphoreGive(s_lock);
    status_set("Checking GitHub releases");
    http_buffer_t b = {.body = heap_caps_malloc(JSON_LIMIT + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)};
    if (!b.body) { status_set("Not enough memory for release metadata"); return false; }
    /* Only the worker task runs checks, so one static URL buffer is safe and
     * keeps the measured frame budget. Fall back to the previous repository
     * name only on 404 from the current one (before the GitHub rename). */
    static char api[112];
    esp_err_t err = ESP_FAIL; int code = 0; unsigned repo = 0;
    for (; repo < OTA_REPO_COUNT; ++repo) {
        b.body[0] = 0; b.used = 0; b.overflow = false;
        snprintf(api, sizeof api, "https://api.github.com/repos/%s/releases?per_page=10", ota_repo(repo));
        esp_http_client_handle_t client = http_client(api, &b);
        err = client ? esp_http_client_perform(client) : ESP_ERR_NO_MEM;
        code = client ? esp_http_client_get_status_code(client) : 0;
        if (client) esp_http_client_cleanup(client);
        if (err != ESP_OK || code != 404) break;
    }
    if (err != ESP_OK || code != 200 || b.overflow) {
        free(b.body);
        status_set(b.overflow ? "GitHub response too large" : code == 403 || code == 429 ? "GitHub rate limit; retry later" : "GitHub check failed (HTTPS/network/server)");
        return false;
    }
    const char *end = NULL;
    cJSON *json = cJSON_ParseWithLengthOpts(b.body, b.used + 1, &end, true);
    free(b.body);
    if (!cJSON_IsArray(json)) { cJSON_Delete(json); status_set("Invalid GitHub release response"); return false; }
    const esp_partition_t *target = ota_flash_next_partition();
    if (!target) { cJSON_Delete(json); status_set("OTA flash dispatcher unavailable or no update slot"); return false; }
    char tag[32] = {0}; uint32_t size = 0; unsigned char digest[32];
    const esp_app_desc_t *app = esp_app_get_description();
    bool found = target && app && asset && ota_remote_select_release(json, app->version, beta, asset, reinstall, target->size, tag, &size, digest);
    cJSON_Delete(json);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_state.checked = true; s_state.last_check = (uint32_t)time(NULL);
    s_state.update_available = found; s_state.asset_size = size; s_state.repo = (uint8_t)repo;
    strlcpy(s_state.latest_version, tag, sizeof s_state.latest_version);
    if (found) {
        memcpy(s_digest, digest, sizeof s_digest); strlcpy(s_state.asset, asset, sizeof s_state.asset);
        snprintf(s_state.release_url, sizeof s_state.release_url, "https://github.com/%s/releases/tag/%s", ota_repo(repo), tag);
    }
    xSemaphoreGive(s_lock);
    status_set(!found ? "No newer compatible release"
               : app && !strcmp(tag[0] == 'v' ? tag + 1 : tag, app->version) ? "Same version in the selected language available"
               : "Update available");
    return true;
}

/* Check the app descriptor before erasing the inactive slot, not just after
 * downloading. Factory images, upstream builds and mismatched tags are refused. */
static bool image_matches(const unsigned char *data, size_t length, const char *tag)
{
    if (length < sizeof(esp_image_header_t) + sizeof(esp_image_segment_header_t) + sizeof(esp_app_desc_t)) return false;
    esp_image_header_t header; esp_app_desc_t app;
    memcpy(&header, data, sizeof header);
    memcpy(&app, data + sizeof header + sizeof(esp_image_segment_header_t), sizeof app);
    const esp_app_desc_t *running = esp_app_get_description();
    const char *expected = tag[0] == 'v' ? tag + 1 : tag;
    return header.magic == ESP_IMAGE_HEADER_MAGIC && header.chip_id == ESP_CHIP_ID_ESP32S3 &&
           app.magic_word == ESP_APP_DESC_MAGIC_WORD && memchr(app.version, 0, sizeof app.version) &&
           memchr(app.project_name, 0, sizeof app.project_name) && running &&
           !strcmp(app.project_name, running->project_name) && !strcmp(app.version, expected);
}

static OTA_NOINLINE bool install_release(void)
{
    ota_remote_state_t state; ota_remote_get_state(&state);
    if (!state.checked || !state.update_available) return false;
    if (!ota_writer_try_acquire()) { status_set("Another firmware upload is active"); return false; }
    bool success = false;
    bool cleanup_failed = false;
    esp_ota_handle_t writer = 0;
    char url[192];
    const char *repo = ota_repo(state.repo);
    if (!repo) { ota_writer_release(); return false; }
    snprintf(url, sizeof url, "https://github.com/%s/releases/download/%s/%s", repo, state.latest_version, state.asset);
    http_buffer_t b = {.location = malloc(2048)};
    unsigned char *buffer = malloc(2048);
    esp_http_client_handle_t client = NULL;
    mbedtls_sha256_context hash; mbedtls_sha256_init(&hash);
    status_set("Downloading verified firmware");
    if (!b.location || !buffer || !ota_download_url_allowed_for(url, state.asset)) goto done;
    client = http_client(url, &b);
    if (!client) goto done;
    bool opened = false;
    for (unsigned redirects = 0; redirects <= 3; ++redirects) {
        b.location[0] = 0;
        if (esp_http_client_open(client, 0) != ESP_OK) break;
        int64_t length = esp_http_client_fetch_headers(client);
        int code = esp_http_client_get_status_code(client);
        if (code == 200 && length == state.asset_size) { opened = true; break; }
        esp_http_client_close(client);
        if ((code != 301 && code != 302 && code != 303 && code != 307 && code != 308) ||
            !ota_download_url_allowed_for(b.location, state.asset) || esp_http_client_set_url(client, b.location) != ESP_OK) break;
    }
    if (!opened || mbedtls_sha256_starts(&hash, 0) != 0) goto done;
    size_t used = 0;
    const size_t prefix = sizeof(esp_image_header_t) + sizeof(esp_image_segment_header_t) + sizeof(esp_app_desc_t);
    int64_t deadline = esp_timer_get_time() + 180LL * 1000000;
    while (used < prefix && esp_timer_get_time() < deadline) {
        int n = esp_http_client_read(client, (char *)buffer + used, prefix - used);
        if (n <= 0) goto done;
        used += (size_t)n;
    }
    if (!image_matches(buffer, used, state.latest_version)) { status_set("Rejected: wrong board, firmware or version"); goto done; }
    const esp_partition_t *target = ota_flash_next_partition();
    if (!target || state.asset_size > target->size || ota_flash_begin(target, state.asset_size, &writer) != ESP_OK) goto done;
    if (mbedtls_sha256_update(&hash, buffer, used) != 0 || ota_flash_write(writer, buffer, used) != ESP_OK) goto done;
    while (used < state.asset_size && esp_timer_get_time() < deadline) {
        size_t wanted = state.asset_size - used;
        if (wanted > 2048) wanted = 2048;
        int n = esp_http_client_read(client, (char *)buffer, wanted);
        if (n <= 0 || mbedtls_sha256_update(&hash, buffer, n) != 0 || ota_flash_write(writer, buffer, n) != ESP_OK) goto done;
        used += (size_t)n;
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_state.progress = (unsigned)(used * 100 / state.asset_size);
        xSemaphoreGive(s_lock);
    }
    unsigned char actual[32];
    if (used != state.asset_size || !esp_http_client_is_complete_data_received(client) ||
        mbedtls_sha256_finish(&hash, actual) != 0 || memcmp(actual, s_digest, sizeof actual)) {
        status_set("Rejected: incomplete download or SHA-256 mismatch"); goto done;
    }
    esp_err_t err = ota_flash_end(&writer);
    if (err != ESP_OK || ota_flash_set_boot_partition(target) != ESP_OK) goto done;
    success = true;
done:
    if (writer) cleanup_failed = ota_flash_abort(writer) != ESP_OK;
    if (client) esp_http_client_cleanup(client);
    mbedtls_sha256_free(&hash); free(b.location); free(buffer);
    if (success) {
        status_set("Installed; restarting");
        vTaskDelay(pdMS_TO_TICKS(2000)); ota_flash_restart();
    } else {
        /* A failed dispatch/abort must not admit another writer over a still
         * active SDK transaction. Keep exclusion until an explicit restart. */
        if (cleanup_failed) status_set("OTA cleanup failed; restart before retrying");
        else ota_writer_release();
        ota_remote_get_state(&state);
        if (!strncmp(state.status, "Downloading", 11)) status_set("Install failed; running firmware unchanged");
    }
    return success;
}

static void worker(void *unused)
{
    (void)unused;
    int64_t last_poll = 0, last_install = 0;
    for (;;) {
        uint32_t bits = 0;
        xTaskNotifyWait(0, UINT32_MAX, &bits, pdMS_TO_TICKS(last_poll ? 60000 : 20000));
        if (bits & CONFIG_BIT) last_poll = 0;
        ota_remote_state_t state; ota_remote_get_state(&state);
        int64_t now = esp_timer_get_time();
        bool requested = (bits & (CHECK_BIT | INSTALL_BIT)) != 0;
        bool due = state.config.enabled && (!last_poll || now - last_poll >= DAILY_US);
        /* Reserve background work atomically with config/HTTP requests.
         * An idle iteration must never clear another request's reservation. */
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (!requested && s_state.busy) { xSemaphoreGive(s_lock); continue; }
        state = s_state;
        due = state.config.enabled && (!last_poll || now - last_poll >= DAILY_US);
        bool pending_auto = state.config.enabled && state.config.auto_install && state.checked && state.update_available &&
                            (!last_install || now - last_install >= 3600LL * 1000000);
        if (!requested && !due && !pending_auto) { xSemaphoreGive(s_lock); continue; }
        s_state.busy = true;
        xSemaphoreGive(s_lock);
        esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        if (!sta || !esp_netif_is_netif_up(sta)) {
            status_set("Waiting for WiFi uplink");
            xSemaphoreTake(s_lock, portMAX_DELAY); s_state.busy = false; xSemaphoreGive(s_lock);
            continue;
        }
        bool checked = false;
        if (requested || due) {
            xSemaphoreTake(s_lock, portMAX_DELAY); s_state.busy = true; s_state.progress = 0; xSemaphoreGive(s_lock);
            checked = check_release();
            last_poll = now; /* failed polls do not hammer GitHub */
        }
        ota_remote_get_state(&state);
        bool automatic = state.config.enabled && state.config.auto_install && state.checked && state.update_available &&
                         (!last_install || now - last_install >= 3600LL * 1000000);
        if (automatic && state.config.install_hour >= 0) {
            time_t epoch = time(NULL); struct tm local;
            automatic = epoch > 1700000000 && localtime_r(&epoch, &local) && local.tm_hour == state.config.install_hour;
        }
        if (((bits & INSTALL_BIT) && checked && state.update_available) || automatic) {
            xSemaphoreTake(s_lock, portMAX_DELAY); s_state.busy = true; s_state.progress = 0; xSemaphoreGive(s_lock);
            /* Automatic delayed/retry installs refresh metadata too. */
            if (checked || check_release()) (void)install_release();
            last_install = now;
        }
        xSemaphoreTake(s_lock, portMAX_DELAY); s_state.busy = false; xSemaphoreGive(s_lock);
    }
}

static bool start_worker_locked(void)
{
    if (!s_flash_ready) return false;
    if (s_task) return true;
    return xTaskCreateWithCaps(worker, "ota_fork", WORKER_STACK, NULL, 4, &s_task,
                               MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) == pdPASS;
}

esp_err_t ota_remote_set_config(const ota_remote_config_t *config)
{
    if (!config || config->install_hour < -1 || config->install_hour > 23 ||
        (config->auto_install && !config->enabled) || !memchr(config->language, 0, sizeof config->language) ||
        !ota_asset_for(config->language)) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_state.busy) { xSemaphoreGive(s_lock); return ESP_ERR_INVALID_STATE; }
    if (config->enabled && !start_worker_locked()) { xSemaphoreGive(s_lock); return ESP_ERR_NO_MEM; }
    saved_config_t saved = {1, config->enabled, config->auto_install, config->beta_channel, config->install_hour};
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "ota_fork_v1", &saved, sizeof saved);
        /* Separate key: the v1 blob stays readable by earlier firmware. */
        if (err == ESP_OK) err = nvs_set_str(nvs, "ota_lang", config->language);
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err == ESP_OK) {
        s_state.config = *config;
        s_state.checked = s_state.update_available = false;
        s_state.latest_version[0] = s_state.release_url[0] = 0;
        strlcpy(s_state.status, config->enabled ? "Settings saved; check scheduled" : "Periodic checks disabled", sizeof s_state.status);
        if (s_task) xTaskNotify(s_task, CONFIG_BIT, eSetBits);
    }
    xSemaphoreGive(s_lock); return err;
}

esp_err_t ota_remote_request(bool install)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_state.busy) { xSemaphoreGive(s_lock); return ESP_ERR_INVALID_STATE; }
    if (!start_worker_locked()) { xSemaphoreGive(s_lock); return ESP_ERR_NO_MEM; }
    s_state.busy = true; s_state.progress = 0;
    strlcpy(s_state.status, install ? "Latest install requested" : "Check requested", sizeof s_state.status);
    xTaskNotify(s_task, install ? INSTALL_BIT : CHECK_BIT, eSetBits);
    xSemaphoreGive(s_lock); return ESP_OK;
}

void ota_remote_init(void)
{
    if (s_lock) return;
    s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    s_state.config.install_hour = -1;
    strlcpy(s_state.config.language, OTA_UI_LANGUAGE, sizeof s_state.config.language);
    /* Initialize the bounded mailbox, not a new internal stack. The lifetime-
     * long admin server attaches when started; early requests fail closed. */
    s_flash_ready = ota_flash_init() == ESP_OK;
    strlcpy(s_state.status, "Periodic checks disabled", sizeof s_state.status);
    nvs_handle_t nvs; saved_config_t saved; size_t length = sizeof saved;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        esp_err_t err = nvs_get_blob(nvs, "ota_fork_v1", &saved, &length); nvs_close(nvs);
        if (err == ESP_OK && length == sizeof saved && saved.schema == 1 && saved.enabled <= 1 &&
            saved.automatic <= 1 && saved.beta <= 1 && saved.hour >= -1 && saved.hour <= 23 &&
            (!saved.automatic || saved.enabled))
            s_state.config = (ota_remote_config_t){saved.enabled, saved.automatic, saved.beta, saved.hour, OTA_UI_LANGUAGE};
        /* Language chosen for updates; the running variant when never set. */
        char language[sizeof s_state.config.language]; size_t n = sizeof language;
        if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
            if (nvs_get_str(nvs, "ota_lang", language, &n) == ESP_OK && ota_asset_for(language))
                strlcpy(s_state.config.language, language, sizeof s_state.config.language);
            nvs_close(nvs);
        }
    }
    if (!s_flash_ready) status_set("OTA flash dispatcher unavailable");
    else if (s_state.config.enabled && !start_worker_locked()) status_set("Update worker failed to start");
}
