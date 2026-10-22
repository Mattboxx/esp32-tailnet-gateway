# Validation ledger

## Current checkpoint — dev.6 continuation (2026-10-22, Claude Code session)

Source **0.1.38-Mattboxx-1.14-dev.6**, uncommitted root/dependency work, taken
over from the interrupted Codex session without resetting anything.

- Interrupted SNMP block completed: agent-side provider + 21 Gauge32 rows
  `1.3.6.1.4.1.99999.2.N.0`, 1 s snapshot cache, unavailable-by-default.
- Target build PASS before web/MQTT-status edits (includes MQTT retry/Discovery
  and SNMP): app **1,788,808 / 1,966,080 (91.0%)**, static RAM 90,148 (27.5%).
  Log `build/validation-20261022-095234-226087/firmware-build.log`. No image
  snapshot saved; later firmware edits are not covered by that build.
- Actual-code drivers PASS: snmp_codec (codec + real MIB walk/ops cache),
  web_security (new: request screening, host trust, login budget, legacy
  control/DHCP assertions now executed), service_retry (+ status snapshot),
  mqtt_discovery, ops_api, capabilities, tailnet_api. Logs under
  `build/validation-20261022-0952*` … `-1004*`.
- Second target build PASS incl. web screening, MQTT status and F23 profiles:
  app **1,799,832 / 1,966,080 (91.5%)**, static RAM 90,316. Log
  `build/validation-20261022-101108-399954/firmware-build.log`. config_profiles
  driver PASS (actual core, fixture settings/NVS). SPA `node --check` PASS.
  Flash headroom ~162 KiB: keep later additions compact.
- Browser suite PASS: 43 synthetic Playwright scenarios (39 prior + profiles,
  guided setup, two MQTT backoff badges), log
  `build/validation-20261022-browser-dev6/browser.log`. Fixed a never-run Codex
  step (checkbox under switch track; now clicks the label like a user) and a real
  UI bug (`.btn` overrode `hidden`). Run with NODE_PATH at the Codex runtime
  node_modules (playwright). Wizard/profile SPA edits followed the last build.
- Service Gateway block (owner priority): service_check driver PASS; final
  target build PASS with every edit: app **1,811,812 / 1,966,080 (92.2%)**,
  static RAM 90,620. Private snapshot
  `build/development-0.1.38-Mattboxx-1.14-dev.6/current-source/`: BIN 1,812,224 B
  SHA-256 `49a6e582333fb259cb7f4663f5ec19293b2895ccac5fe3d278ae2d524ae33dce`;
  ELF 16,671,932 B SHA-256 `a309ea1c78176e74f772e3ab3569435a90207606d4c46e6ced6a6bf27f0c1d57`.
  Browser 47/47 PASS after the last SPA edit. Not flashed; no hardware evidence.
- Local checkpoint commits (no push): microlink `a3d712a`, root `ce11271`.
  After them: admitted-reply evidence (ml_policy), per-rule activity stamps,
  evidence-aware diagnosis, inline guide test. Drivers PASS: policy_protocols,
  tailnet_filter/core/sdk (fixtures repaired for Codex's housekeeping split),
  gateway_operations (incl. evidence states and every-allocation failure),
  service_check, tailnet_api, ops_api. Build PASS app **1,814,296 (92.3%)**.
  Snapshot `build/development-0.1.38-Mattboxx-1.14-dev.6/service-evidence/`:
  BIN SHA-256 `fc8a2fa60f310fae5687bb7a9c06e1681e633b56b5b10f87a39c1f93dca4e101`, ELF SHA-256 `296846b218fac611e61977d8979b60257b6b53f57545cdfd612d8322c8837b83`. Browser 48/48.
- Pending:
  sanitizers, full suite, hardware. Nothing here is hardware evidence.


## Current checkpoint — dev.5 continuation (2026-10-21)

Local **0.1.38-Mattboxx-1.14-dev.5**, uncommitted root/dependency work. Prior
sections below are historical. No live device access, flash, push or release.

- Current-source target build PASS: app **1,766,260 / 1,966,080 bytes (89.8%)**;
  static RAM **89,988 / 327,680 bytes (27.5%)**. Not runtime minima/headroom.
- Latest private artifacts: `build/development-0.1.38-Mattboxx-1.14-dev.5/current-source/`.
  BIN **1,766,672 bytes**, SHA-256
  `9a14b20604aa430bbb26e8f0f4f5c26f5dbcc8dcb05a36bab460b4b588f63c23`;
  ELF **16,419,944 bytes**, SHA-256
  `419c68adb0f015ac99dc2f90dea50ddaded2264311721f5617f003d221f29502`.
  Build log: `build/integration-dev5/current-source-build.log`.
  No firmware changes followed that build; later docs/test edits do not
  requalify or invalidate its source compilation. Earlier `security/` and
  `integrated/` images are preserved intermediate snapshots, not current source.
- Seven targeted native drivers PASS: service_lease, tailnet_state, ops_api,
  health_monitor, forwarding_transactions, policy_protocols, policy_reassembly.
  Logs: `build/validation-20261021-233547-047763/`.
  Additional exact legacy v1/v2 lease migration/length/ambiguity cases PASS:
  `build/validation-20261021-234146-272370/`.
- Confirmed/reproduced defect: moving an expired positional lease to an empty
  rule slot could grant permanent forwarding. Before-fix failure saved in
  `build/validation-20261021-232658-033930/`. Stable binding ledger plus strict
  unconfirmed bindings fixes this; deletion and MQTT selectors use the shared
  forwarding owner. Mock NVS/config cleanup does not prove physical power-loss.
- Actual reassembly/policy and actual WG receive PASS for bounded IPv4/IPv6
  TCP/UDP allow/deny, bad key, crypto failure, epoch/revoke, overlap/expiry/OOM/
  capacity and balanced pbuf ownership. Crypto/netif are mocked. Health checks
  use mock probes/platform; real DNS/TCP/router/Tailnet failures are untested.
- Current exact ntfy ELF frame guards PASS: task 640, poll 768, info 1520,
  alert 32, command 352, publish 496, state 512, batch 48 bytes.
  `build/integration-dev5/ntfy-elf.log`. Not runtime stack high-water proof.
- Root/history scan: 280 paths, 16 artifact payloads, 1,532 historical blobs;
  dependency scan: 105 paths; zero pattern findings. Logs under
  `build/integration-dev5/sensitive-*.log`. These preceded final documentation,
  UI hint and synthetic browser/legacy-fixture edits; not a no-secrets guarantee.
- Full 34-driver/C/SDK/ASan/UBSan/browser regression campaign NOT executed.
  Browser operational/health scenarios are prepared, not claimed passed.
  No hardware, real two-client direct/DERP, NVS/OTA, measured resources or soak.
- Development-plan structural checks PASS (three checks, all 42 matrix rows and
  immutable Master archive retained). Whitespace checks recognize Windows CRLF;
  an initial check without that setting reported line endings as whitespace.
- Latest inline UI and browser-test script syntax PASS; browser behavior still
  unexecuted. Logs: `build/integration-dev5/*script-syntax.log`.

Remaining release blockers include fragmented TX/return recording, broader
IPv6/PMTU/NAT/4via6 compatibility, stale peer metadata/concurrency, actual server
reconnect behavior, full administration/persistence/OTA audit and the remaining
roadmap. Resource thresholds are uncalibrated. Global tunnel health and route
approval remain unknown. **Not ready for a stable release.**

## Historical checkpoint — dev.4 integration (2026-10-21)

Local **0.1.38-Mattboxx-1.14-dev.4** builds on dev.3; older results below are
historical, not a complete dev.4 qualification. Root/dependency HEAD unchanged,
both dirty. No push, flash, board access, publication or stable promotion.

- Current-source S3 build PASS: app **1,751,932 / 1,966,080 bytes (89.1%)**;
  static RAM **89,484 bytes (27.3%)**. No runtime minima/performance claim.
- Saved private image: 1,752,336 bytes; SHA-256
  `bd107ec960f09f12eed9a3e52bf468a623b4c1c1906d3a2d1bc4b33639c49ecb`.
  Matching ELF: 16,334,888 bytes; SHA-256
  `756e2e51726f0e1180b3861d36e1513462349b4d4abad75d67be8a2671cb6207`.
  Latest artifacts: `build/development-0.1.38-Mattboxx-1.14-dev.4/json-ownership-review/`.
  Build log: `build/integration-dev4/json-ownership-review-build.log`.
  Parent dev.4 artifacts are the preserved initial snapshot, not latest source.
  No firmware changes followed this build. Later runner timeout changes have
  syntax checks only; no timeout-behavior validation. Existing targeted tests
  and scans below preceded the final cJSON/UI review, not a full final campaign.
- Targeted native drivers PASS: authorization, protocol headers/ICMP, ops core,
  ops HTTP API, service leases, Tailnet filter/state, ntfy logic/transport.
  These use explicit mock crypto/HTTP/time/NVS/module/queue boundaries.
- Exact current ntfy ELF frame guards PASS: task 640, poll 768, info 1520,
  command 352, publish 496, state 512, batch 48, alert 32 bytes. Not task HWM.
- JS/Python syntax PASS. New browser cases prepared, **not run** (34 total).
  Root/dependency sensitive-pattern/history scans: zero findings; local logs.
- Unified runner has 32 Python drivers, existing C/unit checks and optional
  build/browser/sanitizer scopes. **Full campaign not executed** in this mode.
  Logs: `build/validation-*`, build/check logs: `build/integration-dev4/`.

Implemented code spans registry/recovery, opt-in checks/admission, lease expiry,
capabilities/export and API/UI/MQTT/HA/ntfy integration. Refer to the matrix for
remaining subsets. Guard thresholds are uncalibrated; socket counts are observed,
not reserved. TCP connection success is not application health or power proof;
WoL success means confirmed local send, not boot. DNS can delay cancellation
until its finite SDK lookup completes. No infinite recovery/reboot loop.

Remaining gates: non-atomic tunnel fragments/full policy/PMTU compatibility,
control-outage and metadata ordering; physical NVS/OTA/heap/socket/stack/load/
reconnect/soak and real two-client authorization; remaining health, profiles/
wizards/manifest/export/integration/SNMP/Ethernet roadmap work. Automatic lease
deletion/reindex is not implemented; expired records stay and deny forwarding.
**Release readiness: NO. All 42 requirements remain in scope.**

## Checkpoint 2026-10-21 — permanent plan and local dev.3

Source: **0.1.38-Mattboxx-1.14-dev.3**, from dev.2.
Root HEAD `8dbf06081392b292f37746a4858cf5a09f289757`; MicroLink HEAD
`1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`. Both worktrees contain local changes;
these hashes alone do not reproduce the candidate. Preserve the unrelated
`docs/COMMUNITY-POSTS.md`. No push, commit, flash/OTA install, policy change,
board setting change, tag or publication performed.

### Exact artifacts, not published

Ignored internal record: `build/development-0.1.38-Mattboxx-1.14-dev.3/INTERNAL-VALIDATION.md`.

- Application `firmware.bin`: 1,727,712 bytes; SHA-256
  `01b6143c2fcf7b02710aeed4c26c028900693d4a539bf30f8e3e659d99e471fc`.
- Matching ELF: 16,185,412 bytes; SHA-256
  `70e0c5b45c12f3da83f51fffe4bbe83589b2f63e817a6b6aab6129847ad140bd`.
- S3 target build PASS: ESP-IDF 5.5.3 / PlatformIO espressif32 6.13.0;
  application 1,727,312/1,966,080 (87.9%); static RAM 86,012/327,680 (26.2%).
  Relative to dev.2: +708 application bytes, unchanged static RAM.
- Actual ELF types: policy 27,080 PSRAM bytes; flow 84 bytes ×32 included;
  current+candidate normally 54,160 bytes plus in-flight retired snapshots.
  Peer update 288 bytes. Target ENTRY frames: prune 320, map application 144,
  peer-status query 48, policy compiler 160, RX gate 96 bytes. Individual frames
  are not task high-water measurements. Existing ntfy ELF frame budgets PASS.
- Strong linked policy RX/TX/sent/apply/reset/status symbols verified.
- No new firmware socket/task/NVS key. CPU cost/runtime minima/throughput are
  unmeasured. Prior dev.1/dev.2 images and public stable 1.13 remain intact.
  No release/flashing ZIP generated for this unqualified candidate.

### Confirmed problems and corrections

Actual-C pre-fix tests reproduced: valid at-capacity policy replacement was
rejected; coordinator/WG replacement could lose the new peer because adds ran
before pruning; stale jobs and ignored alloc/queue failure did not converge.
Private policy now removes before upserts; WG owner reconciles before adds;
current membership blocks obsolete queued key work; initial/stream application
propagates failures and blocks for refresh. Nonempty full-map precedence and
KeepAlive no-mutation behavior corrected. No extra peer slots or port authority
from visibility. See ADR-003 and `TAILNET-AUTHORIZATION.md` for exact limits.

Full Master Prompt archived (1,603 lines), compared equal to supplied original
after newline normalization. Goals/constraints/full roadmap/F01–F42 matrix/
continuation checkpoint created; no approved feature removed.

### Executed now — offline, not hardware

- **28 Python drivers PASS**: 24 existing packaging/session/feature/upstream/
  ntfy/SNMP/routing/netif/startup/forwarding/Web-port/Tailnet/PeerAPI/OTA/WoL
  drivers, plus policy, peer convergence, plan and observer. Detailed inventory
  in the internal record/workflow. Packaging 7, session 6 and preservation
  4 unit cases; gateway fixtures include WoL failed-write/reload/concurrency.
- Policy actual-C + extracted WG receive (MOCK crypto/replay/netif) PASS:
  ports/protocols/source/destination/visibility/replies/revocation, 100,000 packet
  mutations, 4,000 publications with 3 readers, bounds/OOM/malformed input.
- Peer driver PASS (4 scenarios): maximum16 replacement, same-ID remove/upsert,
  full/delta/empty/null/keepalive precedence, obsolete queue jobs, 16 allocation
  and 16 queue-failure points. Actual parser/compiler/manager functions, but
  queue/WG-install/NVS sinks, not complete WG add/FreeRTOS/flash behavior.
- Both affected actual-C drivers PASS on Linux GCC ASan/UBSan with leak checks
  and halt-on-error; host-only non-PIE workaround, no host-security changes.
- Pinned actual SDK IPv4/NAPT/pbuf: 38 synthetic-interface scenarios PASS;
  not a live tunnel or proof of fragmented WG ingress support.
- 32 synthetic local browser scenarios PASS. Scanner 3/upstream integration
  11 unit tests and two compiled C validator programs PASS.
- Permanent-plan structural tests 3 PASS; external sampler 8 fake-HTTP/clock
  tests PASS (whitelist, null metrics, version guard, cadence, gaps, transitions,
  diag failures). Neither suite proves firmware feature behavior or uptime.
- Final secret-pattern/history scans: root 262 paths/16 payloads/1,467 historical
  blobs and dependency 103 paths, zero findings after final docs/tools.
  Zero findings are not a
  security guarantee. Both Git whitespace checks PASS (CRLF-aware).
- Host baseline warnings in upstream X25519 array-parameter annotation and
  SDK NAPT fixture debug counters remain visible; no new runtime fix claimed.

The read-only sampler exists but has **not contacted the physical ESP** in this
checkpoint. It preserves null for unavailable socket usage, labels raw stack
units and reports control status only. It does not assign a qualification pass.

## Open essential gates and release decision

Two independent real clients and effective permissions; positive/negative
TCP/UDP/IPv4/IPv6 over direct/DERP, ESP/subnet/exit/NAT/forwarding/4via6; actual
Tailscale/Headscale maps and revocation/key/full-table changes. Physical NVS
migration/power loss, OTA/interruption/rollback, runtime min/largest internal
heap/PSRAM/socket/stack/CPU/timing, measured admission and mixed-load reconnect/
fault/soak. No candidate install authorization exists; prepare tests and continue
independent local P0 work. Historical stable uptime is not candidate evidence.

Tunnel fragments, IPv6 extensions, ICMP errors/PMTU and other protocols remain
conservatively rejected. Precise transport-outage policy and same-key queued
metadata ordering remain incomplete. These are compatibility/availability
gates, not hidden by passing negative cases. **Release readiness: NO.**
Next available work: P0-PROTOCOL F05/F06 in `NEXT-STEPS-FOR-AGENT.md`.
