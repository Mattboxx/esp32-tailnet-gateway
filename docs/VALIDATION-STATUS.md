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
- Commits microlink `2ec076b`, root `6304913`. Then: 9 risk-annotated rule
  templates with first-free listen port, open temporary access on the home
  card, sanitized Service Gateway evidence in the diagnostic export (actual
  helper: no names/destinations/IPs/ports/CIDRs/errors, every allocation
  failure). ops_api + gateway_operations PASS; build PASS **1,816,232 (92.4%)**;
  browser 50/50. Snapshot `.../service-templates-export/`: BIN `f318c6a558b2f8081ff854443509547e26bc0c2c474c302bae11e857403b6571`,
  ELF `b5b9d510e9f832c5abd00bc91a87bcf13f867f2f3e2f7bbf40f41b82c6285208`.
- Commit root `ccf32ab` (microlink unchanged). Then: shared
  `service_evidence.h` used by Web API, export and MQTT (one diagnosis);
  MQTT state per rule `status`/`destination_check`/`service_reply_age_s` and an
  HA "Tailnet rule status" sensor per rule with orphan cleanup. gateway_operations,
  ops_api, mqtt_discovery, service_retry PASS; build PASS **1,818,068 (92.5%)**.
  Snapshot `.../service-mqtt-evidence/`: BIN `004d703b47cd44291c25cdbac9dc0ad9e6a8c3ef8c650d46f1e2319a3774f1e6`, ELF `328d1b76a12abc2cba1a80370650f1cd2877b10f197bbddb47f345b608e0f2bf`. SPA
  unchanged in this block (browser not rerun).
- Commit root `18cc45b`. Then MQTT state budget: new `mqtt_state` driver on
  the actual rule array/fitting code. MEASURED (host, synthetic worst case):
  8 rules 3,783 B full vs 1,055 B compact; fitted states 5,469 B (level 1) and
  4,741 B (level 2) under the 6,144 B budget. Whole on-device state size is
  still unmeasured. Build PASS **1,818,188 (92.5%)**. Snapshot
  `.../mqtt-state-budget/`: BIN `5d09639fa75d22dd20dbb04256c59c9b4603741c50c6d62401eb00cfd794a562`, ELF `331272c5b5e6339e0626275aa0ea2ad632c4860cc7a7e34da0522a805ce88ba4`.
- Commit root `371c2c7`. Then F29 opt-in ntfy system events (boot with reset
  reason, Tailscale restored after a delivered alert, update available, never
  installed), separate NVS key `ntfy_sysev` for downgrade safety. Drivers PASS:
  ntfy_logic (+actual scheduler), ntfy_transport (+separate-key fault/rollback),
  ntfy_stack incl. exact ELF ENTRY budgets: task_main 688/768,
  send_system_event 576/768, available_update_id 384/768 (frames, not task
  HWM). Build PASS **1,819,668 (92.6%)**; browser 51/51. Snapshot
  `.../ntfy-system-events/`: BIN `553c021c20ac1ddf46c79cb46dac52e8dce7b9e22d464c48fe51a3bbe90c044b`, ELF `2f6eef4bd1a9ba9d44d0745da0d24c0c31a42c9dc8d8f3cbd45891b9317e918b`.
- Commit `a30f87f`. Then SNMP rows 22 (rules with reachable destination test)
  and 23 (rules with admitted service reply) via the shared evidence helper.
  snmp_codec PASS (actual MIB walk, 23 rows) and, after `e0b94b8`, the actual
  provider (values, sentinel, SG counts). SNMP task stack HWM unmeasured. Build PASS
  **1,820,404 (92.6%)**. Snapshot `.../snmp-service-evidence/`: BIN `70412c58f7c7aeb2b88447f46d01440b34c1d966029c11dd369c9260fccc8fd9`, ELF `a0159b1a865bf1d54698fd54749e60632001ed52680371cca391c0170c9c4c7e`.
- Commit `792457d`. Then F31 conditional W5500 Ethernet (ADR-019): eth_uplink
  core driver PASS; capabilities (+3 Ethernet states), route_hook, netif_hooks
  PASS; browser 53/53. Default build PASS **1,828,368 (93.0%)**, BIN `153d0b3b54ffa0d0ebc7e1861fa0c75bb02875c33094693c298abb01adde2681`
  (`.../ethernet-default/`). Ethernet build `esp32-s3-eth` PASS **1,881,192
  (95.7%)**, BIN `60c8109224b82ce7a3a1657675d6ce65c4d8c91b7bfc5c48106b7636028c705b` (`build/validation-20261022-eth-env/`). Driver,
  link, DHCP, ACL hooks and uplink switching are NOT exercised on hardware.
  Reproducibility fix: four inherited options pinned in sdkconfig.defaults.
- Commit `1ce98d2`. Then F08: shared login budget (web + remote console) and
  console VPN binding by tunnel address (ADR-020); web_security PASS (incl.
  tunnel binding cases); build PASS 1,828,444 (93.0%). Console path itself
  not host-tested end-to-end.
- Commit `fbe8e3a`. Then Service Gateway on the selected uplink: bindings use
  Ethernet while selected, "en" ingress accepted, rebinding on change.
  tailnet_core (+Ethernet binding cases), portmap, forwarding_transactions,
  gateway_operations PASS (WiFi path unchanged). Builds PASS: default
  1,828,476 (93.0%), Ethernet 1,883,424 (95.8%). Not hardware-exercised.
- Commits `fa13776`, `96d10fa` (listeners/health on selected uplink). Then the
  opt-in Service watch (ADR-021): service_check PASS incl. watch scheduling,
  two-miss alert, recovery, manual precedence, notify off; ops_api PASS;
  browser 54/54; build PASS 1,830,764 (93.1%). Snapshot `.../service-watch/`:
  BIN `c4b8249572ac8427d84671140d7831a332cc6bd29961586e90a4ab73db68137b`, ELF `6d03841354e558ef07c333ecdf41aeaaeb33bf3daafc33f0f629f9764e31e7d6`. The watch POST handler is not host-tested.
- Commit `beaa161`. Then optional-module supervisor (ADR-022): service_retry
  (+actual supervisor backoff), ops_core PASS; build PASS. Low-memory start
  failure itself not reproduced on hardware.
- Commits `563b0cb`..`4bf99e1` (supervisor, guides). Then F26 export system
  summary: ops_api (+exclusion/OOM of the summary) and config_profiles PASS;
  build PASS 1,831,900 (93.2%). Whole export handler not host-tested end-to-end.
- Consolidated offline run (Windows, no `--build`, `--browser`): 53 checks,
  50 PASS (`build/validation-20261022-144509-119100/`). The 3 failures were
  stale tests from earlier Codex work: feature_preservation did not know the
  deliberate index-only MQTT topic replacement (now an explicit successor
  map), web_port/upstream_038 lacked the json_guard include path. Rerun of the
  3 PASS (`build/validation-20261022-144747-357176/`). Linux sanitizers,
  device tests and hardware were NOT run.
- Commits `d7bdab4`..`f148880`: stale-test fixes (offline suite 53/53),
  hardware guide, per-rule peer path, 60 browser scenarios incl. 375 px phone
  width on six pages, SNMP health rows 24-27, HA Service watch switch and
  profile sensor. Builds PASS, latest 1,833,100 (93.2%).
- Consolidated offline run with `--build --browser` (Windows): **55/55 PASS**,
  `build/validation-20261022-152515-095847/`. Includes new drivers mqtt_commands and the handler tests
  for Service watch, destination check, Ethernet and profiles; browser 70/70.
  Image `.../consolidated-20261022/`: BIN `2e59380ec8d764acee00a076edcf9fc2cf05b752251222b6e6301f4ec870c0ef`,
  ELF `19d590cb66c3db90adfdde2b000922a9d59fb386e9525d931530ec57d247d7a8`. Not run: Linux ASan/UBSan, device tests, hardware.
- Physical board (read-only, 2026-10-22): ESP32-S3 QFN56 rev v0.2, 16 MB flash,
  8 MB PSRAM, USB-Serial/JTAG; no flash encryption/secure boot. Installed:
  stable 0.1.38-Mattboxx-1.13 active in ota_1 (dev.1 in ota_0). Running and
  online (DERP connected, direct peers; MQTT broker unreachable; internal free
  heap about 12.7 KB in the log). Full 16 MB backup read twice: only 4 NVS
  blocks differ (runtime writes); all images/partition MD5 valid. Private copy
  and restore steps are under ignored build/private-device/.
- AP fallback (ADR-023): runtime_recovery PASS with new fallback cases; build PASS.
- **Hardware campaign (owner-authorized, COM3 board, 2026-10-22).** Candidate
  written to ota_0 with ESP-IDF otatool and selected (otadata seq 29); stable
  1.13 kept untouched in ota_1 as the USB rollback target (`otatool
  switch_ota_partition --name ota_1`, or full restore from the private backup).
  - Finding 1 (fixed, `49b8441`/microlink `2e2e96c`): stream start suspended an
    already complete policy, so hosted-control deltas were rejected
    (`delta-while-suspended`), tunnel data blocked, re-registration every ~15 s.
    After the fix: no full-refresh errors, 2 peers linked, `tailscale ping`
    direct ~10 ms, ICMP 0% loss, Web UI over the tailnet HTTP 200.
  - Finding 2 (fixed, this checkpoint): POST login/logout skipped cross-site
    screening (cross-origin login answered 400 instead of 403). Image
    `cb1e0ad431012966964af6bf7b1c208ed9f64b5784456000a4783d89b52306d4` on
    ota_0: cross-origin and `Sec-Fetch-Site: cross-site` login/logout 403,
    same-origin login reaches the credential check, direct ping 12 ms and
    tailnet HTTP 200 after reflash.
  - USB reset of the same image (private serial log): IP after 4.1 s,
    recovery AP off at 6.9 s (uplink connected), direct WireGuard session
    13.5 s, DERP connected ~13.8 s; no panic; internal free heap 10.5–13.2 KB
    across 90 s; DERP task stack free 5,304 B. MQTT retries every ~20 s fail
    only because the broker is unreachable; routing is unaffected.
  - Unauthenticated checks PASS: 401 on protected status/restart/Ethernet/
    Service watch/export/capabilities APIs, setup refused once a password
    exists, CSP/X-Frame-Options/nosniff/Referrer-Policy present.
  - BLOCKED: authenticated Web UI flows (Service Gateway TCP/UDP end-to-end,
    rule expiry, destination test, Service watch, profiles, NVS persistence,
    OTA via UI) — the agent may not type the admin password into a non-local
    host; needs one owner sign-in in the app browser pane. AP-fallback live
    test (requires removing the saved WiFi), W5500 (no hardware), Linux
    sanitizers (no WSL distro/Docker), MQTT/HA (broker unreachable), soak.
- **UX/i18n/rebrand checkpoint (2026-10-22 evening).** Consolidated offline
  run `validate_all.py --browser`: 57/58 PASS; the only failure was the
  sensitive scan flagging synthetic 192.168.1.x examples in the new website
  and diagrams, fixed by giving those documentation trees the same exclusion
  as docs/README (rerun: 0 findings). Includes 73 browser scenarios on the
  built (minified + translated) page, layout audit 8 sections × 20 runs
  (9 viewports, simple/advanced, it/es/zh), website build/link/SEO check and
  9-viewport browser test, i18n coverage ≥ 90 % (it 94.0, es 94.5, zh 95.1).
  Firmware: WiFi `aaf166eddaef76444f37d0a80cde7973707406e4f955e5ca1ca59d77674fd172`
  1,875,760 B (95.4 % of the app slot); Ethernet
  `975e4d61add87edff50e55bfdf7503e8d3fbf25fe7d099992c21771ce95cc331`
  1,930,912 B (98.2 %, only 35 KB headroom: watch before adding anything to
  the Ethernet image). WiFi image flashed to ota_0 on the COM3 board: boot,
  direct tailnet ping 15 ms, Web UI over the tailnet 200, unauth 401,
  cross-site login 403, served page carries the translation bundle, login
  screen verified in EN/IT/ZH. 120 s reboot capture: no panic, internal heap
  7.8–13.0 KB (minimum during TLS handshakes), DERP stack ≥ 5,300 B.
  Updater variant isolation: WiFi image contains no `firmware-eth.bin`, the
  Ethernet image does.
- Pending:
  sanitizers, the BLOCKED hardware items above, Lighthouse on the deployed
  site, a native-speaker review of the it/es/zh wording.


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
