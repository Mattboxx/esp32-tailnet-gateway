"""Remove only this campaign's two precisely identified disposable echo rules.

Opt-in owned-board cleanup, not a general rule deletion tool. Refuses drift;
all owner configuration stays in memory and is compared after the save.
"""
import argparse
import getpass
import ipaddress
from observe_candidate import host
from test_snmp_device import login

FIELDS = ('name', 'enabled', 'protocol', 'listen_port', 'tailnet_destination',
          'destination_port', 'allowed_source_subnet')


def cleanup(api, expected_version, destination):
    assert api('/api/status')['version'] == expected_version
    before = [{key: row[key] for key in FIELDS} for row in api('/api/tailnet-forward')['rules']]
    lab = {('lab-tcp', 'tcp', 18830), ('lab-udp', 'udp', 18831)}
    removed, retained = [], []
    for row in before:
        if (row['name'], row['protocol'], row['listen_port']) in lab:
            assert row['tailnet_destination'] == destination and row['destination_port'] == 47001, 'Lab rule drift; cleanup refused'
            removed.append(row)
        else:
            assert not row['name'].startswith('lab-'), 'Unexpected lab rule; cleanup refused'
            retained.append(row)
    assert len(removed) == 2 and len(retained) == 1, 'Campaign table changed; cleanup refused'
    assert len({(r['name'], r['protocol'], r['listen_port']) for r in removed}) == 2
    # Re-read before mutation; no timer/owner state is erased or rewritten.
    assert [{key: row[key] for key in FIELDS} for row in api('/api/tailnet-forward')['rules']] == before
    assert api('/api/tailnet-forward', {'rules':retained})['ok']
    after = [{key: row[key] for key in FIELDS} for row in api('/api/tailnet-forward')['rules']]
    assert after == retained, 'Cleanup verification failed; inspect locally'
    print('PASS: two disposable echo rules removed; original owner rule unchanged', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=host)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-destination', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--allow-lab-cleanup', required=True, action='store_true')
    args = parser.parse_args()
    password = getpass.getpass('Device password (not saved): ')
    api = login(args.host, password=password)
    password = None
    try:
        cleanup(api, args.expected_version, str(args.expected_destination))
    finally:
        api('/api/auth/logout', {})


if __name__ == '__main__':
    main()
