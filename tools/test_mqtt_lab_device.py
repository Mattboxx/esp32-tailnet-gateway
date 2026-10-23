"""Opt-in MQTT / Home Assistant Discovery test against a LOCAL lab broker.

Points the board's MQTT client at tools/lab_mqtt_broker.py running on the
bench PC (bound to its tailnet address), checks connection, retained
availability/state, Discovery configs, strict command handling and recovery
after a broker outage, then restores the exact previous MQTT settings.

Safety:
- The password is read through a hidden prompt and kept in memory only.
- The stored MQTT password is never sent or changed by this tool; the board
  keeps it. The lab broker discards CONNECT credentials.
- Aborts before any change if the broker watchdog is enabled (restoring an
  unreachable broker after a successful lab connection could re-arm it and
  send a real Wake-on-LAN).
- Only counts, topic shapes and booleans are written to the private result
  file; payloads (which can contain addresses) are not stored.

    python tools/test_mqtt_lab_device.py <board-tailnet-ip> --bench-ip <pc-tailnet-ip> \
        [--wol-lan-ip <pc-lan-ip>] [--wifi-reconnect]
"""
import argparse
import getpass
import socket
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_snmp_device import login  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('enabled', 'uri', 'username', 'base_topic', 'home_assistant_discovery', 'discovery_prefix',
        'interval_seconds', 'broker_watchdog_enabled', 'broker_watchdog_timeout_seconds', 'broker_watchdog_wol_mac')


def wait(pred, seconds, step=1.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(step)
    return False


LAB_MAC = '02:4c:41:42:57:4f'  # locally administered, belongs to no NIC


def magic_listener(ip, port, seconds):
    """Collect magic packets for LAB_MAC on ip:port (unicast, no broadcast bind)."""
    got = []
    want = bytes([0xFF]) * 6 + bytes.fromhex(LAB_MAC.replace(':', '')) * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ip, port)); sock.settimeout(0.5)

    def run():
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                data, _ = sock.recvfrom(512)
            except socket.timeout:
                continue
            got.append(want in data)
        sock.close()
    t = threading.Thread(target=run, daemon=True); t.start()
    return got


class Observer:
    def __init__(self, host, port):
        self.messages = []
        self.lock = threading.Lock()
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, 'lab-observer')
        except AttributeError:
            self.client = mqtt.Client('lab-observer')
        self.client.on_message = self.on_message
        self.client.connect(host, port)
        self.client.subscribe('#', 0)
        self.client.loop_start()

    def on_message(self, client, userdata, msg):
        with self.lock:
            self.messages.append((time.monotonic(), msg.topic, bytes(msg.payload), bool(msg.retain)))

    def topics(self, prefix):
        with self.lock:
            return [m for m in self.messages if m[1].startswith(prefix)]

    def publish(self, topic, payload):
        self.client.publish(topic, payload, qos=0).wait_for_publish(3)

    def stop(self):
        self.client.loop_stop(); self.client.disconnect()


def start_broker(bench_ip, port, seconds):
    return subprocess.Popen([sys.executable, str(ROOT / 'tools/lab_mqtt_broker.py'), '--bind', bench_ip,
                             '--port', str(port), '--seconds', str(seconds)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('host')
    ap.add_argument('--bench-ip', required=True)
    ap.add_argument('--port', type=int, default=18883)
    ap.add_argument('--wol-lan-ip', help='Bench PC LAN address: also test Wake-on-LAN delivery (HTTP and MQTT) '
                    'with a synthetic MAC sent unicast to this address on --wol-port')
    ap.add_argument('--wol-port', type=int, default=47009)
    ap.add_argument('--wifi-reconnect', action='store_true',
                    help='Also send the existing reconnect_wifi command and time in-session recovery')
    a = ap.parse_args()
    password = getpass.getpass('Device password (not saved): ')
    api = login(a.host, password=password)
    password = None
    before = api('/api/mqtt')
    snapshot = {k: before[k] for k in KEYS if k in before}
    result = {'version': api('/api/system')['version'], 'started': time.strftime('%Y-%m-%dT%H:%M:%S'),
              'had_password': bool(before.get('has_password')), 'checks': {}}
    if before.get('broker_watchdog_enabled'):
        result['blocked'] = 'broker watchdog enabled: test not started to avoid a real Wake-on-LAN after restore'
        print(json.dumps(result, indent=2)); return 2
    broker = start_broker(a.bench_ip, a.port, 900)
    time.sleep(1.0)
    observer = Observer(a.bench_ip, a.port)
    base = snapshot['base_topic']; prefix = snapshot.get('discovery_prefix') or 'homeassistant'
    checks = result['checks']
    try:
        lab = {'enabled': True, 'uri': f'mqtt://{a.bench_ip}:{a.port}', 'username': '',
               'home_assistant_discovery': True, 'interval_seconds': 10}
        api('/api/mqtt', lab)
        checks['connected'] = wait(lambda: api('/api/mqtt')['connected'], 90, 2)
        checks['state_published'] = wait(lambda: len(observer.topics(base + '/')) > 0, 30)
        time.sleep(20)  # let Discovery finish
        own = observer.topics(base + '/')
        disc = observer.topics(prefix + '/')
        configs, invalid = 0, 0
        components = {}
        for _, topic, payload, _ in disc:
            if not topic.endswith('/config') or not payload:
                continue
            try:
                doc = json.loads(payload)
                ok = isinstance(doc, dict) and doc.get('unique_id') and doc.get('name') is not None
                state = doc.get('state_topic') or doc.get('stat_t') or ''
                ok = ok and (not state or state.startswith(base) or state.startswith('~'))
            except ValueError:
                ok = False
            configs += 1; invalid += 0 if ok else 1
            comp = topic[len(prefix) + 1:].split('/', 1)[0]
            components[comp] = components.get(comp, 0) + 1
        checks['discovery_configs'] = configs
        checks['discovery_invalid'] = invalid
        checks['discovery_components'] = components
        checks['own_topics'] = len({t for _, t, _, _ in own})
        checks['retained_own'] = len({t for _, t, _, r in own if r})
        avail = [p for _, t, p, _ in own if t.endswith('/availability') or t.endswith('/status')]
        checks['availability_online'] = any(p.strip().lower() in (b'online', b'"online"') for p in avail)
        # Strict command: an invalid switch payload must change nothing and only republish state.
        routes_before = api('/api/tailscale')['settings'].get('accept_routes', None)
        n0 = len(observer.topics(base + '/'))
        observer.publish(f'{base}/command/accept_routes', b'maybe')
        checks['invalid_command_republished'] = wait(lambda: len(observer.topics(base + '/')) > n0, 15)
        checks['invalid_command_no_change'] = api('/api/tailscale')['settings'].get('accept_routes', None) == routes_before
        # Broker outage: routing/administration must stay up; reconnect afterwards.
        observer.stop(); broker.terminate(); broker.wait(10)
        checks['offline_detected'] = wait(lambda: not api('/api/mqtt')['connected'], 60, 2)
        status = api('/api/status')
        checks['tailnet_up_while_broker_down'] = bool(status['tailscale']['connected'])
        broker = start_broker(a.bench_ip, a.port, 600); time.sleep(1.0)
        observer = Observer(a.bench_ip, a.port)
        t0 = time.monotonic()
        checks['reconnected'] = wait(lambda: api('/api/mqtt')['connected'], 180, 3)
        checks['reconnect_seconds'] = round(time.monotonic() - t0, 1)
        if a.wol_lan_ip:
            saved = api('/api/wol')['devices']
            result['wol_saved_count'] = len(saved)
            if len(saved) >= 12:
                checks['wol_blocked'] = 'address book full; not modified'
            else:
                got = magic_listener(a.wol_lan_ip, a.wol_port, 60)
                lab_dev = {'name': 'lab-wol-test', 'mac': LAB_MAC, 'broadcast': a.wol_lan_ip, 'port': a.wol_port}
                try:
                    api('/api/wol', {'devices': saved + [lab_dev]})
                    api('/api/wol/send', {'mac': LAB_MAC})
                    checks['wol_http_delivered'] = wait(lambda: any(got), 10, 0.5)
                    n = len(got)
                    observer.publish(f"{base}/command/wol/{LAB_MAC.replace(':', '')}", b'')
                    checks['wol_mqtt_delivered'] = wait(lambda: len(got) > n and any(got[n:]), 15, 0.5)
                finally:
                    api('/api/wol', {'devices': saved})
                    checks['wol_list_restored'] = api('/api/wol')['devices'] == saved
        if a.wifi_reconnect and checks['reconnected']:
            # In-session transport loss without reboot, through the existing
            # MQTT command. Every tailnet API call travels through WireGuard and
            # the policy gate, so a successful call after recovery is data-plane
            # evidence into the board (not a full peer-to-peer matrix).
            uptime0 = api('/api/status')['uptime_s']
            observer.publish(f'{base}/command/reconnect_wifi', b'')
            t0 = time.monotonic(); lost = None; back = None; samples = []
            while time.monotonic() - t0 < 240:
                try:
                    o = api('/api/operations', timeout=5)
                    ok = bool(o.get('control_connected')) and bool(o.get('authority_ready'))
                    samples.append((round(time.monotonic() - t0, 1), ok))
                    if lost is not None and ok:
                        back = time.monotonic() - t0; break
                    if not ok and lost is None:
                        lost = time.monotonic() - t0
                except Exception:
                    samples.append((round(time.monotonic() - t0, 1), None))
                    if lost is None:
                        lost = time.monotonic() - t0
                time.sleep(2)
            checks['wifi_reconnect_loss_observed'] = lost is not None
            checks['wifi_reconnect_recovered_seconds'] = None if back is None else round(back, 1)
            checks['wifi_reconnect_samples'] = len(samples)
            checks['wifi_reconnect_no_reboot'] = api('/api/status')['uptime_s'] >= uptime0
            checks['wifi_reconnect_mqtt_back'] = wait(lambda: api('/api/mqtt')['connected'], 120, 3)
    finally:
        restore = dict(snapshot)
        try:
            api('/api/mqtt', restore)
            after = api('/api/mqtt')
            result['restored_exactly'] = all(after.get(k) == v for k, v in snapshot.items())
            result['password_still_present'] = bool(after.get('has_password')) == result['had_password']
        except Exception as e:  # report, never retry blindly
            result['restore_error'] = e.__class__.__name__
        try:
            observer.stop()
        except Exception:
            pass
        broker.terminate()
        try:
            broker.wait(10)
        except subprocess.TimeoutExpired:
            broker.kill()
    out = ROOT / 'build/private-device' / f"mqtt-lab-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    required = ('connected', 'state_published', 'invalid_command_republished', 'invalid_command_no_change',
                'offline_detected', 'tailnet_up_while_broker_down', 'reconnected')
    if a.wol_lan_ip and 'wol_blocked' not in checks:
        required += ('wol_http_delivered', 'wol_mqtt_delivered', 'wol_list_restored')
    if a.wifi_reconnect:
        required += ('wifi_reconnect_loss_observed', 'wifi_reconnect_recovered_seconds', 'wifi_reconnect_no_reboot')
    ok = all(checks.get(k) for k in required) and checks.get('discovery_configs', 0) > 0 \
        and checks.get('discovery_invalid', 1) == 0 and result.get('restored_exactly') and result.get('password_still_present')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
