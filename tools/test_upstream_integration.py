"""Static regression guards for the upstream ports, not hardware tests."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpstreamIntegrationTests(unittest.TestCase):
    def text(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

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
        self.assertIn("CONFIG_LWIP_MAX_SOCKETS=26", defaults)
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


if __name__ == "__main__":
    unittest.main()
