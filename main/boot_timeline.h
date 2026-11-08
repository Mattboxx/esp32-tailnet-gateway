/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Boot timeline: when each startup milestone was first reached in this boot.
 *
 * Milliseconds since the application timer started (shortly after the
 * bootloader; ROM and bootloader time are not included). Each milestone is
 * set once, by its first occurrence; later reconnects never change it. RAM
 * only: no NVS key, no flash write, no task. Read by /api/system/diag and
 * the Diagnostics page; the tailnet stages come from MicroLink
 * (microlink_get_boot_marks). */
#pragma once

#include <stdint.h>

typedef enum {
    BOOT_TL_APP_MAIN,       /* app_main entered */
    BOOT_TL_NVS,            /* settings storage open and recovered */
    BOOT_TL_WIFI_START,     /* Wi-Fi driver started (AP and/or STA) */
    BOOT_TL_WIFI_ASSOC,     /* station associated with the uplink network */
    BOOT_TL_IP,             /* station received its IP address */
    BOOT_TL_WEB,            /* web interface and API serving */
    BOOT_TL_TIME,           /* wall-clock time synchronised (needed by Noise) */
    BOOT_TL_COUNT
} boot_timeline_mark_t;

/* Records the milestone if it was not reached yet (any task, any core). */
void boot_timeline_mark(boot_timeline_mark_t m);
/* Copies all milestones; 0 = not reached in this boot. */
void boot_timeline_get(uint32_t out[BOOT_TL_COUNT]);
