# Final hardware campaign procedure (prepared, NOT executed)

Nothing here may run without fresh, explicit authorization for the exact
candidate image. The stable physical ESP stays untouched unless the owner
names it; prefer a second, identified board.

## 0. Preconditions

- Exact candidate: version string, BIN/ELF SHA-256 from
  `build/development-<version>/` (VALIDATION-STATUS.md). Never relabel images.
- Verified backup of the board being flashed: full flash read (esptool
  `read_flash 0 ALL`), its SHA-256, plus a Web UI configuration backup with
  encrypted secrets. Confirm the backup restores on a spare or by checksum.
- Recovery path: USB serial access, stable 1.13 factory image and its hash,
  written steps to restore. Note the downgrade hazard in NVS-KEYS.md.
- Two tailnet clients with distinct identities (A allowed, B denied by ACL),
  one LAN client without Tailscale, a Tailnet service peer (TCP and UDP),
  ability to force DERP (block UDP) and direct paths.

## 1. Service Gateway (primary)

| # | Case | Expected evidence |
|---|---|---|
| 1 | Rule OFF, Test destination | `reachable` with latency; LAN client cannot connect |
| 2 | Enable, LAN client in /32 connects | application works; accepted counter and last-accepted move; `service_replied` |
| 3 | Client outside CIDR | refused; `source_rejected` when it is the only traffic |
| 4 | Peer ACL denies the gateway | `no_tcp_answer`; LAN connection fails |
| 5 | Peer offline | peer path `offline`, test `no_tcp_answer`, watch alerts after two misses, recovery notice |
| 6 | Direct vs DERP | peer path changes; measure throughput and latency for both (record numbers) |
| 7 | UDP rule (syslog) | `udp_unverifiable`; reply age appears after a real reply |
| 8 | Expiry | rule closes at expiry, survives restart closed, ntfy closure event |
| 9 | Edit rule | old test/evidence hidden, new binding token, HA switch topic updated |
| 10 | Uplink loss/return | bindings reinstalled on the new address; no stale listener |

## 2. Recovery, health, integrations

WoL send vs host/service verification; Health Monitor down/recovery;
MQTT broker outage/retry badge and state size (`state_compact_level`); HA
discovery of all entities; ntfy system events (boot, restored, update);
SNMP walk of `1.3.6.1.4.1.99999.2` (rows 1-27); module restart after an
induced low-memory start if practical.

## 3. Security and administration

No-password DNS-rebinding attempt refused (403); cross-site write refused;
login budget shared by Web and console; console VPN binding on a CGNAT LAN.

## 4. Persistence, OTA, rollback

Upgrade from stable with settings preserved; power cut during a profile apply
and a rule save; OTA interrupted; rollback to stable after disabling timed
rules; verify NVS keys behave as documented.

## 5. Resources and soak

`tools/observe_candidate.py` (read-only) for at least 24 h with mixed load:
heap minimum, largest block, socket use, task high-water marks, uptime
continuity, control transitions. Record numbers; do not infer from gaps.

## 6. Ethernet (separate build, only with a W5500 board)

Boot with Ethernet off (WiFi unchanged), wrong pins refused, DHCP and static,
link flap, WiFi-first and Ethernet-first switching, Service Gateway listener on
the selected uplink, ACL hooks effective on Ethernet.

Record every result with the image hash in VALIDATION-STATUS.md; failures stay
open items, never re-labelled as passes.
