# Upstream v0.1.31 integration — Mattboxx 1.9 development

Integration date: October 9, 2026. Target build: `0.1.31-Mattboxx-1.9-dev`.
This aligns the previously integrated v0.1.29 with the published
[v0.1.30 release](https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.30)
(`e41e676a93b80c85fa6321c6707866ff72852312`) and
[v0.1.31 release](https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.31)
(`b053e0bdf3f7d3b6c274bb28d5c93d7b9ceecd92`). Later, unreleased upstream
main-branch commits are intentionally outside this alignment.

Original credit remains with Csontikka/router, Cameron Malone and
Csontikka/microlink, and contributors including gszigethy and 5queezer.
Original MIT licenses/headers remain. Upstream exit-node switch functionality
was already present in this fork and is not presented as a new Mattboxx feature.

## Every upstream change accounted for

| Upstream change | Integration in this fork |
|---|---|
| CGNAT local subnet, DNS and DHCP exceptions | Real packet hook and diagnostic explanation updated. Known peer /32 destinations still win over an overlapping uplink prefix, including a /10. Down interfaces are excluded. |
| Exact WireGuard host-route membership | Ported microlink API and WireGuard helper; consulted in the TCP/IP task, including HTTP diagnostic requests. |
| Supervisor lifecycle lease / connection generation | Reuse the fork's connection mutex, nonblocking supervisor lease and generation tracking. Preserve boot-lifetime published handles and restart-based reinitialization. |
| Default route / netif access and accepted-route publication in TCP/IP context | Synchronous callbacks independent of optional core locking. Retain the fork's cross-core critical section and HTTP snapshots. Completion barrier keeps the lease until queued WireGuard pinning finishes. |
| Netcheck aborts during stop; complete-stop cleanup | Port both microlink changes. Netcheck uses short bounded select slices; completed stops clear the incomplete-stop marker. |
| Received UDP packet queue in PSRAM | Port the upstream IPv4 dataplane allocation change. Existing PSRAM output handling remains. |
| DNS PeerAPI GET/POST and resolver proxy | Port upstream server, bounded DNS messages, strict base64url decoding, UDP-first forwarding and TCP fallback. Use a separate three-client HTTP server with a PSRAM stack. |
| Exit-node switch and NAT | Existing Mattboxx switch, HA command and ntfy visibility retained. Actual server mode is frozen for the running boot; changing saved policy requires restart. |
| PeerAPI Hostinfo announcement | Port microlink's peerapi4/dns-proxy services. Announce the actual port only after listener startup and both handler registrations succeed. |
| Socket budget | Raise defaults, compile guard and future release packaging guard from 26 to 31. Keep pinned ESP-IDF 5.5.3 and existing TCP limits. |
| Upstream UI/docs/version changes | Adapt to the existing fork UI and documentation; version becomes 0.1.31-Mattboxx-1.9-dev. Do not replace custom controls or restore removed telemetry. |

Microlink changes are ported from `7de6a93684a34991fdfa1eeb9281e08523646ef7`
through `17a8c9c0b9f6d7871fd1430f800383c87b99caa2` onto the existing fork,
not by replacing the dependency with an upstream checkout.

## Integration-specific fixes and safeguards

- Keep all custom admin ports. When the Web UI uses 41180, PeerAPI selects
  41181 and advertises it. New TCP AP-side/LAN-to-Tailnet rules cannot collide
  with the active DNS port. No saved forwarding rules are deleted.
- DNS requires both the local VPN address and an exact known remote peer;
  a 100.x address alone is not authorization. IPv4-mapped IPv6 sockets are
  normalized; native IPv6 is rejected. Web authentication is not substituted
  for PeerAPI authorization, because official clients do not use the UI login.
- Check UDP response source IP, source port 53, transaction ID and response
  bit. Reject local, loopback, multicast/reserved and absent resolvers; never
  add a hard-coded public DNS fallback.
- Correct the NAT interaction with CGNAT uplinks: only actual WG TCP egress
  skips translation. WG-to-uplink traffic toward a non-peer CGNAT LAN receives
  configured subnet SNAT or exit-server masquerading, just like other LANs.
- Expose boot-active exit-server state, DNS running state and PeerAPI port in
  Tailscale UI/API, MQTT/Home Assistant and ntfy `info`.

## Mattboxx features preserved

- Optional AP gateway policy and independent AP-side port forwarding.
- Named saved Wake-on-LAN devices, UI actions, MQTT/HA and ntfy commands.
- MQTT availability/state/watchdog/discovery and all existing HA controls.
- ntfy alerts, replay-protected command reception, info/private-info policy,
  error accounting and the 1.8 no-inline/12 KiB stack hotfix.
- Independent LAN-to-Tailnet TCP/UDP forwarding, source CIDRs, MagicDNS
  destinations, per-rule controls and counters, even when AP is disabled.
- 4via6 translation/hooks, route composition without overwriting manual NVS
  routes, exit-node selection/advertising mutual exclusion and fail-closed IPv6.
- Configurable Web UI port, optional password gate/idle timeout, weak-password
  support, fast challenge login, encrypted backup/restore and local OTA.
- CPU/core/temperature metrics, local diagnostics/reset history/logging,
  firewall, DNS cache and hardened optional read-only SNMP.
- No automatic telemetry, external crash/log upload, release polling/download,
  public speed test or public DNS fallback. Optional operator-enabled MQTT,
  ntfy, exit DNS and VPN still generate their explicitly configured traffic.

## Validation and limits

The ESP32-S3 N16R8 build compiles with the pinned toolchain and 31 sockets.
Regression coverage includes actual-C route/diagnostic parity, overlapping
CGNAT prefixes and peer priority, local CGNAT NAT, atomic route snapshots
(20,000 concurrent publications), every prefix width, DNS socket-address
authorization, resolver guards and 50,000 base64url mutations. Static guards
compare all prior HTTP registrations, UI IDs, HA entity IDs and MQTT command
topics with fork baseline `b22035c973a1137d512f24d5eae58ac96c557093`.
The actual SPA is tested with synthetic APIs, including the new DNS status.
ntfy exact-ELF frame budgets and existing validation/privacy/SNMP tests remain.
The main working tree, candidate binary and reachable main history have no
matches in the configured sensitive-data scans. Microlink's current tree also
passes; its history flags nine original example keys, individually verified
as all-X placeholders, not operator credentials. The scanner is not weakened
or bypassed for those historical examples. Pattern checks cannot prove the
absence of all personal data or secrets.

These are build and regression checks, not new hardware validation. This
alignment does not flash a board, validate Internet throughput, certify DNS
compatibility with every official client, or promote a stable release.
Existing v0.1.29-Mattboxx-1.8 downloads remain unchanged. Before promotion,
test official exit-node browsing/DNS, CGNAT DHCP/uplink recovery, custom admin
port 41180, both forwarding systems, 4via6, MQTT/HA and ntfy HTTPS command soak
on the exact candidate image. Default-off/normal subnet-router boots should
have no DNS listener or PeerAPI advertisement.
