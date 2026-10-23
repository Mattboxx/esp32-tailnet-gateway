/* First-boot setup: access point, captive portal, pairing and HTTP API.
 * SPDX-License-Identifier: MIT */
#include "first_boot.h"
#include "first_boot_core.h"

#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "driver/gpio.h"
#include "dns_relay.h"
#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "json_guard.h"
#include "mbedtls/gcm.h"
#include "mbedtls/sha256.h"
#include "lwip/sockets.h"
#include "nvs_params.h"
#include "web_password.h"
#include "web_ui.h"
#include "wifi_networks.h"

/* MicroLink's portable RFC 7748 implementation (src/ml_x25519.h). */
int ml_x25519(unsigned char out[32], const unsigned char scalar[32], const unsigned char base[32], int clamp);

#define TAG "first_boot"
#define FB_BUTTON_GPIO GPIO_NUM_0      /* BOOT button on ESP32-S3 DevKit boards */
#define FB_BODY_MAX 4096
/* The watcher logs through the console/capture hooks (vfprintf), which needed
 * more than the original 3 KiB: a real board overflowed it on a BOOT press.
 * PSRAM stack, so internal RAM is unchanged; headroom reported in the state. */
#define FB_TASK_STACK 6144

static bool s_active;
static bool s_finished;
static fb_ctx_t s_ctx;
static StaticSemaphore_t s_lock_storage;
static SemaphoreHandle_t s_lock;
static uint32_t s_ap_ip_nbo;
static TaskHandle_t s_task;

/* ---------------------------------------------------------------- crypto */

static void fb_random(uint8_t *out, size_t len) { esp_fill_random(out, len); }

static int fb_x25519(uint8_t out[32], const uint8_t scalar[32], const uint8_t point[32])
{
    return ml_x25519(out, scalar, point, 1);
}

static void fb_sha256(const uint8_t *data, size_t len, uint8_t out[32])
{
    mbedtls_sha256(data, len, out, 0);
}

static int fb_gcm_open(const uint8_t key[32], const uint8_t iv[12], const uint8_t *aad, size_t aad_len,
                       const uint8_t *ct, size_t ct_len, const uint8_t tag[16], uint8_t *pt)
{
    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    int ret = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key, 256);
    if (ret == 0) ret = mbedtls_gcm_auth_decrypt(&gcm, ct_len, iv, 12, aad, aad_len, tag, 16, ct, pt);
    mbedtls_gcm_free(&gcm);
    return ret == 0 ? 0 : -1;
}

static const fb_crypto_t s_crypto = { fb_random, fb_x25519, fb_sha256, fb_gcm_open };

/* ------------------------------------------------------------- lifecycle */

static void mac_suffix(char out[5])
{
    uint8_t mac[6] = {0};
    (void)esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP);
    snprintf(out, 5, "%02X%02X", mac[4], mac[5]);
}

void first_boot_setup_ssid(char *out, size_t cap)
{
    char sfx[5]; mac_suffix(sfx);
    snprintf(out, cap, "ESP32-Tailnet-Setup-%s", sfx);
}

void first_boot_default_ssid(char *out, size_t cap)
{
    char sfx[5]; mac_suffix(sfx);
    snprintf(out, cap, "ESP32-Tailnet-%s", sfx);
}

void first_boot_init(void)
{
    uint8_t done = 0;
    bool setup_done = nvs_param_get_u8("setup_done", &done) == ESP_OK && done;
    char *key = nvs_param_get_str("ts_authkey");
    bool has_key = key && key[0];
    free(key);
    bool password = is_web_password_set();
    int networks = wifi_networks_count();
    s_active = fb_should_activate(setup_done, password, networks, has_key);
    if (!s_active && !setup_done) {
        /* Existing installation (for example upgraded from 1.13): record it,
         * so removing its settings later can never reopen an open AP. */
        (void)nvs_param_set_u8("setup_done", 1);
    }
    if (!s_active) return;
    s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    fb_init(&s_ctx, &s_crypto);
    ESP_LOGW(TAG, "unconfigured device: first-boot setup access point active");
}

bool first_boot_active(void) { return s_active; }

static void restart_cb(void *arg) { (void)arg; esp_restart(); }

static void button_task(void *arg)
{
    (void)arg;
    gpio_config_t io = { .pin_bit_mask = 1ULL << FB_BUTTON_GPIO, .mode = GPIO_MODE_INPUT,
                         .pull_up_en = GPIO_PULLUP_ENABLE };
    bool button = gpio_config(&io) == ESP_OK;
    int held = 0;
    uint32_t ticks = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(50));
        uint64_t now = (uint64_t)esp_timer_get_time();
        if (button && gpio_get_level(FB_BUTTON_GPIO) == 0) {
            if (++held == 2) {                         /* 100 ms debounce */
                xSemaphoreTake(s_lock, portMAX_DELAY);
                fb_result_t r = fb_presence(&s_ctx, now);
                xSemaphoreGive(s_lock);
                ESP_LOGW(TAG, "BOOT button: %s", r == FB_OK ? "pairing confirmed" : "no pending pairing");
            }
        } else {
            held = 0;
        }
        if (ticks++ % 600 == 0 && !s_finished) {        /* every 30 s */
            xSemaphoreTake(s_lock, portMAX_DELAY);
            char code[FB_CODE_DIGITS + 1];
            memcpy(code, s_ctx.code, sizeof code);
            xSemaphoreGive(s_lock);
            /* WARN level: the console default shows it. Physical access only. */
            ESP_LOGW(TAG, "Setup code (USB console): %.4s %.4s", code, code + 4);
            memset(code, 0, sizeof code);
        }
    }
}

void first_boot_start(void)
{
    if (!s_active) return;
    esp_netif_t *ap = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
    esp_netif_ip_info_t info = {0};
    if (ap && esp_netif_get_ip_info(ap, &info) == ESP_OK) s_ap_ip_nbo = info.ip.addr;
    if (!dns_relay_is_enabled()) dns_relay_set_enabled(true);
    dns_relay_set_captive(s_ap_ip_nbo);
    if (xTaskCreateWithCaps(button_task, "first_boot", FB_TASK_STACK, NULL, 3, &s_task,
                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) != pdPASS) {
        s_task = NULL;
        ESP_LOGE(TAG, "presence task not started: setup code unavailable on the console");
    }
}

bool first_boot_ap_frame_allowed(const uint8_t *frame, size_t len)
{
    if (!s_active) return true;
    return s_ap_ip_nbo && fb_ap_frame_allowed(frame, len, s_ap_ip_nbo);
}

/* ------------------------------------------------------------------ HTTP */

static esp_err_t send_json(httpd_req_t *req, const char *status, cJSON *root)
{
    if (status) httpd_resp_set_status(req, status);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    char *body = root ? cJSON_PrintUnformatted(root) : NULL;
    cJSON_Delete(root);
    esp_err_t err = httpd_resp_sendstr(req, body ? body : "{\"error\":\"memory\"}");
    free(body);
    return err;
}

static esp_err_t send_error(httpd_req_t *req, const char *status, const char *code, const char *detail)
{
    cJSON *root = cJSON_CreateObject();
    if (root) {
        cJSON_AddStringToObject(root, "error", code);
        if (detail) cJSON_AddStringToObject(root, "detail", detail);
    }
    return send_json(req, status, root);
}

static uint32_t client_ip(httpd_req_t *req)
{
    struct sockaddr_storage peer = {0};
    socklen_t len = sizeof peer;
    int fd = httpd_req_to_sockfd(req);
    if (fd < 0 || getpeername(fd, (struct sockaddr *)&peer, &len) != 0 || peer.ss_family != AF_INET) return 0;
    return ((struct sockaddr_in *)&peer)->sin_addr.s_addr;
}

/* Setup endpoints exist only on an unconfigured device, only through its
 * own AP, and keep the ordinary same-origin request screening. */
static bool setup_request(httpd_req_t *req)
{
    if (!s_active) {
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "setup is complete");
        return false;
    }
    return web_ui_setup_request_ok(req);
}

static cJSON *read_json(httpd_req_t *req, char *buf, size_t cap)
{
    if (req->content_len <= 0 || (size_t)req->content_len >= cap) {
        send_error(req, "413 Payload Too Large", "size", NULL);
        return NULL;
    }
    int got = 0;
    while (got < req->content_len) {
        int n = httpd_req_recv(req, buf + got, req->content_len - got);
        if (n <= 0) return NULL;
        got += n;
    }
    buf[got] = '\0';
    cJSON *root = json_guard_preflight(buf, (size_t)got) ? json_guard_parse(buf) : NULL;
    if (!root) send_error(req, "400 Bad Request", "json", NULL);
    return root;
}

static bool get_sid(const cJSON *root, httpd_req_t *req, uint8_t sid[FB_SID_BYTES])
{
    char hex[FB_SID_BYTES * 2 + 1];
    const cJSON *v = root ? cJSON_GetObjectItem(root, "sid") : NULL;
    if (cJSON_IsString(v)) return fb_hex_decode(v->valuestring, sid, FB_SID_BYTES) == 0;
    if (req && httpd_req_get_hdr_value_str(req, "X-Setup-Session", hex, sizeof hex) == ESP_OK)
        return fb_hex_decode(hex, sid, FB_SID_BYTES) == 0;
    return false;
}

static const char *wifi_state_name(fb_wifi_state_t s)
{
    switch (s) {
    case FB_WIFI_TESTING: return "testing";
    case FB_WIFI_OK: return "ok";
    case FB_WIFI_FAILED: return "failed";
    default: return "idle";
    }
}

static esp_err_t state_handler(httpd_req_t *req)
{
    cJSON *root = cJSON_CreateObject();
    if (!root) return httpd_resp_send_500(req);
    cJSON_AddBoolToObject(root, "setup", s_active);
    if (!s_active) return send_json(req, NULL, root);
    if (!web_ui_setup_request_ok(req)) { cJSON_Delete(root); return ESP_FAIL; }
    char ssid[40];
    first_boot_setup_ssid(ssid, sizeof ssid);
    cJSON_AddStringToObject(root, "setup_ssid", ssid);
    first_boot_default_ssid(ssid, sizeof ssid);
    cJSON_AddStringToObject(root, "default_ap_ssid", ssid);
    cJSON_AddStringToObject(root, "version", esp_app_get_description()->version);
    uint8_t sid[FB_SID_BYTES];
    bool have_sid = get_sid(NULL, req, sid);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    fb_tick(&s_ctx, (uint64_t)esp_timer_get_time());
    fb_state_t st = have_sid ? fb_session_state(&s_ctx, sid) : FB_NONE;
    bool locked = s_ctx.code_failures >= FB_CODE_MAX_FAILS;
    bool busy = s_ctx.s.state != FB_NONE && st == FB_NONE;
    xSemaphoreGive(s_lock);
    cJSON_AddStringToObject(root, "session", st == FB_CLAIMED ? "claimed" : st == FB_PENDING ? "pending" : "none");
    cJSON_AddBoolToObject(root, "other_pairing", busy);
    cJSON_AddBoolToObject(root, "code_locked", locked);
    cJSON_AddBoolToObject(root, "finished", s_finished);
    if (s_task) cJSON_AddNumberToObject(root, "presence_stack_free", uxTaskGetStackHighWaterMark(s_task));
    cJSON_AddNumberToObject(root, "pairing_window_s", (double)(FB_PENDING_TTL_US / 1000000ULL));
    if (st == FB_CLAIMED) {
        fb_wifi_state_t ws; uint32_t ip = 0, mask = 0; int reason = 0;
        wifi_setup_test_get(&ws, &ip, &mask, &reason);
        cJSON *w = cJSON_AddObjectToObject(root, "wifi");
        if (w) {
            cJSON_AddStringToObject(w, "state", wifi_state_name(ws));
            if (ws == FB_WIFI_OK) {
                char a[16];
                esp_ip4addr_ntoa((const esp_ip4_addr_t *)&ip, a, sizeof a);
                cJSON_AddStringToObject(w, "ip", a);
                cJSON_AddNumberToObject(w, "prefix", __builtin_popcount(mask));
            }
            if (ws == FB_WIFI_FAILED) cJSON_AddNumberToObject(w, "reason", reason);
        }
    }
    return send_json(req, NULL, root);
}

static esp_err_t begin_handler(httpd_req_t *req)
{
    if (!setup_request(req)) return ESP_FAIL;
    char buf[256];
    cJSON *root = read_json(req, buf, sizeof buf);
    if (!root) return ESP_FAIL;
    uint8_t pub[32];
    const cJSON *p = cJSON_GetObjectItem(root, "client_pub");
    bool ok = cJSON_IsString(p) && fb_hex_decode(p->valuestring, pub, 32) == 0;
    cJSON_Delete(root);
    if (!ok) return send_error(req, "400 Bad Request", "client_pub", NULL);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    fb_result_t r = fb_begin(&s_ctx, client_ip(req), pub, (uint64_t)esp_timer_get_time());
    char sid[FB_SID_BYTES * 2 + 1], dpub[65], code[FB_CODE_DIGITS + 1] = "";
    if (r == FB_OK) {
        fb_hex_encode(s_ctx.s.sid, FB_SID_BYTES, sid);
        fb_hex_encode(s_ctx.s.device_pub, 32, dpub);
        memcpy(code, s_ctx.code, sizeof code);
    }
    xSemaphoreGive(s_lock);
    if (r == FB_OK) {
        /* Print at once so nobody waits for the 30 s reminder. */
        ESP_LOGW(TAG, "Pairing waiting: press BOOT, or enter setup code %.4s %.4s", code, code + 4);
        memset(code, 0, sizeof code);
    }
    if (r == FB_ERR_BUSY) return send_error(req, "409 Conflict", "busy", "another device is pairing");
    if (r == FB_ERR_CLAIMED) return send_error(req, "409 Conflict", "claimed", "already paired with another device");
    if (r != FB_OK) return send_error(req, "400 Bad Request", "client_pub", NULL);
    cJSON *out = cJSON_CreateObject();
    if (!out) return httpd_resp_send_500(req);
    cJSON_AddStringToObject(out, "sid", sid);
    cJSON_AddStringToObject(out, "device_pub", dpub);
    cJSON_AddNumberToObject(out, "expires_s", (double)(FB_PENDING_TTL_US / 1000000ULL));
    cJSON_AddBoolToObject(out, "button", true);
    return send_json(req, NULL, out);
}

static esp_err_t claim_handler(httpd_req_t *req)
{
    if (!setup_request(req)) return ESP_FAIL;
    char buf[256];
    cJSON *root = read_json(req, buf, sizeof buf);
    if (!root) return ESP_FAIL;
    uint8_t sid[FB_SID_BYTES];
    const cJSON *code = cJSON_GetObjectItem(root, "code");
    bool ok = get_sid(root, NULL, sid) && cJSON_IsString(code);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    fb_result_t r = ok ? fb_claim_code(&s_ctx, sid, code->valuestring, (uint64_t)esp_timer_get_time()) : FB_ERR_NO_SESSION;
    int left = FB_CODE_MAX_FAILS - s_ctx.code_failures;
    xSemaphoreGive(s_lock);
    cJSON_Delete(root);
    memset(buf, 0, sizeof buf);
    if (r == FB_OK) {
        cJSON *out = cJSON_CreateObject();
        if (out) cJSON_AddBoolToObject(out, "claimed", true);
        return send_json(req, NULL, out);
    }
    if (r == FB_ERR_LOCKED) return send_error(req, "423 Locked", "locked", "too many wrong codes; restart the gateway");
    if (r == FB_ERR_BAD_CODE) {
        char d[24]; snprintf(d, sizeof d, "%d", left < 0 ? 0 : left);
        return send_error(req, "403 Forbidden", "bad_code", d);
    }
    return send_error(req, "404 Not Found", "session", NULL);
}

static const char *str_of(const cJSON *o, const char *k)
{
    const cJSON *v = o ? cJSON_GetObjectItem(o, k) : NULL;
    return cJSON_IsString(v) ? v->valuestring : NULL;
}

static bool bool_of(const cJSON *o, const char *k, bool dflt)
{
    const cJSON *v = o ? cJSON_GetObjectItem(o, k) : NULL;
    return cJSON_IsBool(v) ? cJSON_IsTrue(v) : dflt;
}

static void wipe_strings(cJSON *node)
{
    for (; node; node = node->next) {
        if (cJSON_IsString(node) && node->valuestring) memset(node->valuestring, 0, strlen(node->valuestring));
        wipe_strings(node->child);
    }
}

/* LAN CIDR of the tested uplink, for the optional subnet route. */
static bool tested_lan_cidr(char *out, size_t cap)
{
    fb_wifi_state_t ws; uint32_t ip = 0, mask = 0; int reason = 0;
    wifi_setup_test_get(&ws, &ip, &mask, &reason);
    if (ws != FB_WIFI_OK || !mask) return false;
    uint32_t net = lwip_ntohl(ip & mask);
    snprintf(out, cap, "%u.%u.%u.%u/%d", (unsigned)(net >> 24), (unsigned)((net >> 16) & 255),
             (unsigned)((net >> 8) & 255), (unsigned)(net & 255), __builtin_popcount(mask));
    return true;
}

static esp_err_t finish(httpd_req_t *req, const cJSON *cmd)
{
    const cJSON *wifi = cJSON_GetObjectItem(cmd, "wifi");
    const cJSON *tn = cJSON_GetObjectItem(cmd, "tailnet");
    const char *admin = str_of(cmd, "admin_password");
    const char *ssid = str_of(wifi, "ssid"), *wpw = str_of(wifi, "password");
    const char *ap_ssid = str_of(cmd, "ap_ssid"), *ap_pw = str_of(cmd, "ap_password");
    const char *key = str_of(tn, "auth_key"), *server = str_of(tn, "login_server"), *host = str_of(tn, "hostname");
    const char *reason = fb_check_admin_password(admin, ssid);
    if (!reason) reason = fb_check_wifi(ssid, wpw ? wpw : "");
    if (!reason) reason = fb_check_ap_password(ap_pw);
    if (!reason && (!ap_ssid || !*ap_ssid || strlen(ap_ssid) > 32)) reason = "access point name must be 1 to 32 bytes";
    if (!reason) reason = fb_check_auth_key(key);
    if (!reason) reason = fb_check_login_server(server);
    if (!reason) reason = fb_check_hostname(host);
    if (!reason && ap_pw && admin && !strcmp(ap_pw, admin)) reason = "use a different password for the access point";
    if (reason) return send_error(req, "400 Bad Request", "invalid", reason);
    bool share_lan = bool_of(cmd, "share_lan", false), share_ap = bool_of(cmd, "share_ap", false);
    bool exit_node = bool_of(cmd, "exit_node", false), ap_recovery = bool_of(cmd, "ap_recovery_only", true);
    char cidr[24] = "";
    if (share_lan && !tested_lan_cidr(cidr, sizeof cidr)) return send_error(req, "400 Bad Request", "invalid", "test the Wi-Fi connection before sharing the home network");

    /* Order matters for power loss: the protected AP first, then the admin
     * password (which ends setup mode), then the rest, then the marker. */
    esp_err_t e = nvs_param_set_str("ap_ssid", ap_ssid);
    if (e == ESP_OK) e = nvs_param_set_str("ap_passwd", ap_pw);
    if (e == ESP_OK) e = nvs_param_set_u8("ap_auto_off", ap_recovery ? 1 : 0);
    if (e == ESP_OK) e = set_web_password_hashed(admin);
    if (e == ESP_OK) {
        wifi_network_t n = {0};
        strlcpy(n.ssid, ssid, sizeof n.ssid);
        strlcpy(n.passwd, wpw ? wpw : "", sizeof n.passwd);
        n.valid = 1;
        e = wifi_networks_set_all(&n, 1);
        memset(&n, 0, sizeof n);
    }
    bool join = key && *key;
    if (e == ESP_OK) e = nvs_param_set_int("ts_enabled", join ? 1 : 0);
    if (e == ESP_OK && join) e = nvs_param_set_str("ts_authkey", key);
    if (e == ESP_OK && join) e = nvs_param_set_str("ts_login", server ? server : "");
    if (e == ESP_OK && join && host && *host) e = nvs_param_set_str("ts_hostname", host);
    if (e == ESP_OK) e = nvs_param_set_int("ts_adv_ap", share_ap ? 1 : 0);
    if (e == ESP_OK) e = nvs_param_set_str("ts_routes", cidr);
    if (e == ESP_OK) e = nvs_param_set_int("ts_adv_exit", exit_node ? 1 : 0);
    /* Roles chosen in the wizard: the dashboard highlights them and opens the
     * first one's guide once. Only known ids are stored. */
    char roles[72] = "";
    const cJSON *rl = cJSON_GetObjectItem(cmd, "roles"), *r;
    static const char *known[] = {"lan-tailnet", "subnet-router", "iot-ap", "wol", "home-assistant", "advanced"};
    cJSON_ArrayForEach(r, rl) {
        for (size_t i = 0; cJSON_IsString(r) && i < sizeof known / sizeof known[0]; i++)
            if (!strcmp(r->valuestring, known[i]) && !strstr(roles, known[i])
                    && strlen(roles) + strlen(known[i]) + 2 < sizeof roles) {
                if (roles[0]) strlcat(roles, ",", sizeof roles);
                strlcat(roles, known[i], sizeof roles);
            }
    }
    if (e == ESP_OK) e = nvs_param_set_str("ui_roles", roles);
    if (e == ESP_OK) e = nvs_param_set_u8("ui_adv", bool_of(cmd, "advanced_ui", false) ? 1 : 0);
    const char *name = str_of(cmd, "device_name");
    if (e == ESP_OK && name && *name && strlen(name) <= 32) e = nvs_param_set_str("dev_name", name);
    if (e == ESP_OK) e = nvs_param_set_u8("setup_done", 1);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "setup could not be saved: %s", esp_err_to_name(e));
        return send_error(req, "500 Internal Server Error", "storage", esp_err_to_name(e));
    }
    s_finished = true;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    fb_wipe(&s_ctx);
    xSemaphoreGive(s_lock);
    dns_relay_set_captive(0);
    static esp_timer_handle_t timer;
    const esp_timer_create_args_t args = { .callback = restart_cb, .name = "fb_restart" };
    if (!timer && esp_timer_create(&args, &timer) == ESP_OK) esp_timer_start_once(timer, 3000000);
    ESP_LOGW(TAG, "first-boot setup saved; restarting into normal mode");
    cJSON *out = cJSON_CreateObject();
    if (out) {
        cJSON_AddBoolToObject(out, "ok", true);
        cJSON_AddNumberToObject(out, "restart_in_s", 3);
        cJSON_AddBoolToObject(out, "tailnet", join);
    }
    return send_json(req, NULL, out);
}

static esp_err_t apply_handler(httpd_req_t *req)
{
    if (!setup_request(req)) return ESP_FAIL;
    char *buf = malloc(FB_BODY_MAX);
    char *pt = malloc(FB_MAX_PLAINTEXT + 1);
    uint8_t *ct = malloc(FB_MAX_PLAINTEXT);
    if (!buf || !pt || !ct) {
        free(buf); free(pt); free(ct);
        return httpd_resp_send_500(req);
    }
    esp_err_t result = ESP_FAIL;
    cJSON *root = read_json(req, buf, FB_BODY_MAX);
    cJSON *cmd = NULL;
    if (!root) goto out;
    uint8_t sid[FB_SID_BYTES], iv[FB_IV_BYTES], tag[FB_TAG_BYTES];
    const char *ivh = str_of(root, "iv"), *cth = str_of(root, "ct"), *tagh = str_of(root, "tag");
    const cJSON *seqv = cJSON_GetObjectItem(root, "seq");
    size_t ct_len = cth ? strlen(cth) / 2 : 0;
    bool shape = get_sid(root, NULL, sid) && cJSON_IsNumber(seqv) && seqv->valuedouble >= 1
        && seqv->valuedouble <= 4294967295.0 && seqv->valuedouble == (double)(uint32_t)seqv->valuedouble
        && ivh && fb_hex_decode(ivh, iv, sizeof iv) == 0 && tagh && fb_hex_decode(tagh, tag, sizeof tag) == 0
        && cth && ct_len > 0 && ct_len <= FB_MAX_PLAINTEXT && fb_hex_decode(cth, ct, ct_len) == 0;
    if (!shape) { result = send_error(req, "400 Bad Request", "shape", NULL); goto out; }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    fb_result_t r = fb_open(&s_ctx, sid, (uint32_t)seqv->valuedouble, iv, ct, ct_len, tag, pt,
                            (uint64_t)esp_timer_get_time());
    xSemaphoreGive(s_lock);
    if (r == FB_ERR_NOT_CLAIMED) { result = send_error(req, "403 Forbidden", "not_paired", NULL); goto out; }
    if (r == FB_ERR_NO_SESSION) { result = send_error(req, "404 Not Found", "session", NULL); goto out; }
    if (r == FB_ERR_REPLAY) { result = send_error(req, "409 Conflict", "replay", NULL); goto out; }
    if (r != FB_OK) { result = send_error(req, "403 Forbidden", "seal", NULL); goto out; }
    cmd = json_guard_preflight(pt, strlen(pt)) ? json_guard_parse(pt) : NULL;
    memset(pt, 0, FB_MAX_PLAINTEXT + 1);
    const char *action = str_of(cmd, "action");
    if (!action) { result = send_error(req, "400 Bad Request", "action", NULL); goto out; }
    if (!strcmp(action, "wifi_test")) {
        const cJSON *w = cJSON_GetObjectItem(cmd, "wifi");
        const char *ssid = str_of(w, "ssid"), *pw = str_of(w, "password");
        const char *reason = fb_check_wifi(ssid, pw ? pw : "");
        if (reason) { result = send_error(req, "400 Bad Request", "invalid", reason); goto out; }
        if (wifi_setup_test_start(ssid, pw ? pw : "") != ESP_OK) { result = send_error(req, "503 Service Unavailable", "wifi", NULL); goto out; }
        cJSON *o = cJSON_CreateObject();
        if (o) cJSON_AddStringToObject(o, "wifi", "testing");
        result = send_json(req, NULL, o);
    } else if (!strcmp(action, "finish")) {
        result = finish(req, cmd);
    } else {
        result = send_error(req, "400 Bad Request", "action", NULL);
    }
out:
    if (cmd) { wipe_strings(cmd); cJSON_Delete(cmd); }
    if (root) cJSON_Delete(root);
    memset(buf, 0, FB_BODY_MAX); memset(ct, 0, FB_MAX_PLAINTEXT);
    free(buf); free(pt); free(ct);
    return result;
}

esp_err_t first_boot_not_found(httpd_req_t *req, httpd_err_code_t err)
{
    (void)err;
    if (s_active && s_ap_ip_nbo) {
        /* OS connectivity probes (generate_204, hotspot-detect, connecttest)
         * land here through the captive DNS: answering with a redirect makes
         * phones and PCs open the setup page. */
        char loc[40], ip[16];
        esp_ip4addr_ntoa((const esp_ip4_addr_t *)&s_ap_ip_nbo, ip, sizeof ip);
        snprintf(loc, sizeof loc, "http://%s/", ip);
        httpd_resp_set_status(req, "302 Found");
        httpd_resp_set_hdr(req, "Location", loc);
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "not found");
    return ESP_FAIL;
}

esp_err_t first_boot_register_http(httpd_handle_t server)
{
    static const httpd_uri_t uris[] = {
        { .uri = "/api/setup/state", .method = HTTP_GET, .handler = state_handler },
        { .uri = "/api/setup/begin", .method = HTTP_POST, .handler = begin_handler },
        { .uri = "/api/setup/claim", .method = HTTP_POST, .handler = claim_handler },
        { .uri = "/api/setup/apply", .method = HTTP_POST, .handler = apply_handler },
    };
    for (size_t i = 0; i < sizeof uris / sizeof uris[0]; i++) {
        esp_err_t e = httpd_register_uri_handler(server, &uris[i]);
        if (e != ESP_OK) return e;
    }
    return httpd_register_err_handler(server, HTTPD_404_NOT_FOUND, first_boot_not_found);
}
