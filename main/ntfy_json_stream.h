/* Bounded, allocation-free projection of one ntfy JSON event. SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    char id[48], event[16], message[128], title[7];
    bool has_message, message_too_long;
} ntfy_json_event_t;

typedef struct {
    struct { uint8_t kind, phase; } stack[32];
    uint8_t depth, lex, number, literal_pos, field, capture, seen;
    uint8_t unicode_digits, utf8_left, utf8_min, utf8_max;
    uint16_t unicode, high_surrogate;
    bool started, done, invalid, key, overflow;
    size_t used, trim_end;
    const char *literal;
    char text[128];
    ntfy_json_event_t event;
} ntfy_json_parser_t;

void ntfy_json_reset(ntfy_json_parser_t *parser);
void ntfy_json_feed(ntfy_json_parser_t *parser, unsigned char byte);
bool ntfy_json_finish(const ntfy_json_parser_t *parser);
