"""Read-only route diagnostics before/after OTA, with synthetic addresses only.

The record contains interface labels and test-case IDs, not peers or credentials.
It checks diagnostic parity on this configured board, not forwarded traffic.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from test_snmp_device import login


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--record', type=Path)
    group.add_argument('--compare', type=Path)
    args = parser.parse_args()
    api = login(args.host)
    destinations = ('100.64.0.1', '100.127.255.254', '10.10.1.1', '172.16.1.1',
                    '172.31.255.254', '192.168.1.1', '192.168.4.2', '192.168.99.1',
                    '198.51.100.7', '203.0.113.7')
    labels = {}
    for source in ('0.0.0.0', '192.168.4.123'):
        for destination in destinations:
            params = urlencode({'src': source, 'dst': destination})
            result = api('/api/tools/route?' + params)
            assert isinstance(result['reason'], str) and result['reason']
            assert isinstance(result['netif'], str) and result['netif']
            labels[params] = result['netif']
    if args.record:
        args.record.write_text(json.dumps(labels, indent=2) + '\n', encoding='ascii')
        print('PASS: recorded 20 read-only route decisions using synthetic addresses')
    else:
        assert labels == json.loads(args.compare.read_text(encoding='ascii')), 'Route diagnostic decisions changed'
        print('PASS: 20 route diagnostic interface decisions unchanged after OTA')


if __name__ == '__main__':
    main()
