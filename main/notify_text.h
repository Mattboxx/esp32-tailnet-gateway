/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Notification wording shared by ntfy, Telegram and email (3.0.12).
 *
 * One title and one message per event, so every channel says the same thing:
 * ntfy publishes them as Title header and body; Telegram sends the title on
 * the first line; email uses the title as the subject. Pure functions (no
 * ESP-IDF calls): the caller passes the reset cause and the firmware version. */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define NOTIFY_TITLE_MAX 64
#define NOTIFY_MESSAGE_MAX 400

/* Readable reset cause of an esp_reset_reason_t value; "(possible blackout)"
 * is added to a power-on only when power-on notifications were opted in. */
const char *notify_text_reset_cause(int esp_reset_reason, bool poweron_events);

/* The gateway started: power-on or restart, firmware, reset cause. */
void notify_text_boot(char title[NOTIFY_TITLE_MAX], char *msg, size_t cap,
                      const char *version, int esp_reset_reason, bool poweron_events);
/* The uplink works but Tailscale stayed disconnected. */
void notify_text_tailscale_problem(char title[NOTIFY_TITLE_MAX], char *msg, size_t cap);
/* The Tailscale control connection is back after outage_seconds. */
void notify_text_tailscale_restored(char title[NOTIFY_TITLE_MAX], char *msg, size_t cap, uint32_t outage_seconds);
/* A newer firmware was found; nothing installed. */
void notify_text_update_available(char title[NOTIFY_TITLE_MAX], char *msg, size_t cap, const char *version);

/* Telegram/email: the title and message for a queued history event, worded
 * as ntfy words the same event. kind/level are history.h values; the raw
 * event text is kept as the detail where ntfy has no richer wording. */
void notify_text_compose(unsigned kind, unsigned level, const char *event_text,
                         const char *version, int esp_reset_reason, bool poweron_events,
                         char title[NOTIFY_TITLE_MAX], char *msg, size_t cap);
