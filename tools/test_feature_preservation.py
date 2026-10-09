"""Guard the fork's control surface against the pre-0.1.31 baseline.

This checks identifiers and registrations, not real-device functionality.
The baseline is deliberately fixed: subsequent additions may not remove the
existing HTTP endpoints, UI controls, HA entities or MQTT command topics.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = "b22035c973a1137d512f24d5eae58ac96c557093"


def baseline(path):
    return subprocess.check_output(
        ["git", "show", f"{BASE}:{path}"], cwd=ROOT).decode("utf-8")


class FeaturePreservationTests(unittest.TestCase):
    def preserved(self, path, pattern):
        old = set(re.findall(pattern, baseline(path), re.S))
        current = set(re.findall(pattern, (ROOT / path).read_text(encoding="utf-8"), re.S))
        self.assertTrue(old, f"Empty baseline for {path}")
        self.assertEqual(sorted(old - current), [], f"Removed controls in {path}")

    def test_http_paths_methods_and_handlers(self):
        self.preserved("main/web_ui.c",
                       r'\.uri\s*=\s*"([^"\n]+)"\s*,\s*\.method\s*=\s*(HTTP_\w+)\s*,\s*\.handler\s*=\s*(\w+)')

    def test_static_ui_ids(self):
        self.preserved("main/index.html", r'\bid="([^"\n]+)"')

    def test_home_assistant_entity_ids(self):
        self.preserved("main/mqtt_integration.c",
                       r'discovery_publish_entity\(\s*"([^"\n]+)"\s*,\s*"([^"\n]+)"')

    def test_mqtt_command_topics(self):
        self.preserved("main/mqtt_integration.c", r'"([^"\n]*/command/[^"\n]+)"')


if __name__ == "__main__":
    unittest.main()
