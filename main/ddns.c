/* Dynamic DNS; see ddns.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "ddns.h"
#include <stdio.h>
#include <string.h>

/* --- ddns core (begin) --- */
static bool fail(char *why, size_t cap, const char *text)
{
    if (why && cap) snprintf(why, cap, "%s", text);
    return false;
}

static bool lower_alnum(char c) {return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');}
static bool alnum(char c) {return lower_alnum(c) || (c >= 'A' && c <= 'Z');}
static bool hexdigit(char c) {return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');}

static bool host_valid(const char *h)
{
    size_t n = strlen(h), label = 0;
    if (!n || n > 127 || h[0] == '.' || h[n - 1] == '.' || !strchr(h, '.')) return false;
    for (size_t i = 0; i < n; i++) {
        char c = h[i];
        if (c == '.') {if (!label || h[i - 1] == '-') return false; label = 0; continue;}
        if (!alnum(c) && c != '-' && !(c == '*' && i == 0 && h[1] == '.')) return false;
        if (c == '-' && !label) return false;
        if (++label > 63) return false;
    }
    return h[n - 1] != '-';
}

bool ddns_config_valid(const ddns_config_t *c, char *why, size_t cap)
{
    if (!c) return fail(why, cap, "missing settings");
    if (c->provider == DDNS_OFF) return true;
    if (c->provider == DDNS_DUCKDNS) {
        /* "home" or "home,cabin"; the duckdns.org suffix is added by DuckDNS. */
        size_t n = strlen(c->name), label = 0, count = 0;
        if (!n) return fail(why, cap, "enter the DuckDNS sub-domain, e.g. myhome");
        for (size_t i = 0; i <= n; i++) {
            char ch = c->name[i];
            if (ch == ',' || !ch) {if (!label || c->name[i - 1] == '-' || ++count > 5) return fail(why, cap, "sub-domains are letters, digits and -, separated by commas (at most 5)"); label = 0; continue;}
            if (!lower_alnum(ch) && !(ch == '-' && label)) return fail(why, cap, "sub-domains are lower-case letters, digits and -, without .duckdns.org");
            if (++label > 63) return fail(why, cap, "sub-domain too long");
        }
        size_t t = strlen(c->token);
        bool ok = t == 36;
        for (size_t i = 0; ok && i < t; i++) ok = (i == 8 || i == 13 || i == 18 || i == 23) ? c->token[i] == '-' : hexdigit(c->token[i]);
        return ok || fail(why, cap, "the DuckDNS token looks like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx");
    }
    if (c->provider == DDNS_CLOUDFLARE) {
        if (!host_valid(c->name)) return fail(why, cap, "enter the full record name, e.g. home.example.com");
        size_t z = strlen(c->zone);
        bool ok = z == 32;
        for (size_t i = 0; ok && i < z; i++) ok = hexdigit(c->zone[i]);
        if (!ok) return fail(why, cap, "the zone id is 32 hexadecimal characters (Cloudflare dashboard, Overview)");
        size_t t = strlen(c->token);
        ok = t >= 40 && t <= 100;
        for (size_t i = 0; ok && i < t; i++) ok = alnum(c->token[i]) || c->token[i] == '_' || c->token[i] == '-';
        return ok || fail(why, cap, "enter a Cloudflare API token with Zone.DNS edit permission");
    }
    if (c->provider == DDNS_CUSTOM) {
        size_t n = strlen(c->url);
        if (n < 12 || n >= sizeof c->url || strncmp(c->url, "https://", 8)) return fail(why, cap, "the update URL must start with https://");
        const char *host = c->url + 8, *end = host;
        while (*end && *end != '/' && *end != '?' && *end != ':') end++;
        char h[128];
        size_t hl = (size_t)(end - host);
        if (!hl || hl >= sizeof h) return fail(why, cap, "the update URL needs a host name");
        memcpy(h, host, hl); h[hl] = 0;
        if (!host_valid(h) || strchr(h, '*')) return fail(why, cap, "the update URL needs a valid host name");
        for (size_t i = 0; i < n; i++)
            if ((unsigned char)c->url[i] <= 0x20 || (unsigned char)c->url[i] >= 0x7F || c->url[i] == '"' || c->url[i] == '\\' || c->url[i] == '#')
                return fail(why, cap, "the update URL contains spaces or characters that are not allowed");
        const char *at = strchr(c->url, '@');
        if (at && at < end) return fail(why, cap, "put credentials in the query, not before the host name");
        return true;
    }
    return fail(why, cap, "unknown provider");
}

bool ddns_due(const ddns_state_t *st, uint8_t provider, uint32_t ip, uint32_t now)
{
    if (provider == DDNS_OFF || now < st->next_try_s) return false;
    if (!st->ever) return true;
    if (ip && ip != st->last_ip) return true;                      /* the address changed */
    /* Daily refresh; every 30 minutes while the address cannot be seen. */
    return now - st->last_ok_s >= (ip ? DDNS_REFRESH_S : DDNS_BLIND_S);
}

void ddns_result(ddns_state_t *st, bool ok, uint32_t ip, uint32_t now)
{
    if (ok) {
        st->ever = true; st->last_ok_s = now; st->backoff_s = 0; st->next_try_s = now + 60;
        if (ip) st->last_ip = ip;
        return;
    }
    st->backoff_s = !st->backoff_s ? 60 : st->backoff_s * 2 > DDNS_BACKOFF_MAX_S ? DDNS_BACKOFF_MAX_S : st->backoff_s * 2;
    st->next_try_s = now + st->backoff_s;
}

static void ip_text(uint32_t ip, char out[16])
{
    const uint8_t *b = (const uint8_t *)&ip;
    if (ip) snprintf(out, 16, "%u.%u.%u.%u", b[0], b[1], b[2], b[3]); else out[0] = 0;
}

bool ddns_build_url(const ddns_config_t *c, uint32_t ip, char *out, size_t cap)
{
    char addr[16];
    ip_text(ip, addr);
    int n = -1;
    if (c->provider == DDNS_DUCKDNS) {
        n = snprintf(out, cap, "https://www.duckdns.org/update?domains=%s&token=%s&ip=%s", c->name, c->token, addr);
    } else if (c->provider == DDNS_CUSTOM) {
        const char *mark = strstr(c->url, "{ip}");
        if (!mark) n = snprintf(out, cap, "%s", c->url);
        else if (!ip) return false;                                /* the URL needs the address */
        else n = snprintf(out, cap, "%.*s%s%s", (int)(mark - c->url), c->url, addr, mark + 4);
        if (n > 0 && strstr(out, "{ip}")) return false;            /* one placeholder only */
    }
    return n > 0 && (size_t)n < cap;
}
bool ddns_parse_trace(const char *text, uint32_t *ip)
{
    for (const char *p = text; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        if (strncmp(p, "ip=", 3)) continue;
        unsigned part[4];
        int used = 0;
        if (sscanf(p + 3, "%3u.%3u.%3u.%3u%n", &part[0], &part[1], &part[2], &part[3], &used) != 4) return false;
        char end = p[3 + used];
        if ((end && end != '\n' && end != '\r') || part[0] > 255 || part[1] > 255 || part[2] > 255 || part[3] > 255) return false;
        uint8_t b[4] = {(uint8_t)part[0], (uint8_t)part[1], (uint8_t)part[2], (uint8_t)part[3]};
        memcpy(ip, b, 4);
        return *ip != 0;
    }
    return false;
}
/* --- ddns core (end) --- */

#ifdef ESP_PLATFORM
#include "history.h"
#include "json_guard.h"
#include "tailscale_config.h"
#include "task_reaper.h"
#include "web_ui.h"
#include "microlink.h"
#include "esp_attr.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_rom_crc.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "nvs.h"
#include <stdlib.h>

static const char *TAG = "ddns";
#define CFG_MAGIC 0x44444e31u   /* DDN1 */
typedef struct {uint32_t magic, version; ddns_config_t config; uint32_t checksum;} cfg_record_t;

EXT_RAM_BSS_ATTR static ddns_config_t s_cfg;   /* PSRAM: no internal RAM while off */
static ddns_state_t s_state;
static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
static esp_timer_handle_t s_timer;
static bool s_running, s_force;
EXT_RAM_BSS_ATTR static char s_last[96];
static uint32_t s_seen_ip;

static uint32_t now_s(void) {return (uint32_t)(esp_timer_get_time() / 1000000);}
static uint32_t checksum(const cfg_record_t *r) {return esp_rom_crc32_le(0, (const uint8_t *)r, offsetof(cfg_record_t, checksum));}

static void load(ddns_config_t *c)
{
    memset(c, 0, sizeof *c);
    nvs_handle_t h;
    if (nvs_open("tsr", NVS_READONLY, &h) != ESP_OK) return;
    cfg_record_t *r = calloc(1, sizeof *r);
    size_t n = sizeof *r;
    /* Fail closed: a damaged record means off. */
    if (r && nvs_get_blob(h, "ddns_cfg", r, &n) == ESP_OK && n == sizeof *r && r->magic == CFG_MAGIC && r->version == 1 &&
        r->checksum == checksum(r) && ddns_config_valid(&r->config, NULL, 0)) *c = r->config;
    if (r) {memset(r, 0, sizeof *r); free(r);}
    nvs_close(h);
}

static esp_err_t save(const ddns_config_t *c)
{
    cfg_record_t *r = calloc(1, sizeof *r);
    if (!r) return ESP_ERR_NO_MEM;
    r->magic = CFG_MAGIC; r->version = 1; r->config = *c; r->checksum = checksum(r);
    nvs_handle_t h;
    esp_err_t err = nvs_open("tsr", NVS_READWRITE, &h);
    if (!err) {err = nvs_set_blob(h, "ddns_cfg", r, sizeof *r); if (!err) err = nvs_commit(h); nvs_close(h);}
    memset(r, 0, sizeof *r);
    free(r);
    return err;
}

static uint32_t public_ip(void)
{
    microlink_t *ml = tailscale_get_microlink();
    microlink_diag_t d;
    return ml && microlink_get_diag(ml, &d) == ESP_OK && d.wan_public_ip ? htonl(d.wan_public_ip) : 0;
}

/* One HTTPS request; `body` NULL = GET. Reads up to cap-1 bytes of the answer. */
static int request(const char *url, esp_http_client_method_t method, const char *token, const char *body, char *answer, size_t cap)
{
    esp_http_client_config_t hc = {.url = url, .method = method, .timeout_ms = 15000,
                                   .crt_bundle_attach = esp_crt_bundle_attach, .disable_auto_redirect = true};
    esp_http_client_handle_t client = esp_http_client_init(&hc);
    if (!client) return -1;
    if (token) {
        char auth[140];
        snprintf(auth, sizeof auth, "Bearer %s", token);
        esp_http_client_set_header(client, "Authorization", auth);
        memset(auth, 0, sizeof auth);
    }
    if (body) esp_http_client_set_header(client, "Content-Type", "application/json");
    int status = -1, len = body ? (int)strlen(body) : 0;
    answer[0] = 0;
    if (esp_http_client_open(client, len) == ESP_OK && (!len || esp_http_client_write(client, body, len) == len) &&
        esp_http_client_fetch_headers(client) >= 0) {
        status = esp_http_client_get_status_code(client);
        int got = 0, n;
        while (got < (int)cap - 1 && (n = esp_http_client_read(client, answer + got, (int)cap - 1 - got)) > 0) got += n;
        answer[got > 0 ? got : 0] = 0;
    }
    esp_http_client_cleanup(client);
    return status;
}

static bool cloudflare(const ddns_config_t *c, uint32_t *ip_io, char *why, size_t cap)
{
    char url[256], addr[16], *answer = heap_caps_malloc(4096, MALLOC_CAP_SPIRAM);
    if (!answer) return fail(why, cap, "out of memory");
    if (!*ip_io) {
        /* Tailscale has not seen the public address: ask Cloudflare itself. */
        int st = request("https://www.cloudflare.com/cdn-cgi/trace", HTTP_METHOD_GET, NULL, NULL, answer, 1024);
        if (st != 200 || !ddns_parse_trace(answer, ip_io)) {free(answer); return fail(why, cap, "public address unknown (no Tailscale address, Cloudflare trace failed)");}
    }
    uint32_t ip = *ip_io;
    ip_text(ip, addr);
    snprintf(url, sizeof url, "https://api.cloudflare.com/client/v4/zones/%s/dns_records?type=A&name=%s", c->zone, c->name);
    int status = request(url, HTTP_METHOD_GET, c->token, NULL, answer, 4096);
    bool ok = false;
    cJSON *root = status == 200 ? cJSON_Parse(answer) : NULL;
    const cJSON *result = cJSON_GetObjectItemCaseSensitive(root, "result"), *first = cJSON_GetArrayItem(result, 0);
    const cJSON *id = cJSON_GetObjectItemCaseSensitive(first, "id"), *content = cJSON_GetObjectItemCaseSensitive(first, "content");
    if (status < 0) fail(why, cap, "cannot reach api.cloudflare.com");
    else if (status != 200) snprintf(why, cap, "Cloudflare answered %d (check the token permission and zone id)", status);
    else if (!cJSON_IsString(id) || strlen(id->valuestring) != 32) fail(why, cap, "no A record with this name: create it once in Cloudflare");
    else if (cJSON_IsString(content) && !strcmp(content->valuestring, addr)) ok = true;     /* already right */
    else {
        snprintf(url, sizeof url, "https://api.cloudflare.com/client/v4/zones/%s/dns_records/%s", c->zone, id->valuestring);
        char body[48];
        snprintf(body, sizeof body, "{\"content\":\"%s\"}", addr);
        status = request(url, HTTP_METHOD_PATCH, c->token, body, answer, 4096);
        ok = status == 200 && strstr(answer, "\"success\":true");
        if (!ok) snprintf(why, cap, "Cloudflare refused the change (%d)", status);
    }
    cJSON_Delete(root);
    free(answer);
    return ok;
}

static bool simple_get(const ddns_config_t *c, uint32_t ip, char *why, size_t cap)
{
    char url[320], answer[256];
    if (!ddns_build_url(c, ip, url, sizeof url)) return fail(why, cap, ip ? "the update URL is too long" : "waiting for the public address (Tailscale)");
    int status = request(url, HTTP_METHOD_GET, NULL, NULL, answer, sizeof answer);
    memset(url, 0, sizeof url);                              /* carries the token */
    if (status < 0) return fail(why, cap, c->provider == DDNS_DUCKDNS ? "cannot reach www.duckdns.org" : "cannot reach the update server");
    if (c->provider == DDNS_DUCKDNS) {
        if (status == 200 && !strncmp(answer, "OK", 2)) return true;
        return fail(why, cap, "DuckDNS answered KO: check the sub-domain and the token");
    }
    if (status >= 200 && status < 300) return true;
    snprintf(why, cap, "the update server answered %d", status);
    return false;
}

static void worker(void *arg)
{
    (void)arg;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    ddns_config_t *c = heap_caps_malloc(sizeof *c, MALLOC_CAP_SPIRAM);
    if (c) *c = s_cfg;
    xSemaphoreGive(s_lock);
    uint32_t ip = public_ip();
    char why[96] = "";
    bool ok = c && (c->provider == DDNS_CLOUDFLARE ? cloudflare(c, &ip, why, sizeof why) : simple_get(c, ip, why, sizeof why));
    if (c) {memset(c, 0, sizeof *c); free(c);}
    char addr[16];
    ip_text(ip, addr);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool was_failing = s_state.backoff_s != 0;
    ddns_result(&s_state, ok, ip, now_s());
    if (ok) snprintf(s_last, sizeof s_last, "Updated%s%s", addr[0] ? " to " : "", addr);
    else snprintf(s_last, sizeof s_last, "Not updated: %s", why);
    s_running = false;
    xSemaphoreGive(s_lock);
    if (ok) history_event(HIST_EV_UPLINK, HIST_INFO, "Dynamic DNS updated%s%s", addr[0] ? " to " : "", addr);
    else if (!was_failing) history_event(HIST_EV_UPLINK, HIST_WARN, "Dynamic DNS not updated: %s", why);   /* once per failure run */
    task_reaper_self_delete();
}

static void tick(void *arg)
{
    (void)arg;
    uint32_t ip = public_ip();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_seen_ip = ip;
    bool due = !s_running && (s_force || ddns_due(&s_state, s_cfg.provider, ip, now_s()));
    if (due) {
        s_force = false;
        /* A short-lived worker; nothing stays allocated between updates. */
        s_running = xTaskCreateWithCaps(worker, "ddns", 8192, NULL, 2, NULL, MALLOC_CAP_SPIRAM) == pdPASS;
    }
    xSemaphoreGive(s_lock);
}

static void apply_locked(void)
{
    if (s_cfg.provider != DDNS_OFF && !s_timer) {
        const esp_timer_create_args_t args = {.callback = tick, .name = "ddns"};
        if (esp_timer_create(&args, &s_timer) == ESP_OK) esp_timer_start_periodic(s_timer, 60ULL * 1000000);
        else s_timer = NULL;
    } else if (s_cfg.provider == DDNS_OFF && s_timer) {
        esp_timer_stop(s_timer);
        esp_timer_delete(s_timer);
        s_timer = NULL;
    }
}

void ddns_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    snprintf(s_last, sizeof s_last, "Not updated yet");
    load(&s_cfg);
    if (s_cfg.provider != DDNS_OFF) {xSemaphoreTake(s_lock, portMAX_DELAY); apply_locked(); xSemaphoreGive(s_lock);}
}

uint8_t ddns_provider(void) {return s_cfg.provider;}
bool ddns_last_update_ok(void) {return s_state.ever && !s_state.backoff_s;}

static const char *provider_name(uint8_t p) {return p == DDNS_DUCKDNS ? "duckdns" : p == DDNS_CLOUDFLARE ? "cloudflare" : p == DDNS_CUSTOM ? "custom" : "off";}

static esp_err_t get_ddns(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    cJSON *root = cJSON_CreateObject();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    cJSON_AddStringToObject(root, "provider", provider_name(s_cfg.provider));
    cJSON_AddStringToObject(root, "name", s_cfg.name);
    cJSON_AddStringToObject(root, "zone", s_cfg.zone);
    cJSON_AddBoolToObject(root, "has_token", s_cfg.token[0] != 0);
    cJSON_AddBoolToObject(root, "has_url", s_cfg.url[0] != 0);   /* the URL may carry a secret: never returned */
    cJSON_AddStringToObject(root, "status", s_last);
    char addr[16];
    ip_text(s_seen_ip ? s_seen_ip : public_ip(), addr);
    cJSON_AddStringToObject(root, "public_ip", addr);
    ip_text(s_state.last_ip, addr);
    cJSON_AddStringToObject(root, "updated_ip", addr);
    cJSON_AddNumberToObject(root, "updated_ago_s", s_state.ever ? now_s() - s_state.last_ok_s : -1);
    cJSON_AddBoolToObject(root, "running", s_running);
    xSemaphoreGive(s_lock);
    char *text = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!text) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, text);
    cJSON_free(text);
    return err;
}

static esp_err_t post_ddns(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char *body = heap_caps_malloc(1024, MALLOC_CAP_SPIRAM);
    ddns_config_t *next = heap_caps_malloc(sizeof *next, MALLOC_CAP_SPIRAM);
    if (!body || !next) {free(body); free(next); httpd_resp_send_500(req); return ESP_FAIL;}
    int total = req->content_len, received = 0;
    bool ok = total > 0 && total < 1024;
    while (ok && received < total) {int n = httpd_req_recv(req, body + received, total - received); if (n <= 0) ok = false; else received += n;}
    body[ok ? received : 0] = 0;
    cJSON *root = ok ? json_guard_parse(body) : NULL;
    memset(body, 0, 1024);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *next = s_cfg;
    xSemaphoreGive(s_lock);
    char why[120] = "invalid request";
    const cJSON *provider = cJSON_GetObjectItemCaseSensitive(root, "provider"), *update = cJSON_GetObjectItemCaseSensitive(root, "update_now");
    static const char *const names[] = {"off", "duckdns", "cloudflare", "custom"};
    int chosen = -1;
    for (int i = 0; cJSON_IsString(provider) && i < 4; i++) if (!strcmp(provider->valuestring, names[i])) chosen = i;
    ok = cJSON_IsObject(root) && chosen >= 0 && (!update || cJSON_IsBool(update));
    const char *keys[] = {"name", "zone", "token", "url"};
    char *fields[] = {next->name, next->zone, next->token, next->url};
    size_t caps[] = {sizeof next->name, sizeof next->zone, sizeof next->token, sizeof next->url};
    for (int i = 0; ok && i < 4; i++) {
        cJSON *v = cJSON_GetObjectItemCaseSensitive(root, keys[i]);
        if (!v) continue;
        if (!cJSON_IsString(v) || strlen(v->valuestring) >= caps[i]) {ok = false; break;}
        /* Secrets (token, URL) are write-only: empty keeps the saved value. */
        if ((i >= 2 && !v->valuestring[0])) continue;
        strcpy(fields[i], v->valuestring);
    }
    if (ok && chosen != next->provider) {
        /* Another provider: never reuse the old provider's secret. */
        if (!cJSON_GetObjectItemCaseSensitive(root, "token") || !cJSON_GetObjectItemCaseSensitive(root, "token")->valuestring[0]) next->token[0] = 0;
        if (chosen != DDNS_CUSTOM) next->url[0] = 0;
    }
    if (ok) next->provider = (uint8_t)chosen;
    if (ok && next->provider == DDNS_OFF) memset(next, 0, sizeof *next);   /* off: forget the secrets */
    bool force = cJSON_IsTrue(update);
    for (int i = 2; root && i < 4; i++) {cJSON *v = cJSON_GetObjectItemCaseSensitive(root, keys[i]); if (cJSON_IsString(v)) memset(v->valuestring, 0, strlen(v->valuestring));}
    cJSON_Delete(root);
    if (ok && !ddns_config_valid(next, why, sizeof why)) ok = false;
    esp_err_t err = ok ? save(next) : ESP_OK;
    if (ok && !err) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        bool changed = memcmp(&s_cfg, next, sizeof *next) != 0;
        s_cfg = *next;
        if (changed) {memset(&s_state, 0, sizeof s_state); snprintf(s_last, sizeof s_last, "Not updated yet");}
        s_force = s_force || force || changed;
        apply_locked();
        xSemaphoreGive(s_lock);
        if (s_cfg.provider != DDNS_OFF && (force || changed)) tick(NULL);
    }
    memset(next, 0, sizeof *next); free(next); free(body);
    httpd_resp_set_type(req, "application/json");
    if (!ok || err) {
        httpd_resp_set_status(req, ok ? "500 Internal Server Error" : "400 Bad Request");
        cJSON *r = cJSON_CreateObject();
        cJSON_AddBoolToObject(r, "ok", false);
        cJSON_AddStringToObject(r, "error", ok ? esp_err_to_name(err) : why);
        char *text = cJSON_PrintUnformatted(r);
        cJSON_Delete(r);
        esp_err_t e = httpd_resp_sendstr(req, text ? text : "{\"ok\":false}");
        cJSON_free(text);
        return e;
    }
    ESP_LOGI(TAG, "provider %s", provider_name(chosen));
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

esp_err_t ddns_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/ddns", .method = HTTP_GET, .handler = get_ddns},
        {.uri = "/api/ddns", .method = HTTP_POST, .handler = post_ddns}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
