if(NOT CMAKE_BUILD_EARLY_EXPANSION AND NOT CONFIG_LWIP_IP4_REASSEMBLY)
    message(FATAL_ERROR "Enable CONFIG_LWIP_IP4_REASSEMBLY for safe TCP/UDP receive DNAT; regenerate old sdkconfig files before building.")
endif()

# Generate index_html_data.c by gzipping main/index.html at configure
# time. We can't use EMBED_TXTFILES / target_add_binary_data because
# PIO's SCons wrapper double-prefixes the .S output path, breaking the
# assembly step. A helper Python script (gen_index_html_gz.py) does the
# gzip + hex-array emission — Python ships with PIO's toolchain so we
# lose no cross-platform support.
#
# Written under main/ rather than ${CMAKE_CURRENT_BINARY_DIR} because
# the latter is empty during PIO's first configure pass and ends up
# dropping the file in the project root. The generated file is in
# .gitignore.
#
# Tell CMake to re-run the helper whenever index.html OR the helper
# itself changes — without this the device would keep serving a stale
# SPA blob.
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
             "${CMAKE_CURRENT_LIST_DIR}/index.html"
             "${CMAKE_CURRENT_LIST_DIR}/gen_index_html_gz.py")
# UI translations are injected by the helper; any dictionary change must
# regenerate the embedded page as well.
file(GLOB _i18n_files "${CMAKE_CURRENT_LIST_DIR}/i18n/*.json")
if(_i18n_files)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${_i18n_files})
endif()
# 3.0: one image with every Web UI language (the 3.5 MB app slots of the 8 MB
# layout have room). The 2.1 migration bridge must fit a 1920 KiB 2.x slot and
# stays English only.
if(CONFIG_TSR_MIGRATION_BRIDGE)
    set(_index_flags "--english-only")
    set(_index_c "index_html_data_en.c")
else()
    set(_index_flags "")
    set(_index_c "index_html_data.c")
endif()
find_package(Python3 REQUIRED)
execute_process(
    COMMAND ${Python3_EXECUTABLE}
            "${CMAKE_CURRENT_LIST_DIR}/gen_index_html_gz.py" ${_index_flags}
            "${CMAKE_CURRENT_LIST_DIR}/index.html"
            "${CMAKE_CURRENT_LIST_DIR}/${_index_c}"
    RESULT_VARIABLE _gz_rc
    OUTPUT_VARIABLE _gz_out
    ERROR_VARIABLE  _gz_err)
if(NOT _gz_rc EQUAL 0)
    message(FATAL_ERROR
            "gen_index_html_gz.py failed (rc=${_gz_rc}):\n${_gz_out}${_gz_err}")
endif()
message(STATUS "index.html: ${_gz_out}")

# Per-board "<name>.local" (lan_name.c): lwIP's own mDNS responder from the
# pinned SDK, compiled here; ESP-IDF builds only its separate mdns component.
# lwip_mdns/mdns.c is the SDK file with one documented patch (probing on an
# uplink without IPv6 addresses); the two other files are used as shipped.
set(_lwip_mdns "${IDF_PATH}/components/lwip/lwip/src/apps/mdns")

idf_component_register(SRCS "main.c"
                            "ap_policy.c"
                            "log_capture.c"
                            "nvs_params.c"
                            "tailscale_manager.c"
                            "tailscale_mtu.c"
                            "lwip_route_hook.c"
                            "web_ui.c"
                            "web_port.c"
                            "peer_dns.c"
                            "netif_hooks.c"
                            "wifi_networks.c"
                            "wifi_power_save.c"
                            "wol.c"
                            "homelab_ops.c"
                            "snmp_ops.c"
                            "health_monitor.c"
                            "homelab_ops_http.c"
                            "config_profiles.c"
                            "service_check.c"
                            "eth_uplink.c"
                            "cell_uplink.c"
                            "layout_migration.c"
                            "storage_store.c"
                            "history.c"
                            "settings_snapshot.c"
                            "service_lease.c"
                            "service_transfer.c"
                            "mqtt_integration.c"
                            "runtime_metrics.c"
                            "fourvia6.c"
                            "ntfy_integration.c"
                            "ntfy_json_stream.c"
                            "dhcp_reservations.c"
                            "portmap.c"
                            "forwarding_config.c"
                            "tailnet_forward.c"
                            "tailnet_input.c"
                            "tailnet_reassembly.c"
                            "mac_deny.c"
                            "reset_history.c"
                            "ota.c"
                            "ota_remote.c"
                            "ota_flash.c"
                            "first_boot.c"
                            "first_boot_core.c"
                            "lan_name.c"
                            "lwip_mdns/mdns.c"
                            "${_lwip_mdns}/mdns_domain.c"
                            "${_lwip_mdns}/mdns_out.c"
                            "${_index_c}"
                    PRIV_REQUIRES esp_wifi nvs_flash esp_event esp_netif esp_timer
                                  lwip microlink wpa_supplicant
                                  esp-tls mbedtls
                                  esp_http_server json esp_app_format
                                  acl sdlog remote_console
                                  web_password net_diag dhcpserver
                                  espcoredump dns_relay snmp_agent cli task_reaper
                                  app_update
                                  mqtt
                                  esp_http_client
                                  esp_eth esp_driver_spi esp_driver_gpio esp_driver_uart
                    INCLUDE_DIRS ".")

# Phase 1.9k: wrap ip_napt_forward to skip NAPT for tailnet CGNAT
# (100.64/10) destinations. Otherwise NAPT rewrites the AP-client
# source IP to the WG netif's CGNAT address and breaks the TCP
# 4-tuple at the tailnet peer.
# Provenance shown in System > About: exact source commit of this build and
# of the MicroLink dependency ("-dirty" when tracked files differ). Re-run on
# every commit so a stale value cannot be reported.
get_filename_component(_mtg_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
foreach(_mtg_dir IN ITEMS "${_mtg_root}" "${_mtg_root}/external/microlink")
    execute_process(COMMAND git -C "${_mtg_dir}" rev-parse --short=12 HEAD
                    OUTPUT_VARIABLE _mtg_rev OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    execute_process(COMMAND git -C "${_mtg_dir}" status --porcelain --untracked-files=no
                    OUTPUT_VARIABLE _mtg_dirty OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    if(NOT _mtg_rev)
        set(_mtg_rev "unknown")
    elseif(_mtg_dirty)
        set(_mtg_rev "${_mtg_rev}-dirty")
    endif()
    list(APPEND _mtg_revs "${_mtg_rev}")
endforeach()
list(GET _mtg_revs 0 _mtg_build_commit)
list(GET _mtg_revs 1 _mtg_microlink_commit)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    MTG_BUILD_COMMIT="${_mtg_build_commit}" MTG_MICROLINK_COMMIT="${_mtg_microlink_commit}")
if(EXISTS "${_mtg_root}/.git/logs/HEAD")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_mtg_root}/.git/logs/HEAD")
endif()

# Address changes are announced from the GOT_IP handler (lan_name_uplink_up).
target_compile_definitions(${COMPONENT_LIB} PRIVATE LWIP_MDNS_RESPONDER=1 MDNS_RESP_USENETIF_EXTCALLBACK=0)

target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=ip_napt_forward")
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=ip4_input")

# Phase 1.9l: wrap ip4_route_src_hook to add CGNAT-→-WG routing and
# the exit-node LAN-bypass + self-traffic fallback on top of the
# ESP-IDF default. The default symbol lives in
# components/lwip/port/hooks/lwip_default_hooks.c.
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=ip4_route_src_hook")

# Capture the IDF panic-handler output into the RTC pre-crash ring.
# Wrap BOTH panic_print_str AND panic_print_char so we catch the calls
# from external objects (panic_handler.c / panic_arch.c / eh_frame_parser.c
# use panic_print_str; panic_print_hex/dec use panic_print_char). The
# linker's --wrap only intercepts undefined references between objects,
# so the intra-object panic_print_str → panic_print_char calls inside
# panic.c stay unwrapped and don't double-count.
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=panic_print_char")
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=panic_print_str")
# panic_print_hex/dec call panic_print_char intra-object inside panic.c,
# which --wrap cannot intercept. Wrap them too so the Backtrace's hex
# addresses and the register-dump decimals actually appear in the ring.
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=panic_print_hex")
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=panic_print_dec")
