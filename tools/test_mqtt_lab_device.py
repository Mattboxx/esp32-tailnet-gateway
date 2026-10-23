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
        [--wol-lan-ip <pc-lan-ip>] [--wifi-reconnect [CYCLES]]
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


def memory(api):
    """Point-in-time internal/PSRAM numbers from /api/operations (read only)."""
    o = api('/api/operations', timeout=8)
    return {k: o.get(k) for k in ('internal_free', 'internal_min', 'internal_largest',
                                   'psram_largest', 'sockets_used')}


def phase(result, name, fn):
    """Run one phase; a failure is recorded and later phases still run."""
    try:
        fn()
        return True
    except Exception as e:  # class only: messages can carry addresses or data
        result['phase_errors'][name] = e.__class__.__name__
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('host')
    ap.add_argument('--bench-ip', required=True)
    ap.add_argument('--port', type=int, default=18883)
    ap.add_argument('--wol-lan-ip', help='Bench PC LAN address: also test Wake-on-LAN delivery (HTTP and MQTT) '
                    'with a synthetic MAC sent unicast to this address on --wol-port')
    ap.add_argument('--wol-port', type=int, default=47009)
    ap.add_argument('--wifi-reconnect', type=int, nargs='?', const=1, default=0, metavar='CYCLES',
                    help='Also send the existing reconnect_wifi command CYCLES times (default 1) and '
                    'time in-session recovery of Wi-Fi, control, policy authority and MQTT')
    a = ap.parse_args()
    if not 0 <= a.wifi_reconnect <= 5:
        ap.error('--wifi-reconnect accepts 0..5 cycles')
    password = getpass.getpass('Device password (not saved): ')
    api = login(a.host, password=password)
    password = None
    before = api('/api/mqtt')
    snapshot = {k: before[k] for k in KEYS if k in before}
    result = {'version': api('/api/system')['version'], 'started': time.strftime('%Y-%m-%dT%H:%M:%S'),
              'had_password': bool(before.get('has_password')), 'checks': {}, 'memory': {},
              'phase_errors': {}}
    if before.get('broker_watchdog_enabled'):
        result['blocked'] = 'broker watchdog enabled: test not started to avoid a real Wake-on-LAN after restore'
        print(json.dumps(result, indent=2)); return 2
    checks = result['checks']; mem = result['memory']
    mem['start'] = memory(api)
    uptime_start = api('/api/status')['uptime_s']
    base = snapshot['base_topic']; prefix = snapshot.get('discovery_prefix') or 'homeassistant'
    state = {'broker': start_broker(a.bench_ip, a.port, 1800)}
    time.sleep(1.0)
    state['observer'] = Observer(a.bench_ip, a.port)

    def mqtt_connect():
        lab = {'enabled': True, 'uri': f'mqtt://{a.bench_ip}:{a.port}', 'username': '',
               'home_assistant_discovery': True, 'interval_seconds': 10}
        api('/api/mqtt', lab)
        checks['connected'] = wait(lambda: api('/api/mqtt')['connected'], 90, 2)
        checks['state_published'] = wait(lambda: len(state['observer'].topics(base + '/')) > 0, 30)
        time.sleep(20)  # let Discovery finish
        mem['after_mqtt_connect'] = memory(api)

    def discovery():
        own = state['observer'].topics(base + '/')
        disc = state['observer'].topics(prefix + '/')
        configs, invalid, components = 0, 0, {}
        for _, topic, payload, _ in disc:
            if not topic.endswith('/config') or not payload:
                continue
            try:
                doc = json.loads(payload)
                ok = isinstance(doc, dict) and doc.get('unique_id') and doc.get('name') is not None
                st = doc.get('state_topic') or doc.get('stat_t') or ''
                ok = ok and (not st or st.startswith(base) or st.startswith('~'))
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

    def strict_command():
        # An invalid switch payload must change nothing and only republish state.
        routes_before = api('/api/tailscale')['settings'].get('accept_routes', None)
        n0 = len(state['observer'].topics(base + '/'))
        state['observer'].publish(f'{base}/command/accept_routes', b'maybe')
        checks['invalid_command_republished'] = wait(lambda: len(state['observer'].topics(base + '/')) > n0, 15)
        checks['invalid_command_no_change'] = api('/api/tailscale')['settings'].get('accept_routes', None) == routes_before

    def broker_outage():
        # Routing/administration must stay up; reconnect afterwards.
        state['observer'].stop(); state['broker'].terminate(); state['broker'].wait(10)
        checks['offline_detected'] = wait(lambda: not api('/api/mqtt')['connected'], 60, 2)
        checks['tailnet_up_while_broker_down'] = bool(api('/api/status')['tailscale']['connected'])
        mem['broker_down'] = memory(api)
        state['broker'] = start_broker(a.bench_ip, a.port, 1500); time.sleep(1.0)
        state['observer'] = Observer(a.bench_ip, a.port)
        t0 = time.monotonic()
        checks['reconnected'] = wait(lambda: api('/api/mqtt')['connected'], 180, 3)
        checks['reconnect_seconds'] = round(time.monotonic() - t0, 1)
        # The board subscribes to its command topics in the same step that
        # publishes availability "online"; commands sent earlier are lost.
        checks['resubscribed'] = wait(lambda: any(
            p.strip().lower() in (b'online', b'"online"')
            for _, t, p, _ in state['observer'].topics(base + '/') if t.endswith('/availability')), 30, 0.5)
        mem['after_mqtt_reconnect'] = memory(api)

    def wol():
        saved = api('/api/wol')['devices']
        result['wol_saved_count'] = len(saved)
        if len(saved) >= 12:
            checks['wol_blocked'] = 'address book full; not modified'
            return
        got = magic_listener(a.wol_lan_ip, a.wol_port, 60)
        lab_dev = {'name': 'lab-wol-test', 'mac': LAB_MAC, 'broadcast': a.wol_lan_ip, 'port': a.wol_port}
        try:
            api('/api/wol', {'devices': saved + [lab_dev]})
            api('/api/wol/send', {'mac': LAB_MAC})
            checks['wol_http_delivered'] = wait(lambda: any(got), 10, 0.5)
            n = len(got)
            # Empty payloads are dropped by design; Home Assistant buttons send PRESS.
            state['observer'].publish(f"{base}/command/wol/{LAB_MAC.replace(':', '')}", b'PRESS')
            checks['wol_mqtt_delivered'] = wait(lambda: len(got) > n and any(got[n:]), 15, 0.5)
        finally:
            api('/api/wol', {'devices': saved})
            checks['wol_list_restored'] = api('/api/wol')['devices'] == saved

    def wifi_cycle(i):
        # In-session transport loss without reboot, through the existing MQTT
        # command: Wi-Fi drops, so the DERP TCP/TLS stream and the control
        # long-poll are lost and must be re-established. Every API call travels
        # over the tailnet (WireGuard + policy gate), so a successful call after
        # recovery is data-plane evidence into the board, not a peer matrix.
        cyc = {}
        uptime0 = api('/api/status')['uptime_s']
        state['observer'].publish(f'{base}/command/reconnect_wifi', b'PRESS')
        t0 = time.monotonic(); lost = None; back = None; samples = 0; low = None
        while time.monotonic() - t0 < 300:
            try:
                o = api('/api/operations', timeout=5)
                samples += 1
                ok = bool(o.get('control_connected')) and bool(o.get('authority_ready'))
                if isinstance(o.get('internal_largest'), int):
                    low = o['internal_largest'] if low is None else min(low, o['internal_largest'])
                if lost is not None and ok:
                    back = time.monotonic() - t0
                    break
                if not ok and lost is None:
                    lost = time.monotonic() - t0
            except Exception:
                samples += 1
                if lost is None:
                    lost = time.monotonic() - t0
            time.sleep(2)
        cyc['loss_observed'] = lost is not None
        cyc['loss_after_seconds'] = None if lost is None else round(lost, 1)
        cyc['recovered_seconds'] = None if back is None else round(back, 1)
        cyc['samples'] = samples
        cyc['internal_largest_min_seen'] = low
        cyc['no_reboot'] = api('/api/status')['uptime_s'] >= uptime0
        t1 = time.monotonic()
        cyc['mqtt_back'] = wait(lambda: api('/api/mqtt')['connected'], 120, 3)
        cyc['mqtt_back_seconds'] = round(time.monotonic() - t1, 1)
        # A fresh "online" means command topics are subscribed again (next cycle).
        cyc['resubscribed'] = wait(lambda: any(
            ts > t1 and t.endswith('/availability') and p.strip().lower() in (b'online', b'"online"')
            for ts, t, p, _ in state['observer'].topics(base + '/')), 60, 0.5)
        time.sleep(20)  # let DERP/TLS settle before sampling
        mem[f'after_wifi_cycle_{i}'] = memory(api)
        checks.setdefault('wifi_cycles', []).append(cyc)

    try:
        if phase(result, 'mqtt_connect', mqtt_connect) and checks.get('connected'):
            phase(result, 'discovery', discovery)
            phase(result, 'strict_command', strict_command)
            phase(result, 'broker_outage', broker_outage)
            if a.wol_lan_ip:
                phase(result, 'wol', wol)
            if a.wifi_reconnect and checks.get('reconnected'):
                for i in range(1, a.wifi_reconnect + 1):
                    if not phase(result, f'wifi_cycle_{i}', lambda: wifi_cycle(i)):
                        break
    finally:
        try:
            api('/api/mqtt', dict(snapshot))
            after = api('/api/mqtt')
            result['restored_exactly'] = all(after.get(k) == v for k, v in snapshot.items())
            result['password_still_present'] = bool(after.get('has_password')) == result['had_password']
        except Exception as e:  # report, never retry blindly
            result['restore_error'] = e.__class__.__name__
        try:
            mem['end'] = memory(api)
            result['no_reboot_overall'] = api('/api/status')['uptime_s'] >= uptime_start
        except Exception as e:
            result['phase_errors']['end_sample'] = e.__class__.__name__
        try:
            state['observer'].stop()
        except Exception:
            pass
        state['broker'].terminate()
        try:
            state['broker'].wait(10)
        except subprocess.TimeoutExpired:
            state['broker'].kill()
        out = ROOT / 'build/private-device' / f"mqtt-lab-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    required = ('connected', 'state_published', 'invalid_command_republished', 'invalid_command_no_change',
                'offline_detected', 'tailnet_up_while_broker_down', 'reconnected', 'resubscribed')
    if a.wol_lan_ip and 'wol_blocked' not in checks:
        required += ('wol_http_delivered', 'wol_mqtt_delivered', 'wol_list_restored')
    ok = all(checks.get(k) for k in required) and checks.get('discovery_configs', 0) > 0 \
        and checks.get('discovery_invalid', 1) == 0 and result.get('restored_exactly') \
        and result.get('password_still_present') and not result['phase_errors']
    if a.wifi_reconnect:
        cycles = checks.get('wifi_cycles', [])
        ok = ok and len(cycles) == a.wifi_reconnect and all(
            c['loss_observed'] and c['recovered_seconds'] is not None and c['no_reboot'] and c['mqtt_back'] and c['resubscribed']
            for c in cycles)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
