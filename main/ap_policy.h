/* Coalesced, retryable AP transitions; no persistent 8KB worker stack. */
#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t ap_policy_init(bool (*apply)(bool on));
void ap_policy_request(bool on);
void ap_policy_shutdown(void);
bool ap_policy_is_shutdown(void);
