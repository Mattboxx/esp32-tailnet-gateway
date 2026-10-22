"""Opt-in, read-only external resource/continuity sampler (not qualification).

No configuration changes, restart, SNMP enablement, OTA or traffic generation.
Only session authentication plus GET /api/status, /api/system/diag,
/api/operations and /api/tailnet-forward (reduced to counts). Output
is a strict numeric/boolean allowlist, never raw responses, hosts or secrets.
TEST_DEVICE_PASSWORD is read by the existing challenge/session helper.
"""
import argparse
import getpass
import ipaddress
import json
import math
from pathlib import Path
import re
import time

from test_snmp_device import login

STATUS_NUMBERS = ('uptime_s', 'free_heap', 'free_psram', 'mem_internal_free',
                  'mem_internal_total', 'mem_spiram_free', 'mem_spiram_total',
                  'cpu_load_pct', 'cpu_core0_pct', 'cpu_core1_pct', 'cpu_temp_c')
MEMORY_NUMBERS = ('internal_total', 'internal_free', 'internal_min_free',
                  'internal_largest', 'spiram_total', 'spiram_free',
                  'spiram_min_free', 'spiram_largest')
READ_PATHS = frozenset(('/api/status', '/api/system/diag', '/api/operations', '/api/tailnet-forward'))


def number(value, *, temperature=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if value < (-100 if temperature else 0) or value > 2**53 - 1:
        return None
    return value


def boolean(value):
    return value if type(value) is bool else None


def obj(value):
    return value if type(value) is dict else {}


def version(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', value) else None


def host(value):
    """This tool deliberately accepts only an explicit IPv4[:port] target."""
    address, separator, port = value.partition(':')
    ipaddress.IPv4Address(address)
    if separator and (not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535):
        raise ValueError('Invalid port')
    return value


def sample(api, expected, index, *, clock=time.monotonic):
    result = {'kind': 'sample', 'index': index, 'version': None,
              'status_ok': False, 'diag_ok': None, 'version_matches': None,
              'socket_usage': None, 'stack_hwm_min_raw': None}

    def read(path):
        assert path in READ_PATHS
        # No payload argument: the shared helper issues a GET, never a write.
        return obj(api(path, timeout=10))

    start = clock()
    try:
        status = read('/api/status')
        result['version_matches'] = version(status.get('version')) == expected
        result['version'] = expected if result['version_matches'] else None
        result['status_ok'] = result['version_matches'] and number(status.get('uptime_s')) is not None
        for key in STATUS_NUMBERS:
            result[key] = number(status.get(key), temperature=key == 'cpu_temp_c')
        result['wifi_associated'] = boolean(obj(status.get('sta')).get('connected'))
        result['tailnet_control_connected'] = boolean(obj(status.get('tailscale')).get('connected'))
    except Exception:
        # Exception text can contain target URLs, credentials or response data.
        result['status_error'] = True
    result['status_request_ms'] = round((clock() - start)*1000, 2)
    if not result['status_ok'] or index % 5:
        return result
    start = clock()
    try:
        diag = read('/api/system/diag')
        memory = obj(diag.get('memory'))
        for key in MEMORY_NUMBERS:
            result[key] = number(memory.get(key))
        limits = obj(diag.get('network_limits'))
        result['socket_limit'] = number(limits.get('sockets'))
        result['active_tcp_limit'] = number(limits.get('active_tcp'))
        # Limits are NOT usage. The current API has no live socket-use count.
        tasks = diag.get('tasks')
        values = [number(obj(t).get('stack_hwm')) for t in tasks[:128]] if isinstance(tasks, list) else []
        values = [n for n in values if n is not None]
        result['stack_hwm_min_raw'] = min(values) if values else None
        result['task_count_observed'] = len(tasks) if isinstance(tasks, list) and len(tasks) <= 128 else None
        result['diag_ok'] = all(result[k] is not None for k in MEMORY_NUMBERS)
    except Exception:
        result['diag_ok'] = False
    result['diag_request_ms'] = round((clock() - start)*1000, 2)
    start = clock()
    try:
        ops = read('/api/operations')
        # A point-in-time count of open sockets, not a reservation or a maximum.
        result['socket_usage'] = number(ops.get('sockets_used'))
        result['policy_authority_ready'] = boolean(ops.get('authority_ready'))
        result['module_restarts'] = number(ops.get('module_restarts'))
        forward = read('/api/tailnet-forward')
        rules = forward.get('rules')
        rules = [obj(r) for r in rules[:8]] if isinstance(rules, list) else []
        result['sg_rules'] = len(rules)
        result['sg_enabled'] = sum(r.get('enabled') is True for r in rules)
        result['sg_installed'] = sum(r.get('installed') is True for r in rules)
        result['sg_destination_reachable'] = sum(obj(r.get('destination_check')).get('state') == 'reachable' for r in rules)
        result['sg_service_replied'] = sum(number(obj(r.get('activity')).get('service_reply_age_s')) is not None for r in rules)
        result['evidence_ok'] = True
    except Exception:
        result['evidence_ok'] = False
    result['evidence_request_ms'] = round((clock() - start)*1000, 2)
    return result


class Ledger:
    def __init__(self):
        self.attempts = self.good = self.uptime_decreases = self.control_transitions = 0
        self.diag_attempts = self.diag_failures = 0
        self.previous_uptime = self.previous_control = None
        self.minima = {}

    def add(self, row):
        self.attempts += 1
        if row.get('diag_ok') is not None:
            self.diag_attempts += 1
            self.diag_failures += not row['diag_ok']
        if not row['status_ok']:
            # A gap does not prove a reset or connection transition.
            return
        self.good += 1
        uptime = row['uptime_s']
        if self.previous_uptime is not None and uptime < self.previous_uptime:
            self.uptime_decreases += 1
        self.previous_uptime = uptime
        connected = row.get('tailnet_control_connected')
        if connected is not None:
            if self.previous_control is not None and connected != self.previous_control:
                self.control_transitions += 1
            self.previous_control = connected
        for key in ('mem_internal_free', 'free_psram', 'internal_min_free',
                    'internal_largest', 'spiram_min_free', 'spiram_largest', 'stack_hwm_min_raw'):
            value = row.get(key)
            if value is not None:
                self.minima[key] = min(value, self.minima.get(key, value))

    def summary(self, elapsed):
        return {'kind': 'summary', 'elapsed_s': round(elapsed, 2),
                'attempts': self.attempts, 'matching_samples': self.good,
                'missing_or_wrong_version_samples': self.attempts-self.good,
                'diag_attempts': self.diag_attempts, 'diag_failures': self.diag_failures,
                'observed_uptime_decreases': self.uptime_decreases,
                'observed_control_state_transitions': self.control_transitions,
                'observed_minima': self.minima,
                'data_plane_verified': False, 'qualification_pass': None}


def observe(api, expected, seconds, interval, stream, *, clock=time.monotonic, sleep=time.sleep):
    assert 30 <= interval <= 3600 and interval <= seconds <= 86400 and version(expected)
    ledger = Ledger()
    start = clock()
    def write(row):
        stream.write(json.dumps(row, allow_nan=False, separators=(',', ':'))+'\n')
        stream.flush()
    write({'kind': 'metadata', 'expected_version': expected, 'interval_s': interval,
           'requested_duration_s': seconds, 'mode': 'read-only-external-observation',
           'diag_every_samples': 5, 'stack_unit': 'raw-api-not-qualified'})
    index = 0
    while clock()-start < seconds:
        row = sample(api, expected, index, clock=clock)
        row['elapsed_s'] = round(clock()-start, 2)
        ledger.add(row)
        write(row)
        if row['version_matches'] is False:
            write(ledger.summary(clock()-start))
            return 2  # Never qualify a different firmware.
        index += 1
        remaining = seconds-(clock()-start)
        if remaining > 0:
            sleep(min(interval, remaining))
    summary = ledger.summary(clock()-start)
    write(summary)
    # Exit zero means collection completed, NOT a reliability/security pass.
    return 0 if ledger.good == ledger.attempts and ledger.good else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=host, help='IPv4[:port], not stored in the report')
    parser.add_argument('--expected-version', required=True, type=version)
    parser.add_argument('--seconds', type=int, default=3600)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--output', required=True, type=Path, help='New private JSONL file; refuses overwrite')
    parser.add_argument('--prompt-password', action='store_true', help='Read password through a hidden terminal prompt, not an environment variable')
    args = parser.parse_args()
    if not args.expected_version or not 30 <= args.interval <= 3600 or not args.interval <= args.seconds <= 86400:
        parser.error('Require a valid version, interval 30..3600 s and duration interval..86400 s')
    try:
        # Importing this helper does not invoke its invasive SNMP main routine.
        with args.output.open('x', encoding='utf-8') as stream:
            password = getpass.getpass('Device password (not saved): ') if args.prompt_password else None
            api = login(args.host, password=password)
            password = None
            return observe(api, args.expected_version, args.seconds, args.interval, stream)
    except KeyboardInterrupt:
        print('Observation interrupted; partial records are not continuous-run evidence.')
        return 130
    except Exception:
        print('Observation could not complete. Check target, credentials and new output path locally.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
