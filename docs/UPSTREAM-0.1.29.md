# Upstream v0.1.29 integration — Mattboxx 1.7

Integration date: October 4, 2026. Original release/tag: `v0.1.29`,
commit `294af8880140ae78ec5b7153a22a6edfccc50732`. At integration time
this is the published upstream release and main-branch tip.
Credit: Csontikka and contributors, including gszigethy's routing fixes
(upstream #12/#13). Original MIT headers/licenses remain.

## Upstream changes, accounted for individually

- Checked HTTP registrations with handler-table headroom: already present
  in 1.6 (88 slots for the fork's 64 handlers). Kept rather than reduced to
  upstream's smaller table.
- Inline/local favicon, available without a session: already present in 1.6.
- WireGuard interface detection by the `wg` name, rather than a 100.64/10 IP:
  integrated in the route hook, supervisor and selective NAPT consumers.
  A CGNAT-addressed STA can no longer stand in for an unaddressed tunnel.
- LAN-bypass prefix matching skips interfaces without both UP and LINK_UP,
  in the packet hook and diagnostic explanation. Integrated.
- One shared RFC1918 predicate replaces four duplicated expressions.
- Microlink gitlink is unchanged upstream; the fork keeps its existing
  privacy/4via6 modifications and original credits. No dependency update is
  needed for this release.

## Extra defects addressed in this fork

- The supervisor previously rewrote accepted-route entries while the TCP/IP
  packet task and HTTP task could still read the old count. That allowed a
  mixed generation of network/prefix values. Peer collection now builds a
  local generation, publication takes a real cross-core critical section,
  and diagnostics/API readers use a protected snapshot. No microlink calls,
  logging or I/O occur inside it. Packet routing copies only the matched entry.
- The release SDK has optional TCP/IP core locking disabled, making the old
  default-route supervisor's LOCK_TCPIP_CORE calls ineffective. Route changes
  now use a TCP/IP task callback, independent of that SDK option.
- The Web Session card said "Disabled" when only the idle timeout was zero.
  It now explicitly distinguishes password protection and idle timeout.

## Deliberate preserved differences

MQTT/Home Assistant, ntfy, named WOL, AP policy, independent LAN → Tailnet
forwarding, 4via6, exit-node advertising, configurable web port, authentication,
encrypted backups and hardened read-only SNMP remain. No Ethernet wiring is
assumed. Telemetry, external crash/log upload, automatic update traffic, public
speed tests and hard-coded public DNS remain removed. Exit-node selection
still requires a restart, because published VPN handles are retained by
existing consumers; changing that lifetime contract is not part of this update.

Evidence and limitations: [RELEASE-1.7.md](RELEASE-1.7.md).
