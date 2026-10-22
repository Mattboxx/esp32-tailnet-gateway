/* MQTT status/command bridge with native Home Assistant discovery. */
#include "mqtt_integration.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "runtime_metrics.h"
#include "snmp_agent.h"
#include "control_validation.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_app_desc.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/ip4_addr.h"
#include "mqtt_client.h"
#include "microlink.h"
#include "nvs_params.h"
#include "wifi_power_save.h"
#include "tailscale_config.h"
#include "peer_dns.h"
#include "ota_remote.h"
#include "wol.h"
#include "homelab_ops.h"
#include "service_lease.h"
#include "service_evidence.h"
#include "config_profiles.h"
#include "service_retry.h"
#include "discovery_budget.h"
#include "health_monitor.h"
#include "fourvia6.h"
#include "tailnet_forward.h"

static const char *TAG = "mqtt_bridge";
static mqtt_integration_config_t s_config;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_manager_task;
static esp_mqtt_client_handle_t s_client;
static volatile bool s_connected;
static volatile bool s_publish_requested;
static volatile bool s_discovery_requested;
static volatile bool s_watchdog_triggered;
static volatile uint32_t s_watchdog_wake_count;
static int64_t s_last_broker_ok_us;
static portMUX_TYPE s_broker_clock_mux = portMUX_INITIALIZER_UNLOCKED;
static uint32_t s_connection_events;
#define BROKER_CONNECTED 1u
#define BROKER_DISCONNECTED 2u
static volatile bool s_restart_requested;
static volatile bool s_wifi_reconnect_requested;
static char s_device_id[24];
static char s_availability_topic[128];
static char s_state_topic[128];
static discovery_budget_t s_discovery;
static mqtt_integration_status_t s_status;
static portMUX_TYPE s_status_mux = portMUX_INITIALIZER_UNLOCKED;

static void broker_clock_set(bool connected, bool reset)
{
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&s_broker_clock_mux);
    /* Failed reconnects must not postpone the outage watchdog forever. */
    if (reset || connected || s_connected) s_last_broker_ok_us = now;
    s_connected = connected;
    portEXIT_CRITICAL(&s_broker_clock_mux);
}

static int64_t broker_silence_us(void)
{
    int64_t now = esp_timer_get_time();
    portENTER_CRITICAL(&s_broker_clock_mux);
    int64_t elapsed = s_connected || !s_last_broker_ok_us ? 0 : now - s_last_broker_ok_us;
    portEXIT_CRITICAL(&s_broker_clock_mux);
    return elapsed > 0 ? elapsed : 0;
}

extern bool wifi_ap_policy_auto_off(void);
extern bool wifi_ap_runtime_enabled(void);
extern void wifi_ap_policy_set_auto_off(bool auto_off);

static void config_defaults(mqtt_integration_config_t *config)
{
    memset(config, 0, sizeof *config);
    config->interval_seconds = 30;
    config->broker_watchdog_timeout_seconds = 300;
    strlcpy(config->discovery_prefix, "homeassistant", sizeof config->discovery_prefix);
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(s_device_id, sizeof s_device_id, "esp32_router_%02x%02x%02x",
             mac[3], mac[4], mac[5]);
    snprintf(config->base_topic, sizeof config->base_topic, "esp32-router/%02x%02x%02x",
             mac[3], mac[4], mac[5]);
}

static void load_string(const char *key, char *destination, size_t size)
{
    char *value = nvs_param_get_str(key);
    if (value) {
        strlcpy(destination, value, size);
        free(value);
    }
}

static void load_config(void)
{
    config_defaults(&s_config);
    uint8_t flag = 0;
    if (nvs_param_get_u8("mqtt_en", &flag) == ESP_OK) s_config.enabled = flag != 0;
    if (nvs_param_get_u8("mqtt_ha", &flag) == ESP_OK) s_config.home_assistant_discovery = flag != 0;
    uint16_t interval = 0;
    if (nvs_param_get_u16("mqtt_int", &interval) == ESP_OK && interval >= 5)
        s_config.interval_seconds = interval;
    load_string("mqtt_uri", s_config.uri, sizeof s_config.uri);
    load_string("mqtt_user", s_config.username, sizeof s_config.username);
    load_string("mqtt_pass", s_config.password, sizeof s_config.password);
    load_string("mqtt_topic", s_config.base_topic, sizeof s_config.base_topic);
    load_string("mqtt_hapfx", s_config.discovery_prefix, sizeof s_config.discovery_prefix);
    load_string("mqtt_wmac", s_config.broker_watchdog_wol_mac,
                sizeof s_config.broker_watchdog_wol_mac);
    if (nvs_param_get_u8("mqtt_wdog", &flag) == ESP_OK)
        s_config.broker_watchdog_enabled = flag != 0;
    uint32_t watchdog_timeout = 0;
    if (nvs_param_get_u32("mqtt_wdto", &watchdog_timeout) == ESP_OK
        && watchdog_timeout >= 30 && watchdog_timeout <= 86400)
        s_config.broker_watchdog_timeout_seconds = watchdog_timeout;
}

static int publish(const char *topic, const char *payload, int retain)
{
    if (!s_client || !s_connected) return -1;
    return esp_mqtt_client_publish(s_client, topic, payload ? payload : "", 0, 1, retain);
}

static bool add_device(cJSON *root)
{
    cJSON *device = cJSON_AddObjectToObject(root, "device");
    cJSON *ids = cJSON_AddArrayToObject(device, "identifiers");
    if(!device||!ids)return false;
    cJSON *id=cJSON_CreateString(s_device_id);if(!id)return false;
    if(!cJSON_AddItemToArray(ids,id)){cJSON_Delete(id);return false;}
    return cJSON_AddStringToObject(device,"name","ESP32 Homelab Gateway — Mattboxx Edition")
        &&cJSON_AddStringToObject(device,"manufacturer","Espressif / Mattboxx Edition")
        &&cJSON_AddStringToObject(device,"model","ESP32-S3 Homelab Gateway");
}

static void discovery_publish_entity(const char *domain, const char *object_id,
                                     const char *name, const char *state_topic,
                                     const char *value_template,
                                     const char *command_topic,
                                     const char *device_class, const char *unit)
{
    if(!discovery_visit(&s_discovery))return;
    mqtt_integration_config_t cfg;
    mqtt_integration_get_config(&cfg);
    char topic[256];
    snprintf(topic, sizeof topic, "%s/%s/%s/%s/config", cfg.discovery_prefix,
             domain, s_device_id, object_id);
    cJSON *root = cJSON_CreateObject();
    if (!root) {discovery_result(&s_discovery,false);return;}
    char unique_id[96];
    snprintf(unique_id, sizeof unique_id, "%s_%s", s_device_id, object_id);
    bool complete=cJSON_AddStringToObject(root,"name",name)&&cJSON_AddStringToObject(root,"unique_id",unique_id);
    if (state_topic) complete=complete&&cJSON_AddStringToObject(root, "state_topic", state_topic);
    if (value_template) complete=complete&&cJSON_AddStringToObject(root, "value_template", value_template);
    if (command_topic) complete=complete&&cJSON_AddStringToObject(root, "command_topic", command_topic);
    if (device_class) complete=complete&&cJSON_AddStringToObject(root, "device_class", device_class);
    if (unit) complete=complete&&cJSON_AddStringToObject(root, "unit_of_measurement", unit);
    if (strcmp(domain, "sensor") == 0 || strcmp(domain, "binary_sensor") == 0)
        complete=complete&&cJSON_AddStringToObject(root, "entity_category", "diagnostic");
    complete=complete&&cJSON_AddStringToObject(root,"availability_topic",s_availability_topic)
        &&cJSON_AddStringToObject(root,"payload_available","online")
        &&cJSON_AddStringToObject(root,"payload_not_available","offline")&&add_device(root);
    char *json = complete?cJSON_PrintUnformatted(root):NULL;
    cJSON_Delete(root);
    if (json) {
        discovery_result(&s_discovery,publish(topic, json, 1)>=0);
        cJSON_free(json);
    }else discovery_result(&s_discovery,false);
}

static void normalized_mac(const uint8_t mac[6], char out[13])
{
    snprintf(out, 13, "%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static void publish_discovery(void)
{
    mqtt_integration_config_t cfg;
    char command[160];
    mqtt_integration_get_config(&cfg);
    if (!cfg.home_assistant_discovery || !cfg.discovery_prefix[0]) return;
    discovery_publish_entity("sensor","recovery_state","Recovery state",s_state_topic,
        "{{ value_json.operations.recovery_state }}",NULL,NULL,NULL);
    snprintf(command,sizeof command,"%s/command/health_monitor_enabled",cfg.base_topic);
    discovery_publish_entity("switch","health_monitor_enabled","Configured connectivity checks",s_state_topic,
        "{{ value_json.operations.health.enabled }}",command,NULL,NULL);
    snprintf(command,sizeof command,"%s/command/service_watch_enabled",cfg.base_topic);
    discovery_publish_entity("switch","service_watch","Service watch (periodic destination tests)",s_state_topic,
        "{{ value_json.service_watch }}",command,NULL,NULL);
    discovery_publish_entity("sensor","configuration_profile","Configuration profile",s_state_topic,
        "{{ value_json.profile }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","sockets_used","Sockets in use",s_state_topic,
        "{{ value_json.operations.sockets_used }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","gateway_health","Configured gateway TCP check",s_state_topic,
        "{{ value_json.operations.health.checks[0].state }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","dns_health","Configured DNS lookup",s_state_topic,
        "{{ value_json.operations.health.checks[1].state }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","internet_health","Configured Internet TCP check",s_state_topic,
        "{{ value_json.operations.health.checks[2].state }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","tailnet_service_health","Configured Tailnet service check",s_state_topic,
        "{{ value_json.operations.health.checks[3].state }}",NULL,NULL,NULL);
    discovery_publish_entity("sensor","internal_largest","Largest internal block",s_state_topic,
        "{{ value_json.operations.internal_largest }}",NULL,NULL,"B");

    discovery_publish_entity("sensor", "cpu_load", "CPU load", s_state_topic,
                             "{{ value_json.cpu_load_pct }}", NULL, NULL, "%");
    discovery_publish_entity("binary_sensor", "snmp_enabled", "SNMP enabled", s_state_topic,
                             "{{ value_json.snmp_enabled }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "snmp_running", "SNMP running", s_state_topic,
                             "{{ value_json.snmp_running }}", NULL, "connectivity", NULL);
    discovery_publish_entity("sensor", "socket_limit", "Socket limit", s_state_topic,
                             "{{ value_json.socket_limit }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "cpu_core0", "CPU core 0 load", s_state_topic,
                             "{{ value_json.cpu_core0_pct }}", NULL, NULL, "%");
    discovery_publish_entity("sensor", "cpu_core1", "CPU core 1 load", s_state_topic,
                             "{{ value_json.cpu_core1_pct }}", NULL, NULL, "%");
    discovery_publish_entity("binary_sensor", "uplink", "Uplink", s_state_topic,
                             "{{ value_json.uplink_connected }}", NULL,
                             "connectivity", NULL);
    discovery_publish_entity("sensor", "uplink_ip", "Uplink IP", s_state_topic,
                             "{{ value_json.uplink_ip }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "wifi_rssi", "WiFi signal", s_state_topic,
                             "{{ value_json.rssi }}", NULL, "signal_strength", "dBm");
    discovery_publish_entity("sensor", "wifi_ssid", "WiFi SSID", s_state_topic,
                             "{{ value_json.ssid }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "tailscale", "Tailscale", s_state_topic,
                             "{{ value_json.tailscale_connected }}", NULL,
                             "connectivity", NULL);
    discovery_publish_entity("sensor", "tailscale_ip", "Tailscale IP", s_state_topic,
                             "{{ value_json.tailscale_ip }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "free_heap", "Free heap", s_state_topic,
                             "{{ value_json.free_heap }}", NULL, NULL, "B");
    discovery_publish_entity("sensor", "minimum_free_heap", "Minimum free heap",
                             s_state_topic, "{{ value_json.minimum_free_heap }}",
                             NULL, NULL, "B");
    discovery_publish_entity("sensor", "uptime", "Uptime", s_state_topic,
                             "{{ value_json.uptime_seconds }}", NULL, "duration", "s");
    discovery_publish_entity("sensor", "firmware", "Firmware", s_state_topic,
                             "{{ value_json.firmware }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "update_checks", "Automatic update checks", s_state_topic,
                             "{{ value_json.update_checks }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "update_auto", "Automatic firmware install", s_state_topic,
                             "{{ value_json.update_auto }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "update_beta", "Beta update channel", s_state_topic,
                             "{{ value_json.update_beta }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "update_available", "Firmware update available", s_state_topic,
                             "{{ value_json.update_available }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "update_version", "Available firmware version", s_state_topic,
                             "{{ value_json.update_version }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "update_status", "Firmware update status", s_state_topic,
                             "{{ value_json.update_status }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "update_progress", "Firmware update progress", s_state_topic,
                             "{{ value_json.update_progress }}", NULL, NULL, "%");
    discovery_publish_entity("sensor", "reset_reason", "Reset reason code", s_state_topic,
                             "{{ value_json.reset_reason }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "access_point", "Access point", s_state_topic,
                             "{{ value_json.ap_enabled }}", NULL, "connectivity", NULL);
    discovery_publish_entity("sensor", "ap_clients", "AP clients", s_state_topic,
                             "{{ value_json.ap_clients }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "mqtt_watchdog_wakes", "MQTT watchdog wakes",
                             s_state_topic, "{{ value_json.mqtt_watchdog_wake_count }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("sensor", "service_closures", "Temporary service access closures",
                             s_state_topic, "{{ value_json.operations.service_closures }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "mqtt_watchdog_triggered",
                             "MQTT watchdog triggered", s_state_topic,
                             "{{ value_json.mqtt_watchdog_triggered }}", NULL,
                             "problem", NULL);
    discovery_publish_entity("sensor", "broker_silence", "MQTT broker silence",
                             s_state_topic, "{{ value_json.broker_silence_seconds }}",
                             NULL, "duration", "s");
    discovery_publish_entity("sensor", "tailscale_peers", "Tailscale peers",
                             s_state_topic, "{{ value_json.tailscale_peer_count }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailscale_peers_online",
                             "Tailscale peers online", s_state_topic,
                             "{{ value_json.tailscale_online_peer_count }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("sensor", "advertised_routes", "Advertised routes",
                             s_state_topic, "{{ value_json.advertised_routes }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "fourvia6", "4via6 routing",
                             s_state_topic, "{{ value_json.fourvia6_enabled }}",
                             NULL, "connectivity", NULL);
    discovery_publish_entity("sensor", "fourvia6_prefix", "4via6 prefix",
                             s_state_topic, "{{ value_json.fourvia6_prefix }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("sensor", "fourvia6_flows", "4via6 active flows",
                             s_state_topic, "{{ value_json.fourvia6_active_flows }}",
                             NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailnet_forward_configured", "LAN to Tailnet rules",
                             s_state_topic, "{{ value_json.tailnet_forward_configured }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailnet_forward_enabled", "LAN to Tailnet rules enabled",
                             s_state_topic, "{{ value_json.tailnet_forward_enabled }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailnet_forward_installed", "LAN to Tailnet rules active",
                             s_state_topic, "{{ value_json.tailnet_forward_installed }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailnet_forward_accepted", "LAN to Tailnet accepted packets",
                             s_state_topic, "{{ value_json.tailnet_forward_accepted_packets }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "tailnet_forward_blocked", "LAN to Tailnet blocked packets",
                             s_state_topic, "{{ value_json.tailnet_forward_blocked_packets }}", NULL, NULL, NULL);

    snprintf(command, sizeof command, "%s/command/ap_always_on", cfg.base_topic);
    discovery_publish_entity("switch", "ap_always_on", "Access point always on",
                             s_state_topic, "{{ value_json.ap_always_on }}", command,
                             NULL, NULL);
    snprintf(command, sizeof command, "%s/command/tailscale_enabled", cfg.base_topic);
    discovery_publish_entity("switch", "tailscale_enabled", "Tailscale enabled",
                             s_state_topic, "{{ value_json.tailscale_enabled }}", command,
                             NULL, NULL);
    snprintf(command, sizeof command, "%s/command/accept_routes", cfg.base_topic);
    discovery_publish_entity("switch", "accept_routes", "Accept peer subnet routes",
                             s_state_topic, "{{ value_json.accept_routes }}", command,
                             NULL, NULL);
    snprintf(command, sizeof command, "%s/command/snat_subnet_routes", cfg.base_topic);
    discovery_publish_entity("switch", "snat_subnet_routes",
                             "Source-NAT advertised routes", s_state_topic,
                             "{{ value_json.snat_subnet_routes }}", command, NULL, NULL);
    snprintf(command, sizeof command, "%s/command/advertise_ap", cfg.base_topic);
    discovery_publish_entity("switch", "advertise_ap",
                             "Advertise AP subnet (restart)", s_state_topic,
                             "{{ value_json.advertise_ap }}", command, NULL, NULL);
    snprintf(command, sizeof command, "%s/command/advertise_exit_node", cfg.base_topic);
    discovery_publish_entity("switch", "advertise_exit_node",
                             "Advertise as exit node", s_state_topic,
                             "{{ value_json.advertise_exit_node }}", command, NULL, NULL);
    discovery_publish_entity("binary_sensor", "exit_server_active", "Exit-node server active",
                             s_state_topic, "{{ value_json.exit_server_active }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "exit_server_configured", "Exit-node server configured",
                             s_state_topic, "{{ value_json.exit_server_configured }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "manual_exit_advertisement", "Manual exit-node route",
                             s_state_topic, "{{ value_json.manual_exit_advertisement }}", NULL, NULL, NULL);
    snprintf(command, sizeof command, "%s/command/wifi_power_save", cfg.base_topic);
    discovery_publish_entity("switch", "wifi_power_save", "WiFi power save",
                             s_state_topic, "{{ value_json.wifi_power_save }}", command, NULL, NULL);
    discovery_publish_entity("sensor", "wifi_power_save_runtime", "WiFi power-save runtime",
                             s_state_topic, "{{ value_json.wifi_power_save_runtime }}", NULL, NULL, NULL);
    discovery_publish_entity("binary_sensor", "exit_dns_running", "Exit-node DNS running",
                             s_state_topic, "{{ value_json.exit_dns_running }}", NULL, NULL, NULL);
    discovery_publish_entity("sensor", "exit_dns_port", "Exit-node DNS port",
                             s_state_topic, "{{ value_json.exit_dns_port }}", NULL, NULL, NULL);
    snprintf(command, sizeof command, "%s/command/exit_node_lan_bypass", cfg.base_topic);
    discovery_publish_entity("switch", "exit_node_lan_bypass",
                             "Exit node allow LAN access", s_state_topic,
                             "{{ value_json.exit_node_lan_bypass }}", command, NULL, NULL);
    snprintf(command, sizeof command, "%s/command/fourvia6_enabled", cfg.base_topic);
    discovery_publish_entity("switch", "fourvia6_enabled", "4via6 routing enabled",
                             s_state_topic, "{{ value_json.fourvia6_enabled }}", command,
                             NULL, NULL);
    snprintf(command, sizeof command, "%s/command/restart", cfg.base_topic);
    discovery_publish_entity("button", "restart", "Restart", NULL, NULL, command,
                             "restart", NULL);
    snprintf(command, sizeof command, "%s/command/reconnect_wifi", cfg.base_topic);
    discovery_publish_entity("button", "reconnect_wifi", "Reconnect WiFi",
                             NULL, NULL, command, "restart", NULL);
    snprintf(command, sizeof command, "%s/command/reconnect_tailscale", cfg.base_topic);
    discovery_publish_entity("button", "reconnect_tailscale", "Reconnect Tailscale (device restart)",
                             NULL, NULL, command, "restart", NULL);
    snprintf(command, sizeof command, "%s/command/status", cfg.base_topic);
    discovery_publish_entity("button", "publish_status", "Publish status now",
                             NULL, NULL, command, NULL, NULL);

    int tf_count = tailnet_forward_count();
    for (int i = 0; i < tf_count; i++) {
        tailnet_forward_rule_t rule;
        if (!tailnet_forward_get(i, &rule, NULL)) continue;
        char object_id[48], state_template[96], label[80];
        snprintf(object_id, sizeof object_id, "tailnet_forward_%d", i + 1);
        snprintf(command, sizeof command, "%s/command/tailnet_forward/%d/%08lx", cfg.base_topic, i,(unsigned long)service_lease_token(&rule));
        snprintf(state_template, sizeof state_template, "{{ value_json.tailnet_forward_rules[%d].enabled }}", i);
        snprintf(label, sizeof label, "LAN to Tailnet: %.60s", rule.name[0] ? rule.name : rule.destination);
        discovery_publish_entity("switch", object_id, label, s_state_topic, state_template, command, NULL, NULL);
        snprintf(object_id,sizeof object_id,"tailnet_expiry_%d",i+1);
        snprintf(state_template,sizeof state_template,"{{ value_json.forwarding_leases[%d].remaining_s }}",i);
        discovery_publish_entity("sensor",object_id,"Tailnet rule time remaining",s_state_topic,state_template,NULL,NULL,"s");
        snprintf(object_id,sizeof object_id,"tailnet_status_%d",i+1);
        snprintf(state_template,sizeof state_template,"{{ value_json.tailnet_forward_rules[%d].status }}",i);
        discovery_publish_entity("sensor",object_id,"Tailnet rule status",s_state_topic,state_template,NULL,NULL,NULL);
    }
    /* Retained discovery records survive rule deletion and reboot. Clear every
     * unused slot so Home Assistant does not keep orphaned rule switches. */
    for (int i = tf_count; i < TAILNET_FORWARD_MAX; i++) {
        char object_id[48], topic[256];
        snprintf(object_id, sizeof object_id, "tailnet_forward_%d", i + 1);
        snprintf(topic, sizeof topic, "%s/switch/%s/%s/config",
                 cfg.discovery_prefix, s_device_id, object_id);
        if(discovery_visit(&s_discovery))discovery_result(&s_discovery,publish(topic,"",1)>=0);
        snprintf(topic,sizeof topic,"%s/sensor/%s/tailnet_expiry_%d/config",cfg.discovery_prefix,s_device_id,i+1);
        if(discovery_visit(&s_discovery))discovery_result(&s_discovery,publish(topic,"",1)>=0);
        snprintf(topic,sizeof topic,"%s/sensor/%s/tailnet_status_%d/config",cfg.discovery_prefix,s_device_id,i+1);
        if(discovery_visit(&s_discovery))discovery_result(&s_discovery,publish(topic,"",1)>=0);
    }

    int count = wol_count();
    for (int i = 0; i < count; i++) {
        wol_device_t device;
        if (!wol_get(i, &device)) continue;
        char mac[13];
        normalized_mac(device.mac, mac);
        char object_id[32];
        snprintf(object_id, sizeof object_id, "wol_%s", mac);
        snprintf(command, sizeof command, "%s/command/wol/%s", cfg.base_topic, mac);
        char name[64];
        snprintf(name, sizeof name, "Wake %s", device.name[0] ? device.name : mac);
        discovery_publish_entity("button", object_id, name, NULL, NULL, command,
                                 NULL, NULL);
        snprintf(object_id,sizeof object_id,"recovery_%s",mac);
        snprintf(command,sizeof command,"%s/command/recovery/%s",cfg.base_topic,mac);
        snprintf(name,sizeof name,"Recover %.40s",device.name[0]?device.name:mac);
        discovery_publish_entity("button",object_id,name,NULL,NULL,command,NULL,NULL);
    }
    if(discovery_finished(&s_discovery))ESP_LOGI(TAG, "Home Assistant discovery accepted locally (%d WOL button(s)); broker delivery unverified", count);
}

/* QoS1 retained state shares the client's 8 KiB outbox with Discovery and
 * acknowledgements; keep one state message well below it. */
#define MQTT_STATE_BUDGET 6144u

/* Compact mode keeps only the fields Home Assistant templates read plus the
 * evidence, never names, destinations or ports. */
static bool add_tailnet_rules(cJSON *root, bool compact)
{
    cJSON *tf_rules = cJSON_AddArrayToObject(root, "tailnet_forward_rules");
    if (!tf_rules) return false;
    for (int i = 0; i < tailnet_forward_count(); i++) {
        tailnet_forward_rule_t rule; tailnet_forward_runtime_t rt;
        if (!tailnet_forward_get(i, &rule, &rt)) continue;
        cJSON *j = cJSON_CreateObject();
        if (!j || !cJSON_AddItemToArray(tf_rules, j)) {cJSON_Delete(j); return false;}
        /* Same evidence as the Web API; uplink/control are published separately. */
        service_evidence_t ev;
        service_evidence_collect(i, service_lease_token(&rule), &rule, &rt, true, true, &ev);
        bool ok = cJSON_AddStringToObject(j, "enabled", rule.enabled ? "ON" : "OFF")
            && cJSON_AddStringToObject(j, "installed", rt.installed ? "ON" : "OFF")
            && cJSON_AddStringToObject(j, "status", ev.diag.code)
            && cJSON_AddStringToObject(j, "destination_check", service_check_state_name(ev.checked ? ev.check.state : SC_NONE))
            && (ev.replied ? cJSON_AddNumberToObject(j, "service_reply_age_s", ev.reply_ms / 1000) != NULL
                           : cJSON_AddNullToObject(j, "service_reply_age_s") != NULL);
        if (ok && !compact)
            ok = cJSON_AddStringToObject(j, "name", rule.name)
                && cJSON_AddStringToObject(j, "protocol", rule.proto == 17 ? "udp" : "tcp")
                && cJSON_AddNumberToObject(j, "listen_port", rule.listen_port)
                && cJSON_AddStringToObject(j, "destination", rule.destination)
                && cJSON_AddNumberToObject(j, "destination_port", rule.destination_port);
        if (!ok) return false;
    }
    return true;
}

/* Print the state; if it exceeds the budget, drop detail that the Web API
 * still serves (device list, events, duplicate leases, then rule labels) and
 * mark the level. Returns NULL only on allocation failure. */
static char *state_print_fitted(cJSON *root, size_t budget, unsigned *level)
{
    *level = 0;
    char *json = cJSON_PrintUnformatted(root);
    for (unsigned step = 1; json && strlen(json) > budget && step <= 2; step++) {
        free(json);
        json = NULL;
        *level = step;
        if (step == 1) {
            cJSON *ops = cJSON_GetObjectItemCaseSensitive(root, "operations");
            cJSON_DeleteItemFromObjectCaseSensitive(ops, "devices");
            cJSON_DeleteItemFromObjectCaseSensitive(ops, "events");
            cJSON_DeleteItemFromObjectCaseSensitive(ops, "forwarding_leases");
        } else {
            cJSON_DeleteItemFromObjectCaseSensitive(root, "tailnet_forward_rules");
            if (!add_tailnet_rules(root, true)) return NULL;
        }
        cJSON_DeleteItemFromObjectCaseSensitive(root, "state_compact_level");
        if (!cJSON_AddNumberToObject(root, "state_compact_level", step)) return NULL;
        json = cJSON_PrintUnformatted(root);
    }
    return json;
}

static void publish_state(void)
{
    if (!s_connected) return;
    cJSON *root = cJSON_CreateObject();
    if (!root) return;

    bool uplink = false;
    char uplink_ip[16] = "";
    char ssid[33] = "";
    int rssi = 0;
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {0};
    if (sta && esp_netif_get_ip_info(sta, &ip) == ESP_OK && ip.ip.addr) {
        uplink = true;
        snprintf(uplink_ip, sizeof uplink_ip, IPSTR, IP2STR(&ip.ip));
        wifi_ap_record_t record;
        if (esp_wifi_sta_get_ap_info(&record) == ESP_OK) {
            strlcpy(ssid, (const char *)record.ssid, sizeof ssid);
            rssi = record.rssi;
        }
    }
    bool ts_connected = tailscale_is_connected();
    char ts_ip[16] = "";
    if (tailscale_tunnel_ip) {
        ip4_addr_t address = { .addr = tailscale_tunnel_ip };
        snprintf(ts_ip, sizeof ts_ip, IPSTR, IP2STR(&address));
    }
    int peer_count = 0;
    int online_peer_count = 0;
    microlink_t *ml = tailscale_get_microlink();
    if (ml) {
        peer_count = microlink_get_peer_count(ml);
        for (int i = 0; i < peer_count; i++) {
            microlink_peer_info_t peer = {0};
            if (microlink_get_peer_info(ml, i, &peer) == ESP_OK && peer.online)
                online_peer_count++;
        }
    }
    wifi_sta_list_t clients = {0};
    int client_count = 0;
    if (wifi_ap_runtime_enabled() && esp_wifi_ap_get_sta_list(&clients) == ESP_OK)
        client_count = clients.num;

    cJSON_AddStringToObject(root, "uplink_connected", uplink ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "uplink_ip", uplink_ip);
    cJSON_AddStringToObject(root, "ssid", ssid);
    cJSON_AddNumberToObject(root, "rssi", rssi);
    cJSON_AddStringToObject(root, "tailscale_connected", ts_connected ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "tailscale_enabled", tailscale_enabled ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "tailscale_ip", ts_ip);
    cJSON_AddNumberToObject(root, "tailscale_peer_count", peer_count);
    cJSON_AddNumberToObject(root, "tailscale_online_peer_count", online_peer_count);
    cJSON_AddStringToObject(root, "advertised_routes",
                            tailscale_active_routes());
    cJSON_AddStringToObject(root, "advertise_ap", tailscale_advertise_ap ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "reported_client_version", tailscale_ipn_version ? tailscale_ipn_version : "");
    cJSON_AddStringToObject(root, "accept_routes",
                            tailscale_accept_routes ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "snat_subnet_routes",
                            tailscale_snat_subnet_routes ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "advertise_exit_node",
                            tailscale_advertise_exit_node ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "exit_server_active", tailscale_exit_server_active() ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "exit_server_configured", tailscale_exit_server_configured() ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "manual_exit_advertisement", tailscale_manual_exit_configured() ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "wifi_power_save", wifi_power_save_configured() ? "ON" : "OFF");
    bool wifi_ps_active = false;
    bool wifi_ps_known = wifi_power_save_runtime(&wifi_ps_active);
    cJSON_AddStringToObject(root, "wifi_power_save_runtime", wifi_ps_known ?
                           (wifi_ps_active ? "ON" : "OFF") : "Unknown");
    cJSON_AddStringToObject(root, "exit_dns_running", peer_dns_is_running() ? "ON" : "OFF");
    cJSON_AddNumberToObject(root, "exit_dns_port", tailscale_peerapi_port());
    cJSON_AddStringToObject(root, "exit_node_lan_bypass",
                            tailscale_lan_bypass ? "ON" : "OFF");
    fourvia6_status_t v6;
    fourvia6_get_status(&v6);
    cJSON_AddStringToObject(root, "fourvia6_enabled", v6.enabled ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "fourvia6_lan_cidr", v6.lan_cidr);
    cJSON_AddNumberToObject(root, "fourvia6_site_id", v6.site_id);
    cJSON_AddStringToObject(root, "fourvia6_prefix", v6.advertised_prefix);
    cJSON_AddNumberToObject(root, "fourvia6_active_flows", v6.active_flows);
    cJSON_AddNumberToObject(root, "fourvia6_translated_packets", v6.translated_packets);
    cJSON_AddNumberToObject(root, "fourvia6_dropped_packets", v6.dropped_packets);
    cJSON_AddStringToObject(root, "ap_enabled", wifi_ap_runtime_enabled() ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "ap_always_on", wifi_ap_policy_auto_off() ? "OFF" : "ON");
    cJSON_AddNumberToObject(root, "ap_clients", client_count);
    cJSON_AddNumberToObject(root, "uptime_seconds", esp_timer_get_time() / 1000000ULL);
    cJSON_AddNumberToObject(root, "free_heap", esp_get_free_heap_size());
    runtime_metrics_t cpu = runtime_metrics_get();
    if (cpu.valid) {
        cJSON_AddNumberToObject(root, "cpu_load_pct", cpu.load_pct);
        cJSON_AddNumberToObject(root, "cpu_core0_pct", cpu.core_pct[0]);
        cJSON_AddNumberToObject(root, "cpu_core1_pct", cpu.core_pct[1]);
    } else {
        cJSON_AddNullToObject(root, "cpu_load_pct");
        cJSON_AddNullToObject(root, "cpu_core0_pct");
        cJSON_AddNullToObject(root, "cpu_core1_pct");
    }
    cJSON_AddNumberToObject(root, "minimum_free_heap", esp_get_minimum_free_heap_size());
    cJSON_AddStringToObject(root, "snmp_enabled", snmp_agent_is_enabled() ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "snmp_running", snmp_agent_is_running() ? "ON" : "OFF");
    cJSON_AddNumberToObject(root, "socket_limit", CONFIG_LWIP_MAX_SOCKETS);
    const esp_app_desc_t *app = esp_app_get_description();
    cJSON_AddStringToObject(root, "firmware", app ? app->version : "");
    ota_remote_state_t update; ota_remote_get_state(&update);
    cJSON_AddStringToObject(root, "update_checks", update.config.enabled ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "update_auto", update.config.auto_install ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "update_beta", update.config.beta_channel ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "update_available", update.update_available ? "ON" : "OFF");
    cJSON_AddStringToObject(root, "update_version", update.latest_version);
    cJSON_AddStringToObject(root, "update_status", update.status);
    cJSON_AddNumberToObject(root, "update_progress", update.progress);
    cJSON_AddNumberToObject(root, "reset_reason", esp_reset_reason());
    cJSON_AddStringToObject(root, "mqtt_watchdog_triggered",
                            s_watchdog_triggered ? "ON" : "OFF");
    cJSON_AddNumberToObject(root, "mqtt_watchdog_wake_count", s_watchdog_wake_count);
    service_watch_config_t watch; service_watch_get(&watch);
    cJSON_AddStringToObject(root, "service_watch", watch.enabled ? "ON" : "OFF");
    profile_id_t profile; bool profile_rollback; config_profiles_status(&profile, &profile_rollback);
    cJSON_AddStringToObject(root, "profile", config_profile_name(profile));
    cJSON_AddNumberToObject(root, "broker_silence_seconds",
                            mqtt_integration_broker_silence_seconds());
    uint32_t tf_enabled=0,tf_installed=0,tf_accepted=0,tf_blocked=0;
    tailnet_forward_totals(&tf_enabled,&tf_installed,&tf_accepted,&tf_blocked);
    cJSON_AddNumberToObject(root,"tailnet_forward_configured",tailnet_forward_count());
    cJSON_AddNumberToObject(root,"tailnet_forward_enabled",tf_enabled);
    cJSON_AddNumberToObject(root,"tailnet_forward_installed",tf_installed);
    cJSON_AddNumberToObject(root,"tailnet_forward_accepted_packets",tf_accepted);
    cJSON_AddNumberToObject(root,"tailnet_forward_blocked_packets",tf_blocked);
    (void)add_tailnet_rules(root,false);

    cJSON *operations=homelab_ops_snapshot(false);
    if(operations && !cJSON_AddItemToObject(root,"operations",operations))cJSON_Delete(operations);
    cJSON *leases=service_lease_snapshot();
    if(leases && !cJSON_AddItemToObject(root,"forwarding_leases",leases))cJSON_Delete(leases);
    unsigned level = 0;
    char *json = state_print_fitted(root, MQTT_STATE_BUDGET, &level);
    cJSON_Delete(root);
    if (json) {
        if (strlen(json) > MQTT_STATE_BUDGET)
            ESP_LOGW(TAG, "state %u bytes exceeds the %u-byte budget after compaction",
                     (unsigned)strlen(json), (unsigned)MQTT_STATE_BUDGET);
        publish(s_state_topic, json, 1);
        free(json);
    }
}

static void schedule_restart(void)
{
    /* Only the manager restarts; commands cannot allocate unlimited tasks.
     * Do not destroy microlink while routing/UI/ntfy still hold its handle. */
    s_restart_requested = true;
}

static bool set_tailscale_flag(const char *nvs_key, int32_t *runtime, bool enabled)
{
    if ((*runtime != 0) == enabled) return false;
    esp_err_t err = nvs_param_set_int(nvs_key, enabled ? 1 : 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Cannot save MQTT setting: %s", esp_err_to_name(err));
        return false;
    }
    *runtime = enabled ? 1 : 0;
    s_publish_requested = true;
    return true;
}

static void handle_command(const char *topic, const char *payload)
{
    mqtt_integration_config_t cfg;
    mqtt_integration_get_config(&cfg);
    char prefix[128];
    snprintf(prefix, sizeof prefix, "%s/command/", cfg.base_topic);
    if (strncmp(topic, prefix, strlen(prefix)) != 0) return;
    const char *command = topic + strlen(prefix);
    bool enabled = false;
    bool is_switch = !strcmp(command, "ap_always_on")
        || !strcmp(command, "wifi_power_save")
        || !strcmp(command, "health_monitor_enabled")
        || !strcmp(command, "service_watch_enabled")
        || !strcmp(command, "tailscale_enabled") || !strcmp(command, "accept_routes")
        || !strcmp(command, "snat_subnet_routes") || !strcmp(command, "advertise_exit_node")
        || !strcmp(command, "advertise_ap")
        || !strcmp(command, "exit_node_lan_bypass") || !strcmp(command, "fourvia6_enabled")
        || !strncmp(command, "tailnet_forward/", 16);
    if (is_switch && !control_parse_bool(payload, &enabled)) {
        ESP_LOGW(TAG, "Rejected invalid MQTT switch payload");
        s_publish_requested = true;
        return;
    }
    if (!strcmp(command, "status")) {
        s_publish_requested = true;
    } else if (!strncmp(command,"recovery/",9)) {
        const char *compact=command+9;char mac[18];
        if(strlen(compact)==12 && (!strcmp(payload,"PRESS") || !strcmp(payload,"1"))){
            snprintf(mac,sizeof mac,"%.2s:%.2s:%.2s:%.2s:%.2s:%.2s",compact,compact+2,compact+4,compact+6,compact+8,compact+10);
            (void)homelab_ops_command(mac,true);
        }
        s_publish_requested=true;
    } else if (!strcmp(command, "restart")) {
        schedule_restart();
    } else if (!strcmp(command, "ap_always_on")) {
        if (enabled == !wifi_ap_policy_auto_off()) return;
        if (nvs_param_set_u8("ap_auto_off", enabled ? 0 : 1) == ESP_OK) {
            wifi_ap_policy_set_auto_off(!enabled);
            s_publish_requested = true;
        }
    } else if (!strcmp(command, "wifi_power_save")) {
        esp_err_t err = wifi_power_save_set(enabled);
        if (err != ESP_OK) ESP_LOGW(TAG, "WiFi power-save change failed: %s", esp_err_to_name(err));
        s_publish_requested = true;
    } else if (!strcmp(command, "tailscale_enabled")) {
        if (set_tailscale_flag("ts_enabled", &tailscale_enabled, enabled))
            schedule_restart();
    } else if (!strcmp(command, "accept_routes")) {
        set_tailscale_flag("ts_acpt_rt", &tailscale_accept_routes, enabled);
    } else if (!strcmp(command, "snat_subnet_routes")) {
        set_tailscale_flag("ts_snat_sr", &tailscale_snat_subnet_routes, enabled);
    } else if (!strcmp(command, "advertise_ap")) {
        if (set_tailscale_flag("ts_adv_ap", &tailscale_advertise_ap, enabled))
            schedule_restart();
    } else if (!strcmp(command, "advertise_exit_node")) {
        if (enabled && tailscale_exit_node_ip != 0) {
            ESP_LOGW(TAG, "Cannot advertise as exit node while another exit node is selected");
            s_publish_requested = true;
            return;
        }
        if (set_tailscale_flag("ts_adv_exit", &tailscale_advertise_exit_node, enabled)
            && tailscale_enabled) schedule_restart();
    } else if (!strcmp(command, "exit_node_lan_bypass")) {
        set_tailscale_flag("ts_lan_bp", &tailscale_lan_bypass, enabled);
    } else if (!strcmp(command, "fourvia6_enabled")) {
        fourvia6_status_t v6;
        fourvia6_get_status(&v6);
        if (v6.enabled == enabled) return;
        char error[96];
        if (fourvia6_set_config(enabled, v6.lan_cidr, v6.site_id, error, sizeof error) == ESP_OK) {
            s_publish_requested = true;
            schedule_restart();
        }
    } else if (!strcmp(command, "reconnect_wifi")) {
        s_wifi_reconnect_requested = true;
    } else if (!strcmp(command, "reconnect_tailscale")) {
        if (tailscale_enabled) schedule_restart();
    } else if (!strcmp(command, "service_watch_enabled")) {
        /* Toggles periodic tests only; interval/notify stay as configured. */
        service_watch_config_t watch;
        service_watch_get(&watch);
        watch.enabled = enabled;
        (void)service_watch_set(&watch);
        s_publish_requested = true;
    } else if (!strcmp(command,"health_monitor_enabled")) {
        if(health_monitor_set_enabled(enabled)==ESP_OK)s_publish_requested=true;
    } else if (!strncmp(command, "tailnet_forward/", 16)) {
        /* Unbound legacy index-only messages are deliberately rejected: a
         * delayed command must not target a survivor after rule compaction. */
        uint32_t token;
        if (strlen(command+16)==10&&command[16]>='0'&&command[16]<'0'+TAILNET_FORWARD_MAX
            &&command[17]=='/'&&control_parse_hex32(command+18,&token)&&token
            &&tailnet_forward_set_enabled_bound(command[16]-'0',token,enabled)==ESP_OK) {
            s_publish_requested = true;
            s_discovery_requested = true;
        }
    } else if (!strncmp(command, "wol/", 4)) {
        const char *compact = command + 4;
        char mac[18];
        if (strlen(compact) == 12) {
            snprintf(mac, sizeof mac, "%.2s:%.2s:%.2s:%.2s:%.2s:%.2s",
                     compact, compact + 2, compact + 4, compact + 6,
                     compact + 8, compact + 10);
            (void)wol_send_saved_mac_text(mac);
        } else {
            (void)wol_send_saved_mac_text(compact);
        }
    }
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = event_data;
    if (!event || event->client != s_client) return;
    if (event_id == MQTT_EVENT_CONNECTED) {
        broker_clock_set(true, false);
        __atomic_fetch_or(&s_connection_events, BROKER_CONNECTED, __ATOMIC_RELEASE);
    } else if (event_id == MQTT_EVENT_DISCONNECTED) {
        broker_clock_set(false, false);
        __atomic_fetch_or(&s_connection_events, BROKER_DISCONNECTED, __ATOMIC_RELEASE);
        ESP_LOGW(TAG, "disconnected");
    } else if (event_id == MQTT_EVENT_DATA) {
        /* Command topics are edge-triggered controls, never state.  A retained
         * `restart` (or Tailscale toggle) would otherwise execute on every
         * reconnect and can trap the device in a reboot loop.  QoS1 duplicate
         * deliveries are ignored for the same reason: WOL/reboot are not
         * safely repeatable actions. */
        if (event->retain || event->dup) {
            ESP_LOGW(TAG, "ignored %s MQTT command delivery",
                     event->retain ? "retained" : "duplicate");
            return;
        }
        if (event->current_data_offset != 0 || event->data_len != event->total_data_len
            || event->topic_len <= 0 || event->topic_len >= 191
            || event->data_len <= 0 || event->data_len >= 127
            || !event->topic || !event->data
            || memchr(event->topic, '\0', event->topic_len)
            || memchr(event->data, '\0', event->data_len)) return;
        char topic[192];
        char payload[128];
        memcpy(topic, event->topic, event->topic_len);
        topic[event->topic_len] = '\0';
        memcpy(payload, event->data, event->data_len);
        payload[event->data_len] = '\0';
        handle_command(topic, payload);
    } else if (event_id == MQTT_EVENT_ERROR) {
        ESP_LOGW(TAG, "client error");
    }
}

static void stop_client(void)
{
    if (s_client) {
        esp_mqtt_client_stop(s_client);
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
    }
    broker_clock_set(false, false);
    __atomic_store_n(&s_connection_events, 0, __ATOMIC_RELEASE);
}

static bool start_client(void)
{
    mqtt_integration_config_t cfg;
    mqtt_integration_get_config(&cfg);
    if (!cfg.enabled || !cfg.uri[0] || !cfg.base_topic[0]) return false;
    if(!homelab_ops_admit())return false;
    snprintf(s_availability_topic, sizeof s_availability_topic, "%s/availability", cfg.base_topic);
    snprintf(s_state_topic, sizeof s_state_topic, "%s/state", cfg.base_topic);
    const esp_mqtt_client_config_t client_config = {
        .broker.address.uri = cfg.uri,
        .broker.verification.crt_bundle_attach = esp_crt_bundle_attach,
        .credentials.username = cfg.username[0] ? cfg.username : NULL,
        .credentials.authentication.password = cfg.password[0] ? cfg.password : NULL,
        .session.last_will.topic = s_availability_topic,
        .session.last_will.msg = "offline",
        .session.last_will.qos = 1,
        .session.last_will.retain = 1,
        .session.keepalive = 60,
        .network.disable_auto_reconnect = true,
        .network.timeout_ms = 10000,
        .outbox.limit = 8192,
        .task.stack_size = 6144,
        .buffer.size = 2048,
    };
    s_client = esp_mqtt_client_init(&client_config);
    if (!s_client) {
        ESP_LOGE(TAG, "esp_mqtt_client_init failed");
        return false;
    }
    esp_err_t err = esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    if (err == ESP_OK) err = esp_mqtt_client_start(s_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "start failed: %s", esp_err_to_name(err));
        esp_mqtt_client_destroy(s_client);
        s_client = NULL;
        return false;
    } else {
        /* URI may contain embedded credentials: never copy it into logs. */
        ESP_LOGI(TAG, "connecting to configured broker");
    }
    return true;
}

static void status_update(const mqtt_integration_config_t *cfg, const service_retry_t *retry,
                          bool discovery_pending, uint64_t now_ms)
{
    mqtt_integration_status_t next = {0};
    next.configured = cfg->enabled && cfg->uri[0] && cfg->base_topic[0];
    next.connected = next.configured && s_connected;
    next.connecting = next.configured && !s_connected && retry->awaiting;
    next.retry_level = retry->failures;
    if (next.configured && !s_connected && !retry->awaiting && retry->next_ms > now_ms)
        next.retry_in_seconds = (uint32_t)((retry->next_ms - now_ms + 999) / 1000);
    next.discovery_pending = next.connected && discovery_pending;
    next.discovery_entities = next.connected ? s_discovery.cursor : 0;
    portENTER_CRITICAL(&s_status_mux);
    s_status = next;
    portEXIT_CRITICAL(&s_status_mux);
}

static void manager_task(void *arg)
{
    (void)arg;
    service_retry_t retry = {0};
    service_retry_t discovery_retry = {0};
    bool discovery_pending = false;
    broker_clock_set(false, true);
    int elapsed = 0;
    while (true) {
        uint32_t notified = ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
        if (s_restart_requested) {
            ESP_LOGW(TAG, "Applying MQTT command with a controlled device restart");
            publish_state();
            vTaskDelay(pdMS_TO_TICKS(750));
            esp_restart();
        }
        if (s_wifi_reconnect_requested) {
            s_wifi_reconnect_requested = false;
            (void)esp_wifi_disconnect();
            vTaskDelay(pdMS_TO_TICKS(750));
            (void)esp_wifi_connect();
        }
        if (notified) {
            stop_client();
            service_retry_reset(&retry);
            discovery_reset(&s_discovery);discovery_pending=false;service_retry_reset(&discovery_retry);
            broker_clock_set(false, true);
            s_watchdog_triggered = false;
            elapsed = 0;
        }
        mqtt_integration_config_t cfg;
        mqtt_integration_get_config(&cfg);
        uint64_t now_ms = (uint64_t)esp_timer_get_time() / 1000;
        uint32_t events = __atomic_exchange_n(&s_connection_events, 0, __ATOMIC_ACQ_REL);
        if (events && s_connected) {
            service_retry_reset(&retry);
            s_watchdog_triggered = false;
            char command_topic[128];
            snprintf(command_topic, sizeof command_topic, "%s/command/#", cfg.base_topic);
            esp_mqtt_client_subscribe(s_client, command_topic, 1);
            publish(s_availability_topic, "online", 1);
            s_discovery_requested = true;
            s_publish_requested = true;
        } else if (events & BROKER_DISCONNECTED) {
            service_retry_failed(&retry, now_ms);
        }
        if (!s_connected && cfg.enabled && cfg.uri[0] && cfg.base_topic[0]) {
            if (service_retry_timed_out(&retry, now_ms)) {
                stop_client();
                service_retry_failed(&retry, now_ms);
            } else if (service_retry_due(&retry, now_ms)) {
                service_retry_begin(&retry, now_ms);
                bool started = s_client
                    ? homelab_ops_admit() && esp_mqtt_client_reconnect(s_client) == ESP_OK
                    : start_client();
                if (!started) service_retry_failed(&retry, now_ms);
            }
        }
        elapsed++;
        if (s_connected && (s_publish_requested || elapsed >= cfg.interval_seconds)) {
            s_publish_requested = false;
            elapsed = 0;
            publish_state();
        }
        if (s_connected && s_discovery_requested) {
            s_discovery_requested = false;
            discovery_reset(&s_discovery);discovery_pending=true;service_retry_reset(&discovery_retry);
        }
        if (s_connected && discovery_pending && service_retry_due(&discovery_retry,now_ms)) {
            discovery_begin(&s_discovery);
            if(!homelab_ops_admit()){service_retry_failed(&discovery_retry,now_ms);}
            else {
                publish_discovery();
                if(discovery_finished(&s_discovery))discovery_pending=false;
                if(s_discovery.failed)service_retry_failed(&discovery_retry,now_ms);
                else {service_retry_reset(&discovery_retry);discovery_retry.next_ms=now_ms+1000;}
            }
        }
        status_update(&cfg, &retry, discovery_pending, now_ms);
        if (!s_connected && cfg.enabled && cfg.broker_watchdog_enabled
            && cfg.broker_watchdog_wol_mac[0] && !s_watchdog_triggered) {
            int64_t silence_us = broker_silence_us();
            if (silence_us >= (int64_t)cfg.broker_watchdog_timeout_seconds * 1000000LL) {
                esp_err_t wake_err = wol_send_saved_mac_text(cfg.broker_watchdog_wol_mac);
                s_watchdog_triggered = true; /* one three-packet burst per outage */
                if (wake_err == ESP_OK) {
                    s_watchdog_wake_count++;
                    ESP_LOGW(TAG, "broker silent for %lu s; watchdog WOL sent to %s",
                             (unsigned long)cfg.broker_watchdog_timeout_seconds,
                             cfg.broker_watchdog_wol_mac);
                } else {
                    ESP_LOGE(TAG, "broker watchdog WOL failed for %s: %s",
                             cfg.broker_watchdog_wol_mac, esp_err_to_name(wake_err));
                }
            }
        }
    }
}

void mqtt_integration_init(void)
{
    if (s_manager_task) return;
    if (!s_lock) s_lock = xSemaphoreCreateMutex();
    if (!s_lock) { ESP_LOGE(TAG, "Cannot allocate MQTT configuration lock"); return; }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    load_config();
    xSemaphoreGive(s_lock);
    if (xTaskCreate(manager_task, "mqtt_bridge", 6144, NULL, 4, &s_manager_task) != pdPASS) {
        s_manager_task = NULL;
        ESP_LOGE(TAG, "Cannot allocate MQTT manager stack");
    }
}

void mqtt_integration_get_config(mqtt_integration_config_t *out)
{
    if (!out) return;
    if (!s_lock) {
        config_defaults(out);
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(out, &s_config, sizeof *out);
    xSemaphoreGive(s_lock);
}

esp_err_t mqtt_integration_set_config(const mqtt_integration_config_t *config)
{
    if (!config || config->interval_seconds < 5 || config->interval_seconds > 3600)
        return ESP_ERR_INVALID_ARG;
    if (config->enabled && (!config->uri[0] || !config->base_topic[0]))
        return ESP_ERR_INVALID_ARG;
    uint8_t watchdog_mac[6];
    if (config->broker_watchdog_timeout_seconds < 30
        || config->broker_watchdog_timeout_seconds > 86400
        || (config->broker_watchdog_enabled
            && (!config->enabled
                || !wol_parse_mac(config->broker_watchdog_wol_mac, watchdog_mac))))
        return ESP_ERR_INVALID_ARG;
    esp_err_t err = nvs_param_set_u8("mqtt_en", config->enabled ? 1 : 0);
#define SAVE_STR(key, field) do { if (err == ESP_OK) err = nvs_param_set_str((key), (field)); } while (0)
    SAVE_STR("mqtt_uri", config->uri);
    SAVE_STR("mqtt_user", config->username);
    SAVE_STR("mqtt_pass", config->password);
    SAVE_STR("mqtt_topic", config->base_topic);
    SAVE_STR("mqtt_hapfx", config->discovery_prefix);
    SAVE_STR("mqtt_wmac", config->broker_watchdog_wol_mac);
#undef SAVE_STR
    if (err == ESP_OK) err = nvs_param_set_u8("mqtt_ha", config->home_assistant_discovery ? 1 : 0);
    if (err == ESP_OK) err = nvs_param_set_u16("mqtt_int", config->interval_seconds);
    if (err == ESP_OK) err = nvs_param_set_u8("mqtt_wdog", config->broker_watchdog_enabled ? 1 : 0);
    if (err == ESP_OK) err = nvs_param_set_u32("mqtt_wdto", config->broker_watchdog_timeout_seconds);
    if (err != ESP_OK) return err;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memcpy(&s_config, config, sizeof s_config);
    xSemaphoreGive(s_lock);
    if (s_manager_task) xTaskNotifyGive(s_manager_task);
    return ESP_OK;
}

bool mqtt_integration_connected(void)
{
    return s_connected;
}

bool mqtt_integration_task_running(void)
{
    return s_manager_task != NULL;
}

void mqtt_integration_get_status(mqtt_integration_status_t *out)
{
    if (!out) return;
    portENTER_CRITICAL(&s_status_mux);
    *out = s_status;
    portEXIT_CRITICAL(&s_status_mux);
}

bool mqtt_integration_watchdog_triggered(void)
{
    return s_watchdog_triggered;
}

uint32_t mqtt_integration_watchdog_wake_count(void)
{
    return s_watchdog_wake_count;
}

uint32_t mqtt_integration_broker_silence_seconds(void)
{
    return (uint32_t)(broker_silence_us() / 1000000LL);
}

void mqtt_integration_publish_now(void)
{
    s_publish_requested = true;
}

void mqtt_integration_wol_changed(void)
{
    s_discovery_requested = true;
}

void mqtt_integration_tailnet_forward_changed(void)
{
    s_discovery_requested = true;
    s_publish_requested = true;
}
