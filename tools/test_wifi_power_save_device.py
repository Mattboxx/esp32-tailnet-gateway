"""Opt-in WiFi-policy live/persistence check. Restores the original policy.

Own device only. Does not print credentials, routes or private settings.
Temporarily enables modem sleep and reboots twice to verify persistence.
"""
import argparse
import time
import urllib.error
from test_snmp_device import login
from test_candidate_ota import snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--allow-change-and-restart', action='store_true', required=True)
    parser.add_argument('--expected-version', required=True)
    args = parser.parse_args()
    api = login(args.host)
    system = api('/api/system')
    assert system['version'] == args.expected_version
    original = system['wifi_power_save']
    saved = snapshot(api)

    def check_policy(expected):
        state = api('/api/system')
        assert state['wifi_power_save'] is expected
        assert state['wifi_power_save_known'] and state['wifi_power_save_active'] is expected

    def restart_and_wait(expected):
        nonlocal api
        assert api('/api/system/restart', {})['ok']
        time.sleep(8)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            try:
                api = login(args.host)
                state = api('/api/status')
                system = api('/api/system')
                if state['uptime_s'] < 150 and state['sta']['connected'] and \
                        state['tailscale']['connected'] and api('/api/mqtt')['connected']:
                    assert system['version'] == args.expected_version
                    assert system['reset_history'][0]['reason'] == 'SW'
                    check_policy(expected)
                    assert snapshot(api) == saved
                    print('PASS: WiFi policy persists across software restart; Tailnet HTTP and MQTT recover; other saved settings unchanged', flush=True)
                    return
            except (OSError, ValueError):
                pass
            time.sleep(4)
        raise RuntimeError('Board did not recover after controlled restart')

    try:
        before = api('/api/status')['uptime_s']
        try:
            api('/api/system', {'wifi_power_save': 'false'})
            raise AssertionError('Non-boolean policy accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 400
        check_policy(original)
        assert api('/api/system', {'wifi_power_save': not original})['ok']
        check_policy(not original)
        assert api('/api/status')['uptime_s'] >= before
        print('PASS: strict boolean input and live policy change without restart', flush=True)
        restart_and_wait(not original)
    finally:
        api = login(args.host)
        assert api('/api/system', {'wifi_power_save': original})['ok']
        check_policy(original)
        print('Restored original WiFi power-save policy', flush=True)
    restart_and_wait(original)


if __name__ == '__main__':
    main()
