# Final hardware campaign procedure (partly executed — see VALIDATION-STATUS.md and CODEX-PUBLISH-HANDOFF.md)

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

## 7. Bench lab recipe (authenticated part, ready to run)

Newest executed results are in TAKEOVER-VALIDATION.md. The earlier nominal
60-minute capture was interrupted after 42m50s; do not call it a completed
soak. Use visible browser controls or an explicitly scoped device API driver;
never use browser page evaluation for network requests or export its cookies.
Credentials and sessions stay in memory and out of reports.

1. Echo service on the bench PC, bound to its **tailnet** address only:
   `python tools/lab_echo.py --bind <pc-tailnet-ip> --port 47001 --seconds 1800`.
2. In the UI (or `POST /api/tailnet-forward` with the full rule list): rule
   `lab-tcp` TCP listen `18830` → `<pc-tailnet-ip>:47001`, source
   `<pc-lan-ip>/32`, enabled; rule `lab-udp` UDP listen `18831` → same port.
   Press **Test destination** on `lab-tcp`.
3. Verify the PC's actual selected egress first: a LAN destination IP can be
   routed through Tailscale. On Windows force this probe socket to WiFi using
   `--source-ip <pc-lan-ip> --interface-index <wifi-index>` (network-byte-order
   `IP_UNICAST_IF`), without changing routes/firewall. Other platforms must
   independently establish LAN egress; source binding alone is not proof.
   From the PC: `python tools/lab_echo.py --probe <board-lan-ip>:18830 --proto tcp --count 20`
   and `--probe <board-lan-ip>:18831 --proto udp --count 20`; expect 20/20 exact
   echoes and growing accepted counters; the echo log shows the board's
   tailnet address as the peer (proof the traffic went through the board).
4. Source refusal: change only the disposable lab rule's source to synthetic
   `192.0.2.123/32`, save, force the same LAN ingress and probe again → 0/20
   and a growing rejected counter. Restore the source. This single-client
   restriction test is not two-client/Tailnet-identity authorization coverage.
5. Expiry: give `lab-tcp` a 2-minute timer; confirm it closes and probes fail.
6. Service watch: it probes every enabled TCP rule, including existing owner
   rules. Do not enable unless every target is approved for probing. In an
   isolated approved table, enable with a 60 s interval; stop the echo; confirm
   the "stopped answering" event; restart it; confirm recovery. Restore OFF.
7. Profiles: preview → apply `monitoring` → rollback; confirm the listed
   changes only.
8. Reboot (System → Restart); after reconnect confirm rules, timers and
   settings are unchanged (NVS persistence).
9. Clean up: delete the `lab-*` rules, disable Service watch, stop the echo.
10. OTA (never overwrite ota_1 for a test): `otatool switch_ota_partition --name ota_1`
    to boot stable 1.13, sign in, upload the candidate `firmware.bin` (1.13
    writes ota_0), confirm the candidate boots with settings intact. 1.13 stays
    in ota_1.

If Windows Firewall drops the echo port on the tailnet interface, record the
test as BLOCKED; do not change host firewall settings for the test.
