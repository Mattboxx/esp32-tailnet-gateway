"""Offline checks for session renewal used by opt-in hardware tests."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from test_snmp_device import login


class Client:
    def __init__(self, failures):
        self.failures = list(failures)
        self.authentications = 0
        self.requests = 0

    def open(self, request, timeout):
        assert timeout > 0
        path = request.full_url.split('.invalid', 1)[1]
        if path == '/api/auth/challenge':
            data = dict(supported=True, salt='00'*16, nonce='01'*16,
                        iterations=1, context='fixture')
        elif path == '/api/auth/login':
            self.authentications += 1
            data = {'ok': True}
        else:
            self.requests += 1
            if self.failures:
                raise self.failures.pop(0)
            data = {'ok': True}
        return io.BytesIO(json.dumps(data).encode())


class Sessions(unittest.TestCase):
    def exercise(self, failures, expected=None):
        client = Client(failures)
        with patch.dict('os.environ', TEST_DEVICE_PASSWORD='fixture-only-not-a-secret'), \
             patch('urllib.request.build_opener', return_value=client):
            api = login('board.invalid')
            if expected:
                with self.assertRaises(expected):
                    api('/api/snmp', {'enabled': False})
            else:
                self.assertTrue(api('/api/snmp', {'enabled': False})['ok'])
        return client

    def test_explicit_401_renews_once(self):
        c = self.exercise([HTTPError('', 401, 'fixture', {}, None)])
        self.assertEqual((c.authentications, c.requests), (2, 2))

    def test_network_error_never_resends_a_write(self):
        c = self.exercise([URLError('fixture')], URLError)
        self.assertEqual((c.authentications, c.requests), (1, 1))

    def test_non_auth_http_error_never_resends(self):
        c = self.exercise([HTTPError('', 503, 'fixture', {}, None)], HTTPError)
        self.assertEqual((c.authentications, c.requests), (1, 1))

    def test_second_401_does_not_loop(self):
        c = self.exercise([HTTPError('', 401, 'fixture', {}, None)]*2, HTTPError)
        self.assertEqual((c.authentications, c.requests), (2, 2))


if __name__ == '__main__':
    unittest.main()
