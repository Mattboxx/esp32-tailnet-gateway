/* Mattboxx Edition changes: Copyright (C) 2026 Mattboxx, GPL-3.0-only (LICENSE,
 * LICENSE-EXCEPTION.md). The original code keeps the licence stated in its own
 * notice below (see also NOTICE.md and licenses/upstream/). */
/* Web interface password — set, verify, query.
 *
 * SPDX-License-Identifier: MIT
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "esp_err.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "mbedtls/md.h"
#include "psa/crypto.h"
#include "nvs.h"

#include "web_password.h"
#include "login_budget.h"

/* Must match the NVS_NAMESPACE define in main/nvs_params.h. Duplicated
 * here so web_password can live as its own component and be required
 * by both main and remote_console without a cycle. */
#define PW_NVS_NAMESPACE "tsr"
#define PW_NVS_KEY       "web_password"
#define PW_SALT_LEN      16
#define PW_HASH_LEN      32  /* SHA-256 output */
#define PW_PBKDF2_PREFIX "pbkdf2-sha256$"
#define PW_PBKDF2_ITERS  60000U
#define PW_PBKDF2_ITERS_MIN 10000U
#define PW_PBKDF2_ITERS_MAX 500000U

/* A successful PBKDF2 verification seeds a boot-local, salted exact-match
 * cache.  It is deliberately never persisted: the strong PBKDF2 record
 * remains the only password verifier in NVS and the first login after every
 * reboot still proves the password against it.  Subsequent correct unlocks
 * (for example after an idle session timeout) avoid repeatedly blocking the
 * ESP HTTP task for the full PBKDF2 run.  Cache misses still fall through to
 * PBKDF2, preserving the cost of wrong guesses in addition to endpoint rate
 * limiting. */
static portMUX_TYPE s_fast_cache_mux = portMUX_INITIALIZER_UNLOCKED;
static portMUX_TYPE s_budget_mux = portMUX_INITIALIZER_UNLOCKED;
static login_budget_t s_budget;

uint64_t web_password_attempt_wait_us(uint64_t now_us)
{
    portENTER_CRITICAL(&s_budget_mux);
    uint64_t wait = login_budget_wait_us(&s_budget, now_us);
    portEXIT_CRITICAL(&s_budget_mux);
    return wait;
}

void web_password_attempt_failed(uint64_t now_us)
{
    portENTER_CRITICAL(&s_budget_mux);
    login_budget_failed(&s_budget, now_us);
    portEXIT_CRITICAL(&s_budget_mux);
}
static bool    s_fast_cache_valid;
static uint8_t s_fast_cache_salt[PW_SALT_LEN];
static uint8_t s_fast_cache_hash[PW_HASH_LEN];

/* Local helpers — raw NVS instead of nvs_params.h to avoid pulling a
 * cross-component dep on main. */
static char *nvs_dup_str(const char *key)
{
    nvs_handle_t h;
    if (nvs_open(PW_NVS_NAMESPACE, NVS_READONLY, &h) != ESP_OK) return NULL;
    size_t len = 0;
    if (nvs_get_str(h, key, NULL, &len) != ESP_OK || len == 0) {
        nvs_close(h);
        return NULL;
    }
    char *buf = malloc(len);
    if (!buf) { nvs_close(h); return NULL; }
    if (nvs_get_str(h, key, buf, &len) != ESP_OK) {
        free(buf);
        nvs_close(h);
        return NULL;
    }
    nvs_close(h);
    return buf;
}

static esp_err_t nvs_write_str(const char *key, const char *value)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(PW_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = nvs_set_str(h, key, value);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}

static void bytes_to_hex(const uint8_t *src, size_t len, char *out)
{
    for (size_t i = 0; i < len; i++) {
        sprintf(out + i * 2, "%02x", src[i]);
    }
    out[len * 2] = '\0';
}

static int hex_to_bytes(const char *src, uint8_t *dst, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        unsigned int b;
        if (sscanf(src + i * 2, "%2x", &b) != 1) return -1;
        dst[i] = (uint8_t)b;
    }
    return 0;
}

static bool compute_hash(const uint8_t *salt, size_t salt_len,
                         const char *plaintext, uint8_t *hash_out)
{
    mbedtls_md_context_t ctx;
    mbedtls_md_init(&ctx);
    int rc = mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 0);
    if (rc == 0) rc = mbedtls_md_starts(&ctx);
    if (rc == 0) rc = mbedtls_md_update(&ctx, salt, salt_len);
    if (rc == 0) rc = mbedtls_md_update(&ctx, (const uint8_t *)plaintext, strlen(plaintext));
    if (rc == 0) rc = mbedtls_md_finish(&ctx, hash_out);
    mbedtls_md_free(&ctx);
    return rc == 0;
}

/* Preserve the stored PBKDF2-HMAC-SHA256 record and its iteration limits. */
static bool compute_pbkdf2(const uint8_t *salt, size_t salt_len,
                           const char *plaintext, uint32_t iterations,
                           uint8_t hash_out[PW_HASH_LEN])
{
    if (!salt || !plaintext || iterations < PW_PBKDF2_ITERS_MIN
        || iterations > PW_PBKDF2_ITERS_MAX) return false;

    psa_key_derivation_operation_t operation = PSA_KEY_DERIVATION_OPERATION_INIT;
    psa_status_t status = psa_key_derivation_setup(&operation, PSA_ALG_PBKDF2_HMAC(PSA_ALG_SHA_256));
    if (status == PSA_SUCCESS)
        status = psa_key_derivation_input_integer(&operation, PSA_KEY_DERIVATION_INPUT_COST, iterations);
    if (status == PSA_SUCCESS)
        status = psa_key_derivation_input_bytes(&operation, PSA_KEY_DERIVATION_INPUT_SALT, salt, salt_len);
    if (status == PSA_SUCCESS)
        status = psa_key_derivation_input_bytes(&operation, PSA_KEY_DERIVATION_INPUT_PASSWORD,
                                                (const uint8_t *)plaintext, strlen(plaintext));
    if (status == PSA_SUCCESS)
        status = psa_key_derivation_output_bytes(&operation, hash_out, PW_HASH_LEN);
    if (psa_key_derivation_abort(&operation) != PSA_SUCCESS) return false;
    return status == PSA_SUCCESS;
}

static bool hashes_equal(const uint8_t a[PW_HASH_LEN],
                         const uint8_t b[PW_HASH_LEN])
{
    volatile unsigned diff = 0;
    for (size_t i = 0; i < PW_HASH_LEN; i++) diff |= a[i] ^ b[i];
    return diff == 0;
}

static void fast_cache_invalidate(void)
{
    portENTER_CRITICAL(&s_fast_cache_mux);
    s_fast_cache_valid = false;
    memset(s_fast_cache_salt, 0, sizeof s_fast_cache_salt);
    memset(s_fast_cache_hash, 0, sizeof s_fast_cache_hash);
    portEXIT_CRITICAL(&s_fast_cache_mux);
}

static void fast_cache_store(const char *plaintext)
{
    uint8_t salt[PW_SALT_LEN];
    uint8_t hash[PW_HASH_LEN];
    esp_fill_random(salt, sizeof salt);
    if (!compute_hash(salt, sizeof salt, plaintext, hash)) {
        fast_cache_invalidate();
        return;
    }

    portENTER_CRITICAL(&s_fast_cache_mux);
    memcpy(s_fast_cache_salt, salt, sizeof salt);
    memcpy(s_fast_cache_hash, hash, sizeof hash);
    s_fast_cache_valid = true;
    portEXIT_CRITICAL(&s_fast_cache_mux);

    volatile uint8_t *wipe = hash;
    for (size_t i = 0; i < sizeof hash; i++) wipe[i] = 0;
}

static bool fast_cache_matches(const char *plaintext)
{
    uint8_t salt[PW_SALT_LEN];
    uint8_t expected[PW_HASH_LEN];

    portENTER_CRITICAL(&s_fast_cache_mux);
    bool valid = s_fast_cache_valid;
    if (valid) {
        memcpy(salt, s_fast_cache_salt, sizeof salt);
        memcpy(expected, s_fast_cache_hash, sizeof expected);
    }
    portEXIT_CRITICAL(&s_fast_cache_mux);
    if (!valid) return false;

    uint8_t computed[PW_HASH_LEN];
    bool match = compute_hash(salt, sizeof salt, plaintext, computed)
                 && hashes_equal(expected, computed);
    volatile uint8_t *wipe_computed = computed;
    volatile uint8_t *wipe_expected = expected;
    for (size_t i = 0; i < sizeof computed; i++) {
        wipe_computed[i] = 0;
        wipe_expected[i] = 0;
    }
    return match;
}

static bool verify_legacy_sha256(const char *stored, const char *plaintext)
{
    const char *colon = strchr(stored, ':');
    if (!colon || (size_t)(colon - stored) != PW_SALT_LEN * 2
        || strlen(colon + 1) != PW_HASH_LEN * 2) return false;

    uint8_t salt[PW_SALT_LEN], expected[PW_HASH_LEN], computed[PW_HASH_LEN];
    if (hex_to_bytes(stored, salt, PW_SALT_LEN) != 0
        || hex_to_bytes(colon + 1, expected, PW_HASH_LEN) != 0) return false;
    return compute_hash(salt, sizeof salt, plaintext, computed)
           && hashes_equal(expected, computed);
}

static bool verify_pbkdf2(const char *stored, const char *plaintext)
{
    const size_t prefix_len = strlen(PW_PBKDF2_PREFIX);
    if (strncmp(stored, PW_PBKDF2_PREFIX, prefix_len) != 0) return false;
    const char *iterations_text = stored + prefix_len;
    char *iterations_end = NULL;
    unsigned long iterations = strtoul(iterations_text, &iterations_end, 10);
    if (!iterations_end || iterations_end == iterations_text || *iterations_end != '$'
        || iterations < PW_PBKDF2_ITERS_MIN || iterations > PW_PBKDF2_ITERS_MAX)
        return false;

    const char *salt_hex = iterations_end + 1;
    const char *separator = strchr(salt_hex, '$');
    if (!separator || (size_t)(separator - salt_hex) != PW_SALT_LEN * 2
        || strlen(separator + 1) != PW_HASH_LEN * 2) return false;

    uint8_t salt[PW_SALT_LEN], expected[PW_HASH_LEN], computed[PW_HASH_LEN];
    if (hex_to_bytes(salt_hex, salt, PW_SALT_LEN) != 0
        || hex_to_bytes(separator + 1, expected, PW_HASH_LEN) != 0
        || !compute_pbkdf2(salt, sizeof salt, plaintext, (uint32_t)iterations,
                           computed)) return false;
    return hashes_equal(expected, computed);
}

static bool parse_pbkdf2_record(const char *stored, uint32_t *iterations,
                                uint8_t salt[PW_SALT_LEN],
                                uint8_t verifier[PW_HASH_LEN])
{
    if (!stored) return false;
    const size_t prefix_len = strlen(PW_PBKDF2_PREFIX);
    if (strncmp(stored, PW_PBKDF2_PREFIX, prefix_len) != 0) return false;
    const char *iterations_text = stored + prefix_len;
    char *iterations_end = NULL;
    unsigned long parsed = strtoul(iterations_text, &iterations_end, 10);
    if (!iterations_end || iterations_end == iterations_text || *iterations_end != '$'
        || parsed < PW_PBKDF2_ITERS_MIN || parsed > PW_PBKDF2_ITERS_MAX)
        return false;
    const char *salt_hex = iterations_end + 1;
    const char *separator = strchr(salt_hex, '$');
    if (!separator || (size_t)(separator - salt_hex) != PW_SALT_LEN * 2
        || strlen(separator + 1) != PW_HASH_LEN * 2
        || hex_to_bytes(salt_hex, salt, PW_SALT_LEN) != 0
        || hex_to_bytes(separator + 1, verifier, PW_HASH_LEN) != 0)
        return false;
    *iterations = (uint32_t)parsed;
    return true;
}

bool web_password_get_proof_params(uint32_t *iterations,
                                   uint8_t salt[WEB_PASSWORD_SALT_LEN])
{
    if (!iterations || !salt) return false;
    char *stored = nvs_dup_str(PW_NVS_KEY);
    uint8_t verifier[PW_HASH_LEN] = {0};
    bool ok = parse_pbkdf2_record(stored, iterations, salt, verifier);
    free(stored);
    volatile uint8_t *wipe = verifier;
    for (size_t i = 0; i < sizeof verifier; i++) wipe[i] = 0;
    return ok;
}

bool verify_web_password_proof(const uint8_t *message, size_t message_len,
                               const uint8_t proof[WEB_PASSWORD_PROOF_LEN])
{
    if (!message || !message_len || !proof) return false;
    char *stored = nvs_dup_str(PW_NVS_KEY);
    uint32_t iterations = 0;
    uint8_t salt[PW_SALT_LEN] = {0}, verifier[PW_HASH_LEN] = {0};
    bool ok = parse_pbkdf2_record(stored, &iterations, salt, verifier);
    free(stored);
    (void)iterations;
    if (ok) {
        const psa_algorithm_t algorithm = PSA_ALG_HMAC(PSA_ALG_SHA_256);
        psa_key_attributes_t attributes = PSA_KEY_ATTRIBUTES_INIT;
        psa_set_key_type(&attributes, PSA_KEY_TYPE_HMAC);
        psa_set_key_usage_flags(&attributes, PSA_KEY_USAGE_VERIFY_MESSAGE);
        psa_set_key_algorithm(&attributes, algorithm);
        psa_key_id_t key = 0;
        ok = psa_import_key(&attributes, verifier, sizeof verifier, &key) == PSA_SUCCESS;
        if (ok)
            ok = psa_mac_verify(key, algorithm, message, message_len,
                                proof, WEB_PASSWORD_PROOF_LEN) == PSA_SUCCESS;
        if (key && psa_destroy_key(key) != PSA_SUCCESS) ok = false;
        psa_reset_key_attributes(&attributes);
    }
    volatile uint8_t *wipe_salt = salt;
    volatile uint8_t *wipe_verifier = verifier;
    for (size_t i = 0; i < sizeof verifier; i++) {
        wipe_verifier[i] = 0;
        if (i < sizeof salt) wipe_salt[i] = 0;
    }
    return ok;
}

bool is_web_password_set(void)
{
    char *s = nvs_dup_str(PW_NVS_KEY);
    if (!s) return false;
    bool set = (s[0] != '\0');
    free(s);
    return set;
}

bool verify_web_password(const char *plaintext)
{
    if (!plaintext) return false;
    if (fast_cache_matches(plaintext)) return true;

    char *stored = nvs_dup_str(PW_NVS_KEY);
    if (!stored) return false;

    bool modern = strncmp(stored, PW_PBKDF2_PREFIX,
                          strlen(PW_PBKDF2_PREFIX)) == 0;
    bool ok = modern ? verify_pbkdf2(stored, plaintext)
                     : verify_legacy_sha256(stored, plaintext);

    free(stored);
    /* Seamless upgrade: an old salt+SHA-256 verifier remains accepted once,
     * then is immediately replaced with the slower version. Login still
     * succeeds if the NVS rewrite fails; availability must not depend on a
     * migration write, and the next successful login will retry it. */
    if (ok && !modern) {
        /* set_web_password_hashed() also seeds the fast cache after the
         * upgraded verifier has reached NVS. */
        if (set_web_password_hashed(plaintext) != ESP_OK) {
            fast_cache_store(plaintext);
        }
    } else if (ok) {
        fast_cache_store(plaintext);
    }
    return ok;
}

esp_err_t set_web_password_hashed(const char *plaintext)
{
    if (!plaintext) return ESP_ERR_INVALID_ARG;
    /* Never let a cached verifier survive a password change or clear. */
    fast_cache_invalidate();
    if (plaintext[0] == '\0') {
        return nvs_write_str(PW_NVS_KEY, "");
    }

    uint8_t salt[PW_SALT_LEN], hash[PW_HASH_LEN];
    esp_fill_random(salt, PW_SALT_LEN);
    if (!compute_pbkdf2(salt, sizeof salt, plaintext, PW_PBKDF2_ITERS, hash))
        return ESP_FAIL;

    char salt_hex[PW_SALT_LEN * 2 + 1];
    char hash_hex[PW_HASH_LEN * 2 + 1];
    bytes_to_hex(salt, sizeof salt, salt_hex);
    bytes_to_hex(hash, sizeof hash, hash_hex);
    char buf[sizeof PW_PBKDF2_PREFIX + 10 + sizeof salt_hex + sizeof hash_hex + 2];
    snprintf(buf, sizeof buf, PW_PBKDF2_PREFIX "%u$%s$%s",
             (unsigned)PW_PBKDF2_ITERS, salt_hex, hash_hex);

    esp_err_t err = nvs_write_str(PW_NVS_KEY, buf);
    if (err == ESP_OK) fast_cache_store(plaintext);
    return err;
}
