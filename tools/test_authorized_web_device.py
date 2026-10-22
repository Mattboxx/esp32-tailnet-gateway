"""Opt-in owned-board session/request-screening checks; no settings writes.

Only invalid configuration bodies are submitted: a screening regression must
not restart, reconfigure or expose the board. Test credentials/cookies and
responses remain in memory. Not a browser-origin or two-principal policy test.
"""
import argparse
import getpass
import urllib.error
import urllib.request
from observe_candidate import host
from test_snmp_device import login


def denied(call, code):
    try:
        call()
    except urllib.error.HTTPError as error:
        assert error.code == code, f'Expected HTTP {code}, got {error.code}'
        return
    raise AssertionError(f'Expected HTTP {code}, request accepted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=host)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--allow-session-test', action='store_true', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Device password (not saved): ')
    api = login(args.host, password=password)
    password = None
    try:
        before = api('/api/status')
        assert before['version'] == args.expected_version
        assert api('/api/auth/status')['auth_required']
        assert api('/api/auth/status')['authenticated']
        print('PASS: challenge login and authenticated reads on expected firmware', flush=True)
        anonymous = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        paths = ('/api/status', '/api/tailnet-forward', '/api/operations',
                 '/api/service-watch', '/api/capabilities', '/api/diagnostics/export')
        for path in paths:
            denied(lambda: anonymous.open('http://' + args.host + path, timeout=6), 401)
        print('PASS: six sensitive read endpoints refuse anonymous access', flush=True)
        for headers in ({'Origin': 'http://qualification.invalid'},
                        {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}):
            for path in ('/api/operations', '/api/service-watch', '/api/tailnet-forward'):
                denied(lambda: api(path, {'__qualification_invalid': True}, request_headers=headers), 403)
            denied(lambda: api('/api/auth/logout', {}, request_headers=headers), 403)
            assert api('/api/auth/status')['authenticated']
        print('PASS: cross-origin, opaque-origin and cross-site requests refused with live session retained', flush=True)
        # Native authenticated GETs deliberately support custom DNS names.
        # Writes with an Origin must match Host; open/no-password access also
        # requires a trusted Host. Do not mistake an injected valid session on
        # a native GET for browser cookie-domain or DNS-rebinding coverage.
        denied(lambda: api('/api/operations', {'__qualification_invalid': True},
                           request_headers={'Host': 'qualification.invalid',
                                            'Origin': 'http://' + args.host}), 403)
        denied(lambda: api('/api/operations', {'__qualification_invalid': True},
                           request_headers={'Origin': 'http://' + args.host}), 400)
        assert api('/api/auth/status')['authenticated']
        assert api('/api/status')['uptime_s'] >= before['uptime_s']
        print('PASS: Host/Origin mismatch refused, valid-origin invalid body rejected; session/uptime retained', flush=True)
    finally:
        assert api('/api/auth/logout', {})['ok']
        assert not api('/api/auth/status')['authenticated']
        print('Test session logged out; no configuration/restart action submitted', flush=True)


if __name__ == '__main__':
    main()
