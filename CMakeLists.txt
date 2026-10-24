# For more information about build system see
# https://docs.espressif.com/projects/esp-idf/en/latest/api-guides/build-system.html
cmake_minimum_required(VERSION 3.16)

# microlink ships as a vendored submodule under external/microlink. Its
# components live at:
#   external/microlink/components/microlink                       (microlink itself)
#   external/microlink/components/microlink/components/wireguard_lwip (the WG-for-lwIP backend)
# The Csontikka/microlink repo also exposes a convenience symlink at
#   external/microlink/components/wireguard_lwip
# but Git on Windows checks symlinks out as plain-text files unless
# Developer Mode is on, so we point ESP-IDF at the real paths instead
# and ignore the symlink. Doing it this way keeps the project building
# on a fresh Windows clone without any setup ritual.
set(EXTRA_COMPONENT_DIRS
    external/microlink/components/microlink
    external/microlink/components/microlink/components/wireguard_lwip
)

# PlatformIO passes an environment-specific generated sdkconfig path. Make the
# tracked defaults explicit as well: otherwise some PlatformIO/CMake cache
# combinations regenerate sdkconfig.<env> from Kconfig defaults (10 sockets)
# and silently discard the network-service budget in sdkconfig.defaults.
set(SDKCONFIG_DEFAULTS "${CMAKE_SOURCE_DIR}/sdkconfig.defaults" CACHE STRING
    "Project sdkconfig defaults" FORCE)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# PROJECT_VER lands in the esp_app_desc_t struct so the running firmware
# can report its version via the OTA APIs and the web UI's Status page.
set(PROJECT_VER "2.0.4-beta.2")

project(esp32_tsr)

# esp-mqtt has no task-memory capabilities option in the pinned SDK. Adapt
# only its task create/delete calls, not global FreeRTOS allocation or SDK files.
# Fail configuration on an unreviewed SDK change: task ownership must be checked
# before applying the same paired allocation adapter to another version.
file(SHA256 "$ENV{IDF_PATH}/components/mqtt/esp-mqtt/mqtt_client.c" _mqtt_source_hash)
if(NOT _mqtt_source_hash STREQUAL "3e558fa88e7bd98d4342bd19fe6d99c56031d04ff7a26405ab1bcd09408cf6f3")
    message(FATAL_ERROR "Unreviewed esp-mqtt source: review task ownership before updating mqtt_task_memory.h adapter")
endif()
idf_component_get_property(_mqtt_component_lib mqtt COMPONENT_LIB)
target_compile_options(${_mqtt_component_lib} PRIVATE
    "-include${CMAKE_CURRENT_SOURCE_DIR}/main/mqtt_task_memory.h")

# GCC 14 (toolchain-xtensa-esp-elf 14.2.0) throws a false-positive
# -Wmaybe-uninitialized in ESP-IDF's esp_driver_i2c/i2c_master.c
# (ops_current in s_i2c_asynchronous_transaction), which IDF's global
# -Werror then turns into a hard build failure. This project doesn't
# touch that code path; downgrade just this one warning back to
# non-fatal for that component rather than patching the framework.
idf_component_get_property(_i2c_master_lib esp_driver_i2c COMPONENT_LIB)
if(_i2c_master_lib)
    target_compile_options(${_i2c_master_lib} PRIVATE -Wno-error=maybe-uninitialized)
endif()
