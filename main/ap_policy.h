/* One statically reserved worker: no runtime AP stack allocation. */
#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t ap_policy_init(bool (*apply)(bool on));
void ap_policy_request(bool on);
void ap_policy_shutdown(void);
bool ap_policy_is_shutdown(void);
