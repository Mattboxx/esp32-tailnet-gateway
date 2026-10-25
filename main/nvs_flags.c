/* Switches in one NVS byte; see nvs_flags.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "nvs_flags.h"
#include "nvs_params.h"

#define RECORD_MARK 0x80u

uint8_t nvs_flags_decode(const nvs_flags_t *f, bool have_record, uint8_t record, const int16_t *legacy_values)
{
    uint8_t all = (uint8_t)((1u << f->count) - 1u);
    if (have_record) {
        /* Damaged (no mark, or unknown switches set): everything off. */
        if (!(record & RECORD_MARK) || (record & ~(RECORD_MARK | all))) return 0;
        return record & all;
    }
    uint8_t bits = 0;
    for (unsigned i = 0; i < f->count; i++)
        if (legacy_values[i] == 1) bits |= (uint8_t)(1u << i);   /* only an explicit 1 is on */
    return bits;
}

uint8_t nvs_flags_load(const nvs_flags_t *f)
{
    uint8_t record = 0, v = 0;
    int16_t legacy[NVS_FLAGS_MAX];
    bool have = nvs_param_get_u8(f->record, &record) == ESP_OK;
    for (unsigned i = 0; !have && i < f->count; i++)
        legacy[i] = nvs_param_get_u8(f->legacy[i], &v) == ESP_OK ? v : -1;
    return nvs_flags_decode(f, have, record, legacy);
}

esp_err_t nvs_flags_save(const nvs_flags_t *f, uint8_t bits)
{
    if (!f->count || f->count > NVS_FLAGS_MAX || bits >> f->count) return ESP_ERR_INVALID_ARG;
    esp_err_t err = nvs_param_set_u8(f->record, (uint8_t)(RECORD_MARK | bits));
    if (err) return err;                                   /* nothing changed */
    for (unsigned i = 0; i < f->count; i++)                /* for a rollback only */
        (void)nvs_param_set_u8(f->legacy[i], (uint8_t)(bits >> i & 1u));
    return ESP_OK;
}
