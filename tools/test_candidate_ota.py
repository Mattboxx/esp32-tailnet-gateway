"""Explicitly authorized candidate OTA; compare saved settings in memory only.

Requires --allow-update and a pinned image hash. Upload once, then poll the
version; never retry an ambiguous upload or print/save private API responses.
This test reboots the board but does not erase its NVS or change configuration.
"""
import argparse
import hashlib
from pathlib import Path
import time
from test_snmp_device import login


def snapshot(api):
    fields = {
        '/api/system': ('web_port', 'web_auth_enabled', 'session_timeout_s', 'device_name'),
        '/api/mqtt': ('enabled', 'uri', 'base_topic', 'interval_seconds'),
        '/api/ntfy': ('enabled', 'server', 'topic', 'info_enabled', 'commands_enabled',
                      'commands_only_when_tailscale_down', 'poll_interval_seconds'),
    }
    saved = {path: {key: value for key, value in api(path).items() if key in keys}
             for path, keys in fields.items()}
    for path in ('/api/wol', '/api/portmap', '/api/dhcp/reservations', '/api/mac/denylist'):
        saved[path] = api(path)
    rules = api('/api/tailnet-forward')['rules']
    config = ('name', 'enabled', 'protocol', 'listen_port', 'tailnet_destination',
              'destination_port', 'allowed_source_subnet')
    saved['/api/tailnet-forward'] = [{key: rule[key] for key in config} for rule in rules]
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--allow-update', action='store_true', required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--expected-version', required=True)
    args = parser.parse_args()
    image = args.image.read_bytes()
    assert hashlib.sha256(image).hexdigest() == args.sha256.lower(), 'Image hash changed'
    assert args.expected_version.encode() in image, 'Wrong candidate version'
    api = login(args.host)
    before = api('/api/system')['version']
    assert before != args.expected_version, 'Candidate already installed; refusing duplicate OTA'
    original = snapshot(api)
    started = time.monotonic()
    print('Uploading the pinned candidate once; settings remain on the board', flush=True)
    try:
        result = api('/api/system/ota', image, raw=True, timeout=180)
        assert result.get('ok') and result.get('reboot_required'), 'OTA was not accepted'
        print('OTA accepted; waiting for its automatic reboot', flush=True)
    except (OSError, TimeoutError):
        print('Upload response unavailable; checking version without resubmitting', flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            candidate = login(args.host)
            if candidate('/api/system')['version'] != args.expected_version:
                continue
            api = candidate
            break
        except (OSError, ValueError, AssertionError):
            continue
    else:
        raise RuntimeError('Candidate did not appear; upload was not repeated')
    current = snapshot(api)
    assert current == original, 'Saved settings changed; private values are not displayed'
    print(f'PASS: exact candidate booted in {time.monotonic()-started:.0f}s; '
          f'{len(original)} saved-setting groups unchanged; no private snapshot written', flush=True)


if __name__ == '__main__':
    main()
