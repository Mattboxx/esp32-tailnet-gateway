# Continuation — dev.7 source / dev.6 hardware checkpoint (2026-10-22)

> **Newest checkpoint:** [TAKEOVER-VALIDATION.md](TAKEOVER-VALIDATION.md).
> Authenticated echo/source-denial/expiry/profile checks now have real results;
> Linux is available; final campaigns PASS. Both captures completed, all jobs
> exited, temporary lab rules removed and SNMP/profile restored. Older tasks below
> are historical, not an instruction to repeat already completed work.

Latest: parent `99548da`, MicroLink `fa3153b`, local only. Dev.7 fixes initial-map
recovery plus truthful rule/policy diagnostics. WiFi/Ethernet builds PASS;
Final Windows offline/browser **63/63**, Linux sanitizer **60/60 PASS**.
75 synthetic browser scenarios; logs/hashes in TAKEOVER-VALIDATION.md.
SNMP 27 operational OIDs (v1/v2c forced LAN) + 12 Tailnet replies PASS; restored
OFF unchanged. COM3 serial capture completed 3600.22 s, later API sampler 1800 s
(30/30 samples). No observed panic/WDT/reset, but a five-minute authority outage
is a confirmed dev.6 finding, not an availability PASS. Tight heap remains.
Do not flash dev.7 using old dev.6 authority. Stable ota_1 must remain untouched.
Lab cleanup completed: two disposable rules removed, owner rule exactly
unchanged; browser reload one rule/no lab names. Do not rerun cleanup blindly.
Next incomplete available work: exact dev.7 physical install/recovery campaign
only IF owner answers the pending explicit image authorization. Otherwise keep
the board intact; prepare controlled integration/two-client procedures without
changing production exposure/policies. Two real clients, NVS/OTA/AP recovery,
longer resource/fault qualification and optional integrations remain open.

All owned jobs finished at about 23:08; no COM3 reader remains. Do not revive old
session IDs. Device-tool guards committed in `df8a420`: exact starting version/
slot and protected slot required, host guard tests PASS. Never run the OTA
upload helper on current active ota_0: it would target protected stable ota_1.
Authorized safe path must first verify backup/recovery, boot stable ota_1 and
upload the pinned WiFi dev.7 image to ota_0; no blanket flash permission.

23:08 update: physical dev.7 permission still pending; no reboot/flash so far.
Temporary SNMP/profile/lab exposure cleaned; strict
lease ledger intentionally retained. Root firmware inputs unchanged since
`99548da`; exact private dev.7 artifacts/hashes preserved. The owner's untracked
COMMUNITY-POSTS.md remains untouched and must not be committed. No push/release.

> **Handoff:** the current state, open work and next actions for the publishing agent are in [CODEX-PUBLISH-HANDOFF.md](CODEX-PUBLISH-HANDOFF.md). Read it first.

## Latest session (Claude Code, took over interrupted Codex work)

**Latest checkpoint (2026-10-22 evening):** rebrand (ESP32 Tailnet Gateway),
website (website/ + tools/build_site.py), GitHub files/CI, OTA rename bridge
and per-variant update assets, UI design system + goal launcher + simple mode +
EN/IT/ES/ZH (owner: no FR/DE for now; drafts in main/i18n/disabled/),
packaging with wifi/eth variants and manifest, launch drafts in docs/launch/.
Final candidate `aaf166ed…` runs on the COM3 board. Next: (1) owner signs in
once in the app browser pane → run the authenticated hardware list in
HARDWARE-CAMPAIGN.md (Service Gateway TCP/UDP E2E, expiry, watch, profiles,
NVS persistence, Web UI OTA + rollback); (2) package the tested image with
`package_release.py --prerelease`; (3) owner authorization for push → bridge
release → rename → Pages (docs/MIGRATION-RENAME.md).

Consolidated offline run 55/55 (build+browser). Owner-authorized hardware
campaign is running on the COM3 board: candidate on ota_0, stable 1.13 kept
in ota_1, private verified backup. Two hardware findings fixed (policy barrier,
login/logout cross-site screening); results and BLOCKED items are in
VALIDATION-STATUS.md. Authenticated UI tests need one owner sign-in in the app
browser pane (the agent never types the admin password on a LAN host).

Nothing was reset; Codex's last edits were verified in place. Owner decision
(2026-10-22): Selective Tailnet Service Gateway is the primary feature, Remote
Recovery & Diagnostics the second pillar (GOALS.md, ADR-015, roadmap note).
Done: SNMP operational subtree; web CSRF/DNS-rebinding screening + login budget
(ADR-012); MQTT status snapshot; F23 profiles (ADR-013); F24 12 guides
(ADR-014); F25 manifest-driven UI gates; Service Gateway destination test
(`service_check.c`, POST /api/tailnet-forward/check), per-rule Test button,
primary guide, Status home card, README/SERVICE-GATEWAY identity rewrite.
New drivers: web_security, config_profiles, service_check (validate_all).
Browser: 47 scenarios PASS; run with NODE_PATH=~/.cache/codex-runtimes/
codex-primary-runtime/dependencies/node/node_modules.
Checkpoint commits: microlink `a3d712a`, root `ce11271` (local, not pushed).
Since then (uncommitted): ml_policy admitted-reply evidence, per-rule last
accepted/rejected stamps, evidence-aware diagnosis (ADR-016), inline guide
destination test; 48 browser scenarios. Templates/home-card expiry and sanitized SG export done after commit `6304913`.
SG MQTT/HA evidence done after `ccf32ab` (shared service_evidence.h). Next, in
order: MQTT state budget (ADR-017) and ntfy system events (ADR-018) done.
SNMP provider test and F31 conditional W5500 Ethernet done (ADR-019, separate
env). Listeners/health follow the selected uplink; Service watch done (ADR-021).
Optional-module supervisor (ADR-022), all 20 guides, export summary, peer path,
phone-width UI checks, SNMP health rows and HA watch/profile entities done. Next: (1) F34: all 20 guides present (GUIDES.md); keep in sync with source; (2) F26 export: system summary added; recent-event detail remains as in ops snapshot; (3) F34 guides gap list; (4) on-device MQTT state
size check in the final campaign; (3) F27–F29 remaining events/commands;
(4) F31 Ethernet design (conditional); (5) consolidated validation incl. Linux
sanitizers for web_security/config_profiles/service_check/policy_protocols.
Flash ~135 KiB free (default image): keep additions compact. Nothing committed; no image saved.

## Active continuation — dev.6, operations integration in progress

Source is now 0.1.38-Mattboxx-1.14-dev.6; dev.5 artifacts below are historical.
TX TCP/UDP fragments now have current-destination ownership checks and separate
successful-send reconstruction before epoch-bound return-state publication.
RX handles bounded IPv6 padding/Router-Alert headers before fragmentation.
Current-key metadata mailbox merges delayed/reordered peer jobs. Bounded JSON
preflight rejects deep/duplicate/NUL bodies before cJSON. AP table saves now
reject malformed/oversize tables without silently dropping rows. Service-rule
export and OFF-only import use preview, explicit confirmation and a current-table
guard under the existing forwarding owner; AP forwarding remains separate.
Security build PASS (`build/integration-dev6/security-build.log`); operations
build PASS (`operations-build.log`) predates the final AP validator/MQTT changes.
Actual host fixtures PASS: reassembly, policy, peer convergence, JSON, service
transfer, tailnet state/API, ops API and corrected portmap compatibility.
MQTT now retries resource/init/connect failures with bounded worker-owned backoff,
defers Discovery/state/subscription out of the connection callback, preserves
outage time across failed retries and omits credential-bearing URI logs.
Actual retry/clock/callback/manager fixture PASS (mock SDK/broker):
`build/validation-20261022-002210-410300/`. MQTT target rebuild pending.
Next: finish integration diagnostics/backoff and expiry events, then remaining
profiles/wizards/manifest and independent roadmap work. Prepare browser import
cases; new JS syntax and full regression/sanitizers/hardware remain pending.
No new matching dev.6 image/ELF snapshot saved yet; dev.5 artifacts remain intact.

Current source **0.1.38-Mattboxx-1.14-dev.6**. Development is NOT complete.
All 42 roadmap items and token-efficient instructions remain applicable.
No push, flash, OTA install, release, live device access or production policy change.
Root branch `mattboxx`, HEAD `8dbf06081392b292f37746a4858cf5a09f289757`;
MicroLink HEAD `1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`, both dirty.
The untracked policy/reassembly/health files are essential: HEAD alone cannot
reproduce this work. Preserve all untracked files/private build outputs and
unrelated COMMUNITY-POSTS. See WORKSPACE-CHECKPOINT.md for the saved inventory.

## Completed since the shutdown checkpoint

- Operational UI actions now disable on stale/failed reads; drafts remain.
  WoL labels distinguish confirmed local send, possible partial send and boot.
- Bounded tunnel-ingress reassembly: two lazy PSRAM slots, 4096-byte datagram,
  32 fragments, five-second lifetime, key/source/local ownership + policy epoch,
  overlap/checksum/size/capacity/OOM refusal. Final normal RX authorization still
  checks original ports/protocols before translation. No retained borrowed pbuf.
- Transport interruption suspends all data. A fresh COMPLETE identical map within
  30 s can retain bounded return tuples; changed/invalid policy and explicit
  disconnect reset them. Cached peers, keepalives and deltas cannot resume data.
- OFF-by-default gateway/DNS/configured Internet/Tailnet checks share the existing
  recovery worker/socket budget. Separate checksummed ops_health NVS, backoff,
  configuration-generation checks, truthful reasons/next steps, sanitized state,
  HTTP/UI, four HA sensors + enable switch and optional ntfy alerts/info.
- Reproduced dev.4 expired-rule reindex bypass, then fixed it with strict stable
  identity ledger v3. Existing permanent bindings captured at first opt-in;
  later new/edited bindings require explicit confirmation. Legacy v1/v2 migration
  keeps matching timers but denies untracked/ambiguous identities.
- Retain-closed or optional transactional deletion after expiry, with 60 s
  housekeeping failure backoff and retained ledger tombstones. MQTT forwarding
  commands now require index AND expected binding; old index-only topics reject.

## Latest actual evidence

Target build PASS; matching current-source image/ELF saved privately in
`build/development-0.1.38-Mattboxx-1.14-dev.5/current-source/`.
Exact hashes/metrics are in VALIDATION-STATUS.md. Earlier dev.5 security/integrated
subfolders and dev.1–dev.4 images are preserved historical snapshots, not latest.

Seven targeted drivers PASS:
service_lease, tailnet_state, ops_api, health_monitor, forwarding_transactions,
policy_protocols, policy_reassembly. Logs:
`build/validation-20261021-233547-047763/`.
Additional exact legacy v1/v2 length/migration/ambiguity lease cases PASS:
`build/validation-20261021-234146-272370/`.
Actual WG receive uses mock crypto/netif, health uses mock probes/platform,
NVS/clock/locks are host fixtures; none equals two real clients or physical NVS.
Exact target ntfy ELF frame budgets PASS (not task HWM); root/history/dependency
pattern scans zero findings at their recorded scope. No fresh full suite,
ASan/UBSan, full SDK matrix, browser run, hardware/soak or release qualification.

## First incomplete work on resumption — no broad initial audit

1. P0 fragment/protocol completion: current RX subset does not solve fragmented
   TX/return-state recording, IPv6 pre-fragment extension chains or real
   PMTU/NAT/exit/4via6 interoperability. Inspect the actual netif fragmentation/
   successful-send boundary before adding state. Never authorize later fragments
   using a loose tuple, bypass current policy, or treat blanket denial as parity.
2. P0 review same-key queued peer metadata/endpoint freshness and reconnect
   server compatibility (complete-map barrier versus actual Tailscale/Headscale
   initial responses). No production policy changes/device use to test this.
   Keep source/key/policy revocation independent of cache installation.
3. Complete administration/CSRF/DNS-rebinding/rate/OTA/NVS audit and resource/
   optional-service isolation. Current thresholds are not measured guarantees.
4. Independent approved work when a concrete P0 dependency blocks progress:
   finish per-peer/direct/DERP health diagnostics and controls; expiry events/
   opt-in notifications; service gateway commissioning and safe import/export;
   non-destructive shared config owner, all five profiles and all 12 wizards.
5. Finish capability-driven UI/export/privacy/integration/SNMP coverage, actual
   conditional Ethernet/uplink support and advanced remaining roadmap scope.
6. Consolidated final validation only after feasible implementation is integrated:
   34-driver offline runner + C/SDK/sanitizers/browser, NVS/OTA/resource/fault tests.
   Hardware requires fresh authority, identified board, verified firmware/config
   backup and concrete recovery. Stable ESP remains untouched.

Use `tools/validate_all.py --only <drivers>` for essential critical/failed checks,
not a repeated full campaign. Final: `python tools/validate_all.py --build --browser`;
Linux sanitizers: `--sanitizers --browser` with pinned SDK/cJSON/lwIP dependencies.
Do not glob device tests. Use the existing external PlatformIO build override,
not stale .pio images. Check flash headroom (~200 KiB current app slot) before
large additions; do not silently alter installed partitions/OTA layout.
Keep implementing related blocks, log full output privately, update scoped
evidence and checkpoint before context exhaustion. Do not ask for next feature
or claim the 42-item project finished.
