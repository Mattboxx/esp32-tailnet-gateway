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


if __name__ == '__main__': unittest.main()
