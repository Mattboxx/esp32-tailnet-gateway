/* One statically reserved worker: no runtime AP stack allocation. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
esp_err_t ap_policy_init(bool (*apply)(bool on));
void ap_policy_request(bool on);
/* Like ap_policy_request(), with an explicit delay. A repeated request for the
 * same pending target never postpones it (retries cannot starve the AP); a
 * request for the other target replaces it at once. */
void ap_policy_request_after(bool on, uint32_t delay_ms);
void ap_policy_shutdown(void);
bool ap_policy_is_shutdown(void);
