# Takeover validation — 2026-10-22 evening

Current evidence supersedes older missing-session/Linux statements in the
historical ledgers. Verdict remains **NOT READY**. No external publication,
push, flash, reboot or OTA installation performed during this takeover.

## Source and installed image

- Source now **0.1.38-Mattboxx-1.14-dev.7**, the uninstalled correction
  candidate, distinct from the board's dev.6 image.
- Starting parent `4e53eae`, MicroLink `2e2e96c`, branch `mattboxx`.
- Installed WiFi dev.6 is still `aaf166ed…`, active ota_0. Stable 1.13 in
  ota_1 and verified private backups remain intact. Later black/green builds
  and the diagnostic correction below are **not installed**.
- Preserve the owner's untracked `docs/COMMUNITY-POSTS.md`.
- Owner authenticated the browser and explicitly authorized subsequent routine
  sign-in to this board. Credentials/session material must stay out of files.
  Browser interaction uses supported visible controls, not page-context fetch.

## Confirmed correction

Rejected-only rule traffic was masked by shared remote-tuple reply evidence,
which could originate from a destination test or another binding. Actual handler
regression reproduced FAIL before the change, then PASS. Rejection now wins
over unrelated reply/no-answer evidence; reply text no longer claims successful
LAN delivery or application health. No packet authorization behavior was changed.
Files: `main/service_diagnostics.h`, `tools/test_gateway_operations.py`,
`docs/TROUBLESHOOTING.md`.
Logs: `build/validation-20261022-221427-074702/` (before),
`build/validation-20261022-221447-993957/` (after).

## Real hardware evidence (installed aaf166 image only)

- Existing user rule preserved. Two disposable `lab-*` echo rules added OFF,
  then enabled, saved and reloaded using authenticated UI.
- Windows selected a Tailnet route to the board's LAN IP by default. Those
  initial attempts were discarded as LAN-path evidence. Probe tool now binds
  the LAN source and sets per-socket Windows `IP_UNICAST_IF` (network byte
  order), without route/firewall changes. A host regression covers this.
- Forced LAN → ESP → PC Tailnet echo: **TCP 20/20, UDP 20/20** payload matches.
  Echo server observed the ESP Tailnet source; UI counters increased.
- Same client, rule source changed to synthetic ineligible `/32`:
  **TCP 0/3, UDP 0/3**, reject counters increased. Source restored:
  **TCP 2/2, UDP 2/2**. This is NOT two independent Tailnet identities and
  the PC has Tailscale installed to host the destination service.
- TCP destination test succeeded while the rule was OFF (17 ms): proves only
  gateway-to-service TCP handshake. Initial OFF probes did not force LAN and
  must not be advertised as LAN-specific negative coverage.
- TCP 120 s lease armed then expired: forced-LAN TCP **0/2**, simultaneous
  permanent UDP control **2/2**. Reboot/persistence remains untested.
- Monitoring profile preview reported two changes; apply succeeded. Owner
  confirmed native rollback dialog after browser automation stalled. UI now
  reports **Active: none / Rolled back**. No reboot persistence proof.
- Re-read confirmed device monitoring and Health Monitor OFF after rollback.
- Temporarily owner-authorized SNMP: v1/v2c sysDescr identified dev.6; all
  **27 operational Gauge32 OIDs in both versions over forced LAN**, plus
  **12 Tailnet SNMP replies** across refresh ticks PASS. Zero LAN retries.
  Finally verified SNMP OFF with community/name/contact/location unchanged.
  No returned values/identifiers logged. Used `--ops-only --prompt-password`,
  not the legacy stress/cycle path.
- Private raw evidence: `build/private-device/lab-*-takeover.log`,
  `lab-*-lan-*.log`, `soak-takeover-60min.log`. Never upload these.

## Resource capture and test tooling

Recovered earlier nominal 60-minute capture is actually **2570 s / 42m50s**,
without completion footer. Internal free heap 7,847–13,011 B, last 12,555 B;
DERP stack minimum 5,296 B; no panic/WDT/allocation-failure/brownout lines;
one boot marker with attribution not independently proven. This is not a
60-minute PASS. Largest block was not measured by that capture.

New no-reset COM3 serial capture started around 22:07 local for 60 minutes.
At this checkpoint it is RUNNING, not PASS. Exact timing/result must come from
its final private summary. Only one process may own COM3. Do not reboot during
this continuity capture. Soak tool now refuses overwrite, restricts private
output paths, records completion/elapsed time and can analyze old logs offline.
Host drivers `soak_serial` and `lab_echo` PASS; they do not qualify hardware.

### Reconnection finding and correction candidate

The server ended its map stream at +1339 s. Next registration returned no map;
the initial streaming read timed out, yet control was declared connected with
authority suspended. Forced-LAN UDP then failed 0/2. A subsequent full map
restored authority at +1639–1646 s without reboot: about five minutes of
disrupted service, not a permanently wedged board. DERP/WG handshakes alone
were not evidence of working data. Exact transport/root-server cause is open.

Confirmed defects: stream requests always set OmitPeers=true, even without
current complete authority; missing initial netmap was nonfatal and could
declare CONNECTED. Dev.7 requests peers when authority is missing and retries
incomplete initial registration through existing bounded backoff. No cached
policy is promoted, and filtering stays closed. Status/Tailscale UI separately
reports pending policy. **Physical recovery improvement is not yet tested.**

Actual request/initial-state branches (mock Noise/H2/control) reproduce the old
failure then PASS: `build/validation-20261022-223539-220577/` (before),
`build/validation-20261022-223543-653808/` (after). Linux ASan/UBSan targeted
coordinator + authorization + convergence **3/3 PASS**:
`build/linux-validation-20261022-223638/`.

Authenticated read-only resource capture started around 22:37 for 30 minutes,
password entered through hidden prompt only. Initial samples: internal free
13,027 B, lifetime minimum 5,435 B, largest block 4,864–5,120 B, sockets 9/31,
28 tasks, minimum task HWM raw 484 (not a calibrated safe margin). This is
tight headroom, not a stability certificate or full-hour largest-block history.

## Linux ASan/UBSan

Linux Docker is available. `tools/validate_linux_docker.ps1` runs an isolated
Ubuntu container with read-only source/public SDK mounts and only a dedicated
writable output directory. The `/work/build` shadow hides private device data;
no credentials, Docker socket, host security changes or published ports.

First full run: **55/57 PASS**, two test-fixture defects, not demonstrated
production defects: leaked cJSON fixture root and signed IPv4 helper shift.
Both fixtures corrected without weakening ASan/UBSan/leak detection.
Targeted rerun **2/2 PASS**:
`build/linux-validation-20261022-222634/`.
First full logs: `build/linux-validation-20261022-222125/`.
Final full Linux rerun **58/58 PASS**, ASan/UBSan/leak checks retained:
`build/linux-validation-20261022-224008/validation-20261022-204038-800086/`.
No browser/build/hardware ran inside that campaign. Windows full build/browser
campaign **62/62 PASS**, including **75 synthetic browser scenarios** and full
layout/site checks: `build/validation-20261022-223937-803972/`.
WiFi app 1,878,592 / 1,966,080 B (95.6%), static RAM 91,172 B; Ethernet app
1,933,008 B (98.3%), RAM 91,508 B, build log
`build/takeover-dev7-ethernet-build.log`. These app usage figures differ from
complete binary lengths including image headers/alignment.

Later device-tool-only changes: hidden prompt/request-screening headers and
guarded lab cleanup; client/session observer targeted **2/2 PASS** at
`build/validation-20261022-224736-316314/`, cleanup guard **1/1 PASS** at
`build/validation-20261022-224759-200424/`. Full campaign above predates the
addition of that cleanup driver (does not qualify a physical deletion).

Authenticated physical request checks: challenge login, six protected anonymous
GET refusals, cross-origin/opaque-origin/cross-site POST/logout refusal,
Host/Origin mismatch and invalid same-origin body refusal PASS; test session
logged out, no restart/configuration action submitted. Initial checker wrongly
expected arbitrary Host refusal on authenticated native GET: source explicitly
permits it (cookie required, custom names supported). Corrected the test model,
not firmware protections. This is native HTTP coverage, not a browser-origin
or stolen-cookie identity test.

Dev.7 private exact artifacts, **not installed or distributed**:
`build/development-0.1.38-Mattboxx-1.14-dev.7/target/`.

| Variant | Artifact | Bytes | SHA-256 |
|---|---|---:|---|
| WiFi | firmware.bin | 1878992 | `3248512507b784ab715bd66052f7753997fab49be5fb17727b13373401efa1c1` |
| WiFi | firmware.elf | 16851872 | `bfc9bc7d9f3c7f11a5e223583447190ae843017db3db8246c4cc8a2799e7ef31` |
| Ethernet | firmware.bin | 1933408 | `f3ce7b92f8da96ec4589236e092a00fcd9793ea4c0c5f22e02060e1edaa72cc7` |
| Ethernet | firmware.elf | 17243980 | `ddabde7549b6c96ad84bca85291d09b7547f574e8d885ef56ef0bae3b5a6e978` |

Existing full-flash backup files were rehashed against their recorded manifest;
both match their individual records (not claimed byte-identical to each other).
Exact dev.7 installation permission requested; **pending owner answer**.

## Local source preservation and privacy scope

MicroLink correction committed locally as `fa3153b`; no push. Root commit
pending. Current root/history and nested working-tree scans found zero at
their recorded scope. A newly expanded **nested full-history** scan reports
nine matches in upstream example blobs (458 blobs inspected). Each match was
read and classified against the exact `tskey-auth-X+(-X+)?` template form:
all nine consist solely of uppercase-X example suffixes, not identified real
keys. Raw scanner result remains nine findings; no exception/suppression or
history rewrite was introduced to turn that scan green. Private metadata-only
log: `build/takeover-sensitive-dependency-history.log`.

## Exact continuation / temporary live state

1. Keep uninterrupted capture running to completion, verify profile rollback
   fields and collect largest-block/socket/task metrics via authenticated UI.
2. Temporary TCP lab lease is expired/retained closed; UDP lab rule remains
   enabled/permanent. Remove only the two `lab-*` rules before finishing;
   preserve the original user rule. First lease opt-in established strict v3
   permanent bindings; do not erase its NVS ledger.
3. Service watch, MQTT/ntfy/SNMP fault campaign, authenticated security tests,
   NVS/reboot, AP recovery and safe OTA upgrade remain pending. Inspect the
   watch's target scope before enabling it; do not probe unrelated targets.
4. Never write stable ota_1 just to test OTA. Before booting old 1.13 remove or
   disable timed lab rules: old firmware does not enforce the lease ledger.
5. Two real identities/direct+DERP policy matrix and W5500 hardware remain
   independent missing gates. No policy parity or release readiness claim.
6. Review both worktrees, scan credentials/history, make scoped local commits,
   then final full offline/Linux/browser/build campaign and exact artifact hashes.
   No push/release/rename/Pages without final explicit authorization.
