"""Explicit owned-board lab: echo, source refusal, expiry, reboot and watch.

Requires one original rule, no active profile/backup and Service Watch OFF.
Starts no server: provide an owned TCP+UDP echo peer on the specified port.
Preserves the original rule, watch settings and profile; never edits Tailnet
policy or credentials. Not a two-client identity/ACL or forced-DERP test.
"""
import argparse
import contextlib
import getpass
import ipaddress
import json
from pathlib import Path
import time
from cleanup_gateway_lab_device import FIELDS, cleanup
from lab_echo import probe
from observe_candidate import host
from test_candidate_ota import snapshot
from test_snmp_device import login


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', required=True, type=host)
    p.add_argument('--source', required=True, type=ipaddress.IPv4Address)
    p.add_argument('--interface-index', type=int)
    p.add_argument('--destination', required=True, type=ipaddress.IPv4Address)
    p.add_argument('--port', type=int, default=47001, choices=(47001,))
    p.add_argument('--expected-version', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--allow-lab-test', required=True, action='store_true')
    a = p.parse_args()
    private = Path(__file__).resolve().parents[1]/'build/private-device'
    if not a.output.resolve().is_relative_to(private.resolve()) or a.output.exists():
        p.error('Use a new report under ignored build/private-device/')
    if a.destination not in ipaddress.ip_network('100.64.0.0/10') or not 1 <= a.port <= 65535:
        p.error('Provide the owned echo peer Tailnet IP and port')
    password = getpass.getpass('Device password (not saved): ')
    api = login(a.host, password=password, source_ip=str(a.source), interface_index=a.interface_index)
    password = None
    def rules():
        return [{k:r[k] for k in FIELDS} for r in api('/api/tailnet-forward')['rules']]
    original = rules()
    assert len(original)==1 and not original[0]['name'].startswith('lab-')
    assert api('/api/status')['version']==a.expected_version
    original_config = snapshot(api)
    original_watch = api('/api/service-watch')
    assert not original_watch['enabled']
    profile = api('/api/profiles')
    assert profile['active']=='none' and not profile['rollback_available']
    labs = [dict(name='lab-'+proto, enabled=False, protocol=proto, listen_port=18830+i,
                 tailnet_destination=str(a.destination), destination_port=a.port,
                 allowed_source_subnet=str(a.source)+'/32') for i,proto in enumerate(('tcp','udp'))]
    changed = watch_changed = profile_changed = False
    results = {'real_tailnet_clients':1, 'independent_identity_acl_test':False,
               'forced_stream_loss_test':False, 'forced_derp_test':False}
    def save():
        nonlocal changed
        assert rules()[0]==original[0], 'Concurrent owner edit'
        changed = True  # Mark before an ambiguous response can occur.
        assert api('/api/tailnet-forward', {'rules':original+labs})['ok']
    def arm(tcp=180,udp=600):
        leases = api('/api/service-leases')
        for index,seconds in ((1,tcp),(2,udp)):
            lease = next(l for l in leases if l['index']==index)
            assert api('/api/operations',dict(action='lease',index=index,rule_token=lease['rule_token'],
                seconds=seconds,permanent=False,delete_on_expiry=False))['ok']
    def probes(proto,count,expected):
        port=18830 if proto=='tcp' else 18831
        with contextlib.redirect_stdout(None):
            seen=probe(a.host+':'+str(port),proto,count,str(a.source),a.interface_index,2)
        assert seen==expected, f'{proto}: expected {expected}/{count}, saw {seen}'
    try:
        save()
        for proto in ('tcp','udp'): probes(proto,1,0)
        results['disabled_tcp_udp_refused']=True
        for row in labs: row['enabled']=True
        save();arm()
        for proto in ('tcp','udp'): probes(proto,20,20)
        results['tcp_echoes']=results['udp_echoes']=20
        print('PASS forced-LAN TCP 20/20, UDP 20/20; disabled rules refused',flush=True)
        for row in labs: row['allowed_source_subnet']='192.0.2.123/32'
        save();arm()
        for proto in ('tcp','udp'): probes(proto,3,0)
        assert all(r['diagnostic']['code']=='source_rejected' for r in api('/api/tailnet-forward')['rules'][1:])
        results['same_client_cidr_denial']=True
        print('PASS same-client source denial and actual refusal diagnosis',flush=True)
        for row in labs: row['allowed_source_subnet']=str(a.source)+'/32'
        save();arm(tcp=60)
        for proto in ('tcp','udp'): probes(proto,2,2)
        # Advanced changes only profile metadata, not monitoring/exposure.
        preview=api('/api/profiles?preview=advanced')['preview']
        assert not preview['changes']
        profile_changed=True
        assert api('/api/profiles',dict(action='apply',profile='advanced',token=preview['token']))['ok']
        watch_changed=True
        api('/api/service-watch',dict(enabled=True,notify=False,interval_s=60))
        assert api('/api/service-watch')['enabled']
        time.sleep(65)
        probes('tcp',2,0);probes('udp',2,2)
        results['expiry_with_udp_control']=True
        before=api('/api/status')['uptime_s']
        # Submit exactly once. Even a lost reply may mean restart was accepted.
        try:
            assert api('/api/system/restart',{})['ok']
        except OSError:
            pass
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            try:
                state=api('/api/status')
                if state['uptime_s']<before and state['tailscale']['connected'] and api('/api/operations')['authority_ready']:
                    break
            except OSError:
                pass
            time.sleep(2)
        else: raise TimeoutError('Restart/authority not observed')
        assert rules()==original+labs
        leases=api('/api/service-leases')
        assert not next(l for l in leases if l['index']==1)['effective_enabled']
        assert next(l for l in leases if l['index']==2)['effective_enabled']
        probes('tcp',2,0);probes('udp',2,2)
        assert api('/api/profiles')['active']=='advanced' and api('/api/profiles')['rollback_available']
        assert api('/api/service-watch')['enabled']
        results['reboot_rule_profile_watch_persistence']=True
        results['reboot_expired_tcp_closed_udp_live']=True
        print('PASS reboot: expired TCP closed, UDP lease works, rule/profile/watch settings persist',flush=True)
        deadline=time.monotonic()+155
        while time.monotonic()<deadline:
            check=api('/api/tailnet-forward')['rules'][1].get('destination_check',{})
            if check.get('state')=='reachable':
                results['automatic_service_watch_tcp_reachable']=True
                break
            time.sleep(6)
        else:
            results['service_watch_last_state']=check.get('state','not_tested')
            raise TimeoutError('Owned TCP service not verified by automatic watch')
        print('PASS automatic Service Watch reached the owned TCP echo service',flush=True)
    finally:
        # Recover read-only first; do not blindly resend ambiguous writes.
        deadline=time.monotonic()+90
        while True:
            try:
                assert api('/api/status')['version']==a.expected_version
                break
            except OSError:
                if time.monotonic()>=deadline: raise
                time.sleep(3)
        if watch_changed:
            api('/api/service-watch',original_watch)
            assert api('/api/service-watch')==original_watch
        if profile_changed:
            current=api('/api/profiles')
            if current['active']=='advanced' and current['rollback_available']:
                assert api('/api/profiles',dict(action='rollback'))['ok']
            assert api('/api/profiles')['active']=='none'
        if changed:
            cleanup(api,a.expected_version,str(a.destination))
        assert snapshot(api)==original_config
        results['original_configuration_restored']=True
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf-8') as report:
            json.dump(results,report,indent=2)
        api('/api/auth/logout',{})
        print('RESTORED original rule/settings, profile none and Service Watch OFF',flush=True)


if __name__=='__main__': main()
