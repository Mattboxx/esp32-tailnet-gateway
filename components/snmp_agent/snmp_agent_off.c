/* Build without the SNMP agent (CONFIG_TSR_SNMP off): the same API, no
 * listener, no task, no configuration. Only the die temperature stays,
 * because Status and diagnostics read it through this component.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "snmp_agent.h"
#include "snmp_operational.h"
#include "driver/temperature_sensor.h"
#include <string.h>

static temperature_sensor_handle_t s_temp_sensor;

void snmp_agent_init(void)
{
    temperature_sensor_config_t cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(-10, 80);
    if (temperature_sensor_install(&cfg, &s_temp_sensor) == ESP_OK) temperature_sensor_enable(s_temp_sensor);
    else s_temp_sensor = NULL;
}

void snmp_agent_apply_live(bool enabled, const char *community, const char *sys_name,
                           const char *sys_contact, const char *sys_location)
{
    (void)enabled; (void)community; (void)sys_name; (void)sys_contact; (void)sys_location;
}

esp_err_t snmp_agent_save_config(bool enabled, const char *community, const char *sys_name,
                                 const char *sys_contact, const char *sys_location)
{
    (void)enabled; (void)community; (void)sys_name; (void)sys_contact; (void)sys_location;
    return ESP_ERR_NOT_SUPPORTED;
}

bool snmp_agent_is_enabled(void) {return false;}
bool snmp_agent_is_running(void) {return false;}

void snmp_agent_get_config(bool *enabled_out, bool *running_out, char *community, size_t comm_sz,
                           char *sys_name, size_t name_sz, char *sys_contact, size_t cont_sz,
                           char *sys_location, size_t loc_sz)
{
    *enabled_out = *running_out = false;
    if (comm_sz) community[0] = 0;
    if (name_sz) sys_name[0] = 0;
    if (cont_sz) sys_contact[0] = 0;
    if (loc_sz) sys_location[0] = 0;
}

bool snmp_agent_chip_temp_c(float *out_c)
{
    float c = 0.0f;
    if (!s_temp_sensor || !out_c || temperature_sensor_get_celsius(s_temp_sensor, &c) != ESP_OK) return false;
    *out_c = c;
    return true;
}

void snmp_agent_set_operational_provider(snmp_operational_provider_t provider) {(void)provider;}
