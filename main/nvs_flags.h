/* A few on/off switches saved as one NVS byte, so a save is all or nothing.
 *
 * Bit 7 marks the record, bits 0..count-1 are the switches, the others must
 * be zero (otherwise the record is damaged and every switch reads off).
 * Images up to 3.0.1 kept each switch in its own key: those keys are read
 * only while the record is absent (migration), and written after the record
 * on every save, best effort, so that a rollback keeps the settings. They
 * never decide once the record exists.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#define NVS_FLAGS_MAX 7

typedef struct {
    const char *record;                 /* NVS key of the one-byte record */
    const char *const *legacy;          /* per-switch keys of older images, count entries */
    unsigned count;                     /* 1..NVS_FLAGS_MAX */
} nvs_flags_t;

/* Core (pure, host-tested): bits from the record, or from the legacy values
 * (-1 = absent) when there is no record. */
uint8_t nvs_flags_decode(const nvs_flags_t *f, bool have_record, uint8_t record, const int16_t *legacy_values);

/* Firmware (nvs_params): current switches, and an all-or-nothing save. */
uint8_t nvs_flags_load(const nvs_flags_t *f);
esp_err_t nvs_flags_save(const nvs_flags_t *f, uint8_t bits);
