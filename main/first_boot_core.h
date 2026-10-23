/* First-boot setup: platform-independent state and checks.
 *
 * A brand-new gateway opens an unprotected setup access point. Anybody in
 * radio range can join it and every frame on it can be read, so pairing has
 * two independent protections:
 *   1. Physical presence: one pending pairing at a time is claimed only by
 *      the BOOT button or by a setup code printed on the USB serial console.
 *   2. Confidentiality: browser and gateway agree on a key with X25519 and
 *      every setup request is AES-256-GCM sealed with an increasing sequence
 *      number, so passwords and keys never cross the open radio in clear.
 * An active attacker present during setup can still impersonate the access
 * point; that residual risk is documented, not hidden.
 *
 * Crypto and randomness are injected so the logic runs in host tests.
 * SPDX-License-Identifier: MIT */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FB_KEY_BYTES        32
#define FB_SID_BYTES        16
#define FB_IV_BYTES         12
#define FB_TAG_BYTES        16
#define FB_CODE_DIGITS      8
#define FB_PENDING_TTL_US   (120ULL * 1000000ULL)   /* pairing must be confirmed within 2 min */
#define FB_CLAIMED_IDLE_US  (30ULL * 60ULL * 1000000ULL)
#define FB_CODE_MAX_FAILS   5
#define FB_MAX_PLAINTEXT    1536

typedef enum { FB_NONE = 0, FB_PENDING, FB_CLAIMED } fb_state_t;

typedef enum {
    FB_OK = 0,
    FB_ERR_BUSY,          /* another client has a pending pairing */
    FB_ERR_CLAIMED,       /* already paired with another client */
    FB_ERR_NO_SESSION,    /* unknown/expired session id */
    FB_ERR_NOT_CLAIMED,   /* presence not confirmed yet */
    FB_ERR_BAD_KEY,       /* malformed or low-order public key */
    FB_ERR_LOCKED,        /* too many wrong setup codes this boot */
    FB_ERR_BAD_CODE,
    FB_ERR_AUTH,          /* seal does not verify */
    FB_ERR_REPLAY,        /* sequence not increasing */
    FB_ERR_SIZE,
    FB_ERR_CRYPTO,
} fb_result_t;

typedef struct {
    void (*random)(uint8_t *out, size_t len);
    /* RFC 7748 X25519; returns 0, or -1 for an all-zero (low-order) result. */
    int (*x25519)(uint8_t out[32], const uint8_t scalar[32], const uint8_t point[32]);
    void (*sha256)(const uint8_t *data, size_t len, uint8_t out[32]);
    /* AES-256-GCM open: returns 0 only when the tag verifies. */
    int (*gcm_open)(const uint8_t key[32], const uint8_t iv[12], const uint8_t *aad, size_t aad_len,
                    const uint8_t *ct, size_t ct_len, const uint8_t tag[16], uint8_t *pt);
} fb_crypto_t;

typedef struct {
    fb_state_t state;
    uint8_t sid[FB_SID_BYTES];
    uint8_t device_pub[32];
    uint8_t key[FB_KEY_BYTES];
    uint32_t client_ip;
    uint64_t created_us, touched_us;
    uint32_t last_seq;
} fb_session_t;

typedef struct {
    fb_session_t s;
    char code[FB_CODE_DIGITS + 1];
    uint8_t code_failures;
    const fb_crypto_t *crypto;
} fb_ctx_t;

/* Unconfigured means: never completed setup, no admin password, no saved
 * uplink and no tailnet key. Any single item marks an existing installation
 * (for example one upgraded from 1.13), which never gets the open AP. */
bool fb_should_activate(bool setup_done, bool password_set, int wifi_networks, bool has_auth_key);

void fb_init(fb_ctx_t *ctx, const fb_crypto_t *crypto);
/* Expire stale pending/idle sessions. */
void fb_tick(fb_ctx_t *ctx, uint64_t now_us);
fb_result_t fb_begin(fb_ctx_t *ctx, uint32_t client_ip, const uint8_t client_pub[32], uint64_t now_us);
/* BOOT button: confirms the single fresh pending pairing. */
fb_result_t fb_presence(fb_ctx_t *ctx, uint64_t now_us);
fb_result_t fb_claim_code(fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES], const char *code, uint64_t now_us);
/* Verify and decrypt a sealed request; `seq` must be greater than the last.
 * `pt` must hold ct_len + 1 bytes and is NUL-terminated on success. */
fb_result_t fb_open(fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES], uint32_t seq,
                    const uint8_t iv[FB_IV_BYTES], const uint8_t *ct, size_t ct_len,
                    const uint8_t tag[FB_TAG_BYTES], char *pt, uint64_t now_us);
/* Session id check without consuming a sequence (status reads). */
fb_state_t fb_session_state(const fb_ctx_t *ctx, const uint8_t sid[FB_SID_BYTES]);
void fb_wipe(fb_ctx_t *ctx);

/* Setup-AP isolation: true when an Ethernet frame received on the setup AP
 * may reach the stack (ARP, or IPv4 to the AP itself or broadcast). Anything
 * else would be forwarded towards the uplink and is dropped. */
bool fb_ap_frame_allowed(const uint8_t *frame, size_t len, uint32_t ap_ip_nbo);

/* Field checks shared by the HTTP layer; return NULL or an English reason. */
const char *fb_check_admin_password(const char *pw, const char *ssid);
const char *fb_check_wifi(const char *ssid, const char *password);
const char *fb_check_ap_password(const char *pw);
const char *fb_check_auth_key(const char *key);
const char *fb_check_login_server(const char *url);
const char *fb_check_hostname(const char *name);

int fb_hex_decode(const char *hex, uint8_t *out, size_t out_len);
void fb_hex_encode(const uint8_t *in, size_t len, char *out);

#ifdef __cplusplus
}
#endif
