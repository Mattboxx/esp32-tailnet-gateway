/* Fail-closed local LAN→Tailnet exposure leases. No AP-side forwarding changes. */
#pragma once
#include "tailnet_forward.h"
#include "cJSON.h"
void service_lease_init(void);
bool service_lease_tick(void);
bool service_lease_allowed(int slot,const tailnet_forward_rule_t *rule);
uint32_t service_lease_token(const tailnet_forward_rule_t *rule);
esp_err_t service_lease_set(int slot,uint32_t expected_rule,uint32_t seconds,bool permanent);
esp_err_t service_lease_set_mode(int slot,uint32_t expected_rule,uint32_t seconds,bool permanent,bool delete_on_expiry);
bool service_lease_delete_requested(const tailnet_forward_rule_t *rule);
cJSON *service_lease_snapshot(void);
