"""Opt-in startup/policy/restart checks on the owner's reference board.

Keeps private settings/logs in memory. Does not disconnect WiFi or enable an
inactive AP. Posts the existing recovery-only setting, then restarts twice.
"""
import argparse
import time
import urllib.error
from test_snmp_device import login
from test_candidate_ota import snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('--allow-restart', action='store_true', required=True)
    p.add_argument('--expected-version', required=True)
    p.add_argument('--tailnet-host')
    args = p.parse_args()
    api = login(args.host)

    def ready(api):
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            status = api('/api/status')
            ts = status['tailscale']
            if ts.get('startup_error') and not ts.get('startup_retrying'):
                raise AssertionError('Unrecovered startup failure: ' + ts['startup_error'])
            if status['sta']['connected'] and ts['connected'] and api('/api/mqtt')['connected']:
                assert api('/api/system')['version'] == args.expected_version
                return status
            time.sleep(3)
        raise AssertionError('WiFi/Tailscale/MQTT startup did not complete')

    ready(api)
    assert api('/api/system')['reset_history'][0]['reason'] in ('FLASH', 'SW'), 'Unexpected candidate panic'
    original = snapshot(api)
    ap_auto = api('/api/network')['ap']['auto_off_when_connected']
    identity = api('/api/tailscale')['runtime'].get('identity_pubkey_prefix')
    assert identity, 'Persistent identity unavailable'
    # No extra AP broadcast or client disconnection: repeat only the already
    # active recovery-only policy, when the radio AP is currently OFF.
    status = api('/api/status')
    if ap_auto and not status['ap']['enabled']:
        for _ in range(8):
            assert api('/api/network', {'ap': {'auto_off_when_connected': True}})['ok']
        time.sleep(3)
        assert not api('/api/status')['ap']['enabled']
        assert api('/api/network')['ap']['auto_off_when_connected'] == ap_auto
        print('PASS: repeated unchanged AP policy requests coalesce; AP remains OFF', flush=True)
    else:
        print('AP runtime change skipped; existing radio/client state retained', flush=True)

    for cycle in range(2):
        before = api('/api/status')['uptime_s']
        while before < 10:
            time.sleep(2)
            before = api('/api/status')['uptime_s']
        start = time.monotonic()
        assert api('/api/system/restart', {})['ok']
        # Post once; detect the new boot without repeating an ambiguous restart.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            time.sleep(3)
            try:
                candidate = login(args.host)
                if candidate('/api/status')['uptime_s'] < before:
                    api = candidate
                    break
            except (OSError, ValueError, AssertionError):
                continue
        else:
            raise AssertionError('New software boot was not observed')
        ready(api)
        system = api('/api/system')
        assert system['reset_history'][0]['reason'] == 'SW'
        assert api('/api/tailscale')['runtime'].get('identity_pubkey_prefix') == identity
        assert snapshot(api) == original, 'Saved settings changed; private values are not displayed'
        assert api('/api/network')['ap']['auto_off_when_connected'] == ap_auto
        old_log = api('/api/log/precrash')['text']
        assert 'could not create AP policy worker' not in old_log
        live_log = api('/api/log/raw')['data']
        assert 'Failed to create wg_mgr task' not in live_log
        if args.tailnet_host:
            tailnet = login(args.tailnet_host)
            assert tailnet('/api/system')['version'] == args.expected_version
            assert tailnet('/api/status')['tailscale']['connected']
        print(f'PASS: software restart {cycle+1}/2; WiFi/Tailscale/MQTT ready in '
              f'{time.monotonic()-start:.0f}s, same identity/configuration; '
              f'shutdown marker recorded={"shutdown=1" in old_log}', flush=True)
    print('PASS: startup/restart recovery; no credential/configuration/log dump written', flush=True)


if __name__ == '__main__':
    main()
