"""Opt-in owned-device LAN -> ESP -> Tailnet file benchmark, not an OTA tool.

Only creates/removes an expiring /32 TCP rule; optional INFO/WARN comparisons
restore the console setting. All data, addresses and recovery state stay private.
No default route, firewall, Tailnet policy or integration enable flag is changed.
"""
import argparse
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import statistics
import sys
import threading
import time
import urllib.request

from gateway_benchmark import FileService, TemporaryRule, configs, percentile, restore_console, transfer
from test_snmp_device import bound_http_handler, login

ROOT = Path(__file__).resolve().parents[1]


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--lan-source', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--interface-index', type=int)
    parser.add_argument('--peer-bind', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--size-mb', type=int, default=32, choices=range(1, 513), metavar='1..512')
    parser.add_argument('--runs', type=int, default=3, choices=range(1, 10))
    parser.add_argument('--compare-console', action='store_true', help='Explicit temporary INFO/WARN setting changes')
    parser.add_argument('--allow-temporary-rule', required=True, action='store_true')
    parser.add_argument('--output', type=Path, help='New directory under ignored build/private-device/')
    parser.add_argument('--recover-only', type=Path, help='Existing private result folder; remove exact rule/restore owned console change only')
    args = parser.parse_args()
    if args.interface_index is not None and not 1 <= args.interface_index <= 0xffffffff:
        parser.error('Invalid interface index')
    if sys.platform == 'win32' and args.interface_index is None:
        parser.error('Windows requires --interface-index to force the physical LAN path')
    if args.peer_bind not in ipaddress.ip_network('100.64.0.0/10'):
        parser.error('Server must bind to the owned PC Tailnet IPv4')
    if 'TEST_DEVICE_PASSWORD' not in os.environ:
        parser.error('Set TEST_DEVICE_PASSWORD for this process only; never pass it as an argument')
    args.output = args.recover_only or args.output or ROOT/'build/private-device'/('gateway-perf-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    args.output = args.output.resolve()
    if not args.output.is_relative_to((ROOT/'build/private-device').resolve()):
        parser.error('Output/recovery must stay under ignored build/private-device/')
    if args.output.exists() and not args.recover_only:
        parser.error('Use a new output folder')
    return args


def main():
    a = arguments()
    a.output.mkdir(parents=True, exist_ok=bool(a.recover_only))
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    api = login(str(a.host), source_ip=str(a.lan_source), interface_index=a.interface_index)
    os.environ.pop('TEST_DEVICE_PASSWORD', None)
    state_file = a.output/'state-private.json'
    report = {'state': 'preflight', 'runs': [], 'sampling_interval_s': 5,
              'topology': 'Same owned PC file source on Tailnet and LAN-bound receiver',
              'forced_derp': False, 'all_features_qualification': False}

    def persist():
        temporary = state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(state_file)

    system = api('/api/system')
    if system['version'] != a.expected_version:
        raise RuntimeError('Unexpected firmware; refusing mutation')
    if a.recover_only:
        report = json.loads(state_file.read_text())
        if report['host'] != str(a.host) or report['version'] != a.expected_version:
            raise RuntimeError('Recovery target mismatch')
        rule = TemporaryRule(api, report['rule'])
        rule.original = report['original_rules']
        rule.original_leases = report['original_leases']
        report['cleanup'] = rule.cleanup()
        report['console_restored'] = restore_console(api, report['console_original'],
            report.get('console_last_owned'), report.get('console_write_intent'))
        report['recovered'] = True
        persist()
        print('Recovery completed; inspect the private cleanup result.')
        return

    status, ops = api('/api/status'), api('/api/operations')
    network = ipaddress.ip_network(status['sta']['ip']+'/'+str(status['sta']['prefix']), strict=False)
    if not status['sta']['connected'] or a.lan_source not in network or str(a.host) != status['sta']['ip']:
        raise RuntimeError('Expected physical Wi-Fi LAN path not available')
    if not status['tailscale']['connected'] or not ops['authority_ready'] or api('/api/system/updates').get('busy'):
        raise RuntimeError('Tailnet authority unavailable or OTA busy')
    esp_ip = status['tailscale']['tunnel_ip']
    if esp_ip == str(a.peer_bind):
        raise RuntimeError('Server and ESP Tailnet addresses must differ')
    log = api('/api/sdlog')
    if a.compare_console and log['console_level'] != 3:
        raise RuntimeError('INFO/WARN comparison requires an initial INFO setting')
    report.update(host=str(a.host), version=system['version'], build_commit=system.get('build_commit'),
        initial_status=status, initial_operations=ops, initial_diag=api('/api/system/diag'),
        console_original=log['console_level'], console_last_owned=log['console_level'],
        console_write_intent=False, instrumentation_scope='status + operations every 5s; task diagnostics between runs')
    persist()
    payload = a.output/'source.bin'
    digest = hashlib.sha256()
    with payload.open('wb') as stream:
        left = a.size_mb*1_000_000
        while left:
            data = os.urandom(min(left, 1024*1024))
            stream.write(data)
            digest.update(data)
            left -= len(data)
    service = FileService(str(a.peer_bind), esp_ip, payload)
    rows = configs(api('/api/tailnet-forward')['rules'])
    listen = secrets.randbelow(10000)+22000
    while any(r['listen_port'] == listen for r in rows) or listen == system.get('web_port', 80):
        listen = secrets.randbelow(10000)+22000
    row = dict(name='perf-'+secrets.token_hex(5), enabled=True, protocol='tcp', listen_port=listen,
        tailnet_destination=str(a.peer_bind), destination_port=service.port,
        allowed_source_subnet=str(a.lan_source)+'/32')
    rule = TemporaryRule(api, row, persist)
    report.update(rule=row, original_rules=rule.original, original_leases=rule.original_leases,
                  server_port=service.port, server_path=service.url_path, source_sha256=digest.hexdigest())
    persist()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), bound_http_handler(str(a.lan_source), a.interface_index))
    url = f'http://{a.host}:{listen}'+service.url_path
    monitor = None
    monitor_stop = threading.Event()
    try:
        service.start()
        # Conservative upper bound includes slow transfers and pauses. Expiry is
        # a fallback after a process kill; normal cleanup removes the exact rule.
        rule.install(min(604800, (a.runs*(2 if a.compare_console else 1))*185+180))
        schedule = [log['console_level']]*a.runs
        if a.compare_console:
            schedule = [v for i in range(a.runs) for v in ((3, 2) if i % 2 == 0 else (2, 3))]
        time.sleep(2)
        for number, level in enumerate(schedule, 1):
            if cancel.is_set() or (a.output/'STOP').exists():
                raise RuntimeError('Owner stopped benchmark')
            current = api('/api/sdlog')['console_level']
            if current != report['console_last_owned']:
                raise RuntimeError('Owner changed console setting; preserving it')
            if level != current:
                report.update(console_write_intent=True, console_last_owned=level)
                persist()  # Intent survives an ambiguous HTTP result.
                api('/api/sdlog', {'console_level': level})
                if api('/api/sdlog')['console_level'] != level:
                    raise RuntimeError('Console change not applied')
            samples, errors = [], []
            monitor_stop.clear()

            def observe():
                misses = 0
                while not monitor_stop.wait(5):
                    started = time.monotonic()
                    try:
                        s = api('/api/status', timeout=5)
                        o = api('/api/operations', timeout=5)
                        sample = dict(epoch=time.time(), control_pair_latency_s=time.monotonic()-started,
                                      status=s, operations=o)
                        samples.append(sample)
                        with (a.output/'samples-private.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(dict(run=number, **sample))+'\n')
                        misses = 0
                        # Abort floors are emergency stops, NOT qualified service
                        # reserves. Real reserve gates need concurrent-load data.
                        if s['uptime_s'] < status['uptime_s']:
                            raise RuntimeError('ESP reboot observed')
                        if o['internal_free'] < 12000 or o['internal_largest'] < 2048:
                            raise RuntimeError('Emergency resource floor reached')
                        if not s['tailscale']['connected'] or not o['authority_ready']:
                            raise RuntimeError('Tunnel/control authority lost')
                    except Exception as error:
                        errors.append(dict(epoch=time.time(), error=str(error)))
                        misses += 1
                        if isinstance(error, RuntimeError) or misses >= 2:
                            cancel.set()
                            return

            monitor = threading.Thread(target=observe, daemon=True)
            monitor.start()
            report.update(state='transferring', active_run=number, console_level=level)
            persist()

            def progress(window):
                report['active_progress'] = window
                persist()

            try:
                result = transfer(opener, url, a.output/f'download-{number}.bin', a.size_mb*1_000_000,
                    digest.hexdigest(), progress=progress,
                    cancelled=lambda: cancel.is_set() or (a.output/'STOP').exists())
            finally:
                monitor_stop.set()
                monitor.join(timeout=40)
                if monitor.is_alive():
                    raise RuntimeError('Monitor did not stop; refusing concurrent control writes')
            result.update(run=number, console_level=level, samples=len(samples), errors=errors,
                observed_internal_min=min((s['operations']['internal_free'] for s in samples), default=None),
                largest_block_min=min((s['operations']['internal_largest'] for s in samples), default=None),
                cpu_median=statistics.median([s['status']['cpu_load_pct'] for s in samples]) if samples else None,
                control_pair_p95_s=percentile([s['control_pair_latency_s'] for s in samples], .95))
            report['runs'].append(result)
            report['last_rule_state'] = api('/api/tailnet-forward')
            report['last_diag'] = api('/api/system/diag')
            result['diag_memory'] = report['last_diag']['memory']
            if cancel.is_set() or errors:
                raise RuntimeError('Control/resource monitor reported a failure')
            if len(service.records) != number or service.records[-1]['source'] != esp_ip:
                raise RuntimeError('Server route evidence mismatch')
            persist()
            print(f'Run {number}/{len(schedule)}: {result["mbps"]:.3f} Mbit/s, hash PASS, control p95 {result["control_pair_p95_s"]}', flush=True)
            time.sleep(2)
        report['state'] = 'completed'
        report['summary'] = {str(level): dict(median_mbps=statistics.median(values), min_mbps=min(values), max_mbps=max(values))
            for level in set(schedule) if (values := [r['mbps'] for r in report['runs'] if r['console_level'] == level])}
    except BaseException as error:
        report.update(state='failed', error=type(error).__name__+': '+str(error))
    finally:
        monitor_stop.set()
        if monitor:
            monitor.join(timeout=40)
        service.close()
        report['server_records'] = service.records
        try:
            report['cleanup'] = rule.cleanup()
        except Exception as error:
            report['cleanup_error'] = type(error).__name__+': '+str(error)
        try:
            report['console_restored'] = restore_console(api, report['console_original'],
                report['console_last_owned'], report['console_write_intent'])
            report['final_status'] = api('/api/status')
            report['final_operations'] = api('/api/operations')
            report['reboot_observed'] = report['final_status']['uptime_s'] < status['uptime_s']
        except Exception as error:
            report['cleanup_error'] = type(error).__name__+': '+str(error)
        persist()
    print(json.dumps({'state': report['state'], 'summary': report.get('summary'),
                      'cleanup': report.get('cleanup'), 'error': report.get('error'),
                      'cleanup_error': report.get('cleanup_error')}, indent=2))
    return 0 if (report['state'] == 'completed' and not report.get('cleanup_error')
                 and report.get('console_restored') and
                 all(report.get('cleanup', {}).values())) else 1


if __name__ == '__main__':
    sys.exit(main())
