"""Opt-in ntfy HTTPS/info regression on your own configured board.

Temporarily allows commands while Tailscale is connected, then restores that
setting. Publishes generic info commands to the user's configured endpoint.
Does not print/save topics, tokens, private responses or device credentials.
Does not send WOL or deliberately disconnect WiFi/Tailscale.
"""
import argparse
import json
import re
import time
import urllib.request
from test_snmp_device import login


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--commands', type=int, default=5)
    parser.add_argument('--expect-network-policy', action='store_true')
    args = parser.parse_args()
    api = login(args.host)
    version = api('/api/system')['version']
    assert isinstance(version, str) and version, 'Missing running firmware version'
    deadline = time.monotonic() + 120
    while True:
        state = api('/api/status')
        if state['sta']['connected'] and state['tailscale']['connected'] and api('/api/mqtt')['connected']:
            break
        assert time.monotonic() < deadline, 'Uplink/Tailscale/MQTT did not become ready after boot'
        time.sleep(5)
    print('PASS: uplink, Tailscale and MQTT ready after boot', flush=True)
    original = api('/api/ntfy')
    assert original['enabled'] and original['commands_enabled'] and original['info_enabled']
    assert not original['has_token'], 'Token is write-only; authenticated broker needs a separate publisher'
    assert original['server'].startswith('https://'), 'This regression must exercise TLS'
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    sent = 0
    baseline = original['commands_received']
    baseline_errors = original['command_errors']
    previous = api('/api/status')['uptime_s']
    minimum_stack = 2**32
    minimum_heap = 2**32
    start = time.monotonic()
    next_command = start
    try:
        assert api('/api/ntfy', {'commands_only_when_tailscale_down': False})['ok']
        assert api('/api/ntfy/test', {}, timeout=25)['ok']
        print('PASS: HTTPS test notification accepted', flush=True)
        time.sleep(5)
        while time.monotonic() - start < args.seconds:
            now = time.monotonic()
            ntfy = api('/api/ntfy')
            if sent < args.commands and now >= next_command and ntfy['commands_received'] >= baseline + sent:
                endpoint = original['server'].rstrip('/') + '/' + original['topic']
                request = urllib.request.Request(endpoint, b'info', headers={'Content-Type': 'text/plain'})
                with client.open(request, timeout=20) as response:
                    event = json.loads(response.read(8192))
                    assert event.get('event') == 'message'
                sent += 1
                next_command = time.monotonic() + max(30, original['poll_interval_seconds'] * 2)
                print(f'Published generic info command {sent}/{args.commands}', flush=True)
            state = api('/api/status')
            assert state['uptime_s'] > previous, 'Unexpected restart/frozen uptime'
            previous = state['uptime_s']
            assert state['sta']['connected'] and state['tailscale']['connected']
            assert api('/api/mqtt')['connected']
            assert ntfy['task_running'] and ntfy['enabled']
            assert ntfy['command_errors'] == baseline_errors, 'Command failed'
            minimum_stack = min(minimum_stack, ntfy['stack_min_free_bytes'])
            minimum_heap = min(minimum_heap, state['mem_internal_free'])
            assert minimum_stack >= 2048, 'Insufficient ntfy stack reserve'
            assert minimum_heap >= 12000, 'Insufficient internal heap reserve'
            time.sleep(5)
        final = api('/api/ntfy')
        assert sent == args.commands and final['commands_received'] >= baseline + sent
        assert final['last_publish_ok'], 'Last info reply was not accepted'
        # Verify replies actually reached the broker without displaying their private body.
        query = original['server'].rstrip('/') + '/' + original['topic'] + '/json?poll=1&since=10m'
        with client.open(query, timeout=20) as response:
            lines = response.read(1024 * 1024).splitlines()
        replies = [json.loads(line) for line in lines if line]
        version_pattern = re.compile(r'(?<![A-Za-z0-9.-])' + re.escape(version) + r'(?![A-Za-z0-9.-])')
        matching = [e for e in replies if e.get('title', '').startswith('ESP32 router info')
                    and version_pattern.search(e.get('message', ''))]
        assert matching
        if args.expect_network_policy:
            assert any('WiFi power save:' in e.get('message', '') and
                       'manual default route:' in e.get('message', '') for e in matching)
        print(f'PASS: {sent} info commands/replies; {time.monotonic()-start:.0f}s without restart; '
              f'minimum stack {minimum_stack} B, internal heap {minimum_heap} B', flush=True)
    finally:
        assert api('/api/ntfy', {'commands_only_when_tailscale_down': original['commands_only_when_tailscale_down']})['ok']
        print('Restored original command availability policy', flush=True)


if __name__ == '__main__':
    main()
