"""Opt-in first MQTT activation after an OFF-at-boot software reboot.

Own bench board and local lab broker only; restores original MQTT settings.
No OTA, flash, Tailnet policy change or credential writes. The device password
is prompted without echo; private summaries contain only counts and metrics.
Use --allow-restart explicitly. Not part of offline test discovery.
"""
import argparse
import getpass
import json
from pathlib import Path
import time

from test_snmp_device import login
from test_mqtt_lab_device import KEYS, Observer, memory, start_broker

ROOT = Path(__file__).resolve().parents[1]


def exercise(api, expected, observer, bench, port, settle, result, *, sleep=time.sleep, clock=time.monotonic):
    """The caller owns the broker and guarantees restoration in a finally block."""
    assert api('/api/system')['version'] == expected, 'Unexpected firmware'
    original = api('/api/mqtt')
    assert not original.get('broker_watchdog_enabled'), 'Watchdog must be OFF before this lab test'
    assert api('/api/operations')['authority_ready'], 'Initial policy authority unavailable'
    assert api('/api/status')['uptime_s'] > 20, 'Let initial boot settle first'
    result['memory_before'] = memory(api)
    api('/api/mqtt', {'enabled': False})
    limit = clock() + 45
    while api('/api/mqtt')['connected']:
        assert clock() < limit, 'MQTT did not stop'
        sleep(1)
    old_uptime = api('/api/status')['uptime_s']
    # One unambiguous restart request; never blindly retry a POST.
    assert api('/api/system/restart', {})['ok']
    deadline = clock() + 150
    sleep(3)
    while True:
        try:
            state = api('/api/status', timeout=5)
            if state['uptime_s'] < old_uptime and api('/api/operations')['authority_ready']:
                break
        except (OSError, ValueError):
            pass
        assert clock() < deadline, 'New boot with policy authority not observed'
        sleep(3)
    assert api('/api/system')['version'] == expected
    assert not api('/api/mqtt')['enabled'] and not api('/api/mqtt')['connected']
    result['off_at_boot_confirmed'] = True
    sleep(settle)  # let routing/TLS and the other optional workers allocate first
    result['memory_before_first_enable'] = memory(api)
    base = original['base_topic']
    cycles = result.setdefault('cycles', [])
    for index in range(3):
        start = clock()
        api('/api/mqtt', {'enabled': True, 'uri': f'mqtt://{bench}:{port}',
                         'username': '', 'home_assistant_discovery': True, 'interval_seconds': 10})
        deadline = clock() + 120
        while not api('/api/mqtt')['connected']:
            assert clock() < deadline, 'MQTT activation timeout'
            sleep(2)
        deadline = clock() + 45
        while not any(ts >= start for ts, _, _, _ in observer.topics(base + '/')):
            assert clock() < deadline, 'No actual MQTT state received'
            sleep(1)
        assert api('/api/operations')['authority_ready']
        cycles.append({'cycle': index+1, 'activation_seconds': round(clock()-start, 2),
                       'state_received': True, 'memory': memory(api)})
        if index < 2:
            api('/api/mqtt', {'enabled': False})
            deadline = clock() + 45
            while api('/api/mqtt')['connected']:
                assert clock() < deadline, 'MQTT stop timeout'
                sleep(1)
            sleep(5)
    system = api('/api/system')
    assert system['reset_history'][0]['reason'] == 'SW', 'Unexpected reset after planned reboot'
    result['planned_reboot_only'] = True
    # Whitelisted task names and stack values; never save raw diagnostics.
    tasks = api('/api/system/diag').get('tasks', [])
    result['task_stacks'] = [{k: task.get(k) for k in ('name', 'stack_hwm')}
                             for task in tasks if task.get('name') in ('mqtt_bridge', 'mqtt_task')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('--bench-ip', required=True)
    p.add_argument('--port', type=int, default=18883)
    p.add_argument('--expected-version', required=True)
    p.add_argument('--allow-restart', required=True, action='store_true')
    p.add_argument('--settle-seconds', type=int, default=60)
    p.add_argument('--lan-source')
    p.add_argument('--interface-index', type=int)
    args = p.parse_args()
    if not 1 <= args.port <= 65535 or not 30 <= args.settle_seconds <= 300:
        p.error('Invalid broker port or settle duration')
    password = getpass.getpass('Device password (not saved): ')
    api = login(args.host, password=password, source_ip=args.lan_source, interface_index=args.interface_index)
    password = None  # the session closure retains it only for 401 challenge renewals
    original = api('/api/mqtt')
    assert api('/api/system')['version'] == args.expected_version, 'Unexpected firmware'
    assert not original.get('broker_watchdog_enabled'), 'Watchdog enabled; no changes made'
    snapshot = {k: original[k] for k in KEYS if k in original}
    broker = observer = None
    result = {'version': args.expected_version, 'passed': False, 'restored': False}
    try:
        broker = start_broker(args.bench_ip, args.port, 1200)
        time.sleep(1)
        observer = Observer(args.bench_ip, args.port)
        exercise(api, args.expected_version, observer, args.bench_ip, args.port, args.settle_seconds, result)
        result['passed'] = True
    except Exception as error:
        result['error_class'] = type(error).__name__
    finally:
        try:
            api('/api/mqtt', snapshot)
            after = api('/api/mqtt')
            result['restored'] = all(after.get(k) == v for k, v in snapshot.items()) and \
                bool(after.get('has_password')) == bool(original.get('has_password'))
        except Exception as error:
            result['restore_error_class'] = type(error).__name__
        if observer:
            observer.stop()
        if broker:
            broker.terminate()
            try:
                broker.wait(10)
            except Exception:
                broker.kill(); broker.wait(5)
        out = ROOT / 'build/private-device' / ('mqtt-activation-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    return 0 if result['passed'] and result['restored'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
