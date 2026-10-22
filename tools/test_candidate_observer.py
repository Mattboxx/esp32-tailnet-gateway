"""Offline sampler tests with fake HTTP and time, NOT a physical soak run."""
import io
import json
import unittest

from observe_candidate import Ledger, host, number, observe, sample, version

VERSION = '0.1.38-Mattboxx-1.14-dev.3'


class Clock:
    def __init__(self): self.now = 0
    def time(self): return self.now
    def sleep(self, seconds): self.now += seconds


class API:
    def __init__(self): self.paths = []; self.uptime = 100
    def __call__(self, path, *, timeout):
        self.assert_timeout = timeout
        self.paths.append(path)
        if path == '/api/status':
            self.uptime += 1
            return dict(version=VERSION, uptime_s=self.uptime, mem_internal_free=12000,
                        free_psram=1000000, cpu_load_pct=None,
                        sta=dict(connected=True, ssid='PRIVATE', ip='192.168.123.45'),
                        tailscale=dict(connected=True, hostname='PRIVATE'), password='PRIVATE')
        assert path == '/api/system/diag'
        return dict(memory={k: 1000 for k in ('internal_total','internal_free','internal_min_free',
                         'internal_largest','spiram_total','spiram_free','spiram_min_free','spiram_largest')},
                    network_limits=dict(sockets=31, active_tcp=24),
                    tasks=[dict(name='PRIVATE',stack_hwm=200)], token='PRIVATE')


class ObserverTests(unittest.TestCase):
    def test_read_only_allowlist_and_no_socket_usage_invention(self):
        api = API(); row = sample(api, VERSION, 0)
        self.assertTrue(row['status_ok'] and row['diag_ok'])
        self.assertEqual(api.paths, ['/api/status', '/api/system/diag'])
        self.assertNotIn('PRIVATE', json.dumps(row))
        self.assertNotIn('192.168.123.45', json.dumps(row))
        self.assertIsNone(row['socket_usage'])
        self.assertIsNone(row['cpu_load_pct'])
        self.assertEqual(row['socket_limit'], 31)
        self.assertEqual(row['stack_hwm_min_raw'], 200)

    def test_missing_invalid_numbers_are_not_zero(self):
        for value in (True, '50', float('nan'), float('inf'), -1, 2**54):
            self.assertIsNone(number(value))
        self.assertEqual(number(0), 0)
        self.assertEqual(number(-5, temperature=True), -5)
        row = sample(lambda *a, **kw: {}, VERSION, 0)
        self.assertFalse(row['status_ok']); self.assertIsNone(row['free_heap'])

    def test_bounded_cadence_and_summary_is_not_qualification(self):
        api = API(); clock = Clock(); output = io.StringIO()
        self.assertEqual(observe(api, VERSION, 360, 60, output, clock=clock.time, sleep=clock.sleep), 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(api.paths.count('/api/status'), 6)
        self.assertEqual(api.paths.count('/api/system/diag'), 2)
        self.assertEqual(rows[-1]['elapsed_s'], 360)
        self.assertFalse(rows[-1]['data_plane_verified'])
        self.assertIsNone(rows[-1]['qualification_pass'])
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_wrong_version_stops_before_diag(self):
        api = API(); clock = Clock(); output = io.StringIO()
        self.assertEqual(observe(api, 'wrong-version', 360, 60, output, clock=clock.time, sleep=clock.sleep), 2)
        self.assertEqual(api.paths, ['/api/status'])
        self.assertIsNone(json.loads(output.getvalue().splitlines()[1])['version'])
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['matching_samples'], 0)

    def test_failures_record_no_exception_secrets_and_continue(self):
        api = API(); clock = Clock(); output = io.StringIO(); count = 0
        def flaky(path, **kw):
            nonlocal count
            if path == '/api/status':
                count += 1
                if count == 2: raise OSError('PRIVATE')
            return api(path, **kw)
        self.assertEqual(observe(flaky, VERSION, 180, 60, output, clock=clock.time, sleep=clock.sleep), 1)
        last = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(last['missing_or_wrong_version_samples'], 1)
        self.assertEqual(last['observed_uptime_decreases'], 0)
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_observed_transitions_are_not_inferred_from_outage(self):
        ledger = Ledger()
        for ok, uptime, state in ((True, 100, True),(False, 0, False),(True, 101, True),
                                  (True, 102, False),(True, 2, True)):
            ledger.add(dict(status_ok=ok,uptime_s=uptime,tailnet_control_connected=state))
        self.assertEqual(ledger.uptime_decreases, 1)
        self.assertEqual(ledger.control_transitions, 2)

    def test_diag_failure_is_separate_from_control_health(self):
        api = API()
        def failed_diag(path, **kw):
            if path.endswith('/diag'): raise OSError('PRIVATE')
            return api(path, **kw)
        row = sample(failed_diag, VERSION, 0)
        self.assertTrue(row['status_ok'])
        self.assertFalse(row['diag_ok'])
        ledger = Ledger(); ledger.add(row)
        self.assertEqual(ledger.summary(1)['diag_failures'], 1)
        self.assertEqual(ledger.summary(1)['matching_samples'], 1)
        self.assertNotIn('PRIVATE', json.dumps(row))

    def test_target_and_version_validation(self):
        self.assertEqual(host('192.0.2.10:8080'), '192.0.2.10:8080')
        for value in ('http://192.0.2.1/', 'user:password@192.0.2.1', '192.0.2.1:0', '192.0.2.1:65536'):
            with self.assertRaises(ValueError): host(value)
        self.assertIsNone(version('PRIVATE\nTEXT'))


if __name__ == '__main__': unittest.main()
