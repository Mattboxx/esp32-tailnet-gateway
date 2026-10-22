/* Non-destructive configuration profiles over the existing setting owners.
 * Persist the backup record before touching any setting; undo a failed
 * apply; rollback never overrides a setting the operator changed since.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "config_profiles.h"
#include "homelab_ops.h"
#include "health_monitor.h"
#include "json_guard.h"
#include "nvs.h"
#include "nvs_params.h"
#include "web_ui.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#define PROFILE_MAGIC 0x50524631u /* PRF1 */
typedef struct {
    uint32_t magic, version;
    uint8_t active, previous, has_backup, applied_mask;
    uint8_t previous_values[PK_COUNT], reserved[8 - PK_COUNT];
    uint32_t generation, checksum;
} profile_record_t;
/* Platform hooks; the core below is also compiled against host fixtures. */
static bool values_read(profile_values_t *out);
static esp_err_t value_write(profile_key_t key, uint8_t value);
static esp_err_t record_save(const profile_record_t *r);

/* --- profile core (begin) --- */

static profile_record_t record;
static const char *const profile_names[PROFILE_COUNT] =
    {"none", "gateway", "recovery", "iot", "monitoring", "advanced"};
static const char *const key_names[PK_COUNT] =
    {"device_monitoring", "service_expiry_notifications", "health_monitor"};
static const uint8_t profile_wants[PROFILE_COUNT] = {
    [PROFILE_GATEWAY] = 1u << PK_LEASE_NOTIFY,
    [PROFILE_RECOVERY] = 1u << PK_OPS_MONITORING,
    [PROFILE_MONITORING] = 1u << PK_OPS_MONITORING | 1u << PK_HEALTH,
};

const char *config_profile_name(profile_id_t profile)
{
    return profile < PROFILE_COUNT ? profile_names[profile] : "unknown";
}

bool config_profile_parse(const char *name, profile_id_t *out)
{
    for (unsigned i = PROFILE_GATEWAY; name && i < PROFILE_COUNT; i++)
        if (!strcmp(name, profile_names[i])) {*out = (profile_id_t)i; return true;}
    return false;
}

static uint32_t fnv(uint32_t hash, const void *data, size_t length)
{
    const uint8_t *p = data;
    while (length--) hash = (hash ^ *p++) * 16777619u;
    return hash;
}

static uint32_t record_checksum(const profile_record_t *r)
{
    return fnv(2166136261u, r, offsetof(profile_record_t, checksum));
}

static bool record_valid(const profile_record_t *r)
{
    if (r->magic != PROFILE_MAGIC || r->version != 1 || r->checksum != record_checksum(r)
        || r->active >= PROFILE_COUNT || r->previous >= PROFILE_COUNT
        || r->has_backup > 1 || r->applied_mask >> PK_COUNT) return false;
    for (unsigned k = 0; k < PK_COUNT; k++) if (r->previous_values[k] > 1) return false;
    for (unsigned i = 0; i < sizeof r->reserved; i++) if (r->reserved[i]) return false;
    return true;
}

static void record_defaults(profile_record_t *r)
{
    memset(r, 0, sizeof *r);
    r->magic = PROFILE_MAGIC;
    r->version = 1;
}

static void profile_plan(profile_id_t profile, const profile_values_t *current,
                         profile_plan_t *out)
{
    memset(out, 0, sizeof *out);
    out->profile = profile;
    out->proposed_mask = profile < PROFILE_COUNT ? profile_wants[profile] : 0;
    for (unsigned k = 0; k < PK_COUNT; k++)
        if (out->proposed_mask >> k & 1 && !current->value[k]) out->change_mask |= 1u << k;
    uint32_t id = profile, hash = 2166136261u;
    hash = fnv(hash, &id, sizeof id);
    hash = fnv(hash, current->value, sizeof current->value);
    hash = fnv(hash, &record.active, 1);
    hash = fnv(hash, &record.has_backup, 1);
    hash = fnv(hash, &record.generation, sizeof record.generation);
    out->token = hash | 1u;
}

static esp_err_t save_record(profile_record_t *r)
{
    r->checksum = record_checksum(r);
    return record_valid(r) ? record_save(r) : ESP_ERR_INVALID_STATE;
}

static esp_err_t preview_locked(profile_id_t profile, profile_plan_t *out)
{
    if (profile <= PROFILE_NONE || profile >= PROFILE_COUNT) return ESP_ERR_INVALID_ARG;
    profile_values_t current;
    if (!values_read(&current)) return ESP_FAIL;
    profile_plan(profile, &current, out);
    return ESP_OK;
}

static esp_err_t apply_locked(profile_id_t profile, uint32_t token, profile_result_t *out)
{
    memset(out, 0, sizeof *out);
    profile_plan_t plan;
    profile_values_t current;
    if (profile <= PROFILE_NONE || profile >= PROFILE_COUNT) return ESP_ERR_INVALID_ARG;
    if (!values_read(&current)) return ESP_FAIL;
    profile_plan(profile, &current, &plan);
    if (!token || token != plan.token) return ESP_ERR_INVALID_STATE;
    profile_record_t next = record;
    next.previous = record.active;
    next.active = (uint8_t)profile;
    next.has_backup = 1;
    next.applied_mask = plan.change_mask;
    memcpy(next.previous_values, current.value, sizeof next.previous_values);
    next.generation = record.generation + 1;
    esp_err_t err = save_record(&next);
    if (err != ESP_OK) return err;               /* nothing changed yet */
    uint8_t done = 0;
    for (unsigned k = 0; k < PK_COUNT && err == ESP_OK; k++)
        if (plan.change_mask >> k & 1) {
            err = value_write((profile_key_t)k, 1);
            if (err == ESP_OK) done |= 1u << k;
        }
    if (err == ESP_OK) {
        record = next;
        out->applied = true;
        out->changed_mask = done;
        return ESP_OK;
    }
    uint8_t stuck = 0;
    for (unsigned k = 0; k < PK_COUNT; k++)
        if (done >> k & 1 && value_write((profile_key_t)k, current.value[k]) != ESP_OK)
            stuck |= 1u << k;
    out->rolled_back = true;
    profile_record_t restore = record;
    if (!stuck && save_record(&restore) == ESP_OK) return err;
    /* Keep a truthful backup for whatever could not be undone. */
    next.applied_mask = stuck;
    (void)save_record(&next);
    record = next;
    out->partial = true;
    out->changed_mask = stuck;
    return err;
}

static esp_err_t rollback_locked(profile_result_t *out)
{
    memset(out, 0, sizeof *out);
    if (!record.has_backup) return ESP_ERR_NOT_FOUND;
    profile_values_t current;
    if (!values_read(&current)) return ESP_FAIL;
    uint8_t restore = 0, kept = 0, done = 0;
    for (unsigned k = 0; k < PK_COUNT; k++) {
        if (!(record.applied_mask >> k & 1)) continue;
        if (current.value[k] == 1) restore |= 1u << k;
        else kept |= 1u << k;                     /* operator already changed it */
    }
    esp_err_t err = ESP_OK;
    for (unsigned k = 0; k < PK_COUNT && err == ESP_OK; k++)
        if (restore >> k & 1) {
            err = value_write((profile_key_t)k, record.previous_values[k]);
            if (err == ESP_OK) done |= 1u << k;
        }
    if (err != ESP_OK) {
        uint8_t stuck = 0;
        for (unsigned k = 0; k < PK_COUNT; k++)
            if (done >> k & 1 && value_write((profile_key_t)k, 1) != ESP_OK) stuck |= 1u << k;
        out->partial = stuck != 0;
        out->changed_mask = stuck;
        return err;
    }
    profile_record_t next = record;
    next.active = record.previous;
    next.previous = PROFILE_NONE;
    next.has_backup = 0;
    next.applied_mask = 0;
    memset(next.previous_values, 0, sizeof next.previous_values);
    next.generation = record.generation + 1;
    err = save_record(&next);
    out->changed_mask = done;
    out->kept_mask = kept;
    if (err != ESP_OK) {out->partial = done != 0; return err;}  /* retry finds them kept */
    record = next;
    out->rolled_back = true;
    return ESP_OK;
}
/* --- profile core (end) --- */

static SemaphoreHandle_t lock;
static StaticSemaphore_t lock_storage;
static bool initialized;

static bool values_read(profile_values_t *out)
{
    ops_settings_t settings;
    homelab_ops_settings(&settings);
    out->value[PK_OPS_MONITORING] = settings.monitoring ? 1 : 0;
    out->value[PK_LEASE_NOTIFY] = settings.lease_notifications ? 1 : 0;
    out->value[PK_HEALTH] = health_monitor_enabled() ? 1 : 0;
    return true;
}

static esp_err_t value_write(profile_key_t key, uint8_t value)
{
    if (key == PK_HEALTH) return health_monitor_set_enabled(value != 0);
    ops_settings_t settings;
    homelab_ops_settings(&settings);
    if (key == PK_OPS_MONITORING) settings.monitoring = value;
    else if (key == PK_LEASE_NOTIFY) settings.lease_notifications = value;
    else return ESP_ERR_INVALID_ARG;
    return homelab_ops_set_settings(&settings);
}

static esp_err_t record_save(const profile_record_t *r)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err != ESP_OK) return err;
    err = nvs_set_blob(nvs, "cfg_profile", r, sizeof *r);
    if (err == ESP_OK) err = nvs_commit(nvs);
    nvs_close(nvs);
    return err;
}

void config_profiles_init(void)
{
    if (initialized) return;
    lock = xSemaphoreCreateMutexStatic(&lock_storage);
    record_defaults(&record);
    nvs_handle_t nvs;
    profile_record_t loaded;
    size_t size = sizeof loaded;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        /* An invalid record means "no profile and no rollback", never a
         * guess about which settings a profile once changed. */
        if (nvs_get_blob(nvs, "cfg_profile", &loaded, &size) == ESP_OK
            && size == sizeof loaded && record_valid(&loaded)) record = loaded;
        nvs_close(nvs);
    }
    initialized = true;
}

#define LOCKED(call) do { config_profiles_init(); xSemaphoreTake(lock, portMAX_DELAY); \
    esp_err_t locked_err = (call); xSemaphoreGive(lock); return locked_err; } while (0)

esp_err_t config_profiles_preview(profile_id_t profile, profile_plan_t *out) {LOCKED(preview_locked(profile, out));}
esp_err_t config_profiles_apply(profile_id_t profile, uint32_t token, profile_result_t *out) {LOCKED(apply_locked(profile, token, out));}
esp_err_t config_profiles_rollback(profile_result_t *out) {LOCKED(rollback_locked(out));}

void config_profiles_status(profile_id_t *active, bool *rollback_available)
{
    config_profiles_init();
    xSemaphoreTake(lock, portMAX_DELAY);
    *active = (profile_id_t)record.active;
    *rollback_available = record.has_backup;
    xSemaphoreGive(lock);
}

/* --- HTTP --- */
static const char *const profile_titles[PROFILE_COUNT] = {
    "No profile", "Gateway", "Recovery", "IoT", "Monitoring", "Advanced"};
static const char *const profile_summaries[PROFILE_COUNT] = {
    "Settings are exactly as configured.",
    "Routing, subnet and remote access. Turns on expiry notifications for temporary service rules.",
    "Wake-on-LAN, Smart Recovery and device control. Turns on device reachability monitoring.",
    "Devices without a Tailscale client behind the AP gateway, with integrations. Changes nothing automatically.",
    "Monitoring and diagnostics first. Turns on device monitoring and the Health Monitor worker.",
    "Full configuration access. Changes nothing automatically."};
static const char *const profile_steps[PROFILE_COUNT][3] = {
    [PROFILE_GATEWAY] = {"Advertise subnet routes or exit node in the Tailscale tab, then approve them in your admin console.",
                         "Add LAN to Tailnet rules in the Service Gateway; new rules start disabled.", NULL},
    [PROFILE_RECOVERY] = {"Add devices with MAC and target in Devices & Recovery.",
                          "Optionally configure ntfy or MQTT for recovery results.", NULL},
    [PROFILE_IOT] = {"Enable the AP gateway and review AP-side forwarding rules.",
                     "Configure MQTT and Home Assistant Discovery for device integrations.", NULL},
    [PROFILE_MONITORING] = {"Configure Health Monitor targets (gateway, DNS, Internet, Tailnet).",
                            "Health checks are light TCP/DNS probes; they never change routing.", NULL},
    [PROFILE_ADVANCED] = {"All settings remain available in every profile.", NULL, NULL}};

static esp_err_t send_json(httpd_req_t *req, cJSON *root)
{
    if (!root) {httpd_resp_send_500(req); return ESP_FAIL;}
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, body);
    free(body);
    return err;
}

static bool add_keys(cJSON *parent, const char *name, uint8_t mask)
{
    cJSON *array = cJSON_AddArrayToObject(parent, name);
    if (!array) return false;
    for (unsigned k = 0; k < PK_COUNT; k++)
        if (mask >> k & 1 && !cJSON_AddItemToArray(array, cJSON_CreateString(key_names[k]))) return false;
    return true;
}

static cJSON *snapshot(profile_id_t preview, esp_err_t *err)
{
    *err = ESP_OK;
    config_profiles_init();
    xSemaphoreTake(lock, portMAX_DELAY);
    profile_record_t r = record;
    profile_plan_t plan = {0};
    profile_values_t current = {0};
    if (!values_read(&current)) *err = ESP_FAIL;
    else if (preview != PROFILE_NONE) profile_plan(preview, &current, &plan);
    xSemaphoreGive(lock);
    if (*err != ESP_OK) return NULL;
    cJSON *root = cJSON_CreateObject();
    cJSON *list = root ? cJSON_AddArrayToObject(root, "profiles") : NULL;
    bool ok = list && cJSON_AddNumberToObject(root, "schema", 1)
        && cJSON_AddStringToObject(root, "active", profile_names[r.active])
        && cJSON_AddBoolToObject(root, "rollback_available", r.has_backup)
        && cJSON_AddStringToObject(root, "rollback_to", profile_names[r.has_backup ? r.previous : r.active])
        && add_keys(root, "rollback_restores", r.has_backup ? r.applied_mask : 0);
    for (unsigned i = PROFILE_GATEWAY; ok && i < PROFILE_COUNT; i++) {
        cJSON *item = cJSON_CreateObject();
        if (!item || !cJSON_AddItemToArray(list, item)) {cJSON_Delete(item); ok = false; break;}
        ok = cJSON_AddStringToObject(item, "id", profile_names[i])
            && cJSON_AddStringToObject(item, "title", profile_titles[i])
            && cJSON_AddStringToObject(item, "summary", profile_summaries[i])
            && add_keys(item, "enables", profile_wants[i]);
    }
    if (ok && preview != PROFILE_NONE) {
        cJSON *p = cJSON_AddObjectToObject(root, "preview");
        cJSON *changes = p ? cJSON_AddArrayToObject(p, "changes") : NULL;
        cJSON *steps = p ? cJSON_AddArrayToObject(p, "manual_steps") : NULL;
        ok = changes && steps && cJSON_AddStringToObject(p, "profile", profile_names[preview])
            && cJSON_AddNumberToObject(p, "token", plan.token)
            && cJSON_AddBoolToObject(p, "disables_anything", false)
            && cJSON_AddBoolToObject(p, "changes_network_exposure", false);
        for (unsigned k = 0; ok && k < PK_COUNT; k++) {
            if (!(plan.proposed_mask >> k & 1)) continue;
            cJSON *c = cJSON_CreateObject();
            if (!c || !cJSON_AddItemToArray(changes, c)) {cJSON_Delete(c); ok = false; break;}
            ok = cJSON_AddStringToObject(c, "setting", key_names[k])
                && cJSON_AddBoolToObject(c, "current", current.value[k])
                && cJSON_AddBoolToObject(c, "proposed", true)
                && cJSON_AddStringToObject(c, "change", plan.change_mask >> k & 1 ? "enable" : "unchanged");
        }
        for (unsigned i = 0; ok && i < 3 && profile_steps[preview][i]; i++)
            ok = cJSON_AddItemToArray(steps, cJSON_CreateString(profile_steps[preview][i]));
    }
    if (!ok) {cJSON_Delete(root); *err = ESP_ERR_NO_MEM; return NULL;}
    return root;
}

static esp_err_t send_error(httpd_req_t *req, esp_err_t err, const profile_result_t *result)
{
    httpd_resp_set_status(req, err == ESP_ERR_INVALID_ARG ? "400 Bad Request"
        : err == ESP_ERR_INVALID_STATE ? "409 Conflict" : err == ESP_ERR_NOT_FOUND ? "404 Not Found"
        : err == ESP_ERR_NO_MEM ? "503 Service Unavailable" : "500 Internal Server Error");
    cJSON *reply = cJSON_CreateObject();
    if (reply) {
        cJSON_AddBoolToObject(reply, "ok", false);
        cJSON_AddStringToObject(reply, "error", err == ESP_ERR_INVALID_STATE
            ? "settings changed since the preview; preview again" : esp_err_to_name(err));
        if (result) {
            cJSON_AddBoolToObject(reply, "rolled_back", result->rolled_back);
            cJSON_AddBoolToObject(reply, "partial", result->partial);
            add_keys(reply, "left_changed", result->changed_mask);
        }
    }
    return send_json(req, reply);
}

static esp_err_t get_profiles(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    profile_id_t preview = PROFILE_NONE;
    char query[48], value[16];
    if (httpd_req_get_url_query_str(req, query, sizeof query) == ESP_OK
        && httpd_query_key_value(query, "preview", value, sizeof value) == ESP_OK
        && !config_profile_parse(value, &preview)) return send_error(req, ESP_ERR_INVALID_ARG, NULL);
    esp_err_t err;
    cJSON *root = snapshot(preview, &err);
    return root ? send_json(req, root) : send_error(req, err, NULL);
}

static esp_err_t post_profiles(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[160];
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) return send_error(req, ESP_ERR_INVALID_ARG, NULL);
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) return send_error(req, ESP_FAIL, NULL);
        received += n;
    }
    body[received] = 0;
    cJSON *root = json_guard_parse(body);
    const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
    const cJSON *name = cJSON_GetObjectItemCaseSensitive(root, "profile");
    const cJSON *token = cJSON_GetObjectItemCaseSensitive(root, "token");
    unsigned fields = 0;
    for (const cJSON *f = root ? root->child : NULL; f; f = f->next) fields++;
    profile_result_t result = {0};
    esp_err_t err = ESP_ERR_INVALID_ARG;
    profile_id_t profile;
    if (cJSON_IsObject(root) && cJSON_IsString(action) && !strcmp(action->valuestring, "rollback") && fields == 1)
        err = config_profiles_rollback(&result);
    else if (cJSON_IsObject(root) && cJSON_IsString(action) && !strcmp(action->valuestring, "apply") && fields == 3
             && cJSON_IsString(name) && config_profile_parse(name->valuestring, &profile)
             && cJSON_IsNumber(token) && isfinite(token->valuedouble) && token->valuedouble >= 1
             && token->valuedouble <= UINT32_MAX && floor(token->valuedouble) == token->valuedouble)
        err = config_profiles_apply(profile, (uint32_t)token->valuedouble, &result);
    cJSON_Delete(root);
    if (err != ESP_OK) return send_error(req, err, err == ESP_ERR_INVALID_ARG ? NULL : &result);
    cJSON *reply = cJSON_CreateObject();
    if (reply && !(cJSON_AddBoolToObject(reply, "ok", true)
                   && cJSON_AddBoolToObject(reply, "applied", result.applied)
                   && cJSON_AddBoolToObject(reply, "rolled_back", result.rolled_back)
                   && add_keys(reply, "changed", result.changed_mask)
                   && add_keys(reply, "kept", result.kept_mask))) {cJSON_Delete(reply); reply = NULL;}
    return send_json(req, reply);
}

esp_err_t config_profiles_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/profiles", .method = HTTP_GET, .handler = get_profiles},
        {.uri = "/api/profiles", .method = HTTP_POST, .handler = post_profiles}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
