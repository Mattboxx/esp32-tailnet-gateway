"""Static regression guards for the v0.1.27 port, not hardware tests."""
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
        self.assertIn("CONFIG_LWIP_MAX_ACTIVE_TCP=24", defaults)
        self.assertIn("CONFIG_LWIP_TCP_OOSEQ_MAX_PBUFS=4", defaults)
        self.assertIn("#define TS_MTU_TAILSCALE       1280", self.text("main/tailscale_mtu.h"))
        html = self.text("main/index.html")
        for control in ("ts-adv-ap", "ts-ipn-version", "ts-effective-routes", "ts-exit-pending"):
            self.assertIn(f'id="{control}"', html)

    def test_routes_not_written_by_composer(self):
        source = self.text("main/tailscale_manager.c")
        composer = source.split("bool tailscale_routes_preview(", 1)[1].split("const char *tailscale_active_routes", 1)[0]
        self.assertNotIn("nvs_param_set", composer)
        self.assertNotIn("static char buf", composer)
        self.assertIn("xSemaphoreCreateMutexStatic", source)
        self.assertIn("s_active_ipn_version", source)


if __name__ == "__main__":
    unittest.main()
