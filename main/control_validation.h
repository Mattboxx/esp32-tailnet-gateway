#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <strings.h>

/* Unknown payloads are errors, never an implicit OFF command. */
static inline bool control_parse_bool(const char *text, bool *out)
{
    if (!text || !out) return false;
    if (!strcasecmp(text, "ON") || !strcmp(text, "1") || !strcasecmp(text, "true")) {
        *out = true;
        return true;
    }
    if (!strcasecmp(text, "OFF") || !strcmp(text, "0") || !strcasecmp(text, "false")) {
        *out = false;
        return true;
    }
    return false;
}

/* No signs, whitespace, empty index, overflow or trailing characters. */
static inline bool control_parse_index(const char *text, unsigned limit, unsigned *out)
{
    if (!text || !*text || !out || !limit) return false;
    unsigned value = 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return false;
        unsigned digit = (unsigned)(*text - '0');
        if (value > (UINT32_MAX - digit) / 10) return false;
        value = value * 10 + digit;
        if (value >= limit) return false;
    }
    *out = value;
    return true;
}

/* Binding/version selector, NOT authentication. Exactly eight hex digits. */
static inline bool control_parse_hex32(const char *text,uint32_t *out)
{
    if(!text||!out||strlen(text)!=8)return false;
    uint32_t n=0;
    for(unsigned i=0;i<8;i++){
        unsigned char c=(unsigned char)text[i];unsigned digit;
        if(c>='0'&&c<='9')digit=c-'0';
        else if(c>='a'&&c<='f')digit=c-'a'+10;
        else if(c>='A'&&c<='F')digit=c-'A'+10;
        else return false;
        n=(n<<4)|digit;
    }
    *out=n;return true;
}

static inline uint8_t control_cpu_pct(uint64_t elapsed, uint64_t idle)
{
    if (!elapsed || idle >= elapsed) return 0;
    return (uint8_t)(((elapsed - idle) * 100 + elapsed / 2) / elapsed);
}
