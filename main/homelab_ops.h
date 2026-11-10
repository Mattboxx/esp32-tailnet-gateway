/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Bounded operational layer; core routing never depends on this worker. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"
#include "wol.h"
#include "remote_commands.h"
#include "cJSON.h"

typedef struct {
    uint8_t mac[6];
    uint8_t monitor,notify;
    char target[96];
    uint16_t host_port,service_port,timeout_s,interval_s;
    uint8_t max_checks,kind;
    uint8_t reserved[2];
} ops_device_t;
typedef struct {
    uint8_t monitoring,guard,remote_commands,lease_notifications;
    uint32_t minimum_internal,minimum_largest;
    uint16_t socket_reserve,interval_s;
} ops_settings_t;
typedef struct {
    uint32_t internal_free,internal_min,internal_largest,psram_free,psram_min,psram_largest;
    uint32_t worker_stack_min;
    int sockets_used,socket_limit;
    bool worker_running;
} ops_resources_t;
void homelab_ops_init(void);
esp_err_t homelab_ops_start_optional_worker(void);
void homelab_ops_resources(ops_resources_t *out);
bool homelab_ops_admit(void);
/* True while the enabled guard would defer optional work (MQTT, ntfy, checks,
 * recovery); unlike homelab_ops_admit() it counts no denial. For status only. */
bool homelab_ops_guard_deferring(void);
bool homelab_ops_device(int index,ops_device_t *out);
esp_err_t homelab_ops_set_device(int index,const ops_device_t *profile);
void homelab_ops_settings(ops_settings_t *out);
esp_err_t homelab_ops_set_settings(const ops_settings_t *settings);
esp_err_t homelab_ops_request(int index,bool wake,ops_recovery_origin_t origin);
esp_err_t homelab_ops_cancel(void);
/* Coalesced closure event: no names/addresses/credentials; no packet-path I/O. */
void homelab_ops_service_closed(unsigned count);
/* MAC-address selectors prevent a reordered address book retargeting a command. */
esp_err_t homelab_ops_command(const char *selector,bool wake,ops_recovery_origin_t origin);
/* The legacy shared permission is used until the first channel-specific save. */
bool homelab_ops_recovery_allowed(ops_recovery_origin_t origin);
/* Stage inside the integration's settings transaction, publish after commit.
 * choice: -1 keeps the current permission; 0 denies; 1 allows. */
esp_err_t homelab_ops_stage_recovery(ops_recovery_origin_t origin,int choice,uint8_t *staged);
void homelab_ops_publish_recovery(uint8_t staged);
/* Local JSON: detailed contains saved targets; sanitized never includes them. */
cJSON *homelab_ops_snapshot(bool detailed);
cJSON *homelab_ops_capabilities(void);
esp_err_t homelab_ops_register_http(httpd_handle_t server);
