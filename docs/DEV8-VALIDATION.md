# Dev.8 continuation and hardware evidence — 2026-10-23

This ledger supersedes older pending-install/session/Linux claims. Verdict:
**NOT READY FOR STABLE RELEASE**. Owner authorizes the eventual publication
sequence only after the Quality Gate. No push, release, rename or Pages change
has occurred. All 42 roadmap requirements remain in force.

## Exact source and artifacts

Starting root HEAD `9a4a85b`, MicroLink clean at `fa3153b`. Dev.7 source was
committed in `99548da`; dev.8 changes the SNMP worker allocation and version,
not authorization policy, partitions, NVS schema or product identity. Built
from that working tree, with ESP-IDF 5.5.3 and the external TEMP build directory.

| Variant | BIN SHA-256 | ELF SHA-256 | Status |
|---|---|---|---|
| WiFi dev.8 | `b70ff745fb0328be8f98b9ec7fe9b1ce1468501d082bf083ebdf336c08e1361f` | `dfc0bed0e299aec2ec76c0d2941d29d0079acd870934f7f8bb3bc648b4908ccf` | Installed on ota_0 |
| Ethernet dev.8 | `454226060a3eaf7f12633fccc40a145122a2257c556c38a4c0df3071e01e9544` | `d076e8f944b6b0725daf272931e19a52bb85eca1f85adee3ce71a4eec39539f8` | Compiled only; no W5500 |

Snapshots: ignored `build/development-0.1.38-Mattboxx-1.14-dev.8/target/`.
WiFi BIN 1,878,880 bytes; Ethernet app 1,933,008/1,966,080 bytes. These are
development images, not stable assets and not merely renamed releases.

## Backups, identity and OTA

- Same physical ESP32-S3 and 16 MB flash reidentified privately on COM3; no
  competing Python/serial test remained before using it.
- Original full 16 MB backups retained. Two fresh 4 MB mapped-region backups
  before dev.7 were byte-identical; all mapped partitions are in that region.
  A fresh 64 KiB NVS backup was also read before dev.8. Contains secrets:
  never commit, attach, publish or distribute any backup/raw device log.
- Bulk USB reads failed twice with corrupt/incomplete packets. No app write
  occurred during those failures. Normal boot was restored. Read-only device
  flash digest subsequently matched the verified stable full-slot backup.
- Stable 1.13 remains in ota_1. Its full-slot backup SHA-256 is
  `f5ae8aaae3565ad4e9aa1209bb609d215391eb665d040a2f9c366bd5a0054a04`.
- Safely booted preserved 1.13, then authenticated LAN-bound HTTP OTA into
  ota_0: dev.7 booted in 35 s; dev.8 in 36 s. Exact image/hash/version/layout/
  protected-slot guards applied. Uploads submitted once, never blindly retried.
- Eight saved configuration groups matched before/after each OTA and against
  the preceding candidate. This is not a complete physical NVS power-loss,
  interrupted-OTA or automatic bootloader-rollback qualification.
- Private records: `build/private-device/backup-20261023-before-dev7/` and
  `backup-20261023-before-dev8/`. Never invoke OTA while ota_0 runs: the normal
  target would be protected stable ota_1.

## Confirmed memory defect and correction

Dev.7 SNMP enable failed with `snmp_agent: failed to create task`. During the
10-minute collection the largest internal block reached 3328 B, below the
worker's 4096-byte internal stack request. Total free heap alone concealed
this contiguous-allocation constraint. Routing/control stayed operational;
SNMP was restored OFF. This was a genuine failure, not an SNMP test PASS.

Dev.8 uses `xTaskCreateWithCaps` with PSRAM/8-bit stack capabilities on builds
allowing external stacks, paired with `vTaskDeleteWithCaps`. The TCB still
needs internal RAM. No fallback consumes an internal stack on those builds;
allocation failure releases the start reservation. Builds without external
stack support retain their matching ordinary create/delete APIs. No stack
size, authorization, certificate or resource-admission threshold was weakened.

Physical dev.8 results:

- SNMPv1/v2c release identification and all 27 operational OIDs over forced
  LAN PASS; 12 Tailnet replies across refresh ticks PASS; zero LAN retries.
- Full **109-object** walks in v1/v2c PASS. Wrong/empty community, unsupported
  version and SET ignored; malformed/truncated/oversized datagrams survived.
- Three real disable/enable cycles PASS; OFF did not answer. Original
  community/name/contact/location and OFF state restored unchanged.
- Old hardware driver expected only 82 objects; updated to 109, cross-checked
  against the real compiled MIB table, not by weakening the walk assertion.
- Serial analyzer now counts task/worker creation failures separately; old
  `alloc_fail: 0` did not mean all optional worker allocations succeeded.

## Other completed hardware evidence

- Dev.7: forced-LAN TCP 20/20 and UDP 20/20 exact echo; disabled refusal;
  same-client ineligible CIDR 0/3 each and actual `source_rejected` diagnosis.
- Dev.7: 60-second TCP expiry with live UDP positive control PASS. Combined
  USB-read/reboot/UDP-lease test timed out: NOT PASSED. Subsequent boot retained
  rules and expired TCP was closed; both lab rules removed and all eight
  original configuration groups restored.
- Dev.7: authenticated challenge login, six protected anonymous GET refusals,
  cross-origin/opaque-origin/cross-site writes/logout refusal, Host/Origin
  mismatch refusal and valid-origin invalid body rejection PASS over Tailnet.
- Dev.7: serial 600.00 s, 60 heap samples, 7419–12503 B, DERP stack min 5296;
  no observed panic/WDT/reset/brownout, **one SNMP worker-start failure**.
  Parallel API 600 s, 20/20 samples; lifetime internal min 7939 B, largest
  internal min 3328 B, stack HWM raw 484. Collection is not long-soak PASS.
- Dev.8 `tools/test_gateway_campaign_device.py` COMPLETE: forced-LAN TCP20/20,
  UDP20/20, disabled refusal; same-client CIDR refusal0/3 each and diagnosis;
  expiry with UDP control; software reboot retained exact rules, expired TCP
  stayed closed, unexpired UDP lease worked, Advanced profile and watch settings
  persisted. Automatic Service Watch reached the owned TCP echo peer. The
  Advanced profile changes metadata only; it is not another Monitoring-profile
  behaviour proof. Rollback to none, watch OFF, both lab rules removed and
  original eight-group snapshot restored. Private `dev8-gateway-campaign.json`.
- Dev.8 60-minute passive serial and API collection **COMPLETED** 05:03–06:04
  (collector processes identified by command line, exited normally). Serial,
  no reset: 3600.27 s, capture completed, 360 heap samples, 0 panic/WDT/reboot/
  allocation/worker-start/brownout, 0 error lines, internal heap 9155–11695 B,
  minimum task stack free 5296 B, 43 direct handshakes, largest marker gap 2.6 s.
  API, 30 s: 120/120 correct-version samples, uptime monotonic (no reset),
  control connected 120/120 with 0 state transitions, authority ready 24/24
  diagnostic samples, 0 diagnostic failures; lifetime internal minimum 8043 B
  (reached before the capture), current internal free 10403–12951 B, largest
  internal block 3456 B throughout, PSRAM largest 4.3 MB, sockets ≤ 11/31,
  raw task HWM 484, request time ≤ 255 ms. **Scope:** the DERP connection stayed
  on the same socket for the whole hour and no long-poll closure occurred, so
  stream-loss recovery was NOT exercised; the observer's data-plane check is
  `false` by design (API over the tailnet only). A clean hour, not an
  availability or recovery qualification. Observation (pre-existing, also in
  the dev.6 hour: 214 vs 213): about one TLS certificate validation every
  17 s alongside 156 endpoint MapRequests; not a regression, cost not measured.
  Files: private `dev8-soak-60min.log`, `.log.summary.json`, `.jsonl`.
  The largest internal block (3456 B) stays below one 4 KB internal stack:
  any new internal allocation of that size would still fail. The owned echo
  server used by the gateway campaign was stopped after cleanup.

## Integrations lab on dev.8 (Claude, 2026-10-23)

`tools/test_mqtt_lab_device.py` with the local lab broker on the bench PC's
tailnet address and a synthetic locally administered WoL MAC sent only to the
bench PC. Password typed by the owner in a hidden prompt; nothing stored.
Concurrent passive serial capture (no reset): private `dev8-lab-serial-45min.log`.

Run 1 (09:17, private `mqtt-lab-20261023-092841.json`):
- PASS: runtime MQTT reconfiguration connected; 74 Home Assistant Discovery
  configs (42 sensor, 15 binary_sensor, 12 switch, 5 button), 0 invalid;
  availability "online"; invalid `accept_routes` payload rejected, state
  republished, setting unchanged; broker killed → offline detected, tailnet
  still connected; new broker → reconnect in 3.2 s; WoL over HTTP delivered the
  exact magic packet; WoL list and MQTT settings restored exactly, stored MQTT
  password still present; no reboot. After restore the board reconnected to the
  owner's own broker and republished Discovery.
- Invalid (tool defect, not firmware): WoL over MQTT and both `reconnect_wifi`
  cycles sent an empty payload, which the firmware drops by design (HA buttons
  send `PRESS`). The tool now sends `PRESS` and waits for resubscription
  (commit `7ab0933`).
- RAM during the run: internal free 13.0–13.4 KB, largest block 3456 B and
  lifetime minimum 8043 B unchanged in every phase, sockets 8–9.

Run 2 (WoL over MQTT, two Wi-Fi/DERP reconnect cycles): **PENDING** — the
corrected tool is waiting for the owner to type the password once more.

## Internal RAM analysis (Claude, 2026-10-23)

Measured on the installed dev.8 image (`b70ff745…`): lifetime internal minimum
8043 B (reached before the hour and never lower since), largest internal free
block 3456 B in every API sample of the hour and of the integrations lab,
current internal free 10.4–13.4 KB, minimum task stack free 5296 B (DERP
heartbeat), sockets ≤ 11/31. MQTT connect, broker loss/reconnect, WoL and the
configuration restore did not move the largest block or the lifetime minimum.

Where reconnect paths allocate (source and `sdkconfig.esp32-s3` review):

- TLS (DERP, control, MQTT over TLS, ntfy, updater): `MBEDTLS_EXTERNAL_MEM_ALLOC=y`,
  so contexts and the 16 KB/4 KB record buffers live in PSRAM.
- Wi-Fi/lwIP buffers prefer PSRAM (`SPIRAM_TRY_ALLOCATE_WIFI_LWIP=y`); `malloc`
  ≤ 1024 B tries internal RAM first and falls back to PSRAM, larger requests go
  to PSRAM. These paths do not need a large internal block.
- MicroLink tasks (coord 12 KB, DERP TX/RX 10 KB, WG 8 KB, net I/O 6 KB stacks)
  are created once at start; DERP/control reconnects reuse them.
- Every Wi-Fi `GOT_IP` spawns `ts_connect` with a 4096 B internal stack
  (`main/main.c`). After the first start it is a no-op ("Already initialized");
  if the stack cannot be allocated the failure is silent and harmless, except
  that it is also the only retry when the very first start failed. Low risk.
- **Residual risk:** esp-mqtt creates `mqtt_task` with a 6144 B internal stack
  on every client start (first enable, configuration change, or after the 30 s
  connect timeout destroys the client); ESP-IDF 5.5 esp-mqtt has no PSRAM stack
  option. A configuration change works on hardware because `stop_client()` first
  frees the old task's 6 KB stack and the new task reuses that hole (observed
  twice: lab URI and restore to the owner's broker, both connected). Enabling
  MQTT from OFF after boot, or a restart after something else has taken that
  hole, needs a fresh contiguous ~6.5 KB internal block while the largest is
  3456 B: expected to fail with "Error create mqtt task" and keep retrying until
  a reboot. **NOT TESTED** (would change the owner's integration state).
  Candidate fix for Codex: keep one long-lived client and reconfigure it while
  it waits for reconnection (`esp_mqtt_set_config` in `WAIT_RECONNECT`, then
  `esp_mqtt_client_reconnect`) instead of destroy/recreate, with an actual-code
  mock test; or a reserved PSRAM-backed static task if esp-mqtt gains support.
  Requires a new image and hardware requalification.
- ntfy (12 KB) and the MQTT manager (6 KB) worker stacks are internal and are
  created at boot; the operations supervisor's restart of a dead worker would
  need the same contiguous blocks and would likely fail after fragmentation.
  `module_restarts` stayed 0, so this path was not exercised.

No regression was found in these measurements, so no firmware change was
made. A new internal allocation above ~3.4 KB at runtime remains the main
memory risk.

## Build reproducibility and local package (Claude, 2026-10-23)

Rebuilding dev.8 from unchanged sources does not reproduce `b70ff745…`: each
link orders the component libraries differently, so code placement and hash
change while the symbol set stays identical (ADR-026). The installed snapshot
is therefore the only dev.8 WiFi image that may be packaged.

Local pre-release package `build/release-0.1.38-Mattboxx-1.14-dev.8/` (ignored,
not published): `firmware.bin` = `b70ff745…` (exact tested image),
`firmware-factory.bin` `9591bf46933be052679bbfaaac119ed99eadcab7a65bbf4d684390a377bfab46`,
ZIP `4babfaa1363a36d2d0eeaa91aba9168c29ca497b28d74221c53cfa11a6ce82e8`. Inputs were
staged in `build/development-0.1.38-Mattboxx-1.14-dev.8/package-input/esp32-s3/`:
the snapshot BIN plus bootloader/partitions/OTA data and build description from
the same sources (bootloader and partition images match the dev.6 package
byte for byte). Ethernet is not packaged: no W5500 qualification.

## Offline results actually executed

- Claude continuation, after the dev.8 hour (sources = dev.8 firmware plus
  tool/document changes only): Windows **64/64 PASS** with build and browser,
  `build/validation-20261023-060645-818351/`; Linux **60/60 PASS** with
  ASan/UBSan, `build/linux-validation-20261023-061207/`. The Windows build in
  that run is a relink, not the installed image (ADR-026).

- Windows **64/64 PASS**, including WiFi build, 75 synthetic browser cases,
  layout/site/i18n, SDK/authorization and root/dependency scans:
  `build/validation-20261023-043621-133534/`.
- Ethernet build PASS: private dev.8 `ethernet-build.log`.
- Linux **60/60 PASS**, ASan/UBSan/leak detection:
  `build/linux-validation-20261023-043719/validation-20261023-023816-709423/`.
- Later tool-only fixes targeted PASS: SNMP codec/real worker helpers and MIB
  count, device session, serial failure detection:
  `build/validation-20261023-045901-674401/`.
- See [TAKEOVER-VALIDATION.md](TAKEOVER-VALIDATION.md) for recovered dev.6
  3600.22 s serial and 1800 s API captures and its five-minute authority outage.
  The earlier nominal one-hour file was only 42m50s, not a one-hour PASS.
- Owner reports Claude's 5188 HTTP requests/zero errors and 592/600 Tailnet
  pings (~33 ms mean); underlying load log not located in this workspace.
  Retained as reported historical evidence, not independently reverified or
  attributed to dev.8. Do not rerun simply to duplicate that result.

## Remaining gates

Exact in-session stream-loss recovery on dev.8; two independent real Tailnet
identities with positive/negative TCP/UDP/direct-ESP/subnet/gateway and direct/
DERP policy cases; controlled integrations/HA/recovery targets; AP/uplink loss;
physical NVS power-loss/interrupted OTA/rollback scope; representative final
resource/load/soak and final exact-version packaging. Host crypto/interface
fixtures and one-PC CIDR tests are not substitutes. W5500 remains experimental
unless real hardware is qualified. Remote rename must follow the bridge path
and migration window in [MIGRATION-RENAME.md](MIGRATION-RENAME.md).
