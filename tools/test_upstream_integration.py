"""Static regression guards for the upstream ports, not hardware tests."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpstreamIntegrationTests(unittest.TestCase):
    def text(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_accepted_routes_are_published_atomically(self):
        source = self.text('main/lwip_route_hook.c')
        supervisor = source.split('static void route_supervisor_task', 1)[1].split('void lwip_route_hook_init', 1)[0]
        self.assertNotIn('tailscale_accepted_routes[new_count]', supervisor)
        self.assertIn('tcpip_callback_wait(publish_routes_cb, &new_routes)', supervisor)
        self.assertIn('publish_accepted_routes(state->routes, state->count)', source)
        publisher = source.split('static void publish_accepted_routes', 1)[1].split('int tailscale_accepted_routes_snapshot', 1)[0]
        self.assertLess(publisher.index('portENTER_CRITICAL('), publisher.index('memcpy('))
        self.assertLess(publisher.index('tailscale_accepted_routes_count = count'), publisher.index('portEXIT_CRITICAL('))
        self.assertNotIn('LOCK_TCPIP_CORE()', publisher)
        self.assertIn('tcpip_callback_wait(set_default_callback, target)', source)
        self.assertIn('tailscale_lifecycle_try_acquire()', supervisor)
        self.assertIn('tailscale_lifecycle_release()', supervisor)
        web = self.text('main/web_ui.c')
        self.assertNotIn('tailscale_accepted_routes[i]', web)
        self.assertIn('tailscale_accepted_routes_snapshot(accepted', web)

    def test_custom_features_and_privacy_preserved(self):
        cmake = self.text("main/CMakeLists.txt")
        for source in ("wol.c", "mqtt_integration.c", "ntfy_integration.c",
                       "fourvia6.c", "tailnet_forward.c", "runtime_metrics.c"):
            self.assertIn(source, cmake)
        self.assertNotIn('"telemetry.c"', cmake)
        self.assertFalse((ROOT / "main/telemetry.c").exists())
        hooks = self.text("external/microlink/components/microlink/components/wireguard_lwip/src/wireguardif.c")
        self.assertIn("__attribute__((weak))", hooks)
        self.assertIn("fourvia6", self.text("main/tailscale_manager.c"))

    def test_exit_selection_is_saved_without_live_route_flip(self):
        web = self.text("main/web_ui.c")
        self.assertNotIn("tailscale_exit_node_ip = hbo", web)
        self.assertIn('nvs_save_int("ts_exit_node", (int32_t)hbo)', web)
        self.assertIn('"exit_node_restart_pending"', web)

    def test_channel_roam_never_reboots_or_reconfigures_ap(self):
        main = self.text("main/main.c")
        block = main.split("/* Single radio: the softAP", 1)[1].split("/* Auto-spawn", 1)[0]
        self.assertNotIn("esp_restart();", block)
        self.assertNotIn("esp_wifi_set_config(", block.replace("esp_wifi_set_config(WIFI_IF_AP)", ""))
        self.assertIn('nvs_param_set_int("ap_chan_learned"', block)

    def test_network_limits_and_ui(self):
        defaults = self.text("sdkconfig.defaults")
        self.assertIn("CONFIG_LWIP_MAX_SOCKETS=31", defaults)
        self.assertIn("platform = espressif32@6.13.0", self.text("platformio.ini"))
        self.assertIn("CONFIG_LWIP_MAX_ACTIVE_TCP=24", defaults)
        self.assertIn("CONFIG_LWIP_TCP_OOSEQ_MAX_PBUFS=4", defaults)
        self.assertIn("#define TS_MTU_TAILSCALE       1280", self.text("main/tailscale_mtu.h"))
        html = self.text("main/index.html")
        for control in ("ts-adv-ap", "ts-ipn-version", "ts-effective-routes", "ts-exit-pending"):
            self.assertIn(f'id="{control}"', html)

    def test_snmp_is_optional_authenticated_and_ordered(self):
        source = self.text("components/snmp_agent/snmp_agent.c")
        self.assertIn("static bool   s_enabled  = false", source)
        self.assertIn("SNMP community must not be empty", self.text("main/web_ui.c"))
        main = self.text("main/main.c")
        self.assertLess(main.index("netif_hooks_init();"), main.index("snmp_agent_init();"))
        self.assertNotIn("temperature_sensor_install", self.text("main/web_ui.c"))
        web = self.text("main/web_ui.c")
        for handler in ("snmp_get_handler", "snmp_post_handler"):
            body = web.split(f"static esp_err_t {handler}", 1)[1].split("\n}", 1)[0]
            self.assertIn("require_auth(req)", body)
        apply = source.split("void snmp_agent_apply_live(", 1)[1].split("esp_err_t snmp_agent_save_config", 1)[0]
        self.assertNotIn("close(", apply)
        self.assertIn("shutdown(s_sock", apply)
        self.assertIn("SO_RCVTIMEO", source)

    def test_every_http_endpoint_registration_is_checked(self):
        web = self.text("main/web_ui.c")
        init = web.split("void web_ui_init(void)", 1)[1]
        self.assertNotIn("httpd_register_uri_handler(", init)
        import re
        capacity = int(re.search(r"conf.max_uri_handlers\s*=\s*(\d+)", init)[1])
        self.assertGreaterEqual(capacity, len(re.findall(r"reg_uri\(server,", init)) + 8)
        self.assertIn("reg_uri(server, &uri_favicon)", init)

    def test_routes_not_written_by_composer(self):
        source = self.text("main/tailscale_manager.c")
        composer = source.split("bool tailscale_routes_preview(", 1)[1].split("const char *tailscale_active_routes", 1)[0]
        self.assertNotIn("nvs_param_set", composer)
        self.assertNotIn("static char buf", composer)
        self.assertIn("xSemaphoreCreateMutexStatic", source)
        self.assertIn("s_active_ipn_version", source)

    def test_031_peerapi_is_separate_and_opt_in(self):
        dns = self.text('main/peer_dns.c')
        manager = self.text('main/tailscale_manager.c')
        self.assertIn('!tailscale_exit_server_active()', dns)
        self.assertIn('local_ip != own_ip', dns)
        self.assertIn('peer.vpn_ip == remote_ip', dns)
        self.assertIn('from.sin_port == htons(53)', dns)
        self.assertIn('httpd_stop(server)', dns)
        self.assertIn('.peer_api_port = peer_dns_is_running()', manager)
        self.assertIn('TAILSCALE_PEERAPI_PORT + 1', manager)
        web = self.text('main/web_ui.c')
        init = web.split('void web_ui_init(void)', 1)[1]
        self.assertNotIn('peer_dns_get_handler', init)
        self.assertIn('exit_dns_running', web)
        self.assertIn('exit_dns_running', self.text('main/mqtt_integration.c'))
        self.assertIn('Exit-node DNS:', self.text('main/ntfy_integration.c'))

    def test_030_microlink_stop_and_psram_fixes(self):
        prefix = 'external/microlink/components/microlink/'
        source = self.text(prefix + 'src/ml_netcheck.c')
        self.assertIn('ML_EVT_SHUTDOWN_REQUEST', source)
        self.assertIn('remain > 250000ULL', source)
        self.assertIn('ml->stop_incomplete = false', self.text(prefix + 'src/microlink.c'))
        io = self.text(prefix + 'src/ml_net_io.c')
        self.assertIn('uint8_t *pkt_data = ml_psram_malloc(n)', io)
        wg = self.text(prefix + 'components/wireguard_lwip/src/wireguardif.c')
        self.assertIn('wireguardif_has_host_route', wg)
        self.assertTrue('fourvia6_translate_wg_input' in wg, '4via6 input hook missing')
        self.assertTrue('fourvia6_translate_wg_output' in wg, '4via6 output hook missing')

    def test_updates_are_fork_only_opt_in_and_privileged(self):
        source = self.text('main/ota_remote.c')
        validation = self.text('main/ota_validation.h')
        self.assertIn('OTA_REPO_CURRENT "Mattboxx/esp32-tailnet-gateway"', validation)
        self.assertIn('OTA_REPO_PREVIOUS "Mattboxx/esp32-tailscale-gateway-NAS-recovery"', validation)
        self.assertNotIn('Csontikka', source + validation)
        self.assertIn('.crt_bundle_attach = esp_crt_bundle_attach', source)
        self.assertIn('.disable_auto_redirect = true', source)
        self.assertIn('ota_download_url_allowed_for(b.location, state.asset)', source)
        installer = source.split('static OTA_NOINLINE bool install_release', 1)[1].split('static void worker', 1)[0]
        self.assertLess(installer.index('image_matches('), installer.index('ota_flash_begin('))
        self.assertLess(installer.index('memcmp(actual, s_digest'), installer.index('ota_flash_set_boot_partition('))
        # The HTTPS worker must not regress to direct cache-sensitive SDK calls.
        # Actual dispatch/domain/error behavior is exercised by test_ota_flash.
        for call in ('esp_ota_get_next_update_partition', 'esp_ota_begin', 'esp_ota_write',
                     'esp_ota_end', 'esp_ota_abort', 'esp_ota_set_boot_partition', 'esp_restart'):
            self.assertNotIn(call + '(', source)
        self.assertIn('ota_writer_try_acquire()', installer)
        self.assertIn('ota_writer_release()', installer)
        self.assertNotIn('s_state.config.enabled = true', source)
        web = self.text('main/web_ui.c')
        for handler in ('updates_save_handler', 'updates_check_handler', 'updates_install_handler'):
            block = web.split('static esp_err_t ' + handler, 1)[1].split('\n}', 1)[0]
            self.assertIn('require_password_session(req)', block)


if __name__ == "__main__":
    unittest.main()
