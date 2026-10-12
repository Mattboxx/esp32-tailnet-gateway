"""Opt-in owned-board tunnel probe; private values remain in memory.

Temporarily enable read-only SNMP to compare tunnel RX/TX counters around one
HTTP request. Always restore the original agent configuration. No raw log,
community, account name, endpoint list or credential is printed or saved.
"""
import argparse
import socket
import time
import urllib.request
from test_snmp_device import login, request, decode_reply


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('tailnet_host')
    p.add_argument('--allow-temporary-enable', action='store_true', required=True)
    args = p.parse_args()
    api = login(args.host)
    original = api('/api/snmp')
    assert not original['enabled'], 'Agent already enabled; refusing to change it'
    config = {k: original[k] for k in ('enabled', 'community', 'sys_name', 'sys_contact', 'sys_location')}
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(3)

    def counters():
        values = []
        for column in (10, 11, 16, 17):
            oid = [1, 3, 6, 1, 2, 1, 2, 2, 1, column, 3]
            udp.sendto(request(config['community'], oid), (args.host, 161))
            data, _ = udp.recvfrom(4096)
            result = decode_reply(data)
            assert result[0] == oid
            values.append(int.from_bytes(result[2], 'big'))
        return values

    try:
        assert api('/api/snmp', dict(config, enabled=True))['ok']
        time.sleep(3)
        before = counters()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with client.open('http://' + args.tailnet_host + '/api/auth/challenge', timeout=8) as response:
                assert response.status == 200
                response.read(4096)
                print('PASS: real HTTP over Tailnet', flush=True)
        except OSError:
            print('FAIL: real HTTP over Tailnet timed out or failed', flush=True)
        after = counters()
        print('Tunnel counter deltas (RX bytes/packets, TX bytes/packets):',
              [(a-b) & 0xffffffff for a, b in zip(after, before)], flush=True)
    finally:
        udp.close()
        assert api('/api/snmp', config)['ok']
        restored = api('/api/snmp')
        assert all(restored[k] == v for k, v in config.items())
        print('PASS: SNMP restored OFF with original configuration', flush=True)


if __name__ == '__main__':
    main()
