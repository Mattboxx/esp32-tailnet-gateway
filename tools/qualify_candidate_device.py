"""Opt-in qualification of an installed candidate with one hidden password prompt.

Own bench board, own lab broker, synthetic WoL target only. Phases, each
isolated so one failure does not hide the others:
  identity   exact version, running slot, setup mode inactive on a configured
             board, no first-boot access point, RAM/socket/reaper counters
  activation MQTT OFF -> software reboot -> first enable at runtime, three
             ON/OFF cycles with real state delivery (tools/test_mqtt_activation_device)
  lab        MQTT/HA Discovery, strict commands, broker outage, WoL over HTTP
             and MQTT, in-session Wi-Fi/DERP/control reconnect cycles
             (tools/test_mqtt_lab_device)
  observe    read-only samples of status/operations for --observe-minutes
Every phase restores what it changed. Results contain counts, booleans and
metrics only: build/private-device/qualify-<version>-<time>.json.

    python tools/qualify_candidate_device.py <board-tailnet-ip> --expected-version <v> \\
        --bench-ip <pc-tailnet-ip> --wol-lan-ip <pc-lan-ip> --allow-restart --observe-minutes 30
"""
import argparse
import getpass
import json
from pathlib import Path
import time

from test_snmp_device import login
import test_mqtt_activation_device as activation
import test_mqtt_lab_device as lab

ROOT = Path(__file__).resolve().parents[1]
OPS = ('internal_free', 'internal_min', 'internal_largest', 'psram_largest', 'sockets_used',
       'authority_ready', 'control_connected', 'module_restarts',
       'task_reaper_pending', 'task_reaper_reaped', 'task_reaper_fallbacks')


def ops(api):
    o = api('/api/operations', timeout=8)
    return {k: o.get(k) for k in OPS}


def identity(api, a, result):
    system = api('/api/system')
    assert system['version'] == a.expected_version, 'Unexpected firmware version'
    rows = [p for p in api('/api/system/diag').get('partitions', []) if p.get('name', '').startswith('ota_')]
    running = [p['name'] for p in rows if p.get('running')]
    result['running_slot'] = running[0] if len(running) == 1 else None
    assert result['running_slot'] == a.expected_slot, 'Unexpected running slot'
    status = api('/api/auth/status')
    result['setup_mode'] = bool(status.get('setup_mode'))
    assert not result['setup_mode'], 'Configured board must not enter first-boot setup'
    state = api('/api/setup/state')
    assert state.get('setup') is False, 'Setup API must report inactive'
    ap = api('/api/status').get('ap', {})
    result['ap_ssid_is_setup'] = str(ap.get('ssid', '')).startswith('Tailnet-Gateway-Setup-')
    assert not result['ap_ssid_is_setup'], 'Setup SSID on a configured board'
    result['reset_reason'] = system['reset_history'][0]['reason'] if system.get('reset_history') else None
    result['ops'] = ops(api)
    assert result['ops']['task_reaper_fallbacks'] == 0, 'Reaper fell back to the SDK path'


def observe(api, minutes, result, log):
    end = time.monotonic() + minutes * 60
    first = api('/api/status')['uptime_s']
    samples = []
    while time.monotonic() < end:
        row = {'t': round(time.monotonic(), 1)}
        try:
            st = api('/api/status', timeout=8)
            row.update(uptime_s=st['uptime_s'], connected=bool(st.get('tailscale', {}).get('connected')))
            row.update(ops(api))
        except Exception as e:  # class only
            row['error'] = e.__class__.__name__
        samples.append(row)
        log.write(json.dumps(row) + '\n'); log.flush()
        time.sleep(30)
    ok = [s for s in samples if 'error' not in s]
    num = lambda k: [s[k] for s in ok if isinstance(s.get(k), (int, float))]
    result.update(samples=len(samples), errors=len(samples) - len(ok),
                  uptime_monotonic=all(b['uptime_s'] >= a['uptime_s'] for a, b in zip(ok, ok[1:])) and (not ok or ok[0]['uptime_s'] >= first),
                  control_connected=sum(1 for s in ok if s.get('control_connected')),
                  authority_ready=sum(1 for s in ok if s.get('authority_ready')),
                  internal_min=min(num('internal_min'), default=None),
                  internal_free_min=min(num('internal_free'), default=None),
                  internal_largest_min=min(num('internal_largest'), default=None),
                  sockets_max=max(num('sockets_used'), default=None),
                  reaper_fallbacks_max=max(num('task_reaper_fallbacks'), default=None),
                  reaper_pending_max=max(num('task_reaper_pending'), default=None))
    assert result['errors'] == 0 and result['uptime_monotonic'], 'Observation saw errors or a reset'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('host')
    p.add_argument('--expected-version', required=True)
    p.add_argument('--expected-slot', choices=('ota_0', 'ota_1'), default='ota_0')
    p.add_argument('--bench-ip', required=True)
    p.add_argument('--port', type=int, default=18883)
    p.add_argument('--wol-lan-ip')
    p.add_argument('--wifi-reconnect', type=int, default=2)
    p.add_argument('--allow-restart', action='store_true', help='Needed for the OFF-at-boot MQTT activation phase')
    p.add_argument('--settle-seconds', type=int, default=60)
    p.add_argument('--observe-minutes', type=int, default=30)
    a = p.parse_args()
    if not 0 <= a.observe_minutes <= 240 or not 0 <= a.wifi_reconnect <= 5:
        p.error('observe 0..240 minutes, Wi-Fi cycles 0..5')
    password = getpass.getpass('Device password (not saved): ')
    api = login(a.host, password=password)
    password = None
    stamp = time.strftime('%Y%m%d-%H%M%S')
    out = ROOT / 'build/private-device' / f'qualify-{a.expected_version}-{stamp}.json'
    result = {'version': a.expected_version, 'started': stamp, 'phases': {}}

    def phase(name, fn):
        r = result['phases'].setdefault(name, {})
        try:
            fn(r)
            r['passed'] = r.get('passed', True)
        except Exception as e:
            r['passed'] = False
            r['error'] = f'{e.__class__.__name__}: {e}' if isinstance(e, AssertionError) else e.__class__.__name__
        out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f"{name}: {'PASS' if r['passed'] else 'FAIL'}", flush=True)

    phase('identity', lambda r: identity(api, a, r))
    if a.allow_restart:
        def act(r):
            original = api('/api/mqtt')
            snapshot = {k: original[k] for k in lab.KEYS if k in original}
            broker = lab.start_broker(a.bench_ip, a.port, 1200); time.sleep(1)
            observer = lab.Observer(a.bench_ip, a.port)
            try:
                activation.exercise(api, a.expected_version, observer, a.bench_ip, a.port, a.settle_seconds, r)
                r['ops_after'] = ops(api)
            finally:
                api('/api/mqtt', snapshot)
                after = api('/api/mqtt')
                r['restored'] = all(after.get(k) == v for k, v in snapshot.items()) and \
                    bool(after.get('has_password')) == bool(original.get('has_password'))
                observer.stop(); broker.terminate(); broker.wait(10)
            assert r['restored'], 'MQTT settings not restored'
        phase('activation', act)
    def lab_phase(r):
        ns = argparse.Namespace(bench_ip=a.bench_ip, port=a.port, wol_lan_ip=a.wol_lan_ip, wol_port=47009,
                                wifi_reconnect=a.wifi_reconnect)
        ok, res = lab.run(api, ns)
        r.update(checks=res.get('checks'), memory=res.get('memory'), restored=res.get('restored_exactly'),
                 phase_errors=res.get('phase_errors'), no_reboot=res.get('no_reboot_overall'))
        r['ops_after'] = ops(api)
        assert ok, 'Lab checks failed'
    phase('lab', lab_phase)
    if a.observe_minutes:
        log_path = out.with_suffix('.jsonl')
        with log_path.open('w', encoding='utf-8') as log:
            phase('observe', lambda r: observe(api, a.observe_minutes, r, log))
    passed = all(r.get('passed') for r in result['phases'].values())
    result['passed'] = passed
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(('PASS' if passed else 'FAIL') + f': {out.name}')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
