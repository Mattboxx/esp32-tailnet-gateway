"""Explicitly authorized candidate OTA; compare saved settings in memory only.

Requires --allow-update and a pinned image hash. Upload once, then poll the
version; never retry an ambiguous upload or print/save private API responses.
This test reboots the board but does not erase its NVS or change configuration.
"""
import argparse
import getpass
import hashlib
from pathlib import Path
import time
import urllib.error
from test_snmp_device import login


def ota_target(diag, expected_running, protected, image_size):
    """Explicit 2.x/3.x layouts; never infer an inactive slot's geometry."""
    rows = [p for p in diag.get('partitions', []) if p.get('name', '').startswith('ota_')]
    assert len(rows) == 2 and {p['name'] for p in rows} == {'ota_0','ota_1'}, 'Unknown OTA layout'
    actual = {row['name']: (row['offset'], row['size']) for row in rows}
    known = ({'ota_0': (0x20000, 0x1e0000), 'ota_1': (0x200000, 0x1e0000)},
             {'ota_0': (0x20000, 0x380000), 'ota_1': (0x3a0000, 0x380000)})
    assert actual in known, 'Unknown or mixed OTA layout'
    assert 0 < image_size <= min(row['size'] for row in rows), 'Image does not fit'
    running = [p for p in rows if p.get('running')]
    boot = [p for p in rows if p.get('bootnext')]
    assert len(running) == len(boot) == 1 and running[0] == boot[0], 'Pending/unknown boot selection'
    assert running[0]['name'] == expected_running, 'Unexpected running partition'
    target = next(p['name'] for p in rows if not p.get('running'))
    assert target != protected, 'Refusing to overwrite the protected stable slot'
    return target


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
    parser.add_argument('--expected-running-version', required=True)
    parser.add_argument('--expected-running-slot', choices=('ota_0','ota_1'), required=True)
    parser.add_argument('--protected-slot', choices=('ota_0','ota_1'), required=True)
    parser.add_argument('--prompt-password', action='store_true')
    parser.add_argument('--lan-source')
    parser.add_argument('--interface-index', type=int)
    args = parser.parse_args()
    image = args.image.read_bytes()
    assert hashlib.sha256(image).hexdigest() == args.sha256.lower(), 'Image hash changed'
    assert args.expected_version.encode() in image, 'Wrong candidate version'
    password = getpass.getpass('Device password (not saved): ') if args.prompt_password else None
    def connect():
        return login(args.host, password=password, source_ip=args.lan_source, interface_index=args.interface_index)
    api = connect()
    before = api('/api/system')['version']
    assert before == args.expected_running_version, 'Unexpected starting firmware'
    assert before != args.expected_version, 'Candidate already installed; refusing duplicate OTA'
    ota_target(api('/api/system/diag'), args.expected_running_slot, args.protected_slot, len(image))
    original = snapshot(api)
    started = time.monotonic()
    print('Uploading the pinned candidate once; settings remain on the board', flush=True)
    try:
        result = api('/api/system/ota', image, raw=True, timeout=180)
        assert result.get('ok') and result.get('reboot_required'), 'OTA was not accepted'
        print('OTA accepted; waiting for its automatic reboot', flush=True)
    except urllib.error.HTTPError as error:
        print(f'OTA rejected with HTTP {error.code}; upload was not repeated', flush=True)
        raise RuntimeError(f'OTA request rejected with HTTP {error.code}') from None
    except (OSError, TimeoutError):
        print('Upload response unavailable; checking version without resubmitting', flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            candidate = connect()
            if candidate('/api/system')['version'] != args.expected_version:
                continue
            api = candidate
            break
        except (OSError, ValueError, AssertionError):
            continue
    else:
        raise RuntimeError('Candidate did not appear; upload was not repeated')
    # Startup radio/HTTP transitions can close a read without rejecting OTA.
    # Retry read-only verification, never the image upload.
    verify_until = time.monotonic() + 45
    while True:
        try:
            current = snapshot(api)
            break
        except OSError:
            if time.monotonic() >= verify_until:
                raise
            time.sleep(3)
            api = connect()
    assert api('/api/system')['reset_history'][0]['reason'] in ('FLASH', 'SW'), \
        'Candidate suffered an unexpected reset after OTA'
    assert current == original, 'Saved settings changed; private values are not displayed'
    print(f'PASS: exact candidate booted in {time.monotonic()-started:.0f}s; '
          f'{len(original)} saved-setting groups unchanged; no private snapshot written', flush=True)


if __name__ == '__main__':
    main()
