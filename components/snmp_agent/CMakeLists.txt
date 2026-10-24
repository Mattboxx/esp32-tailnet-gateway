# The agent is optional (CONFIG_TSR_SNMP); without it a stub keeps the API
# and the die-temperature reading.
if(CONFIG_TSR_SNMP)
    set(_snmp_src "snmp_agent.c")
else()
    set(_snmp_src "snmp_agent_off.c")
endif()
idf_component_register(SRCS ${_snmp_src}
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES freertos lwip nvs_flash log esp_app_format esp_timer
                                     esp_netif esp_driver_tsens task_reaper)
