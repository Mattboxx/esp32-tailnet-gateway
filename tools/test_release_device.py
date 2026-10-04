"""Bounded authenticated hardware/API smoke and soak; never writes settings.

Option --test-notification sends a generic ntfy test and queues MQTT state.
Secrets and private response values are never printed or saved.
"""
import argparse
import time
import urllib.error
import urllib.request
from test_snmp_device import login


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--test-notification', action='store_true')
    parser.add_argument('--expected-version', default='0.1.29-Mattboxx-1.8')
    args = parser.parse_args()
    anonymous = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    paths = ('/api/status', '/api/network', '/api/tailscale', '/api/firewall',
             '/api/wol', '/api/mqtt', '/api/ntfy', '/api/tailnet-forward',
             '/api/portmap', '/api/snmp', '/api/system', '/api/system/diag',
             '/api/dhcp/leases', '/api/dhcp/reservations', '/api/mac/denylist')
    for path in paths:
        try:
            anonymous.open('http://' + args.host + path, timeout=5)
            raise AssertionError('Unauthenticated protected endpoint accepted: ' + path)
        except urllib.error.HTTPError as error:
            assert error.code == 401, (path, error.code)
    with anonymous.open('http://' + args.host + '/favicon.ico', timeout=5) as response:
        assert response.headers['Content-Type'] == 'image/svg+xml'
    print('PASS: 15 protected GET endpoints reject unauthenticated access; favicon is served')
    api = login(args.host)
    for path in paths:
        assert isinstance(api(path), (dict, list)), path
    system = api('/api/system')
    assert system['version'] == args.expected_version
    assert not api('/api/snmp')['enabled']
    print('PASS: all protected endpoints load after login; correct release; SNMP OFF')
    if args.test_notification:
        assert api('/api/ntfy/test', {})['ok']
        assert api('/api/ntfy')['last_publish_ok']
        assert api('/api/mqtt/publish', {})['ok']
        print('PASS: ntfy server accepted test notification; MQTT status queued')
    previous = api('/api/status')['uptime_s']
    baseline_heap = None
    minimum_heap = 2**32
    start = time.monotonic()
    samples = 0
    while time.monotonic() - start < args.seconds:
        time.sleep(5)
        state = api('/api/status')
        assert state['uptime_s'] > previous, 'Unexpected restart or frozen uptime'
        previous = state['uptime_s']
        assert state['sta']['connected']
        assert state['tailscale']['connected']
        assert 0 <= state['cpu_load_pct'] <= 100
        assert -10 < state['cpu_temp_c'] < 100
        assert api('/api/mqtt')['connected']
        assert api('/api/ntfy')['enabled']
        heap = state['mem_internal_free']
        if baseline_heap is None:
            baseline_heap = heap
        minimum_heap = min(minimum_heap, heap)
        assert heap > 12000, 'Internal heap fell below the smoke-test reserve'
        samples += 1
        if samples % 12 == 0:
            print(f'PASS: {time.monotonic()-start:.0f}s uptime/network/integration soak ({samples} samples)', flush=True)
    print(f'PASS: {samples} samples without reboot, uplink/tunnel loss or integration disconnect; internal heap minimum {minimum_heap} B')


if __name__ == '__main__':
    main()
