"""Opt-in owned-board test: keep active sessions during additional logins.

May evict inactive sessions at the existing four-session limit. Does not
change the password/timeout or persist credentials, cookies or API bodies.
"""
import argparse
from test_snmp_device import login
from test_candidate_ota import snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('--allow-session-test', action='store_true', required=True)
    p.add_argument('--expected-version', required=True)
    args = p.parse_args()
    clients = []
    try:
        first = login(args.host)
        clients.append(first)
        assert first('/api/system')['version'] == args.expected_version
        assert first('/api/auth/status')['auth_required'], 'Authentication must be enabled for this regression'
        assert first('/api/system')['session_timeout_s'] == 0, 'This test targets disabled timeout'
        original = snapshot(first)
        second = login(args.host)
        clients.append(second)
        for _ in range(8):
            # Auth status never automatically logs in. False means the active
            # token really was evicted; renewal cannot mask that defect.
            assert first('/api/auth/status')['authenticated']
            assert second('/api/auth/status')['authenticated']
            extra = login(args.host)
            clients.append(extra)
            assert first('/api/auth/status')['authenticated'], 'Active first session evicted'
            assert second('/api/auth/status')['authenticated'], 'Active second session evicted'
            assert extra('/api/auth/status')['authenticated']
        assert snapshot(first) == original
        assert first('/api/system')['session_timeout_s'] == 0
        print('PASS: eight additional logins preserve two active no-timeout sessions and saved settings', flush=True)
    finally:
        for api in clients:
            assert api('/api/auth/logout', {})['ok']
        print('Test sessions logged out; no password/timeout change', flush=True)


if __name__ == '__main__':
    main()
