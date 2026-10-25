/* Synthetic API for the embedded Web UI (main/index.html), shared by layout,
 * i18n and screenshot tests. All values are invented documentation data:
 * no device, credential or real network is involved. `overrides[path]`
 * replaces a GET body; POSTs are recorded and answered {ok:true}. */
const fs = require('node:fs');
const path = require('node:path');

const { builtHtml } = require('./ui_build.cjs');
let cached = null;
const html = () => cached || (cached = builtHtml());

function rule(i, o) {
  return Object.assign({ index: i, name: 'Rule ' + i, enabled: true, protocol: 'tcp', listen_port: 18830 + i,
    tailnet_destination: 'broker.example-tailnet.ts.net', destination_port: 1883, allowed_source_subnet: '192.168.1.20/32',
    installed: true, resolved_ip: '100.64.0.9', accepted_packets: 1200 + i, blocked_packets: i, error: '', rule_token: 4096 + i,
    diagnostic: { code: 'traffic_seen', summary: 'Recent traffic was accepted and the service replied', next_step: 'No action needed',
      service_status: 'replied', data_plane_status: 'up' },
    activity: { peer_path: 'direct', service_reply_age_s: 12 },
    destination_check: { state: 'reachable', summary: 'This gateway completed a TCP handshake with the Tailnet destination',
      next_step: 'Enable the rule, then connect from an allowed LAN client', checked_ip: '100.64.0.9', latency_ms: 42, age_s: 300 } }, o || {});
}

const data = {
  '/api/auth/status': { password_set: true, auth_enabled: true, auth_required: true, authenticated: true, device_name: 'Tailnet Gateway', session_timeout_s: 0, session_remaining_s: 0 },
  '/api/status': { version: '0.1.38-Mattboxx-1.14-dev.6', uptime_s: 93784, free_heap: 4210000, heap_total: 8650000, free_psram: 4100000,
    mem_internal_free: 13800, mem_internal_total: 380000, mem_spiram_free: 4100000, mem_spiram_total: 8380000, cpu_load_pct: 23, cpu_core0_pct: 31, cpu_core1_pct: 15,
    cpu_temp_c: 41.5, reset_reason: 'Power on',
    sta: { connected: true, ssid: 'HomeNetwork-5G-but-really-2.4', rssi: -58, channel: 6, mac: '02:00:00:00:10:01', ip: '192.168.1.50', gateway: '192.168.1.1', prefix: 24, cidr: '192.168.1.0/24', dns: '192.168.1.1', bytes_in: 7.4e8, bytes_out: 2.1e8, lan_name: 'esp32-tailnet-1a2b' },
    ap: { enabled: false, auto_off_when_connected: true, clients: 0, ssid: 'Tailnet-Gateway', channel: 6, cfg_channel: 6, mac: '02:00:00:00:10:02', ip: '192.168.4.1', prefix: 24, bytes_in: 0, bytes_out: 0 },
    tx_power: 78,
    tailscale: { enabled: true, connected: true, startup_error: '', startup_retrying: false, advertise_exit_node: false, hostname: 'tailnet-gateway',
      advertise_routes: '192.168.1.0/24', tunnel_ip: '100.64.0.42', exit_node_ip: '', peers_online: 2, peers_total: 3, register_user_id: 1, register_user_name: 'owner@example.com',
      identity_persistent: true, identity_pubkey_prefix: 'nodekey:3f2a…' } },
  '/api/tailscale': {
    settings: { enabled: true, auth_key_set: true, auth_key_len: 61, auth_key_preview: 'tskey-auth-…', hostname: 'tailnet-gateway', login_server: '', ipn_version: '1.80.0', advertise_ap: false,
      effective_routes: '192.168.1.0/24', effective_routes_valid: true, active_routes: '192.168.1.0/24', advertise_routes: '192.168.1.0/24',
      fourvia6: { enabled: false, lan_cidr: '', site_id: 0, advertised_prefix: '', translated_packets: 0, dropped_packets: 0, active_flows: 0 },
      max_peers: 16, default_derp_region: 0, netcheck_threshold_ms: 0, exit_server_active: false, exit_server_configured: false, manual_exit_advertisement: false,
      exit_dns_running: false, peerapi_port: 0, exit_node_ip: '', exit_node_restart_pending: false },
    runtime: { connected: true, tunnel_ip: '100.64.0.42', register_user_id: 1, register_user_name: 'owner@example.com', identity_pubkey_prefix: 'nodekey:3f2a…',
      derp_home_region: 4, derp_region_default: 4, derp_home_region_name: 'Frankfurt', derp_rtts: [{ region_id: 4, name: 'Frankfurt', rtt_ms: 24 }, { region_id: 3, name: 'London', rtt_ms: 38 }],
      startup_error: '', startup_retrying: false },
    mtu: { mode: 0, fixed_mtu: 1280, eff_mtu: 1280, eff_mss: 1240, eff_pmtu: 1500, source: 'auto' },
    peers: [
      { hostname: 'nas-at-the-other-site-with-a-long-name', derp_region: 4, derp_region_name: 'Frankfurt', vpn_ip: '100.64.0.9', online: true, direct_path: true, subnet_routes: [] },
      { hostname: 'laptop', derp_region: 4, derp_region_name: 'Frankfurt', vpn_ip: '100.64.0.11', online: false, direct_path: false, subnet_routes: [] },
      { hostname: 'office-router', derp_region: 3, derp_region_name: 'London', vpn_ip: '100.64.0.12', online: true, direct_path: false, subnet_routes: [{ network: '10.20.0.0', prefix_len: 16 }] }],
    accepted_routes: [{ network: '10.20.0.0', prefix_len: 16 }] },
  '/api/network': { networks: [{ ssid: 'HomeNetwork', static_ip: { ip: '', mask: '', gw: '', dns: '' }, eap: { method: 0, phase2: 0, identity: '', username: '' } }],
    sta_ttl_override: 0, lan_name: 'esp32-tailnet-1a2b', ap: { enabled: false, auto_off_when_connected: true, channel: 6, hidden: false, dns_relay: { enabled: true, healthy: true, upstream: '192.168.1.1' } } },
  '/api/firewall': { lists: ['TO_ESP', 'FROM_ESP', 'TO_AP', 'FROM_AP'].map((name, index) => ({ index, name, desc: name.replace('_', ' ') + ' traffic',
    stats: { allowed: 1000 + index, denied: index * 3, nomatch: 12 }, rules: index ? [] : [{ index: 0, src: '0.0.0.0/0', dest: '192.168.4.0/24', proto: 6, s_port: 0, d_port: 22, action: 0, hits: 4 }] })) },
  '/api/portmap': { mappings: [{ proto: 'tcp', ext_port: 8080, int_ip: '192.168.4.20', int_port: 80, name: 'Sensor hub UI' }], max: 8 },
  '/api/dhcp/reservations': { reservations: [{ mac: '02:00:00:00:20:01', ip: '192.168.4.20', name: 'Sensor hub' }], max: 16 },
  '/api/dhcp/leases': { clients: [], leases: [] },
  '/api/mac/denylist': { denylist: [], max: 16 },
  '/api/tailnet-forward': { rules: [rule(0, { name: 'MQTT broker at the other site' }), rule(1, { name: 'NAS web UI', listen_port: 18443, destination_port: 443, tailnet_destination: 'nas.example-tailnet.ts.net', enabled: false, installed: false,
      diagnostic: { code: 'disabled', summary: 'Rule disabled', next_step: 'Test the destination, then enable', service_status: 'unknown', data_plane_status: 'unknown' } }),
    rule(2, { name: 'Syslog (UDP)', protocol: 'udp', listen_port: 15140, destination_port: 514, allowed_source_subnet: '192.168.1.0/24', destination_check: null })],
    max: 8, uplink_has_ipv4: true, uplink_ip: '192.168.1.50', tailscale_control_connected: true, observation: 'passive_snapshot' },
  '/api/system': { version: '0.1.38-Mattboxx-1.14-dev.6', build_date: 'Oct 22 2026', build_time: '18:00:00', idf_ver: 'v5.5.3',
    firmware_updates: { enabled: false, auto_install: false, beta_channel: false, install_hour: -1 }, device_name: 'Tailnet Gateway', tz: 'CET-1CEST,M3.5.0,M10.5.0/3',
    session_timeout_s: 0, session_remaining_s: 0, web_auth_enabled: true, web_password_set: true, web_port: 80, wifi_power_save: false, wifi_power_save_known: true,
    wifi_power_save_active: false, tx_power: 78, tx_power_nvs: 78, log_tail: 'I (1234) main: ready', reset_history: [{ wallclock: 1792000000, reason: 'Power on', who: 'boot', crash: '' }] },
  '/api/system/updates': { enabled: false, auto_install: false, beta_channel: false, install_hour: -1, busy: false, checked: false, update_available: false,
    status: 'Periodic checks disabled', latest_version: '', repository: 'Mattboxx/esp32-tailnet-gateway' },
  '/api/sdlog': { sd_level: 3, console_level: 3, card_mb: 0, free_mb: 0, current_file: '', file_count: 0, dropped: 0, bytes_written: 0 },
  '/api/wol': { devices: [{ name: 'NAS', mac: '02:00:00:00:30:01', port: 9 }, { name: 'Workstation', mac: '02:00:00:00:30:02', port: 9 }] },
  '/api/mqtt': { enabled: true, connected: false, uri: 'mqtts://broker.example', base_topic: 'home/gateway', interval_seconds: 30, broker_watchdog_timeout_seconds: 300, broker_watchdog_wol_mac: '' },
  '/api/ntfy': { enabled: false, server: 'https://ntfy.example', topic: '', info_enabled: false, commands_enabled: false, last_publish_ok: false },
  '/api/snmp': { enabled: false, running: false, community: 'private-example' },
  '/api/service-watch': { enabled: false, notify: false, interval_s: 900 },
  '/api/service-leases': [],
  '/api/health': { enabled: false, notify: false, interval_s: 60, failure_threshold: 3, gateway_port: 0, dns_name: '', internet_ip: '', internet_port: 0, tailnet_target: '', tailnet_port: 0, checks: [] },
  '/api/operations': { devices: [{ index: 0, name: 'NAS', mac: '02:00:00:00:30:01', target: 'nas.lan', monitor: true, notify: false, host_port: 5000, service_port: 0, timeout_s: 120, interval_s: 300, max_checks: 10, kind: 0, scope: 0, state: 'idle' }], events: [], monitoring: false, guard: false, remote_commands: false,
    recovery_state: 'idle', sockets_used: 12, socket_limit: 31, internal_min: 14000, internal_largest: 12000, minimum_internal: 16384, minimum_largest: 8192, socket_reserve: 4, interval_s: 60, control_connected: true },
  '/api/capabilities': { schema: 2, features: [] },
  '/api/events': { config: { events: true, metrics: true, snapshots: true }, persist: true, storage: true, boot: 12, now: 1792000600, uptime: 93784, events: [
    { k: 'tailnet', l: 'info', b: 12, t: 1792000500, u: 93600, m: 'Tailnet connected' },
    { k: 'uplink', l: 'warn', b: 12, t: 1792000400, u: 93500, m: 'Wi-Fi uplink lost (reason 8)' },
    { k: 'boot', l: 'info', b: 12, t: 1791906800, u: 1, m: 'Started 3.0.0-beta.1 from ota_0, reset SW: web ota' }] },
  '/api/history': { config: { events: true, metrics: true, snapshots: true }, persist: true, storage: true, boot: 12, now: 1792000600, uptime: 93784, range: 'live', step: 60,
    points: Array.from({ length: 60 }, (_, i) => [0, 12, 93784 - i * 60, 44000 + (i % 7) * 300, 30000, 7100000 - i * 900, 400000 + (i % 5) * 90000, 60000 + (i % 3) * 9000, -58 - (i % 4), 20 + (i % 9), 5, 3]) },
  '/api/system/snapshots': { available: true, before_update: true, restore_pending: false, slots: [
    { slot: 1, valid: true, seq: 3, t: 1791906700, reason: 'update', firmware: '3.0.0-dev.2' }, { slot: 2, valid: true, seq: 4, t: 1792000000, reason: 'manual', firmware: '3.0.0-beta.1' },
    { slot: 3, valid: false, seq: 0, t: 0, reason: '', firmware: '' }] },
  '/api/tailnet-names': { enabled: false, lan: false, relay: true, lan_listening: false, peers: 6 },
  '/api/notify': { events: 'problems', waiting: 0, dropped: 0,
    telegram: { enabled: false, has_token: false, chat: '', sent: 0, failed: 0, last_error: '' },
    email: { enabled: false, host: '', port: 465, security: 'tls', user: '', has_password: false, from: '', to: '', sent: 0, failed: 0, last_error: '' } },
  '/api/cellular': { config: { enabled: false, mode: 'failover', roaming: false, data_ack: false, uart: 1, baud: 115200, tx: 17, rx: 18, rts: -1, cts: -1, pwrkey: -1,
      pwrkey_active_high: false, apn: '', user: '', has_password: false, has_pin: false },
    status: { compiled: true, enabled_at_boot: false, task_running: false, state: 'off', registration: 'unknown', rssi_dbm: null, model: '', operator: '', ip: '',
      has_ip: false, selected_uplink: false, restart_required: false, connects: 0, bytes_in: 0, bytes_out: 0, error: '', qualification: 'experimental' } },
  '/api/diag/speedtest':{ running: false, bytes: 0, elapsed_ms: 0, kbps: 0, first_byte_ms: 0, http: 0, result: '' },
  '/api/profiles': { schema: 1, active: 'none', rollback_available: false, rollback_to: 'none', rollback_restores: [],
    profiles: [{ id: 'gateway', title: 'Gateway', summary: 'Service Gateway essentials', enables: [] }, { id: 'recovery', title: 'Recovery', summary: 'Wake and check devices', enables: ['device_monitoring'] },
      { id: 'iot', title: 'IoT', summary: 'AP gateway for devices', enables: [] }, { id: 'monitoring', title: 'Monitoring', summary: 'Health and watch', enables: ['health_monitor'] },
      { id: 'advanced', title: 'Advanced', summary: 'Everything visible', enables: [] }] },
  '/api/ethernet': { config: { enabled: false, chip: 'w5500', spi_host: 2, spi_mhz: 20, sclk: 12, mosi: 11, miso: 13, cs: 10, int: 14, rst: 9, static_ip: false, ip: '', netmask: '', gateway: '', dns: '', preference: 'wifi_first' },
    status: { compiled: false, enabled_at_boot: false, driver_started: false, link_up: false, has_ip: false, selected_uplink: false, restart_required: false, link_changes: 0, ip: '', netmask: '', gateway: '', error: '' } },
};

async function install(page, overrides = {}) {
  const posts = [];
  await page.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: overrides.html || html() });
    if (route.request().method() !== 'GET') {
      posts.push({ path: url.pathname, body: route.request().postData() });
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    }
    const key = url.pathname;
    if (overrides.offline) return route.abort('failed');
    const body = key in overrides ? overrides[key] : key in data ? data[key] : {};
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return posts;
}

module.exports = { install, data, rule };
