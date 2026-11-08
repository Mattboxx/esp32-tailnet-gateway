/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool valid;
    uint8_t load_pct;
    uint8_t core_pct[2];
} runtime_metrics_t;

void runtime_metrics_init(void);
runtime_metrics_t runtime_metrics_get(void);
