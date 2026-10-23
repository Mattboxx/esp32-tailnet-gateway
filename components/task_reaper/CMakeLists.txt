idf_component_register(SRCS "task_reaper.c"
                       INCLUDE_DIRS "include"
                       REQUIRES freertos esp_common
                       PRIV_REQUIRES heap log)
