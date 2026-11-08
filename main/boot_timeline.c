/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Boot timeline (see boot_timeline.h): 7 words of RAM, set once each. */
#include "boot_timeline.h"
#include <stdbool.h>

#ifdef BOOT_TIMELINE_HOST_TEST
extern uint64_t boot_timeline_test_now_us;
static uint64_t now_us(void) { return boot_timeline_test_now_us; }
#else
#include "esp_timer.h"
static uint64_t now_us(void) { return (uint64_t)esp_timer_get_time(); }
#endif

static uint32_t s_ms[BOOT_TL_COUNT];

void boot_timeline_mark(boot_timeline_mark_t m)
{
    if ((unsigned)m >= BOOT_TL_COUNT) return;
    uint64_t ms = now_us() / 1000u;
    uint32_t v = ms == 0 ? 1u : ms > UINT32_MAX ? UINT32_MAX : (uint32_t)ms;   /* 0 means "not reached" */
    uint32_t expected = 0;
    __atomic_compare_exchange_n(&s_ms[m], &expected, v, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED);
}

void boot_timeline_get(uint32_t out[BOOT_TL_COUNT])
{
    for (int i = 0; i < BOOT_TL_COUNT; i++) out[i] = __atomic_load_n(&s_ms[i], __ATOMIC_RELAXED);
}
