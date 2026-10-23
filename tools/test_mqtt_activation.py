"""Offline behavioral tests of the opt-in MQTT hardware harness, NOT hardware."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'tools/test_mqtt_activation_device.py').read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'exercise')


class Clock:
    now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class API:
    def __init__(self):
        self.posts = []; self.enabled = True; self.rebooted = False
        self.watchdog = False; self.connect_fails = False; self.version = 'synthetic-dev'
    def __call__(self, path, payload=None, **kwargs):
        if payload is not None:
            self.posts.append((path, payload.copy()))
            if path == '/api/mqtt': self.enabled = payload['enabled']
            elif path == '/api/system/restart': self.rebooted = True
            else: raise AssertionError('Unexpected mutation')
            return {'ok': True}
        if path == '/api/system': return {'version': self.version, 'reset_history': [{'reason': 'SW'}]}
        if path == '/api/mqtt': return {'enabled': self.enabled, 'connected': self.enabled and not self.connect_fails,
                                       'broker_watchdog_enabled': self.watchdog, 'base_topic': 'synthetic'}
        if path == '/api/operations': return {'authority_ready': True}
        if path == '/api/status': return {'uptime_s': 1 if self.rebooted else 200}
        if path == '/api/system/diag': return {'tasks': [{'name': 'mqtt_task', 'stack_hwm': 1000}]}
        raise AssertionError('Unexpected read')


clock = Clock()
namespace = {'time': clock, 'memory': lambda api: {'internal_largest': 3456}}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'actual-hardware-harness', 'exec'), namespace)
exercise = namespace['exercise']


class Observer:
    def topics(self, prefix): return [(clock.now, prefix+'/state', b'{}', False)]


class HarnessTests(unittest.TestCase):
    def setUp(self): clock.now = 0
    def call(self, api):
        result = {}
        exercise(api, 'synthetic-dev', Observer(), '192.0.2.1', 18883, 60, result,
                 sleep=clock.sleep, clock=clock.monotonic)
        return result
    def test_off_at_boot_three_cycles_not_just_connected_at_boot(self):
        api = API(); result = self.call(api)
        self.assertTrue(result['off_at_boot_confirmed'] and result['planned_reboot_only'])
        self.assertEqual(len(result['cycles']), 3)
        self.assertEqual([p for p, v in api.posts].count('/api/system/restart'), 1)
        enabled = [v['enabled'] for p, v in api.posts if p == '/api/mqtt']
        self.assertEqual(enabled, [False, True, False, True, False, True])
    def test_wrong_version_and_watchdog_never_mutate(self):
        for mode in ('version', 'watchdog'):
            api = API()
            if mode == 'version': api.version = 'other'
            else: api.watchdog = True
            with self.assertRaises(AssertionError): self.call(api)
            self.assertEqual(api.posts, [])
    def test_activation_timeout_is_not_a_pass_or_repeated_restart(self):
        api = API(); api.connect_fails = True
        with self.assertRaisesRegex(AssertionError, 'activation timeout'): self.call(api)
        self.assertEqual([p for p, v in api.posts].count('/api/system/restart'), 1)
        self.assertLess(clock.now, 200)


class CommandProofTests(unittest.TestCase):
    def test_manager_stack_budget_is_external_and_not_reduced(self):
        # Structural guard; actual post-outage high-water marks are device tests.
        source = (ROOT/'main/mqtt_integration.c').read_text(encoding='utf-8')
        self.assertIn('#define MQTT_MANAGER_STACK_BYTES 9216', source)
        self.assertIn('manager_task, "mqtt_bridge", MQTT_MANAGER_STACK_BYTES', source)
        self.assertIn('&s_manager_task, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)', source)
    def setUp(self):
        lab_tree = ast.parse((ROOT/'tools/test_mqtt_lab_device.py').read_text(encoding='utf-8'))
        fn = next(n for n in lab_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'confirm_command_delivery')
        ns = {'LAB_MAC': '02:4c:41:42:57:4f', 'magic_listener': None, 'wait': None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'actual-command-proof', 'exec'), ns)
        self.proof = ns['confirm_command_delivery']
        self.saved = [{'name': 'synthetic', 'mac': '02:00:00:00:00:01'}]
        self.devices = self.saved.copy()
        self.writes = []
    def api(self, path, payload=None):
        self.assertEqual(path, '/api/wol')
        if payload is not None:
            self.devices = payload['devices'].copy(); self.writes.append(self.devices)
        return {'devices': self.devices.copy()}
    def run_proof(self, delivered, observer=None):
        class Observer:
            def publish(inner, topic, payload):
                self.assertEqual(topic, 'synthetic/command/wol/024c4142574f')
                self.assertEqual(payload, b'PRESS')
        return self.proof(self.api, observer or Observer(), 'synthetic', '192.0.2.1', 47010,
                          listen=lambda ip, port, seconds: [delivered],
                          waiter=lambda predicate, seconds, step: predicate())
    def test_packet_is_required_and_catalog_is_restored(self):
        for delivered in (False, True):
            self.assertEqual(self.run_proof(delivered), delivered)
            self.assertEqual(self.devices, self.saved)
            self.assertEqual(self.writes[-2][1]['broadcast'], '192.0.2.1')
    def test_command_failure_still_restores_catalog(self):
        class Broken:
            def publish(inner, topic, payload): raise OSError('synthetic')
        with self.assertRaises(OSError): self.run_proof(False, Broken())
        self.assertEqual(self.devices, self.saved)
    def test_full_catalog_is_not_modified(self):
        self.devices = self.saved * 12
        with self.assertRaises(AssertionError): self.run_proof(True)
        self.assertEqual(self.writes, [])


if __name__ == '__main__': unittest.main()
