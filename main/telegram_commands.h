/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
#pragma once

/* Remote commands over the Telegram bot, with the same commands and options
 * as ntfy (remote_commands.h): info, wol, recover, check; commands only while
 * Tailscale is down; unsaved MAC addresses; private details in info.
 *
 * Off by default. Off, nothing runs: the poller task (PSRAM stack) exists
 * only while commands are on and the Telegram channel is configured. Only
 * messages from the configured chat are executed; others are skipped. The
 * last processed update is saved before a command runs, so nothing runs
 * twice after a restart; on first use the backlog is skipped, and messages
 * older than 10 minutes (with a known clock) are ignored. Replies go to the
 * same chat. Uses the bot token and chat of the Telegram notifications.
 *
 * Original implementation, Mattboxx Edition. MIT. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    bool commands_enabled;
    bool commands_only_when_tailscale_down;
    bool allow_direct_mac;
    bool info_enabled;
    bool info_include_details;
    uint16_t poll_interval_seconds;   /* 5..300 */
} telegram_commands_config_t;

typedef struct {
    bool running;
    uint32_t commands_received;
    uint32_t command_errors;
    uint32_t skipped_other_chats;
    char last_error[64];
} telegram_commands_status_t;

/* Core (pure, host-tested). */
#define TG_CMD_TEXT_MAX 128
typedef struct {
    char text[TG_CMD_TEXT_MAX];
} tg_command_t;
typedef struct {
    int count;                  /* commands from the configured chat, in order */
    tg_command_t cmd[5];
    uint32_t last_update_id;    /* highest update_id seen, 0 when none */
    int other_chats;            /* messages from any other chat (skipped) */
    int stale;                  /* older than the age limit (skipped) */
    bool valid;                 /* a well-formed {"ok":true,"result":[...]} */
} tg_updates_t;
/* Parse a getUpdates answer. chat: the configured chat id as text; now_wall:
 * seconds since 1970 or 0 when the clock is unknown (no age check). */
void tg_updates_parse(const char *json, size_t len, const char *chat, uint32_t now_wall, tg_updates_t *out);
/* "/wol@MyBot nas" -> "wol nas"; plain text is copied. False when it does not fit. */
bool tg_command_normalize(const char *in, char *out, size_t cap);
bool telegram_commands_config_valid(const telegram_commands_config_t *c);

/* Firmware. */
void telegram_commands_init(void);
void telegram_commands_get_config(telegram_commands_config_t *out);
void telegram_commands_get_status(telegram_commands_status_t *out);
esp_err_t telegram_commands_set_config(const telegram_commands_config_t *c);
/* Called when the Telegram notification settings change. */
void telegram_commands_refresh(void);
