/* Non-destructive configuration profiles: presets of the same firmware.
 * A profile only ever enables low-risk optional settings after a preview and
 * an explicit token-bound confirmation; it never disables, deletes or opens
 * network exposure. Exposure changes stay manual steps with their own
 * confirmation. Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"

typedef enum {
    PROFILE_NONE, PROFILE_GATEWAY, PROFILE_RECOVERY, PROFILE_IOT,
    PROFILE_MONITORING, PROFILE_ADVANCED, PROFILE_COUNT
} profile_id_t;

/* Settings a profile may switch ON (never OFF). */
/* Resource Guard is deliberately absent: its uncalibrated thresholds can
 * defer optional services, which a preset must not do silently. */
typedef enum {PK_OPS_MONITORING, PK_LEASE_NOTIFY, PK_HEALTH, PK_COUNT} profile_key_t;

typedef struct {uint8_t value[PK_COUNT];} profile_values_t;

typedef struct {
    profile_id_t profile;
    uint8_t change_mask;   /* keys this apply would switch ON */
    uint8_t proposed_mask; /* keys the profile wants ON (already or newly) */
    uint32_t token;        /* binds confirmation to this exact preview */
} profile_plan_t;

typedef struct {
    bool applied, rolled_back, partial;
    uint8_t changed_mask;  /* keys switched by this operation */
    uint8_t kept_mask;     /* rollback: keys changed by the operator since */
} profile_result_t;

const char *config_profile_name(profile_id_t profile);
bool config_profile_parse(const char *name, profile_id_t *out);
void config_profiles_init(void);
esp_err_t config_profiles_preview(profile_id_t profile, profile_plan_t *out);
/* ESP_ERR_INVALID_STATE: settings changed since preview (token mismatch). */
esp_err_t config_profiles_apply(profile_id_t profile, uint32_t token, profile_result_t *out);
/* ESP_ERR_NOT_FOUND: no applied profile change to roll back. */
esp_err_t config_profiles_rollback(profile_result_t *out);
esp_err_t config_profiles_register_http(httpd_handle_t server);
