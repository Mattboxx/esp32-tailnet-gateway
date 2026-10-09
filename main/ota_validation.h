/* Pure guards shared by firmware and host regression tests. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define OTA_FORK_REPO "Mattboxx/esp32-tailscale-gateway-NAS-recovery"
#define OTA_FORK_URL "https://github.com/" OTA_FORK_REPO
#define OTA_FORK_API "https://api.github.com/repos/" OTA_FORK_REPO "/releases?per_page=10"

typedef struct { uint32_t upstream[3], edition[2], stage, serial; } ota_version_t;

static inline bool ota_number(const char **p, uint32_t *out)
{
    const char *s = *p;
    if (*s < '0' || *s > '9') return false;
    uint32_t n = 0;
    do {
        if (n > 9999) return false;
        n = n * 10 + (uint32_t)(*s++ - '0');
    } while (*s >= '0' && *s <= '9');
    *out = n; *p = s; return true;
}

static inline bool ota_version_parse(const char *text, ota_version_t *out)
{
    if (!text || !out || strlen(text) >= 32) return false;
    const char *p = text;
    if (*p == 'v') ++p;
    ota_version_t v = {0};
    for (int i = 0; i < 3; ++i) {
        if (!ota_number(&p, &v.upstream[i])) return false;
        if (i < 2 && *p++ != '.') return false;
    }
    if (strncmp(p, "-Mattboxx-", 10)) return false;
    p += 10;
    if (!ota_number(&p, &v.edition[0]) || *p++ != '.' || !ota_number(&p, &v.edition[1])) return false;
    v.stage = 4;
    if (*p == '-') {
        ++p;
        const char *names[] = {"dev", "alpha", "beta", "rc"};
        bool found = false;
        for (uint32_t i = 0; i < 4; ++i) {
            size_t n = strlen(names[i]);
            if (!strncmp(p, names[i], n)) { p += n; v.stage = i; found = true; break; }
        }
        if (!found) return false;
        if (*p == '.') { ++p; if (*p < '0' || *p > '9') return false; }
        if (*p && !ota_number(&p, &v.serial)) return false;
    }
    if (*p) return false;
    *out = v; return true;
}

static inline int ota_version_compare(const ota_version_t *a, const ota_version_t *b)
{
    uint32_t aa[] = {a->upstream[0], a->upstream[1], a->upstream[2], a->edition[0], a->edition[1], a->stage, a->serial};
    uint32_t bb[] = {b->upstream[0], b->upstream[1], b->upstream[2], b->edition[0], b->edition[1], b->stage, b->serial};
    for (unsigned i = 0; i < sizeof aa / sizeof aa[0]; ++i)
        if (aa[i] != bb[i]) return aa[i] > bb[i] ? 1 : -1;
    return 0;
}

static inline bool ota_digest_parse(const char *text, unsigned char out[32])
{
    if (!text || strncmp(text, "sha256:", 7) || strlen(text) != 71) return false;
    for (unsigned i = 0; i < 32; ++i) {
        unsigned value = 0;
        for (unsigned j = 0; j < 2; ++j) {
            char c = text[7 + 2*i + j];
            if (c >= '0' && c <= '9') value = value * 16 + (unsigned)(c - '0');
            else if (c >= 'a' && c <= 'f') value = value * 16 + (unsigned)(c - 'a' + 10);
            else return false;
        }
        out[i] = (unsigned char)value;
    }
    return true;
}

/* Fixed release URLs are constructed locally. Redirects may go only to the
 * GitHub release asset CDN, with HTTPS and no credentials/custom ports. */
static inline bool ota_download_url_allowed(const char *url)
{
    if (!url || strlen(url) >= 2048) return false;
    for (const unsigned char *p = (const unsigned char *)url; *p; ++p)
        if (*p <= 32 || *p >= 127 || *p == '\\') return false;
    const char *prefix = OTA_FORK_URL "/releases/download/";
    if (!strncmp(url, prefix, strlen(prefix))) {
        const char *tag = url + strlen(prefix), *slash = strchr(tag, '/');
        if (!slash || (size_t)(slash - tag) >= 32 || strcmp(slash, "/firmware.bin")) return false;
        char version[32] = {0}; memcpy(version, tag, (size_t)(slash - tag));
        ota_version_t v; return ota_version_parse(version, &v);
    }
    prefix = "https://release-assets.githubusercontent.com/github-production-release-asset/";
    return !strncmp(url, prefix, strlen(prefix)) && url[strlen(prefix)] != '\0';
}
