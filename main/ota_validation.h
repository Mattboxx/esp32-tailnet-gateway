/* Pure guards shared by firmware and host regression tests. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#if defined(__has_include)
#if __has_include("sdkconfig.h")
#include "sdkconfig.h"
#endif
#endif

/* 3.0 ships one image (every Web UI language, Ethernet driver), so the
 * updater has one release asset. The 2.x language and Ethernet assets
 * (firmware-<lang>.bin, firmware-eth.bin) belong to the 4 MB layout and are
 * never offered to this firmware. */
#ifndef OTA_ASSET
#define OTA_ASSET "firmware.bin"
#endif

/* Repository rename bridge. Firmware up to 1.14-dev.6 requests the releases
 * API of the previous name with redirects disabled and requires HTTP 200, so
 * it cannot follow a GitHub rename. This bridge looks up releases under the
 * current name first and falls back to the previous name only when the
 * current one answers 404 (before the rename). Downloads are accepted from
 * either fixed release path, so GitHub's previous->current redirect stays
 * inside the allowlist. Never reuse the previous name for another repository. */
#define OTA_REPO_CURRENT "Mattboxx/esp32-tailnet-gateway"
#define OTA_REPO_PREVIOUS "Mattboxx/esp32-tailscale-gateway-NAS-recovery"
#define OTA_REPO_COUNT 2u
#define OTA_FORK_REPO OTA_REPO_CURRENT
#define OTA_FORK_URL "https://github.com/" OTA_FORK_REPO

static inline const char *ota_repo(unsigned index)
{
    return index == 0 ? OTA_REPO_CURRENT : index == 1 ? OTA_REPO_PREVIOUS : NULL;
}

/* Returns the part after ".../<repo>/releases/download/", or NULL. */
static inline const char *ota_release_download_tail(const char *url, const char *repo)
{
    static const char host[] = "https://github.com/", path[] = "/releases/download/";
    size_t h = sizeof host - 1, r = strlen(repo), d = sizeof path - 1;
    if (strncmp(url, host, h) || strncmp(url + h, repo, r) || strncmp(url + h + r, path, d)) return NULL;
    return url + h + r + d;
}

/* Two numbering schemes. Legacy fork builds: "0.1.38-Mattboxx-1.13[-rc.1]"
 * (upstream base + edition). Product builds from 2.0.0 on: "2.0.0[-rc.1]".
 * Every product version is newer than every legacy one, so a legacy-tagged
 * bridge release can move old devices to an updater that understands both. */
typedef struct { uint32_t scheme, upstream[3], edition[2], stage, serial; } ota_version_t;

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
    if (!strncmp(p, "-Mattboxx-", 10)) {
        p += 10;
        if (!ota_number(&p, &v.edition[0]) || *p++ != '.' || !ota_number(&p, &v.edition[1])) return false;
    } else {
        /* Product numbering; 0.x would be ambiguous with the upstream base. */
        if (v.upstream[0] < 2) return false;
        v.scheme = 1;
    }
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
    uint32_t aa[] = {a->scheme, a->upstream[0], a->upstream[1], a->upstream[2], a->edition[0], a->edition[1], a->stage, a->serial};
    uint32_t bb[] = {b->scheme, b->upstream[0], b->upstream[1], b->upstream[2], b->edition[0], b->edition[1], b->stage, b->serial};
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
static inline bool ota_download_url_allowed_for(const char *url, const char *asset)
{
    if (!url || strlen(url) >= 2048) return false;
    for (const unsigned char *p = (const unsigned char *)url; *p; ++p)
        if (*p <= 32 || *p >= 127 || *p == '\\') return false;
    const char *tag = NULL;
    for (unsigned i = 0; i < OTA_REPO_COUNT && !tag; ++i) tag = ota_release_download_tail(url, ota_repo(i));
    if (tag) {
        const char *slash = strchr(tag, '/');
        if (!slash || (size_t)(slash - tag) >= 32 || !asset || strcmp(slash + 1, asset)) return false;
        char version[32] = {0}; memcpy(version, tag, (size_t)(slash - tag));
        ota_version_t v; return ota_version_parse(version, &v);
    }
    const char *prefix = "https://release-assets.githubusercontent.com/github-production-release-asset/";
    return !strncmp(url, prefix, strlen(prefix)) && url[strlen(prefix)] != '\0';
}
static inline bool ota_download_url_allowed(const char *url)
{
    return ota_download_url_allowed_for(url, OTA_ASSET);
}
