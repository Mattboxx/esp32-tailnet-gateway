/* Telegram and email notifications; see notify_channels.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "notify_channels.h"
#include "history.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* --- notify core (begin) --- */
static bool is_digit(char c) {return c >= '0' && c <= '9';}
static bool is_alnum(char c) {return is_digit(c) || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');}
static char upper(char c) {return c >= 'a' && c <= 'z' ? (char)(c - 'a' + 'A') : c;}

static bool fail(char *why, size_t cap, const char *text)
{
    if (why && cap) snprintf(why, cap, "%s", text);
    return false;
}

/* Printable ASCII only: no CR/LF (header and command injection), no controls. */
static bool printable(const char *s, size_t max)
{
    size_t n = 0;
    for (; s[n]; n++) if ((unsigned char)s[n] < 0x20 || (unsigned char)s[n] > 0x7E || n >= max) return false;
    return true;
}

static bool hostname_valid(const char *h)
{
    size_t n = strlen(h), label = 0;
    if (!n || n > 63 || h[0] == '.' || h[0] == '-' || h[n - 1] == '.' || h[n - 1] == '-') return false;
    for (size_t i = 0; i < n; i++) {
        if (h[i] == '.') {if (!label) return false; label = 0; continue;}
        if (!is_alnum(h[i]) && h[i] != '-') return false;
        if (++label > 63) return false;
    }
    return true;
}

static bool email_valid(const char *e)
{
    const char *at = strchr(e, '@');
    if (!at || at == e || strchr(at + 1, '@') || strlen(e) > 95 || !strchr(at + 1, '.')) return false;
    for (const char *p = e; p < at; p++)
        if (!is_alnum(*p) && !strchr("._%+-", *p)) return false;
    return hostname_valid(at + 1);
}

bool notify_config_valid(const notify_config_t *c, char *why, size_t cap)
{
    if (!c) return fail(why, cap, "missing settings");
    if (c->level > NOTIFY_ALL) return fail(why, cap, "unknown event selection");
    if (c->tg_enabled) {
        const char *t = c->tg_token, *colon = strchr(t, ':');
        size_t id = colon ? (size_t)(colon - t) : 0, secret = colon ? strlen(colon + 1) : 0;
        bool ok = colon && id >= 5 && id <= 12 && secret >= 30 && secret <= 64;
        for (size_t i = 0; ok && i < id; i++) ok = is_digit(t[i]);
        for (const char *p = colon ? colon + 1 : ""; ok && *p; p++) ok = is_alnum(*p) || *p == '_' || *p == '-';
        if (!ok) return fail(why, cap, "the bot token looks like 123456789:AA... (from @BotFather)");
        const char *chat = c->tg_chat;
        size_t n = strlen(chat);
        bool chat_ok = n > 0 && n < sizeof c->tg_chat;
        if (chat_ok && chat[0] == '@') {
            chat_ok = n >= 6 && n <= 33;
            for (size_t i = 1; chat_ok && i < n; i++) chat_ok = is_alnum(chat[i]) || chat[i] == '_';
        } else if (chat_ok) {
            size_t i = chat[0] == '-' ? 1 : 0;
            chat_ok = n > i && n - i <= 20;
            for (; chat_ok && i < n; i++) chat_ok = is_digit(chat[i]);
        }
        if (!chat_ok) return fail(why, cap, "the chat id is a number (groups start with -) or @channelname");
    }
    if (c->mail_enabled) {
        if (!hostname_valid(c->mail_host)) return fail(why, cap, "enter the SMTP server name, e.g. smtp.example.com");
        if (!c->mail_port) return fail(why, cap, "enter the SMTP port (465 or 587)");
        if (c->mail_security > NOTIFY_STARTTLS) return fail(why, cap, "unknown connection security");
        if (!email_valid(c->mail_from) || !email_valid(c->mail_to)) return fail(why, cap, "sender and recipient must be plain addresses like name@example.com");
        if (!printable(c->mail_user, sizeof c->mail_user - 1) || !printable(c->mail_pass, sizeof c->mail_pass - 1))
            return fail(why, cap, "user name and password must be printable characters");
        if (!c->mail_user[0] != !c->mail_pass[0]) return fail(why, cap, "enter both the user name and the password, or neither");
    }
    return true;
}

size_t notify_base64(const void *in, size_t len, char *out, size_t cap)
{
    static const char abc[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const uint8_t *p = in;
    size_t need = (len + 2) / 3 * 4;
    if (!out || need + 1 > cap) return 0;
    size_t o = 0;
    for (size_t i = 0; i < len; i += 3) {
        uint32_t v = (uint32_t)p[i] << 16 | (i + 1 < len ? (uint32_t)p[i + 1] << 8 : 0) | (i + 2 < len ? p[i + 2] : 0);
        out[o++] = abc[v >> 18 & 63]; out[o++] = abc[v >> 12 & 63];
        out[o++] = i + 1 < len ? abc[v >> 6 & 63] : '=';
        out[o++] = i + 2 < len ? abc[v & 63] : '=';
    }
    out[o] = 0;
    return o;
}

static size_t json_text(char *out, size_t cap, const char *in)
{
    size_t n = 0;
    for (; *in; in++) {
        unsigned char c = (unsigned char)*in;
        char tmp[8];
        int len = c == '"' || c == '\\' ? snprintf(tmp, sizeof tmp, "\\%c", c) :
                  c == '\n' ? snprintf(tmp, sizeof tmp, "\\n") :
                  c < 0x20 || c == 0x7F ? snprintf(tmp, sizeof tmp, "\\u%04x", c) : snprintf(tmp, sizeof tmp, "%c", c);
        if (n + (size_t)len >= cap) return 0;
        memcpy(out + n, tmp, (size_t)len);
        n += (size_t)len;
    }
    out[n] = 0;
    return n;
}

size_t notify_telegram_body(char *out, size_t cap, const char *chat, const char *text)
{
    char chat_json[64], text_json[NOTIFY_TEXT_MAX * 6 + 64];
    if (!out || !chat || !text || !json_text(chat_json, sizeof chat_json, chat) ||
        (text[0] && !json_text(text_json, sizeof text_json, text))) return 0;
    if (!text[0]) return 0;
    int n = snprintf(out, cap, "{\"chat_id\":\"%s\",\"text\":\"%s\",\"disable_web_page_preview\":true}", chat_json, text_json);
    return n > 0 && (size_t)n < cap ? (size_t)n : 0;
}

bool notify_wanted(uint8_t setting, unsigned kind, unsigned level)
{
    if (kind == HIST_EV_SERVICE) return true;   /* operational results, always */
    return setting == NOTIFY_ALL || level >= HIST_WARN;
}

typedef struct {
    const notify_smtp_io_t *io;
    char buf[1024];
    size_t len;
    char *why;
    size_t cap;
} smtp_t;

static void note_reply(smtp_t *s, const char *what, const char *line, size_t len)
{
    if (!s->why || !s->cap) return;
    char text[96];
    size_t n = len < sizeof text - 1 ? len : sizeof text - 1;
    for (size_t i = 0; i < n; i++) text[i] = (unsigned char)line[i] < 0x20 || (unsigned char)line[i] > 0x7E ? '?' : line[i];
    text[n] = 0;
    /* What to do first, then the server's own words for the details. */
    int code = n >= 3 && is_digit(text[0]) && is_digit(text[1]) && is_digit(text[2]) ? (text[0] - 48) * 100 + (text[1] - 48) * 10 + (text[2] - 48) : 0;
    const char *hint = code == 530 ? "sign-in required: enter the user name and password — "
                     : code == 535 ? "user name or password not accepted (many providers need an app password) — "
                     : (code == 550 || code == 553) && !strcmp(what, "sender") ? "the server refused the From address — "
                     : "";
    snprintf(s->why, s->cap, "%s%s: %s", hint, what, text);
}

/* Reads one (possibly multi-line) reply; returns its code or -1. */
static int reply(smtp_t *s, const char *what)
{
    s->len = 0;
    s->buf[0] = 0;
    for (;;) {
        size_t start = 0;
        for (size_t i = 0; i + 1 < s->len; i++) {
            if (s->buf[i] != '\r' || s->buf[i + 1] != '\n') continue;
            const char *line = s->buf + start;
            size_t n = i - start;
            if (n < 3 || !is_digit(line[0]) || !is_digit(line[1]) || !is_digit(line[2]) || (n > 3 && line[3] != ' ' && line[3] != '-')) {
                fail(s->why, s->cap, "the server sent something that is not SMTP");
                return -1;
            }
            if (n == 3 || line[3] == ' ') {
                int code = (line[0] - '0') * 100 + (line[1] - '0') * 10 + (line[2] - '0');
                note_reply(s, what, line, n);
                return code;
            }
            start = i + 2;
        }
        if (s->len >= sizeof s->buf - 1) {fail(s->why, s->cap, "server reply too long"); return -1;}
        int n = s->io->recv(s->io->ctx, s->buf + s->len, sizeof s->buf - 1 - s->len);
        if (n <= 0) {fail(s->why, s->cap, s->len ? "the server stopped answering" : "no answer from the server"); return -1;}
        s->len += (size_t)n;
        s->buf[s->len] = 0;
    }
}

static bool send_all(smtp_t *s, const char *data, size_t len)
{
    while (len) {
        int n = s->io->send(s->io->ctx, data, len);
        if (n <= 0) return fail(s->why, s->cap, "connection lost while sending");
        data += n; len -= (size_t)n;
    }
    return true;
}

static int command(smtp_t *s, const char *what, const char *a, const char *b, const char *c)
{
    char line[600];
    int n = snprintf(line, sizeof line, "%s%s%s\r\n", a, b ? b : "", c ? c : "");
    bool ok = n > 0 && (size_t)n < sizeof line && send_all(s, line, (size_t)n);
    memset(line, 0, sizeof line);                   /* may hold login data */
    return ok ? reply(s, what) : -1;
}

/* EHLO keyword lookup, case-insensitive, in the last reply. */
static bool offers(const smtp_t *s, const char *keyword, const char *method)
{
    size_t k = strlen(keyword);
    for (const char *line = s->buf; line && *line; line = strstr(line, "\r\n") ? strstr(line, "\r\n") + 2 : NULL) {
        if (strlen(line) < 4 + k) continue;
        bool match = true;
        for (size_t i = 0; match && i < k; i++) match = upper(line[4 + i]) == keyword[i];
        if (!match) continue;
        char next = line[4 + k];
        if (!method) {if (next == '\r' || next == ' ' || next == 0) return true; continue;}
        if (next != ' ' && next != '=') continue;
        size_t m = strlen(method);
        for (const char *p = line + 4 + k; *p && *p != '\r'; p++) {
            if (p[-1] != ' ' && p[-1] != '=') continue;
            bool same = true;
            for (size_t i = 0; same && i < m; i++) same = upper(p[i]) == method[i];
            if (same && (p[m] == ' ' || p[m] == '\r' || p[m] == 0)) return true;
        }
    }
    return false;
}

esp_err_t notify_smtp_send(const notify_smtp_io_t *io, const notify_mail_t *m, char *why, size_t cap)
{
    if (!io || !m || !m->from || !m->to || !m->subject || !m->body || !m->helo) return ESP_ERR_INVALID_ARG;
    smtp_t *s = calloc(1, sizeof *s);
    if (!s) return ESP_ERR_NO_MEM;
    s->io = io; s->why = why; s->cap = cap;
    esp_err_t result = ESP_FAIL;
    char secret[400];
    secret[0] = 0;
    if (reply(s, "greeting") != 220) goto done;
    if (command(s, "EHLO", "EHLO ", m->helo, NULL) != 250) goto done;
    if (m->starttls) {
        /* Never fall back to plain text: no STARTTLS, no login. */
        if (!offers(s, "STARTTLS", NULL)) {fail(why, cap, "the server does not offer STARTTLS on this port"); goto done;}
        if (command(s, "STARTTLS", "STARTTLS", NULL, NULL) != 220) goto done;
        if (!io->starttls || io->starttls(io->ctx) != 0) {fail(why, cap, "TLS failed (certificate or protocol)"); goto done;}
        if (command(s, "EHLO", "EHLO ", m->helo, NULL) != 250) goto done;
    }
    if (m->user && m->user[0]) {
        size_t ul = strlen(m->user), pl = m->pass ? strlen(m->pass) : 0;
        if (ul + pl + 2 > 200) {fail(why, cap, "user name or password too long"); goto done;}
        if (offers(s, "AUTH", "PLAIN")) {
            char plain[204];
            plain[0] = 0; memcpy(plain + 1, m->user, ul); plain[1 + ul] = 0; memcpy(plain + 2 + ul, m->pass, pl);
            size_t n = notify_base64(plain, ul + pl + 2, secret, sizeof secret);
            memset(plain, 0, sizeof plain);
            if (!n || command(s, "login", "AUTH PLAIN ", secret, NULL) != 235) goto done;
        } else if (offers(s, "AUTH", "LOGIN")) {
            if (command(s, "login", "AUTH LOGIN", NULL, NULL) != 334) goto done;
            if (!notify_base64(m->user, ul, secret, sizeof secret) || command(s, "login", secret, NULL, NULL) != 334) goto done;
            if (!notify_base64(m->pass, pl, secret, sizeof secret) || command(s, "login", secret, NULL, NULL) != 235) goto done;
        } else {fail(why, cap, "the server offers no supported login (PLAIN or LOGIN)"); goto done;}
        memset(secret, 0, sizeof secret);
    }
    if (command(s, "sender", "MAIL FROM:<", m->from, ">") != 250) goto done;
    int code = command(s, "recipient", "RCPT TO:<", m->to, ">");
    if (code != 250 && code != 251) goto done;
    if (command(s, "DATA", "DATA", NULL, NULL) != 354) goto done;
    char subject[200], head[640];
    if (!notify_base64(m->subject, strlen(m->subject) > 140 ? 140 : strlen(m->subject), subject, sizeof subject)) {fail(why, cap, "subject too long"); goto done;}
    int n = snprintf(head, sizeof head, "From: <%s>\r\nTo: <%s>\r\nSubject: =?UTF-8?B?%s?=\r\n%s%s%sMIME-Version: 1.0\r\n"
                     "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n",
                     m->from, m->to, subject, m->date ? "Date: " : "", m->date ? m->date : "", m->date ? "\r\n" : "");
    if (n <= 0 || (size_t)n >= sizeof head || !send_all(s, head, (size_t)n)) goto done;
    /* Base64 body in 76-character lines: no line ever starts with a dot. */
    const char *body = m->body;
    size_t left = strlen(body);
    while (left) {
        size_t chunk = left > 57 ? 57 : left;
        char line[80];
        size_t k = notify_base64(body, chunk, line, sizeof line - 2);
        line[k++] = '\r'; line[k++] = '\n';
        if (!send_all(s, line, k)) goto done;
        body += chunk; left -= chunk;
    }
    if (!send_all(s, ".\r\n", 3) || reply(s, "message") != 250) goto done;
    (void)command(s, "QUIT", "QUIT", NULL, NULL);
    result = ESP_OK;
done:
    memset(secret, 0, sizeof secret);
    memset(s, 0, sizeof *s);
    free(s);
    return result;
}
/* --- notify core (end) --- */

#ifdef ESP_PLATFORM
#include "json_guard.h"
#include "esp_rom_crc.h"
#include "lan_name.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "task_reaper.h"
#include "esp_attr.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/entropy.h"
#include "mbedtls/net_sockets.h"
#include "mbedtls/ssl.h"
#include "nvs.h"
#include "nvs_params.h"
#include <stdlib.h>
#include <time.h>

static const char *TAG = "notify";
#define CFG_MAGIC 0x4e544631u      /* NTF1 */
#define QUEUE_MAX 8
#define MAX_ATTEMPTS 10
#define RETRY_S 30
#define CH_TG 1
#define CH_MAIL 2

/* Producers are history_event (at most HIST_TEXT_MAX bytes) and the short
 * explicit test. Preserve a complete history message without overallocating
 * every queue slot for the delivery wrapper's larger formatting buffer. */
typedef struct {uint8_t kind, level, channels, attempts; uint32_t wall, id, episode; uint8_t link; char text[HIST_TEXT_MAX + 1];} note_t;
_Static_assert(HIST_TEXT_MAX + 1 <= NOTIFY_TEXT_MAX, "Delivery must fit a complete history event");
typedef struct {uint32_t sent, failed; bool last_ok; char last_error[192];} channel_status_t;   /* PSRAM */

static SemaphoreHandle_t s_lock;
static StaticSemaphore_t s_lock_storage;
/* Pack new preferences into the two bytes of alignment slack following the
 * old 590-byte external-RAM config. No extra internal-RAM settings globals.
 * This runtime wrapper is never serialized; the legacy NVS layout is intact. */
typedef struct {
    notify_config_t config;
    uint16_t grace_s : 12;
    uint16_t startup_channels : 4;
} notify_runtime_config_t;
_Static_assert(sizeof(notify_config_t) == 590 && sizeof(notify_runtime_config_t) == 592,
               "Keep notification preferences inside the existing aligned config footprint");
EXT_RAM_BSS_ATTR static notify_runtime_config_t s_runtime_cfg;
#define s_cfg (s_runtime_cfg.config)
#define s_link_grace_s (s_runtime_cfg.grace_s)
#define s_startup_channels (s_runtime_cfg.startup_channels)
static note_t *s_queue;            /* PSRAM, QUEUE_MAX; exists only while a channel is on */
/* The queue has eight slots; narrow bounded indices without losing counters. */
static uint8_t s_head, s_count;
EXT_RAM_BSS_ATTR static unsigned s_dropped;
static bool s_worker;
EXT_RAM_BSS_ATTR static channel_status_t s_tg, s_mail;
static uint8_t s_tokens = 6;
EXT_RAM_BSS_ATTR static uint32_t s_refill;
/* Zero means an ordinary event. Links have independent bounded episodes. */
enum {LINK_NONE, LINK_WIFI, LINK_TAILNET, LINK_END};
#define LINK_GRACE_DEFAULT_S 60u
typedef struct {uint32_t since, episode; uint8_t delivered; bool down, announced, suppress_up;} link_state_t;
EXT_RAM_BSS_ATTR static link_state_t s_links[LINK_END];
EXT_RAM_BSS_ATTR static uint32_t s_note_id, s_worker_retry;
static uint16_t s_worker_backoff = 30; /* capped at 300 seconds */
extern volatile int ap_connect;

/* --- notify store (begin) --- */
/* One NVS record holds everything, so a save is all or nothing. The email
 * event choice (3.0.1) lives in the two bytes that were padding before the
 * checksum: size and version stay those of 3.0.0, and a 3.0.0/3.0.1 image
 * that comes back after a rollback still accepts the record. 0 there means
 * "written by 3.0.0/3.0.1": the separate key ntf_mlv of 3.0.1 is used if
 * present, else the shared choice of 3.0.0. ntf_mlv is still written after
 * the record, only for such a rollback; it never decides anything here.
 * The remaining padding byte stores explicit startup choices (bit 7 marks
 * presence, bits 0/1 select other starts and bits 2/3 power-on for Telegram/email). Legacy zero preserves the old
 * All-events behavior. The record size, schema and checksum range stay fixed. */
typedef struct {
    uint32_t magic, version;
    notify_config_t config;
    uint8_t mail_level_plus1;      /* 0: not stored in the record */
    uint8_t startup_flags;
    uint32_t checksum;
} cfg_record_t;

static uint32_t record_checksum(const cfg_record_t *r) {return esp_rom_crc32_le(0, (const uint8_t *)r, offsetof(cfg_record_t, checksum));}

/* Defaults (everything off) when the record is missing or damaged. */
static void store_load(notify_config_t *c, uint8_t *mail_level, uint8_t *startup_channels)
{
    memset(c, 0, sizeof *c);
    c->mail_port = 465;
    *mail_level = NOTIFY_PROBLEMS;
    *startup_channels = 0;
    nvs_handle_t h;
    if (nvs_open("tsr", NVS_READONLY, &h) != ESP_OK) return;
    cfg_record_t *r = calloc(1, sizeof *r);
    size_t n = sizeof *r;
    /* Fail closed: a damaged record means off, never half-applied. */
    if (r && nvs_get_blob(h, "notify_cfg", r, &n) == ESP_OK && n == sizeof *r && r->magic == CFG_MAGIC && r->version == 1 &&
        r->checksum == record_checksum(r) && notify_config_valid(&r->config, NULL, 0) && r->mail_level_plus1 <= NOTIFY_ALL + 1 &&
        (r->startup_flags == 0 || (r->startup_flags & (uint8_t)~0x0f) == 0x80)) {
        *c = r->config;
        uint8_t legacy = 0;
        *mail_level = r->mail_level_plus1 ? (uint8_t)(r->mail_level_plus1 - 1)
                    : nvs_get_u8(h, "ntf_mlv", &legacy) == ESP_OK && legacy <= NOTIFY_ALL ? legacy : c->level;
        *startup_channels = r->startup_flags ? r->startup_flags & 0x0f
                          : (c->level == NOTIFY_ALL ? CH_TG | (CH_TG << 2) : 0) | (*mail_level == NOTIFY_ALL ? CH_MAIL | (CH_MAIL << 2) : 0);
    }
    if (r) {memset(r, 0, sizeof *r); free(r);}
    nvs_close(h);
}

static esp_err_t store_save(const notify_config_t *c, uint8_t mail_level, uint8_t startup_channels)
{
    if (mail_level > NOTIFY_ALL || (startup_channels & (uint8_t)~0x0f)) return ESP_ERR_INVALID_ARG;
    cfg_record_t *r = calloc(1, sizeof *r);
    if (!r) return ESP_ERR_NO_MEM;
    r->magic = CFG_MAGIC; r->version = 1; r->config = *c; r->mail_level_plus1 = (uint8_t)(mail_level + 1);
    r->startup_flags = (uint8_t)(0x80 | startup_channels);
    r->checksum = record_checksum(r);
    nvs_handle_t h;
    esp_err_t err = nvs_open("tsr", NVS_READWRITE, &h);
    if (!err) {
        err = nvs_set_blob(h, "notify_cfg", r, sizeof *r);
        if (!err) err = nvs_commit(h);
        /* For a rollback to 3.0.1 only; failing here changes nothing. */
        if (!err && nvs_set_u8(h, "ntf_mlv", mail_level) == ESP_OK) nvs_commit(h);
        nvs_close(h);
    }
    memset(r, 0, sizeof *r);
    free(r);
    return err;
}
/* --- notify store (end) --- */

static void when_text(uint32_t wall, char *out, size_t cap)
{
    out[0] = 0;
    if (!wall) return;
    time_t t = wall;
    struct tm tm;
    localtime_r(&t, &tm);
    strftime(out, cap, "%d/%m %H:%M", &tm);
}

/* --- Telegram --- */
static esp_err_t telegram(const notify_config_t *c, const char *text, char *why, size_t cap)
{
    char url[160], *body = heap_caps_malloc(NOTIFY_TEXT_MAX * 6 + 160, MALLOC_CAP_SPIRAM);
    if (!body) return ESP_ERR_NO_MEM;
    snprintf(url, sizeof url, "https://api.telegram.org/bot%s/sendMessage", c->tg_token);
    size_t n = notify_telegram_body(body, NOTIFY_TEXT_MAX * 6 + 160, c->tg_chat, text);
    esp_http_client_config_t hc = {.url = url, .method = HTTP_METHOD_POST, .timeout_ms = 15000,
                                   .crt_bundle_attach = esp_crt_bundle_attach, .disable_auto_redirect = true};
    esp_http_client_handle_t client = n ? esp_http_client_init(&hc) : NULL;
    memset(url, 0, sizeof url);                           /* holds the token */
    esp_err_t err = ESP_FAIL;
    if (client) {
        esp_http_client_set_header(client, "Content-Type", "application/json");
        err = esp_http_client_open(client, (int)n);
        if (!err && esp_http_client_write(client, body, (int)n) != (int)n) err = ESP_FAIL;
        if (!err && esp_http_client_fetch_headers(client) < 0) err = ESP_FAIL;
        if (!err) {
            int status = esp_http_client_get_status_code(client);
            char answer[256];
            int got = esp_http_client_read(client, answer, sizeof answer - 1);
            answer[got > 0 ? got : 0] = 0;
            if (status != 200 || !strstr(answer, "\"ok\":true")) {
                const char *d = strstr(answer, "\"description\":\"");
                char text_why[80] = "";
                if (d) {d += 15; size_t k = 0; while (d[k] && d[k] != '"' && k < sizeof text_why - 1) {text_why[k] = d[k]; k++;} text_why[k] = 0;}
                snprintf(why, cap, "Telegram answered %d%s%s", status, text_why[0] ? ": " : "", text_why);
                err = ESP_FAIL;
            }
        } else snprintf(why, cap, "cannot reach api.telegram.org (%s)", esp_err_to_name(err));
        esp_http_client_cleanup(client);
    } else snprintf(why, cap, "message could not be prepared");
    free(body);
    return err;
}

/* --- SMTP over mbedTLS --- */
typedef struct {
    mbedtls_net_context net;
    bool tls;
    const char *host;
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    mbedtls_ctr_drbg_context drbg;
    mbedtls_entropy_context entropy;
} mail_io_t;

static int io_send(void *ctx, const char *data, size_t len)
{
    mail_io_t *m = ctx;
    if (!m->tls) return send(m->net.fd, data, len, 0);
    int n;
    do n = mbedtls_ssl_write(&m->ssl, (const unsigned char *)data, len);
    while (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE);
    return n;
}

static int io_recv(void *ctx, char *out, size_t cap)
{
    mail_io_t *m = ctx;
    if (!m->tls) return recv(m->net.fd, out, cap, 0);
    int n;
    do n = mbedtls_ssl_read(&m->ssl, (unsigned char *)out, cap);
    while (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE);
    return n;
}

static int io_starttls(void *ctx)
{
    mail_io_t *m = ctx;
    if (mbedtls_ctr_drbg_seed(&m->drbg, mbedtls_entropy_func, &m->entropy, NULL, 0) ||
        mbedtls_ssl_config_defaults(&m->conf, MBEDTLS_SSL_IS_CLIENT, MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT))
        return -1;
    mbedtls_ssl_conf_authmode(&m->conf, MBEDTLS_SSL_VERIFY_REQUIRED);   /* never unverified */
    mbedtls_ssl_conf_rng(&m->conf, mbedtls_ctr_drbg_random, &m->drbg);
    if (esp_crt_bundle_attach(&m->conf) != ESP_OK || mbedtls_ssl_setup(&m->ssl, &m->conf) ||
        mbedtls_ssl_set_hostname(&m->ssl, m->host)) return -1;
    mbedtls_ssl_set_bio(&m->ssl, &m->net, mbedtls_net_send, mbedtls_net_recv, NULL);
    int r;
    while ((r = mbedtls_ssl_handshake(&m->ssl)) == MBEDTLS_ERR_SSL_WANT_READ || r == MBEDTLS_ERR_SSL_WANT_WRITE) {}
    if (r || mbedtls_ssl_get_verify_result(&m->ssl)) return -1;
    m->tls = true;
    return 0;
}

static esp_err_t email(const notify_config_t *c, const char *text, char *why, size_t cap)
{
    mail_io_t *m = heap_caps_calloc(1, sizeof *m, MALLOC_CAP_SPIRAM);
    if (!m) return ESP_ERR_NO_MEM;
    mbedtls_net_init(&m->net); mbedtls_ssl_init(&m->ssl); mbedtls_ssl_config_init(&m->conf);
    mbedtls_ctr_drbg_init(&m->drbg); mbedtls_entropy_init(&m->entropy);
    m->host = c->mail_host;
    char port[8];
    snprintf(port, sizeof port, "%u", (unsigned)c->mail_port);
    esp_err_t err = ESP_FAIL;
    if (mbedtls_net_connect(&m->net, c->mail_host, port, MBEDTLS_NET_PROTO_TCP)) {
        snprintf(why, cap, "cannot connect to %s:%s", c->mail_host, port);
    } else {
        struct timeval to = {.tv_sec = 15};
        setsockopt(m->net.fd, SOL_SOCKET, SO_RCVTIMEO, &to, sizeof to);
        setsockopt(m->net.fd, SOL_SOCKET, SO_SNDTIMEO, &to, sizeof to);
        if (c->mail_security == NOTIFY_TLS && io_starttls(m) != 0) {
            snprintf(why, cap, "TLS failed on port %s (certificate, or the port expects STARTTLS)", port);
        } else {
            char host[40], date[40] = "", subject[128], *body = heap_caps_malloc(NOTIFY_TEXT_MAX + 160, MALLOC_CAP_SPIRAM);
            lan_name_get(host, sizeof host);
            if (!host[0]) snprintf(host, sizeof host, "esp32-gateway");
            time_t now = time(NULL);
            if (now > 1700000000) {struct tm tm; gmtime_r(&now, &tm); strftime(date, sizeof date, "%a, %d %b %Y %H:%M:%S +0000", &tm);}
            snprintf(subject, sizeof subject, "%s: %.70s", host, text);
            if (body) {
                snprintf(body, NOTIFY_TEXT_MAX + 160, "%s\n\nSent by the ESP32 Tailnet Gateway \"%s\".\n", text, host);
                notify_smtp_io_t io = {m, io_send, io_recv, io_starttls};
                notify_mail_t mail = {.helo = host, .user = c->mail_user, .pass = c->mail_pass, .from = c->mail_from,
                                      .to = c->mail_to, .subject = subject, .body = body, .date = date[0] ? date : NULL,
                                      .starttls = c->mail_security == NOTIFY_STARTTLS};
                err = notify_smtp_send(&io, &mail, why, cap);
                free(body);
            }
        }
    }
    mbedtls_ssl_free(&m->ssl); mbedtls_ssl_config_free(&m->conf); mbedtls_ctr_drbg_free(&m->drbg);
    mbedtls_entropy_free(&m->entropy); mbedtls_net_free(&m->net);
    free(m);
    return err;
}

/* --- delivery worker: exists only while messages wait --- */
static void record(channel_status_t *st, esp_err_t err, const char *why)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    st->last_ok = err == ESP_OK;
    if (err == ESP_OK) {st->sent++; st->last_error[0] = 0;}
    else {st->failed++; snprintf(st->last_error, sizeof st->last_error, "%s", why[0] ? why : esp_err_to_name(err));}
    xSemaphoreGive(s_lock);
}

static void worker(void *arg)
{
    (void)arg;
    for (;;) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (!s_count || !s_queue) {s_worker = false; xSemaphoreGive(s_lock); task_reaper_self_delete();}
        note_t note = s_queue[s_head];
        notify_config_t c = s_cfg;
        xSemaphoreGive(s_lock);
        char text[NOTIFY_TEXT_MAX + 32], when[16], why[192];   /* PSRAM stack */
        when_text(note.wall, when, sizeof when);
        static const char *const mark[] = {"", "\xE2\x9A\xA0\xEF\xB8\x8F ", "\xE2\x9D\x97 "};   /* warning, error */
        snprintf(text, sizeof text, "%s%s%s%s", note.level < 3 ? mark[note.level] : "", when, when[0] ? " " : "", note.text);
        uint8_t done = 0, delivered = 0;
        if ((note.channels & CH_TG) && c.tg_enabled) {
            why[0] = 0; esp_err_t err = telegram(&c, text, why, sizeof why); record(&s_tg, err, why);
            if (err) ESP_LOGW(TAG, "Telegram delivery failed: event=%u id=%lu attempt=%u/%u error=%s internal=%u largest=%u psram=%u",
                note.kind, (unsigned long)note.id, (unsigned)note.attempts + 1, MAX_ATTEMPTS, esp_err_to_name(err),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
            if (!err) {done |= CH_TG; delivered |= CH_TG;}
        } else done |= CH_TG;
        if ((note.channels & CH_MAIL) && c.mail_enabled) {
            why[0] = 0; esp_err_t err = email(&c, text, why, sizeof why); record(&s_mail, err, why);
            if (err) ESP_LOGW(TAG, "Email delivery failed: event=%u id=%lu attempt=%u/%u error=%s internal=%u largest=%u psram=%u",
                note.kind, (unsigned long)note.id, (unsigned)note.attempts + 1, MAX_ATTEMPTS, esp_err_to_name(err),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
            if (!err) {done |= CH_MAIL; delivered |= CH_MAIL;}
        } else done |= CH_MAIL;
        memset(&c, 0, sizeof c);                          /* secrets off the stack */
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (note.link > LINK_NONE && note.link < LINK_END && s_links[note.link].episode == note.episode)
            s_links[note.link].delivered |= delivered;
        /* A producer may have evicted the in-flight head while HTTPS/SMTP
         * ran without the lock. Never complete or retry a different message. */
        bool same = s_count && s_queue[s_head].id == note.id;
        bool pop = !same;
        if (same) {
            pop = (done & note.channels) == note.channels || ++s_queue[s_head].attempts >= MAX_ATTEMPTS;
            if (!pop) s_queue[s_head].channels &= (uint8_t)~done;
            if (pop) {s_head = (s_head + 1) % QUEUE_MAX; s_count--;}
        }
        xSemaphoreGive(s_lock);
        if (!pop) vTaskDelay(pdMS_TO_TICKS(RETRY_S * 1000));   /* uplink down or server busy */
    }
}

/* Caller holds s_lock. Retry a failed task allocation without requiring a
 * new event, using the already running history poll and bounded backoff. */
static void start_worker_locked(uint32_t now)
{
    if (s_worker || !s_count || (int32_t)(now - s_worker_retry) < 0) return;
    s_worker = xTaskCreateWithCaps(worker, "notify", 12288, NULL, 2, NULL, MALLOC_CAP_SPIRAM) == pdPASS;
    if (s_worker) {s_worker_retry = 0; s_worker_backoff = 30;}
    else {
        s_worker_retry = now + s_worker_backoff;
        s_worker_backoff = s_worker_backoff < 150 ? s_worker_backoff * 2 : 300;
        ESP_LOGW(TAG, "no memory for the delivery worker; retry in %lu seconds", (unsigned long)(s_worker_retry - now));
    }
}

/* Caller holds s_lock. */
static void enqueue_locked(uint8_t kind, uint8_t level, uint8_t channels, uint32_t wall, const char *text)
{
    if (!s_queue || !channels) return;
    if (s_count == QUEUE_MAX) {s_head = (s_head + 1) % QUEUE_MAX; s_count--; s_dropped++;}   /* oldest goes */
    note_t *n = &s_queue[(s_head + s_count) % QUEUE_MAX];
    memset(n, 0, sizeof *n);
    n->kind = kind; n->level = level; n->channels = channels; n->wall = wall;
    if (++s_note_id == 0) ++s_note_id;
    n->id = s_note_id;
    snprintf(n->text, sizeof n->text, "%.*s", (int)sizeof n->text - 1, text);
    s_count++;
    start_worker_locked((uint32_t)(esp_timer_get_time() / 1000000));
}

/* Email has its own event selection since 3.0.1 (stored in the record; see
 * the notify store). */
static uint8_t s_mail_level = NOTIFY_PROBLEMS;

static uint8_t channels_locked(void) {return (s_cfg.tg_enabled ? CH_TG : 0) | (s_cfg.mail_enabled ? CH_MAIL : 0);}

static uint8_t wanted_channels_locked(unsigned kind, unsigned level, const char *text)
{
    /* Normal starts are independently selectable. Crash/WDT/brownout starts
     * remain errors, so opting out here cannot silence the crash path. */
    if (kind == HIST_EV_BOOT && level == HIST_INFO) {
        bool poweron = text && !strncmp(text, "Power-on start ", 15);
        return channels_locked() & (poweron ? s_startup_channels >> 2 : s_startup_channels);
    }
    return (s_cfg.tg_enabled && notify_wanted(s_cfg.level, kind, level) ? CH_TG : 0) |
           (s_cfg.mail_enabled && notify_wanted(s_mail_level, kind, level) ? CH_MAIL : 0);
}

/* Caller holds s_lock. Only delivery is coalesced; local history's own
 * configuration and bounded event recording remain unchanged. */
static note_t *limited_locked(uint8_t kind, uint8_t level, uint8_t channels, uint32_t wall,
                              const char *text, bool count_drop)
{
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000000);
    if (now - s_refill >= 120) {
        uint32_t add = (now - s_refill) / 120;
        s_tokens = s_tokens + add > 6 ? 6 : s_tokens + add;
        s_refill += add * 120;
    }
    if (!channels || !s_queue) return NULL;
    if (!s_tokens) {if (count_drop) s_dropped++; return NULL;}
    s_tokens--;
    enqueue_locked(kind, level, channels, wall, text);
    return &s_queue[(s_head + s_count - 1) % QUEUE_MAX];
}

static uint32_t notify_wall(void) {time_t t = time(NULL); return t > 1700000000 ? (uint32_t)t : 0;}
static unsigned link_kind(unsigned link) {return link == LINK_WIFI ? HIST_EV_UPLINK : HIST_EV_TAILNET;}
static const char *link_name(unsigned link) {return link == LINK_WIFI ? "Wi-Fi uplink" : "Tailnet connection";}

static void link_recovered_locked(unsigned link, uint32_t now)
{
    link_state_t *s = &s_links[link];
    if (!s->down) return;
    uint32_t duration = now - s->since;
    if (s->announced || duration >= s_link_grace_s) {
        char text[NOTIFY_TEXT_MAX];
        snprintf(text, sizeof text, "%s recovered after %lu seconds.", link_name(link), (unsigned long)duration);
        uint8_t queued = 0;
        for (unsigned i = 0; i < s_count; ++i) {
            note_t *n = &s_queue[(s_head + i) % QUEUE_MAX];
            if (n->link == link && n->episode == s->episode) {
                snprintf(n->text, sizeof n->text, "%.*s", (int)sizeof n->text - 1, text);
                n->wall = notify_wall(); n->attempts = 0;
                if (++s_note_id == 0) ++s_note_id;
                n->id = s_note_id;   /* an in-flight old warning cannot discard the new summary */
                queued |= n->channels;
            }
        }
        /* If retries expired while the uplink was absent, send a useful
         * recovery summary instead of replaying a stale "still down" alert. */
        uint8_t missing = wanted_channels_locked(link_kind(link), HIST_WARN, NULL) & (uint8_t)~(s->delivered | queued);
        note_t *n = limited_locked((uint8_t)link_kind(link), HIST_WARN, missing, notify_wall(), text, false);
        if (n) {n->link = (uint8_t)link; n->episode = s->episode;}
    }
    s->down = false; s->suppress_up = true;
}

/* Match only structured messages produced by main.c/history.c. Other uplink
 * events (DDNS failures, throughput results) must never cancel an outage. */
static bool connectivity_offer_locked(unsigned kind, unsigned level, const char *text, uint32_t now)
{
    unsigned link = LINK_NONE; bool up = false;
    if (kind == HIST_EV_UPLINK && level == HIST_WARN && !strncmp(text, "Wi-Fi uplink lost (", sizeof("Wi-Fi uplink lost (") - 1)) link = LINK_WIFI;
    else if (kind == HIST_EV_UPLINK && level == HIST_INFO && !strncmp(text, "Wi-Fi uplink connected, ", sizeof("Wi-Fi uplink connected, ") - 1)) {link = LINK_WIFI; up = true;}
    else if (kind == HIST_EV_TAILNET && level == HIST_WARN && !strcmp(text, "Tailnet connection lost")) link = LINK_TAILNET;
    else if (kind == HIST_EV_TAILNET && level == HIST_INFO && !strcmp(text, "Tailnet connected")) {link = LINK_TAILNET; up = true;}
    if (!link) return false;
    link_state_t *s = &s_links[link];
    if (up) {
        bool had_outage = s->down || s->suppress_up;
        link_recovered_locked(link, now); s->suppress_up = false;
        return had_outage;   /* initial connected info still follows All events */
    }
    if (!s->down) {
        s->down = true; s->announced = false; s->suppress_up = false;
        s->since = now; s->delivered = 0;
        if (++s->episode == 0) ++s->episode;
    }
    return true;
}

static void notify_poll(void)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000000);
    for (unsigned link = LINK_WIFI; link < LINK_END; ++link) {
        link_state_t *s = &s_links[link];
        if (!s->down) continue;
        /* A dropped history line cannot leave a stale down alert pending. */
        if ((link == LINK_WIFI && ap_connect) || (link == LINK_TAILNET && tailscale_is_connected())) {
            link_recovered_locked(link, now); continue;
        }
        if (!s->announced && now - s->since >= s_link_grace_s) {
            char text[NOTIFY_TEXT_MAX];
            snprintf(text, sizeof text, "%s unavailable for at least %u seconds.", link_name(link), (unsigned)s_link_grace_s);
            note_t *n = limited_locked((uint8_t)link_kind(link), HIST_WARN,
                wanted_channels_locked(link_kind(link), HIST_WARN, NULL), notify_wall(), text, false);
            if (n) {n->link = (uint8_t)link; n->episode = s->episode; s->announced = true;}
        }
    }
    start_worker_locked(now);
    xSemaphoreGive(s_lock);
}

/* History sink: runs on the history task. */
static void offer(unsigned kind, unsigned level, uint32_t wall, const char *text)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000000);
    if (!connectivity_offer_locked(kind, level, text, now))
        (void)limited_locked((uint8_t)kind, (uint8_t)level, wanted_channels_locked(kind, level, text), wall, text, true);
    xSemaphoreGive(s_lock);
}

static void apply_locked(void)
{
    bool on = s_cfg.tg_enabled || s_cfg.mail_enabled;
    if (on && !s_queue) s_queue = heap_caps_calloc(QUEUE_MAX, sizeof *s_queue, MALLOC_CAP_SPIRAM);
    if (!on && s_queue && !s_worker) {memset(s_queue, 0, QUEUE_MAX * sizeof *s_queue); free(s_queue); s_queue = NULL; s_head = s_count = 0;}
    if (!on) memset(s_links, 0, sizeof s_links);
    history_set_sink_poller(on && s_queue ? offer : NULL, on && s_queue ? notify_poll : NULL);
}

void notify_channels_enabled(bool *telegram, bool *email)
{
    *telegram = s_cfg.tg_enabled;
    *email = s_cfg.mail_enabled;
}

void notify_channels_init(void)
{
    if (!s_lock) s_lock = xSemaphoreCreateMutexStatic(&s_lock_storage);
    uint8_t startup = 0;
    store_load(&s_cfg, &s_mail_level, &startup);
    s_startup_channels = startup;
    s_link_grace_s = LINK_GRACE_DEFAULT_S;
    uint16_t grace = 0;
    if (nvs_param_get_u16("ntf_grace", &grace) == ESP_OK && grace >= 15 && grace <= 3600) s_link_grace_s = grace;
    if (s_cfg.tg_enabled || s_cfg.mail_enabled) {xSemaphoreTake(s_lock, portMAX_DELAY); apply_locked(); xSemaphoreGive(s_lock);}
}

/* --- HTTP --- */
static void add_string(cJSON *o, const char *k, const char *v) {cJSON_AddStringToObject(o, k, v);}

static esp_err_t get_notify(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    cJSON *root = cJSON_CreateObject(), *tg = cJSON_AddObjectToObject(root, "telegram"), *mail = cJSON_AddObjectToObject(root, "email");
    xSemaphoreTake(s_lock, portMAX_DELAY);
    notify_config_t c = s_cfg;
    uint8_t mail_level = s_mail_level;
    uint8_t startup_channels = s_startup_channels;
    uint16_t grace = s_link_grace_s;
    channel_status_t a = s_tg, b = s_mail;
    unsigned waiting = s_count, dropped = s_dropped, pending = 0;
    for (unsigned i = LINK_WIFI; i < LINK_END; ++i) if (s_links[i].down && !s_links[i].announced) pending++;
    bool worker_running = s_worker;
    xSemaphoreGive(s_lock);
    cJSON_AddStringToObject(root, "events", c.level == NOTIFY_ALL ? "all" : "problems");
    cJSON_AddNumberToObject(root, "waiting", waiting);
    cJSON_AddNumberToObject(root, "dropped", dropped);
    cJSON_AddNumberToObject(root, "connectivity_grace_seconds", grace);
    cJSON_AddNumberToObject(root, "pending_connectivity", pending);
    cJSON_AddBoolToObject(root, "worker_running", worker_running);
    cJSON_AddBoolToObject(tg, "enabled", c.tg_enabled);
    cJSON_AddBoolToObject(tg, "notify_startup", (startup_channels & CH_TG) != 0);
    cJSON_AddBoolToObject(tg, "notify_poweron", (startup_channels & (CH_TG << 2)) != 0);
    cJSON_AddStringToObject(tg, "events", c.level == NOTIFY_ALL ? "all" : "problems");
    cJSON_AddBoolToObject(tg, "has_token", c.tg_token[0] != 0);
    add_string(tg, "chat", c.tg_chat);
    cJSON_AddNumberToObject(tg, "sent", a.sent); cJSON_AddNumberToObject(tg, "failed", a.failed);
    add_string(tg, "last_error", a.last_error);
    cJSON_AddBoolToObject(mail, "enabled", c.mail_enabled);
    cJSON_AddBoolToObject(mail, "notify_startup", (startup_channels & CH_MAIL) != 0);
    cJSON_AddBoolToObject(mail, "notify_poweron", (startup_channels & (CH_MAIL << 2)) != 0);
    cJSON_AddStringToObject(mail, "events", mail_level == NOTIFY_ALL ? "all" : "problems");
    add_string(mail, "host", c.mail_host);
    cJSON_AddNumberToObject(mail, "port", c.mail_port);
    add_string(mail, "security", c.mail_security == NOTIFY_STARTTLS ? "starttls" : "tls");
    add_string(mail, "user", c.mail_user);
    cJSON_AddBoolToObject(mail, "has_password", c.mail_pass[0] != 0);
    add_string(mail, "from", c.mail_from); add_string(mail, "to", c.mail_to);
    cJSON_AddNumberToObject(mail, "sent", b.sent); cJSON_AddNumberToObject(mail, "failed", b.failed);
    add_string(mail, "last_error", b.last_error);
    memset(&c, 0, sizeof c);
    char *text = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!text) {httpd_resp_send_500(req); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, text);
    cJSON_free(text);
    return err;
}

static bool copy_string(const cJSON *o, const char *k, char *out, size_t cap)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    if (!v) return true;                                  /* absent: unchanged */
    if (!cJSON_IsString(v) || strlen(v->valuestring) >= cap) return false;
    strcpy(out, v->valuestring);
    return true;
}

static int receive(httpd_req_t *req, char *body, size_t cap)
{
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)cap) return -1;
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) return -1;
        received += n;
    }
    body[received] = 0;
    return received;
}

static esp_err_t post_timing(httpd_req_t *req, const cJSON *root);

static esp_err_t post_notify(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char *body = heap_caps_malloc(1536, MALLOC_CAP_SPIRAM);
    notify_config_t *next = heap_caps_malloc(sizeof *next, MALLOC_CAP_SPIRAM);
    if (!body || !next) {free(body); free(next); httpd_resp_send_500(req); return ESP_FAIL;}
    char why[120] = "invalid request";
    bool ok = receive(req, body, 1536) > 0;
    cJSON *root = ok ? json_guard_parse(body) : NULL;
    memset(body, 0, 1536);
    /* Timing-only operation shares the existing authenticated route: no
     * additional HTTP handler allocation. Mixed saves are rejected below. */
    if (cJSON_IsObject(root) && cJSON_GetArraySize(root) == 1 &&
        cJSON_HasObjectItem(root, "connectivity_grace_seconds")) {
        esp_err_t result = post_timing(req, root);
        cJSON_Delete(root); memset(next, 0, sizeof *next); free(next); free(body);
        return result;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *next = s_cfg;
    uint8_t mail_level = s_mail_level;
    uint8_t startup_channels = s_startup_channels;
    xSemaphoreGive(s_lock);
    const cJSON *tg = cJSON_GetObjectItemCaseSensitive(root, "telegram"), *mail = cJSON_GetObjectItemCaseSensitive(root, "email");
    const cJSON *events = cJSON_GetObjectItemCaseSensitive(root, "events");
    ok = cJSON_IsObject(root) && !cJSON_HasObjectItem(root, "connectivity_grace_seconds") &&
         (!tg || cJSON_IsObject(tg)) && (!mail || cJSON_IsObject(mail)) &&
         (!events || (cJSON_IsString(events) && (!strcmp(events->valuestring, "all") || !strcmp(events->valuestring, "problems"))));
    /* "events" at the top sets both channels (3.0.0 clients); per channel wins. */
    if (ok && events) next->level = mail_level = !strcmp(events->valuestring, "all") ? NOTIFY_ALL : NOTIFY_PROBLEMS;
    for (int i = 0; ok && i < 2; i++) {
        const cJSON *startup = cJSON_GetObjectItemCaseSensitive(i ? mail : tg, "notify_startup");
        if (startup && !cJSON_IsBool(startup)) {ok = false; break;}
        uint8_t channel = i ? CH_MAIL : CH_TG;
        if (startup) {
            if (cJSON_IsTrue(startup)) startup_channels |= channel;
            else startup_channels &= (uint8_t)~channel;
        }
        const cJSON *power = cJSON_GetObjectItemCaseSensitive(i ? mail : tg, "notify_poweron");
        if (power && !cJSON_IsBool(power)) {ok = false; break;}
        if (power) {
            if (cJSON_IsTrue(power)) startup_channels |= (uint8_t)(channel << 2);
            else startup_channels &= (uint8_t)~(channel << 2);
        }
        const cJSON *e = cJSON_GetObjectItemCaseSensitive(i ? mail : tg, "events");
        if (!e) continue;
        if (!cJSON_IsString(e) || (strcmp(e->valuestring, "all") && strcmp(e->valuestring, "problems"))) {ok = false; break;}
        uint8_t lv = !strcmp(e->valuestring, "all") ? NOTIFY_ALL : NOTIFY_PROBLEMS;
        if (i) mail_level = lv; else next->level = lv;
    }
    if (ok && tg) {
        const cJSON *en = cJSON_GetObjectItemCaseSensitive(tg, "enabled"), *token = cJSON_GetObjectItemCaseSensitive(tg, "token");
        ok = (!en || cJSON_IsBool(en)) && copy_string(tg, "chat", next->tg_chat, sizeof next->tg_chat);
        if (ok && en) next->tg_enabled = cJSON_IsTrue(en);
        /* Write-only secret: empty keeps the stored token. */
        if (ok && cJSON_IsString(token) && token->valuestring[0]) ok = copy_string(tg, "token", next->tg_token, sizeof next->tg_token);
        else if (ok && token && !cJSON_IsString(token)) ok = false;
        if (ok && cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(tg, "clear_token"))) {memset(next->tg_token, 0, sizeof next->tg_token); next->tg_enabled = false;}
    }
    if (ok && mail) {
        const cJSON *en = cJSON_GetObjectItemCaseSensitive(mail, "enabled"), *port = cJSON_GetObjectItemCaseSensitive(mail, "port");
        const cJSON *sec = cJSON_GetObjectItemCaseSensitive(mail, "security"), *pass = cJSON_GetObjectItemCaseSensitive(mail, "password");
        ok = (!en || cJSON_IsBool(en)) && (!port || (cJSON_IsNumber(port) && port->valuedouble >= 1 && port->valuedouble <= 65535 && port->valuedouble == (int)port->valuedouble)) &&
             (!sec || (cJSON_IsString(sec) && (!strcmp(sec->valuestring, "tls") || !strcmp(sec->valuestring, "starttls")))) &&
             copy_string(mail, "host", next->mail_host, sizeof next->mail_host) && copy_string(mail, "user", next->mail_user, sizeof next->mail_user) &&
             copy_string(mail, "from", next->mail_from, sizeof next->mail_from) && copy_string(mail, "to", next->mail_to, sizeof next->mail_to);
        if (ok && en) next->mail_enabled = cJSON_IsTrue(en);
        if (ok && port) next->mail_port = (uint16_t)port->valuedouble;
        if (ok && sec) next->mail_security = !strcmp(sec->valuestring, "starttls") ? NOTIFY_STARTTLS : NOTIFY_TLS;
        if (ok && cJSON_IsString(pass) && pass->valuestring[0]) ok = copy_string(mail, "password", next->mail_pass, sizeof next->mail_pass);
        else if (ok && pass && !cJSON_IsString(pass)) ok = false;
        if (ok && !next->mail_user[0]) memset(next->mail_pass, 0, sizeof next->mail_pass);   /* no user: no password kept */
    }
    if (root) {
        /* Wipe secrets from the parsed tree before freeing it. */
        cJSON *t = cJSON_GetObjectItemCaseSensitive(tg, "token"), *p = cJSON_GetObjectItemCaseSensitive(mail, "password");
        if (cJSON_IsString(t)) memset(t->valuestring, 0, strlen(t->valuestring));
        if (cJSON_IsString(p)) memset(p->valuestring, 0, strlen(p->valuestring));
        cJSON_Delete(root);
    }
    esp_err_t err = ESP_OK;
    if (ok && !notify_config_valid(next, why, sizeof why)) ok = false;
    if (ok) err = store_save(next, mail_level, startup_channels); /* one record, before publishing */
    if (ok && !err) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        s_cfg = *next;
        s_mail_level = mail_level;
        s_startup_channels = startup_channels;
        apply_locked();
        xSemaphoreGive(s_lock);
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
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

/* Timing is a separate atomic setting, so saving it cannot partially save
 * credentials or another channel's card. Existing clients leave it untouched. */
static esp_err_t post_timing(httpd_req_t *req, const cJSON *root)
{
    /* Called only by the authenticated timing-only dispatch above. */
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(root, "connectivity_grace_seconds");
    bool valid = cJSON_IsObject(root) && cJSON_IsNumber(v) && v->valuedouble >= 15 &&
                 v->valuedouble <= 3600 && v->valuedouble == (int)v->valuedouble;
    uint16_t grace = valid ? (uint16_t)v->valuedouble : 0;
    httpd_resp_set_type(req, "application/json");
    if (!valid) {
        httpd_resp_set_status(req, "400 Bad Request");
        return httpd_resp_sendstr(req, "{\"ok\":false,\"error\":\"Use 15 to 3600 whole seconds\"}");
    }
    esp_err_t err = nvs_param_set_u16("ntf_grace", grace);
    if (err != ESP_OK) {
        httpd_resp_set_status(req, "500 Internal Server Error");
        return httpd_resp_sendstr(req, "{\"ok\":false,\"error\":\"Timing not saved\"}");
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_link_grace_s = grace;
    xSemaphoreGive(s_lock);
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

static esp_err_t post_test(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[64];
    if (receive(req, body, sizeof body) <= 0) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "expected {\"channel\":\"telegram\"|\"email\"}"); return ESP_FAIL;}
    uint8_t channel = strstr(body, "\"telegram\"") ? CH_TG : strstr(body, "\"email\"") ? CH_MAIL : 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool on = channel && (channels_locked() & channel) && s_queue;
    if (on) enqueue_locked(HIST_EV_SERVICE, HIST_INFO, channel, (uint32_t)time(NULL), "Test message: notifications from this gateway work.");
    xSemaphoreGive(s_lock);
    httpd_resp_set_type(req, "application/json");
    if (!on) {httpd_resp_set_status(req, "409 Conflict"); return httpd_resp_sendstr(req, "{\"ok\":false,\"error\":\"save and switch on this channel first\"}");}
    return httpd_resp_sendstr(req, "{\"ok\":true,\"queued\":true}");
}

esp_err_t notify_channels_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/notify", .method = HTTP_GET, .handler = get_notify},
        {.uri = "/api/notify", .method = HTTP_POST, .handler = post_notify},
        {.uri = "/api/notify/test", .method = HTTP_POST, .handler = post_test}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
