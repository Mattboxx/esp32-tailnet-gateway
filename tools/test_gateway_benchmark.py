"""Offline behavior tests; mocks and loopback only, never a physical ESP."""
import copy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from gateway_benchmark import FileService, TemporaryRule, percentile, restore_console, transfer, upload


def row(name='owner', port=12345):
    return dict(name=name, enabled=True, protocol='tcp', listen_port=port,
                tailnet_destination='100.64.0.2', destination_port=45000,
                allowed_source_subnet='192.0.2.42/32')


class API:
    def __init__(self):
        self.rows, self.writes, self.console = [row()], [], 3
        self.reject_lease = self.ambiguous = False
        self.drift = False

    def __call__(self, path, payload=None):
        if path == '/api/tailnet-forward':
            if payload is not None:
                self.writes.append(copy.deepcopy(payload))
                self.rows = copy.deepcopy(payload['rules'])
                if self.ambiguous:
                    raise TimeoutError('Reply lost after write')
                return {'ok': True}
            rows = copy.deepcopy(self.rows)
            if self.drift:
                rows[0]['listen_port'] += 1
            return dict(rules=rows, max=8)
        if path == '/api/service-leases':
            return [dict(index=i, rule_token=r['name'], effective_enabled=True,
                         temporary=i > 0) for i, r in enumerate(self.rows)]
        if path == '/api/operations':
            self.writes.append(copy.deepcopy(payload))
            return {'ok': not self.reject_lease}
        if path == '/api/sdlog':
            if payload is not None:
                self.writes.append(copy.deepcopy(payload))
                self.console = payload['console_level']
            return {'console_level': self.console}
        raise AssertionError(path)


class Rules(unittest.TestCase):
    def test_exact_cleanup_preserves_original_and_concurrent_addition(self):
        api = API(); original = copy.deepcopy(api.rows)
        rule = TemporaryRule(api, row('perf', 23456))
        rule.install(600)
        self.assertTrue(api.writes[-1]['delete_on_expiry'])
        api.rows.append(row('new-owner', 23457))
        self.assertTrue(all(rule.cleanup().values()))
        self.assertEqual(api.rows, original + [row('new-owner', 23457)])

    def test_refuses_drift_before_write(self):
        api = API(); rule = TemporaryRule(api, row('perf', 23456)); api.drift = True
        with self.assertRaises(RuntimeError): rule.install(600)
        self.assertFalse(api.writes)

    def test_refuses_modified_owned_rule_and_preserves_it(self):
        api = API(); rule = TemporaryRule(api, row('perf', 23456)); rule.install(600)
        api.rows[-1]['allowed_source_subnet'] = '192.0.2.0/24'
        before = copy.deepcopy(api.rows)
        with self.assertRaises(RuntimeError): rule.cleanup()
        self.assertEqual(before, api.rows)

    def test_ambiguous_write_is_not_retried_and_cleanup_recovers(self):
        api = API(); rule = TemporaryRule(api, row('perf', 23456)); api.ambiguous = True
        with self.assertRaises(TimeoutError): rule.install(600)
        self.assertEqual(len(api.writes), 1)
        self.assertTrue(rule.attempted)
        api.ambiguous = False
        self.assertTrue(rule.cleanup()['temporary_rule_removed'])

    def test_lease_failure_still_allows_cleanup(self):
        api = API(); api.reject_lease = True; rule = TemporaryRule(api, row('perf', 23456))
        with self.assertRaises(RuntimeError): rule.install(600)
        self.assertTrue(rule.cleanup()['original_rules_unchanged'])

    def test_expired_rule_cleanup_is_idempotent(self):
        api = API(); rule = TemporaryRule(api, row('perf', 23456))
        self.assertTrue(all(rule.cleanup().values()))
        self.assertFalse(api.writes)

    def test_full_table_conflict_and_invalid_lease_refused(self):
        for mode in ('full', 'port', 'name', 'lease'):
            api = API(); target = row('perf', 23456)
            if mode == 'full': api.rows = [row(str(i), 10000+i) for i in range(8)]
            if mode == 'port': target['listen_port'] = 12345
            if mode == 'name': target['name'] = 'owner'
            rule = TemporaryRule(api, target)
            with self.assertRaises((RuntimeError, ValueError)): rule.install(1 if mode == 'lease' else 600)
            self.assertFalse(api.writes)

    def test_console_restores_only_last_owned_value(self):
        api = API(); api.console = 2
        self.assertTrue(restore_console(api, 3, 2, True))
        self.assertEqual(api.console, 3)
        api.console = 1; api.writes.clear()
        self.assertFalse(restore_console(api, 3, 2, True))
        self.assertEqual(api.console, 1)
        self.assertFalse(api.writes)


class Transfers(unittest.TestCase):
    def test_loopback_transfer_integrity_and_source_path_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder)/'source.bin', Path(folder)/'dest.bin'
            data = bytes(range(256))*2048; source.write_bytes(data)
            service = FileService('127.0.0.1', '127.0.0.1', source)
            service.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{service.port}'
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(url+'/wrong', timeout=2)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                result = transfer(opener, url+service.url_path, dest, len(data), hashlib.sha256(data).hexdigest())
                self.assertTrue(result['integrity_pass'])
                self.assertEqual(dest.read_bytes(), data)
                self.assertEqual(result['retries'], 0)
                service.allowed_source = '192.0.2.1'
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(url+service.url_path, timeout=2)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
            finally:
                service.close()

    def test_rejects_corruption_incomplete_and_http_metadata(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': '3'}
        class Opener:
            def open(self, *args, **kwargs): return Response(b'bad')
        with tempfile.TemporaryDirectory() as folder:
            for mode in ('corrupt', 'size', 'status', 'incomplete'):
                Response.status = 206 if mode == 'status' else 200
                Response.headers = {'Content-Length': '4' if mode in ('size', 'incomplete') else '3'}
                size = 4 if mode == 'incomplete' else 3
                with self.assertRaises(ValueError):
                    transfer(Opener(), 'http://unused/', Path(folder)/mode, size,
                             hashlib.sha256(b'good').hexdigest())

    def test_cancel_and_deadline_have_no_retry(self):
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': '3'}
        class Opener:
            calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                return Response(b'abc')
        with tempfile.TemporaryDirectory() as folder:
            opener = Opener()
            with self.assertRaises(RuntimeError):
                transfer(opener, 'http://unused/', Path(folder)/'cancel', 3, 'unused', cancelled=lambda: True)
            self.assertEqual(opener.calls, 1)
            with patch('gateway_benchmark.time.monotonic', side_effect=[0, 200]):
                with self.assertRaises(TimeoutError):
                    transfer(opener, 'http://unused/', Path(folder)/'timeout', 3, 'unused', total_timeout=180)
            self.assertEqual(opener.calls, 2)

    def test_loopback_upload_integrity_and_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.bin'
            data = bytes(range(256))*2048; source.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            service = FileService('127.0.0.1', '127.0.0.1', source)
            service.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = f'http://127.0.0.1:{service.port}'
            try:
                result = upload(opener, url+service.url_path, source, len(data), digest)
                self.assertTrue(result['integrity_pass'])
                self.assertEqual((result['direction'], result['retries'], result['resumed']), ('upload', 0, False))
                self.assertEqual(service.records[-1]['bytes_read'], len(data))
                self.assertEqual(service.records[-1]['sha256'], digest)
                # A refusal happens before the body is read: depending on timing the
                # client sees the status or the server closing mid-send.
                def refused(code, send):
                    with self.assertRaises((urllib.error.URLError, ConnectionError)) as error:
                        send()
                    if isinstance(error.exception, urllib.error.HTTPError):
                        self.assertEqual(error.exception.code, code)
                        error.exception.close()
                for path, length, code in (('/wrong', len(data), 403), (service.url_path, len(data)-1, 413)):
                    request = urllib.request.Request(url+path, data=data[:length], method='PUT')
                    refused(code, lambda: opener.open(request, timeout=2))
                service.allowed_source = '192.0.2.1'
                refused(403, lambda: upload(opener, url+service.url_path, source, len(data), digest))
                self.assertEqual(len(service.records), 1)   # refused uploads hold no slot
            finally:
                service.close()

    def test_upload_rejects_server_mismatch_and_bad_status(self):
        class Response(io.BytesIO):
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        class Opener:
            def __init__(self, reply, status=200): self.reply, self.status, self.calls = reply, status, 0
            def open(self, request, timeout):
                self.calls += 1
                while request.data.read(8192): pass    # the body is really sent
                response = Response(self.reply); response.status = self.status
                return response
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'s.bin'; source.write_bytes(b'good')
            good = hashlib.sha256(b'good').hexdigest()
            for reply, status in ((b'{"bytes":4,"sha256":"%s"}' % hashlib.sha256(b'evil').hexdigest().encode(), 200),
                                  (b'{"bytes":3,"sha256":"%s"}' % good.encode(), 200),
                                  (b'{"bytes":4,"sha256":"%s"}' % good.encode(), 206)):
                opener = Opener(reply, status)
                with self.assertRaises(ValueError):
                    upload(opener, 'http://unused/', source, 4, good)
                self.assertEqual(opener.calls, 1)
            with self.assertRaises(ValueError):          # local file differs from the expected hash
                upload(Opener(b'{"bytes":4,"sha256":"%s"}' % good.encode()), 'http://unused/', source, 4,
                       hashlib.sha256(b'other').hexdigest())

    def test_upload_cancel_and_deadline_have_no_retry(self):
        class Opener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                request.data.read(8192)
                raise AssertionError('must stop while sending')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'s.bin'; source.write_bytes(b'abc')
            opener = Opener()
            with self.assertRaises(RuntimeError):
                upload(opener, 'http://unused/', source, 3, 'unused', cancelled=lambda: True)
            with patch('gateway_benchmark.time.monotonic', side_effect=[0, 200, 200]):
                with self.assertRaises(TimeoutError):
                    upload(opener, 'http://unused/', source, 3, 'unused', total_timeout=180)
            self.assertEqual(opener.calls, 2)

    def test_percentile_empty_and_small_samples(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([3, 1, 2], .95), 3)


if __name__ == '__main__': unittest.main()
