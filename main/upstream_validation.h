#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Exact default-route membership, not a substring or a different prefix. */
static inline bool route_list_has_default_v4(const char *list)
{
    if (!list) return false;
    for (const char *p = list; *p;) {
        const char *end = p + strcspn(p, "\r\n");
        const char *next = end + strspn(end, "\r\n");
        while (p < end && (*p == ' ' || *p == '\t')) ++p;
        while (end > p && (end[-1] == ' ' || end[-1] == '\t')) --end;
        if ((size_t)(end - p) == 9 && !memcmp(p, "0.0.0.0/0", 9)) return true;
        p = next;
    }
    return false;
}

/* Append trimmed, exact-deduplicated route lines without silent truncation. */
static inline bool route_list_add(char *out, size_t capacity, const char *list)
{
    if (!out || !capacity || !list) return false;
    for (const char *p = list; *p;) {
        const char *end = p;
        while (*end && *end != '\r' && *end != '\n') ++end;
        const char *next = end;
        while (*next == '\r' || *next == '\n') ++next;
        while (p < end && (*p == ' ' || *p == '\t')) ++p;
        while (end > p && (end[-1] == ' ' || end[-1] == '\t')) --end;
        size_t n = (size_t)(end - p);
        bool duplicate = false;
        for (const char *q = out; *q;) {
            size_t m = strcspn(q, "\n");
            if (m == n && !memcmp(q, p, n)) duplicate = true;
            q += m;
            if (*q) ++q;
        }
        if (n && !duplicate) {
            size_t used = strlen(out), separator = used ? 1 : 0;
            if (used >= capacity || n + separator >= capacity - used) return false;
            if (separator) out[used++] = '\n';
            memcpy(out + used, p, n);
            out[used + n] = '\0';
        }
        p = next;
    }
    return true;
}

static inline bool ipn_version_valid(const char *text)
{
    if (!text || strlen(text) > 32) return false;
    for (; *text; ++text) {
        if (!((*text >= '0' && *text <= '9') || (*text >= 'A' && *text <= 'Z')
              || (*text >= 'a' && *text <= 'z') || *text == '.' || *text == '-'
              || *text == '+')) return false;
    }
    return true;
}

/* Exact cookie name and complete value; no prefix matches or early token exit. */
static inline bool session_cookie_matches(const char *header, const char *token)
{
    if (!header || !token || !*token) return false;
    size_t expected = strlen(token);
    for (const char *p = header; *p;) {
        while (*p == ' ' || *p == '\t' || *p == ';') ++p;
        size_t n = strcspn(p, ";");
        if (n >= 11 && !memcmp(p, "ts_session=", 11) && n - 11 == expected) {
            unsigned diff = 0;
            for (size_t i = 0; i < expected; ++i)
                diff |= (unsigned char)p[11 + i] ^ (unsigned char)token[i];
            if (!diff) return true;
        }
        p += n;
        if (*p) ++p;
    }
    return false;
}
