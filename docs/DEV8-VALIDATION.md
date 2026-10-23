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
- Dev.8 60-minute passive serial and API collection STARTED around 05:04;
  not yet complete at handoff. COM3 is held exclusively by the serial collector.
  Opening API sample: authority ready, 11/31 sockets, lifetime internal minimum
  8043 B, largest block3456 B, raw minimum task HWM484. Do not call these final
  minima or a reliability PASS. Files: `dev8-soak-60min.log` / `.jsonl` under
  private-device. Owned echo server stopped after cleanup.

## Offline results actually executed

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
