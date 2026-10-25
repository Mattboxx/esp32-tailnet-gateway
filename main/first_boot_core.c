/* First-boot setup core; see first_boot_core.h.
 * SPDX-License-Identifier: MIT */
#include "first_boot_core.h"

#include <ctype.h>
#include <string.h>

static const uint8_t BASE_POINT[32] = {9};
static const char KDF_LABEL[] = "mattboxx-tailnet-gateway-setup-v1";

static void wipe(void *p, size_t n)
{
    volatile uint8_t *v = p;
    while (n--) *v++ = 0;
}

static bool equal_ct(const uint8_t *a, const uint8_t *b, size_t n)
{
    uint8_t d = 0;
    for (size_t i = 0; i < n; i++) d |= a[i] ^ b[i];
    return d == 0;
}

bool fb_should_activate(bool setup_done, bool password_set, int wifi_networks, bool has_auth_key)
{
    return !setup_done && !password_set && wifi_networks <= 0 && !has_auth_key;
}

static void new_code(fb_ctx_t *ctx)
{
    for (int i = 0; i < FB_CODE_DIGITS; i++) {
        uint8_t b;
        do ctx->crypto->random(&b, 1); while (b >= 250); /* unbiased 0..9 */
        ctx->code[i] = (char)('0' + b % 10);
    }
    ctx->code[FB_CODE_DIGITS] = '\0';
}

void fb_init(fb_ctx_t *ctx, const fb_crypto_t *crypto)
{
    memset(ctx, 0, sizeof *ctx);
    ctx->crypto = crypto;
    new_code(ctx);
}

void fb_wipe(fb_ctx_t *ctx)
{
    const fb_crypto_t *crypto = ctx->crypto;
    wipe(ctx, sizeof *ctx);
    ctx->crypto = crypto;
}

static void drop_session(fb_ctx_t *ctx)
{
    wipe(&ctx->s, sizeof ctx->s);
}

void fb_tick(fb_ctx_t *ctx, uint64_t now_us)
{
    if (ctx->s.state == FB_PENDING && now_us - ctx->s.created_us >= FB_PENDING_TTL_US) drop_session(ctx);
    else if (ctx->s.state == FB_CLAIMED && now_us - ctx->s.touched_us >= FB_CLAIMED_IDLE_US) drop_session(ctx);
}

fb_result_t fb_begin(fb_ctx_t *ctx, uint32_t client_ip, const uint8_t client_pub_in[32], uint64_t now_us)
{
    fb_tick(ctx, now_us);
    if (ctx->s.state != FB_NONE && ctx->s.client_ip != client_ip)
        return ctx->s.state == FB_CLAIMED ? FB_ERR_CLAIMED : FB_ERR_BUSY;
    /* Same client (for example a reloaded page that lost its key): start a
     * fresh pending pairing. It needs physical presence again. */
    uint8_t client_pub[32], priv[32], shared[32], material[sizeof KDF_LABEL - 1 + 96];
    memcpy(client_pub, client_pub_in, 32);
    client_pub[31] &= 0x7f;                              /* RFC 7748 */
    fb_session_t s = {0};
    ctx->crypto->random(priv, sizeof priv);
    int bad = ctx->crypto->x25519(s.device_pub, priv, BASE_POINT)
            | ctx->crypto->x25519(shared, priv, client_pub);
    wipe(priv, sizeof priv);
    if (bad) {
        wipe(shared, sizeof shared);
        return FB_ERR_BAD_KEY;
    }
    size_t n = 0;
    memcpy(material + n, KDF_LABEL, sizeof KDF_LABEL - 1); n += sizeof KDF_LABEL - 1;
    memcpy(material + n, shared, 32); n += 32;
    memcpy(material + n, s.device_pub, 32); n += 32;
    memcpy(material + n, client_pub, 32); n += 32;
    ctx->crypto->sha256(material, n, s.key);
    wipe(shared, sizeof shared);
    wipe(material, sizeof material);
    ctx->crypto->random(s.sid, sizeof s.sid);
    s.state = FB_PENDING;
    s.client_ip = client_ip;
    s.created_us = s.touched_us = now_us;
    drop_session(ctx);
    ctx->s = s;
    wipe(&s, sizeof s);
    return FB_OK;
}

fb_result_t fb_presence(fb_ctx_t *ctx, uint64_t now_us)
{
    fb_tick(ctx, now_us);
    if (ctx->s.state != FB_PENDING) return FB_ERR_NO_SESSION;
    ctx->s.state = FB_CLAIMED;
    ctx->s.touched_us = now_us;
    return FB_OK;
}

static bool sid_matches(const fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES])
{
    return ctx->s.state != FB_NONE && sid && equal_ct(ctx->s.sid, sid, FB_SID_BYTES);
}

fb_result_t fb_claim_code(fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES], const char *code, uint64_t now_us)
{
    fb_tick(ctx, now_us);
    if (ctx->code_failures >= FB_CODE_MAX_FAILS) return FB_ERR_LOCKED;
    if (!sid_matches(ctx, sid)) return FB_ERR_NO_SESSION;
    if (ctx->s.state != FB_PENDING) return ctx->s.state == FB_CLAIMED ? FB_OK : FB_ERR_NO_SESSION;
    uint8_t given[FB_CODE_DIGITS] = {0};
    size_t len = code ? strlen(code) : 0;
    if (len == FB_CODE_DIGITS) memcpy(given, code, FB_CODE_DIGITS);
    bool ok = len == FB_CODE_DIGITS && equal_ct(given, (const uint8_t *)ctx->code, FB_CODE_DIGITS);
    wipe(given, sizeof given);
    if (!ok) {
        ctx->code_failures++;
        return ctx->code_failures >= FB_CODE_MAX_FAILS ? FB_ERR_LOCKED : FB_ERR_BAD_CODE;
    }
    ctx->s.state = FB_CLAIMED;
    ctx->s.touched_us = now_us;
    return FB_OK;
}

fb_state_t fb_session_state(const fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES])
{
    return sid_matches(ctx, sid) ? ctx->s.state : FB_NONE;
}

fb_result_t fb_open(fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES], uint32_t seq,
                    const uint8_t iv[FB_IV_BYTES], const uint8_t *ct, size_t ct_len,
                    const uint8_t tag[FB_TAG_BYTES], char *pt, uint64_t now_us)
{
    fb_tick(ctx, now_us);
    if (!sid_matches(ctx, sid)) return FB_ERR_NO_SESSION;
    if (ctx->s.state != FB_CLAIMED) return FB_ERR_NOT_CLAIMED;
    if (!ct || !iv || !tag || !pt || ct_len == 0 || ct_len > FB_MAX_PLAINTEXT) return FB_ERR_SIZE;
    if (seq <= ctx->s.last_seq) return FB_ERR_REPLAY;
    /* The session id and sequence are authenticated, not encrypted. */
    uint8_t aad[FB_SID_BYTES + 4];
    memcpy(aad, ctx->s.sid, FB_SID_BYTES);
    aad[FB_SID_BYTES] = (uint8_t)(seq >> 24); aad[FB_SID_BYTES + 1] = (uint8_t)(seq >> 16);
    aad[FB_SID_BYTES + 2] = (uint8_t)(seq >> 8); aad[FB_SID_BYTES + 3] = (uint8_t)seq;
    if (ctx->crypto->gcm_open(ctx->s.key, iv, aad, sizeof aad, ct, ct_len, tag, (uint8_t *)pt) != 0) {
        wipe(pt, ct_len);
        return FB_ERR_AUTH;
    }
    pt[ct_len] = '\0';
    if (memchr(pt, '\0', ct_len)) {
        wipe(pt, ct_len);
        return FB_ERR_SIZE;
    }
    ctx->s.last_seq = seq;
    ctx->s.touched_us = now_us;
    return FB_OK;
}

bool fb_ap_frame_allowed(const uint8_t *f, size_t len, uint32_t ap_ip_nbo)
{
    if (!f || len < 14) return false;
    uint16_t type = (uint16_t)(f[12] << 8 | f[13]);
    if (type == 0x0806) return true;                     /* ARP */
    if (type != 0x0800 || len < 14 + 20) return false;   /* IPv6, VLAN, others */
    const uint8_t *ip = f + 14;
    if ((ip[0] >> 4) != 4 || (ip[0] & 0x0f) < 5) return false;
    uint32_t dst;
    memcpy(&dst, ip + 16, 4);                            /* network byte order */
    return dst == ap_ip_nbo || dst == 0xffffffffu;
}

static bool printable(const char *s)
{
    for (; *s; s++) if ((unsigned char)*s < 0x20 || (unsigned char)*s == 0x7f) return false;
    return true;
}

const char *fb_check_admin_password(const char *pw, const char *ssid)
{
    if (!pw) return "missing password";
    size_t len = strlen(pw);
    if (len < 8) return "password must be at least 8 characters";
    if (len > 64) return "password must be at most 64 characters";
    if (!printable(pw)) return "password contains control characters";
    bool same = true;
    for (size_t i = 1; i < len; i++) if (pw[i] != pw[0]) same = false;
    if (same) return "password must not repeat a single character";
    if (ssid && *ssid && strlen(ssid) == len) {
        bool eq = true;
        for (size_t i = 0; i < len; i++) if (tolower((unsigned char)pw[i]) != tolower((unsigned char)ssid[i])) eq = false;
        if (eq) return "password must differ from the Wi-Fi name";
    }
    return NULL;
}

const char *fb_check_uplink(const char *type, bool has_wifi, bool has_key, bool exit_node)
{
    if (!type || !strcmp(type, "wifi")) return has_wifi ? NULL : "choose a Wi-Fi network";
    if (!strcmp(type, "ethernet")) return NULL;          /* Wi-Fi optional: a backup */
    if (!strcmp(type, "cellular")) {
        if (!has_wifi && !has_key) return "with only the mobile network the gateway is reached through the tailnet: add an auth key";
        if (exit_node) return "an exit node over mobile data is not set up here; turn it on later if your plan allows it";
        return NULL;
    }
    return "unknown connection type";
}

const char *fb_check_tz(const char *tz)
{
    if (!tz || !*tz) return NULL;
    size_t len = strlen(tz);
    if (len > 63) return "time zone rule is too long";
    if (!isalpha((unsigned char)tz[0]) && tz[0] != '<') return "time zone rule must start with a name";
    for (const char *p = tz; *p; p++)
        if (!isalnum((unsigned char)*p) && !strchr(",.:/<>+-", *p)) return "time zone rule contains invalid characters";
    return NULL;
}

const char *fb_check_wifi(const char *ssid, const char *pw)
{
    if (!ssid || !*ssid) return "choose a Wi-Fi network";
    if (strlen(ssid) > 32) return "Wi-Fi name is longer than 32 bytes";
    if (!pw) return "missing Wi-Fi password";
    size_t len = strlen(pw);
    if (len == 0) return NULL;                           /* open network */
    if (len == 64) {
        for (size_t i = 0; i < 64; i++) if (!isxdigit((unsigned char)pw[i])) return "64-character keys must be hexadecimal";
        return NULL;
    }
    if (len < 8 || len > 63) return "Wi-Fi password must be 8 to 63 characters";
    return printable(pw) ? NULL : "Wi-Fi password contains control characters";
}

const char *fb_check_ap_password(const char *pw)
{
    if (!pw) return "missing access point password";
    size_t len = strlen(pw);
    if (len < 8 || len > 63) return "access point password must be 8 to 63 characters";
    return printable(pw) ? NULL : "access point password contains control characters";
}

const char *fb_check_auth_key(const char *key)
{
    if (!key || !*key) return NULL;                      /* tailnet can be joined later */
    size_t len = strlen(key);
    if (len < 10 || len > 200) return "auth key must be 10 to 200 characters";
    for (const char *p = key; *p; p++) if ((unsigned char)*p <= 0x20 || (unsigned char)*p >= 0x7f) return "auth key contains spaces or invalid characters";
    return NULL;
}

const char *fb_check_login_server(const char *url)
{
    if (!url || !*url) return NULL;                      /* Tailscale default */
    size_t len = strlen(url);
    if (len > 200) return "control server URL is too long";
    if (strncmp(url, "https://", 8) != 0 && strncmp(url, "http://", 7) != 0) return "control server URL must start with https://";
    for (const char *p = url; *p; p++) if ((unsigned char)*p <= 0x20 || (unsigned char)*p >= 0x7f) return "control server URL contains invalid characters";
    return NULL;
}

const char *fb_check_hostname(const char *name)
{
    if (!name || !*name) return NULL;
    size_t len = strlen(name);
    if (len > 63) return "device name must be at most 63 characters";
    if (name[0] == '-' || name[len - 1] == '-') return "device name must not start or end with '-'";
    for (const char *p = name; *p; p++)
        if (!(islower((unsigned char)*p) || isdigit((unsigned char)*p) || *p == '-')) return "device name may use a-z, 0-9 and '-'";
    return NULL;
}

int fb_hex_decode(const char *hex, uint8_t *out, size_t out_len)
{
    if (!hex || strlen(hex) != out_len * 2) return -1;
    for (size_t i = 0; i < out_len; i++) {
        int v = 0;
        for (int j = 0; j < 2; j++) {
            char c = hex[2 * i + j];
            int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (d < 0) return -1;
            v = v * 16 + d;
        }
        out[i] = (uint8_t)v;
    }
    return 0;
}

void fb_hex_encode(const uint8_t *in, size_t len, char *out)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < len; i++) { out[2 * i] = digits[in[i] >> 4]; out[2 * i + 1] = digits[in[i] & 15]; }
    out[2 * len] = '\0';
}
