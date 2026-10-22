/* Bounded operational layer; core routing never depends on this worker. MIT. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"
#include "wol.h"
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
bool homelab_ops_device(int index,ops_device_t *out);
esp_err_t homelab_ops_set_device(int index,const ops_device_t *profile);
void homelab_ops_settings(ops_settings_t *out);
esp_err_t homelab_ops_set_settings(const ops_settings_t *settings);
esp_err_t homelab_ops_request(int index,bool wake,bool remote);
esp_err_t homelab_ops_cancel(void);
/* Coalesced closure event: no names/addresses/credentials; no packet-path I/O. */
void homelab_ops_service_closed(unsigned count);
/* MAC-address selectors prevent a reordered address book retargeting a command. */
esp_err_t homelab_ops_command(const char *selector,bool wake);
/* Local JSON: detailed contains saved targets; sanitized never includes them. */
cJSON *homelab_ops_snapshot(bool detailed);
cJSON *homelab_ops_capabilities(void);
esp_err_t homelab_ops_register_http(httpd_handle_t server);
