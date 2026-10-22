"""Offline guard tests for the opt-in hardware lab cleanup tool."""
import copy
import unittest
from cleanup_gateway_lab_device import cleanup

VERSION = 'fixture-dev'
DEST = '100.64.0.2'


def rule(name, protocol, port):
    return dict(name=name, enabled=True, protocol=protocol, listen_port=port,
                tailnet_destination=DEST, destination_port=47001,
                allowed_source_subnet='192.0.2.42/32')


class API:
    def __init__(self):
        self.rules = [rule('owner', 'tcp', 5678), rule('lab-tcp', 'tcp', 18830), rule('lab-udp', 'udp', 18831)]
        self.writes = 0
        self.reads = 0
        self.drift = False

    def __call__(self, path, body=None):
        if path == '/api/status':
            return {'version':VERSION}
        assert path == '/api/tailnet-forward'
        if body is not None:
            self.writes += 1
            self.rules = copy.deepcopy(body['rules'])
            return {'ok':True}
        self.reads += 1
        rows = copy.deepcopy(self.rules)
        if self.drift and self.reads == 2:
            rows[0]['enabled'] = False
        return {'rules':rows}


class Cleanup(unittest.TestCase):
    def test_preserves_exact_owner_binding_and_enabled_state(self):
        api = API()
        api.rules[0]['enabled'] = False
        original = copy.deepcopy(api.rules[0])
        cleanup(api, VERSION, DEST)
        self.assertEqual(api.writes, 1)
        self.assertEqual(api.rules, [original])

    def test_refuses_incomplete_or_unexpected_table(self):
        for change in ('missing', 'extra', 'destination', 'port', 'source-drift'):
            api = API()
            if change == 'missing': api.rules.pop()
            elif change == 'extra': api.rules.append(rule('another-owner', 'tcp', 9000))
            elif change == 'destination': api.rules[1]['tailnet_destination'] = '100.64.0.3'
            elif change == 'port': api.rules[2]['destination_port'] = 9000
            else: api.drift = True
            with self.assertRaises(AssertionError): cleanup(api, VERSION, DEST)
            self.assertEqual(api.writes, 0)


if __name__ == '__main__': unittest.main()
