# Claude continuation — Codex dev.8 checkpoint, 2026-10-23

Code/tool/evidence checkpoint committed locally as `498c04c`. This continuation
document is tracked under a portable filename rather than an ignored HANDOFF
filename. No source change or new test was made during checkpoint preparation.

## Authority and scope

The owner's latest instruction is to hand off the current fixes to Claude,
continue stabilization and local preparation until immediately BEFORE public
publication/rebranding, then return to Codex. **Claude must not push, publish
releases/tags, rename GitHub, enable/deploy Pages, change public metadata or
post announcements.** This supersedes earlier broad public-operation authority
for this handoff. Local implementation, scoped test installs, tests and local
commits remain authorized, preserving stable firmware, NVS and recovery.

Read AGENTS.md, CURRENT in NEXT-STEPS, DEV8-VALIDATION and QUALITY-GATE. Preserve
the full 42-item roadmap and product identity. Do not redo Claude's redesign or
restart an old checkpoint. No new features: fix and qualify the existing work.

## Exact state to recover first

- Workspace: existing PlatformIO project; branch `mattboxx`. Source/tool/evidence
  commit is **498c04c**, after starting **9a4a85b**, not the older Claude checkpoint. Run
  `git log -5 --oneline` and `git status --short`; this handoff commit preserves
  Codex's source/tool/document work. Inspect actual later changes if any.
- `external/microlink`: **fa3153b**, branch `mattboxx`, clean. Parent gitlink
  matches. Its local fixes are not yet published. No remote history rewritten.
- Owner's **untracked docs/COMMUNITY-POSTS.md** is untouched: never stage,
  replace, remove or publish it. All private dumps/artifacts/logs remain ignored.
- **Actually installed:** WiFi `0.1.38-Mattboxx-1.14-dev.8`, ota_0. BIN SHA-256
  `b70ff745fb0328be8f98b9ec7fe9b1ce1468501d082bf083ebdf336c08e1361f`.
  Source version is dev.8 too; no final stable image exists yet.
- Stable **1.13 remains ota_1**. Same physical ESP32-S3 reidentified, 16 MB
  flash/8 MB PSRAM, previous COM3. Identify again before any future install.
- New private backups in `build/private-device/backup-20261023-before-dev7/`
  and `backup-20261023-before-dev8/`; earlier full backups preserved. These
  contain credentials: never commit/upload/attach them. Exact stable digest,
  candidate BIN/ELF hashes and backup limitations are in DEV8-VALIDATION.
- No public push/release/rename/Pages operation has occurred.

## RUNNING at handoff — first action, no new COM3 access

At **05:04–05:05 Europe/Rome, 2026-10-23**, the following owned captures run:

| Collector | Windows PID at checkpoint | Evidence output |
|---|---|---|
| Serial, no reset, 60 min | launcher42268 / worker30600 | `build/private-device/dev8-soak-60min.log`, `.log.summary.json` on completion |
| Tailnet API, 3600 s/30 s | 35788 | `build/private-device/dev8-soak-60min.jsonl` |

COM3 belongs to the serial collector. Do NOT open, reset, flash or restart the
board during collection. Do not kill unrelated Python/Docker/browser processes.
Check process identity/command and live file timestamps; PIDs can be reused.
Expected finish about **06:04–06:05 local**. If this session ends the collectors
early, retain partial files and label interrupted; do not manufacture an hour.
Codex session IDs were serial9217/API82810, but Claude must use actual Windows
processes and files, not assume it can access Codex's terminal sessions.

First opening API sample: correct dev.8/authority ready, sockets11/31, lifetime
internal min8043 B, largest block3456 B, minimum task HWM raw484. These are NOT
final minima. Serial failure analyzer now separately counts worker-start errors.
After completion inspect final JSON/summary and raw event timing privately;
look specifically for natural stream closure and subsequent policy/data recovery.
No reboot observed is not equivalent to uninterrupted data-plane availability.

Completed echo server PID33368 was stopped specifically. All lab rules have
been removed. Profile none, Service Watch OFF, SNMP OFF; original eight-group
configuration snapshot restored. Do not run cleanup against an already clean
table. Agent-created browser tab was closed; routine own-board login is
authorized, credentials must stay in RAM/hidden prompts, not files/env/CLI.

## What Codex changed after Claude — do not lose or repeat blindly

1. Dev.7 fixes at root99548da / MicroLinkfa3153b: fresh peer map when complete
   authority is absent, retry missing initial netmap instead of declaring usable
   control, explicit policy-pending UI, truthful source-rejection diagnostics.
2. Safe device tools: exact image/version/slot/partition/protected-stable guards;
   per-socket forced LAN HTTP/probes because Windows routes the board LAN address
   through Tailscale by default. No host route/firewall edits were needed.
3. Real dev.7 SNMP failure: 4096-byte internal task stack could not be allocated;
   largest observed internal block3328 B. Dev.8 uses SDK PSRAM-stack create and
   matching delete when allowed, preserving internal TCB and OOM semantics.
   Both targets compile. Real SNMP requalification below PASS.
4. SNMP hardware driver expected obsolete82 objects; now109, cross-checked
   against the actual compiled table. Serial analysis now counts task-creation
   failure separately rather than reporting generic allocation-zero as success.
5. New explicit opt-in `tools/test_gateway_campaign_device.py`: actual echo,
   same-client source filter, expiry, reboot, metadata profile persistence/
   rollback and automatic watch, with guarded original-setting cleanup.
6. Documents/changelog/ADR-025 and the scoped validation ledgers updated.

## Actual completed results

- Dev.8 Windows **64/64** including WiFi build, 75 synthetic browser scenarios,
  layout, site, i18n, SDK/authorization/scanner checks:
  `build/validation-20261023-043621-133534/`.
- Linux **60/60**, ASan/UBSan/leak checks:
  `build/linux-validation-20261023-043719/validation-20261023-023816-709423/`.
- Ethernet build PASS; exact snapshot in dev.8 target folder. W5500 is NOT
  hardware-qualified. Keep separate/experimental, never label it validated.
- Later **tool-only** SNMP count/serial failure checks targeted PASS:
  `build/validation-20261023-045901-674401/`. New gateway tool was physically
  exercised; complete final suite after final fixes is still required.
- Dev.8 SNMP: v1/v2c109-object walks,27 operational OIDs,12 Tailnet queries,
  unsupported/wrong-community/SET refusal, malformed/truncated/oversized packets,
  three real OFF/ON cycles PASS; original settings and OFF restored.
- Dev.8 gateway: forced-LAN TCP20/20 and UDP20/20, OFF refusal, same-client
  ineligible CIDR0/3 each and source-rejected diagnosis PASS. Real software
  reboot retained rules, expired TCP remained closed, UDP lease still replied;
  Advanced profile and watch settings persisted. Automatic watch reached owned
  TCP echo. Profile rolled back to none, watch OFF, original rule untouched.
  Evidence `build/private-device/dev8-gateway-campaign.json`. **One Tailnet
  client only**, not independent-identity ACL or forced-DERP coverage.
- Dev.7 authenticated session/request screening PASS, safe OTA/settings checks
  PASS; details and ten-minute resource minima in DEV8-VALIDATION.
- Prior dev.6 serial capture **3600.22 s COMPLETE**, no observed crash but a
  confirmed approximately five-minute control-map/authority outage. Later API
 1800 s/30samples completed. Earlier nominal-hour file was only42m50s.
  See TAKEOVER-VALIDATION and private summaries; don't rerun/relabel them.
- Owner reports Claude's5188HTTP/zeroerrors,592/600pings,~33ms mean. Its raw
  load log was not located here: don't attribute those numbers to dev.8 or
  describe them as independently reverified. No need to duplicate just for that.

## Continue in dependency order

1. Recover the running captures and evaluate policy/data availability and RAM
   truthfully. Fix any confirmed issue, preserving fail-closed policy and
   existing features. Largest internal block remains tight despite SNMP fix.
2. Essential missing boundary: **two independent real Tailnet identities**,
   positive/negative TCP/UDP/direct ESP/subnet/LAN→Tailnet, revocation/reconnect,
   direct and DERP. One-PC CIDR refusal and mocked crypto are not equivalent.
   Do not change production Tailnet policies or unrelated peers just to pass.
   If infrastructure/credentials are missing, record the exact scoped blocker
   and continue other available work; do not mark READY.
3. Exact in-session stream-loss recovery of the corrected candidate remains
   unqualified. Clean boot authority is NOT that test. Avoid a firmware change
   or transport-security weakening merely to fabricate a passing scenario.
4. Complete controlled MQTT/HA/ntfy and WoL/recovery tests without affecting
   unrelated devices. Previous MQTT broker was unreachable; don't silently
   overwrite credentials. Optional failures must not kill routing. Use owned
   lab targets and restore settings, labeling mocks/lab vs real services.
5. AP/uplink-loss and physical NVS/interrupted OTA/rollback scope remain open.
   Existing SSID→password retention is keyed by SSID: do not casually replace
   a saved SSID and assume its secret survives. Need verified concrete USB/
   configuration recovery. Never write stable ota_1 for a test. Existing
   guarded 1.13→dev.8 HTTP upgrade is already proven; don't repeat unnecessarily.
6. Finish real authenticated desktop/mobile UI review; retain black/green logo,
   Simple/Advanced and EN/IT/ES/ZH. No new redesign, FR/DE can stay disabled.
   Browser automation/synthetic layout/site checks already pass. Preserve
   existing16-page site/SEO/assets; finish defects, not a replacement website.
7. Final fix freeze: full consolidated regressions/builds/browser/sanitizers,
   source/dependency/history/artifact scans, exact final-version BIN/ELF hashes,
   manifest and local quick-flash packages from exact committed sources. Do not
   relabel a dev image stable; recompile correct version. Keep old artifacts
   distinguishable and private. Source app identity `esp32_tsr` stays stable.
8. Update matrix42 rows, quality gate, validation, changelog and this handoff.
   Provide Codex an exact local commit/artifact/test map and unresolved gates.
   **STOP before any public operation**, even if final local preparation passes.

## Source/build/privacy constraints

Use apply_patch; preserve dirty/untracked files. No reset/clean/force-push or
history rewrite. Build with the existing external TEMP PlatformIO build dir;
not stale `.pio` artifacts. Pinned IDF5.5.3/cJSON/lwIP paths and commands are in
AGENTS.md. Do not glob `*_device.py` into offline tests. Save full logs ignored,
show concise Italian PASS/FAIL; maintained docs/code/UI remain English.

Both root and nested scans must be rerun before sharing a final source state.
Nested full-history scanner has nine reviewed uppercase-X example placeholders,
not current secrets; raw scanner result must remain explicit, not suppressed
or rewritten. Earlier root/current dependency scans passed. No scanner proves
complete absence of secrets/vulnerabilities. Keep licences/Csontikka credit.

Handoff scan rerun: root419paths/16artifactpayloads/2068historicalblobs,
**0 findings**; nested107paths/459historicalblobs, **9 raw history matches**
(same reviewed placeholders), exit1. Logs in ignored
`build/handoff-dev8-20261023/`. Do not describe the nested full-history scan as
zero/green. Root diff whitespace check PASS, nested worktree clean.
Final root scan after tracking this continuation file:420paths/16payloads/
2076historicalblobs, **0 findings** (`root-sensitive-final.log`).

Public migration is reserved for Codex: bridge stable release under the old
repository name first, legacy updater compatibility and migration window,
then rename existing repository (not a new one) and deploy existing Pages.
See MIGRATION-RENAME.md. Preserve Main, tags/releases/history/fork relationship.
