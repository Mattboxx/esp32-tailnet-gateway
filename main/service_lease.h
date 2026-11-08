/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
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
/* The current rule table (after load and after every save). Expiry of a lease
 * whose rule no longer exists is still applied but not announced. */
void service_lease_rules_changed(const tailnet_forward_rule_t *rules,int count);
cJSON *service_lease_snapshot(void);
