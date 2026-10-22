"""Offline checks for session renewal used by opt-in hardware tests."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from test_snmp_device import login, request, packet_identifier, receive_matching


class Client:
    def __init__(self, failures):
        self.failures = list(failures)
        self.authentications = 0
        self.requests = 0
        self.seen_headers = []

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
            self.seen_headers.append(dict(request.header_items()))
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

    def test_explicit_password_needs_no_environment_secret(self):
        client = Client([])
        with patch.dict('os.environ', {}, clear=True), \
             patch('urllib.request.build_opener', return_value=client):
            api = login('board.invalid', password='fixture-only-not-a-secret')
            self.assertTrue(api('/api/system')['ok'])
        self.assertEqual(client.authentications, 1)

    def test_network_error_never_resends_a_write(self):
        c = self.exercise([URLError('fixture')], URLError)
        self.assertEqual((c.authentications, c.requests), (1, 1))

    def test_request_screening_headers_preserved_on_explicit_401_retry(self):
        client = Client([HTTPError('', 401, 'fixture', {}, None)])
        with patch('urllib.request.build_opener', return_value=client):
            api = login('board.invalid', password='fixture-only-not-a-secret')
            api('/api/operations', {'invalid': True}, request_headers={'Origin':'http://board.invalid'})
        self.assertEqual(len(client.seen_headers), 2)
        for headers in client.seen_headers:
            self.assertEqual(headers['Origin'], 'http://board.invalid')
            self.assertEqual(headers['Content-type'], 'application/json')

    def test_non_auth_http_error_never_resends(self):
        c = self.exercise([HTTPError('', 503, 'fixture', {}, None)], HTTPError)
        self.assertEqual((c.authentications, c.requests), (1, 1))

    def test_second_401_does_not_loop(self):
        c = self.exercise([HTTPError('', 401, 'fixture', {}, None)]*2, HTTPError)
        self.assertEqual((c.authentications, c.requests), (2, 2))

    def test_udp_ids_are_distinct_and_positive(self):
        with patch('test_snmp_device._request_sequence', 126):
            first = request('fixture', [1, 3, 6, 1])
            second = request('fixture', [1, 3, 6, 1])
        self.assertEqual(packet_identifier(first), 127)
        self.assertEqual(packet_identifier(second), 128)

    def test_late_udp_reply_is_not_the_next_walk_response(self):
        old = request('fixture', [1, 3, 6, 1])
        current = request('fixture', [1, 3, 6, 1])

        class UDP:
            replies = [old, current]
            def settimeout(self, timeout):
                assert 0 < timeout <= 1
            def recvfrom(self, size):
                assert size == 4096
                return self.replies.pop(0), ('192.0.2.1', 161)

        with patch('socket.gethostbyname', return_value='192.0.2.1'):
            data, _ = receive_matching(UDP(), current, 'board.invalid', 1)
        self.assertEqual(data, current)


if __name__ == '__main__':
    unittest.main()
