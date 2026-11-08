/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
#pragma once

/* Remote commands shared by ntfy and Telegram, with the same options:
 *   info                         operational state (info_enabled)
 *   wol NAME | wol MAC           Wake-on-LAN; an unsaved MAC needs allow_direct_mac
 *   recover NAME|MAC, check ...  bounded recovery job / reachability check
 * Edges are trimmed; commands of 128 characters or more are ignored.
 * Implemented in ntfy_integration.c. */

#include <stdbool.h>
#include <stddef.h>

typedef enum {
    REMOTE_CMD_NONE,    /* not a command: ignore, count nothing */
    REMOTE_CMD_INFO,    /* the caller sends remote_info_text() */
    REMOTE_CMD_OK,      /* done; reply/title describe it */
    REMOTE_CMD_ERROR,   /* refused or failed; reply may be empty (info disabled) */
} remote_cmd_kind_t;

remote_cmd_kind_t remote_command_run(const char *message, bool info_enabled, bool allow_direct_mac,
                                     char *reply, size_t cap, const char **title);

/* Heap text of the info reply (about 8 KB at most); the caller frees it.
 * Never contains passwords, Wi-Fi keys, Tailscale keys or service tokens. */
char *remote_info_text(bool include_details, bool poweron_events);
