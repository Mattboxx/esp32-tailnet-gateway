/* MQTT state publishing, commands, and Home Assistant discovery. */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool enabled;
    bool home_assistant_discovery;
    char uri[160];
    char username[64];
    char password[96];
    char base_topic[96];
    char discovery_prefix[48];
    uint16_t interval_seconds;
    bool broker_watchdog_enabled;
    uint32_t broker_watchdog_timeout_seconds;
    char broker_watchdog_wol_mac[18];
} mqtt_integration_config_t;

/* Worker-published snapshot, refreshed about once per second. No URI,
 * credentials or topics; a connection is not proof of Home Assistant delivery. */
typedef struct {
    bool configured;            /* enabled with broker URI and base topic */
    bool connected;
    bool connecting;            /* one bounded attempt is in flight */
    bool discovery_pending;     /* Discovery still being paced out */
    uint8_t retry_level;        /* consecutive failures, saturating at 7 */
    uint32_t retry_in_seconds;  /* 0 unless waiting in backoff */
    uint16_t discovery_entities;/* accepted by the client this connection */
} mqtt_integration_status_t;

void mqtt_integration_init(void);
void mqtt_integration_get_config(mqtt_integration_config_t *out);
esp_err_t mqtt_integration_set_config(const mqtt_integration_config_t *config);
bool mqtt_integration_connected(void);
void mqtt_integration_get_status(mqtt_integration_status_t *out);
bool mqtt_integration_watchdog_triggered(void);
uint32_t mqtt_integration_watchdog_wake_count(void);
uint32_t mqtt_integration_broker_silence_seconds(void);
void mqtt_integration_publish_now(void);
void mqtt_integration_wol_changed(void);
void mqtt_integration_tailnet_forward_changed(void);

#ifdef __cplusplus
}
#endif
