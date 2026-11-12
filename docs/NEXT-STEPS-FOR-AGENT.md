# Maintainer continuation

## Active work — ESP-IDF 6.1 beta

The v3.0.18-beta.2 OTA was qualified on the Wi-Fi owner board. Beta.3 is
public and contains the drawer fix and corrected MicroLink dependency link.
Its exact image passed browser, asset and CI checks. The owner board was
not updated to beta.3. The next build removes obsolete upstream version
rows from About and pins the GPLv3 MicroLink licensing revision
`763f5d45f69748322125839d30ee79925aff18d7`. Its original MIT and component
notices must accompany future images. Keep v3.0.17 as the latest stable.

The qualified native-IDF 5.5.6 image is public as v3.0.17. Source
399ee031589d, BIN SHA-256 d715c960a67da1599056c4f92be46aa9f0272d6c1856d1f44b0b1a8f1d669f99.
The owner board keeps it in ota_1. The 15-minute
resource observation, live TCP/UDP gateway, expiry/reboot/watch and UI
checks passed. Exact logs are in the preceding worktree's ignored
build/private-device/install-3.0.17/. The Telegram expiry message came
from the lab rule. Lab settings were restored. PR #18 and Pages are
merged/deployed. The public flasher matches the qualified image.

This worktree is fix/esp-idf-6.1-beta, based on v3.0.17. Current edits
target 3.0.18-beta.2. Hardware qualification is pending. W5500 2.0.1,
wiznet_common 1.1.0 and MQTT 1.1.0 are exact managed dependencies.
The MQTT source guard was updated after reviewing task ownership. The
upstream external-stack option remains off because the project keeps
its reaper. The TLS RNG path is conditional in MicroLink for Mbed TLS 4.
Parent SHA operations now use public generic MD APIs. Setup GCM uses PSA;
the SHA callback can fail closed. Newlib is retained during the migration.

The SDK package is framework-espidf 4.60100.0 and the archive SHA-256 is
dabc3f2d16cc28c61d92fa378bb249da5dd4bc601c3564318a930bce3ddb63e7.
The verified local extraction is under TEMP/mtg-idf61-sdk-native.
The local PlatformIO build uses the pinned GCC 15.2.0 toolchain.
Noise and WireGuard byte-level checks and setup/password software crypto
regressions passed. The final link requires the project's DHCP helpers
to have internal linkage because the SDK defines names of its own.

The first beta boots in ota_0 and keeps settings, MQTT, UI and Tailnet
management operational. A live TCP/UDP Service Gateway lab found no installed
mapping. Its boot log showed the AP netif was not ready when NAPT was enabled.
The next image enables NAPT after the SDK's AP_START handler. Real lwIP host
tests now exercise forwarding after the AP leaves the netif list.

Next: verify the exact image and partition table. Select ota_1 using USB,
then install only the beta application into ota_0 and repeat TCP/UDP, expiry,
reconnect and resource tests. Keep ota_1 available as recovery.
The owner authorized qualification and beta publication after success.
The beta package is for OTA with the existing bootloader.



## Current handover — 3.0.17-beta.1 audit candidate

Local branch `fix/audit-3.0.17` contains source fixes from the November audit.
ESP-IDF 5.5.6 is pinned to the pioarduino archive with its digest documented
in PlatformIO. MicroLink has a local commit that requires DERP TLS validation.
The NVS layout and OTA application identity are unchanged. NVS initialization
or journal recovery failure stops startup without erasing settings. A pending
OTA is kept selected in that state to avoid rebooting into a legacy image that
could erase the same NVS. Recovery then requires serial diagnostics and backup.

Before release: check physical NVS failure and downgrade, Wi-Fi and W5500
failover, split DNS, Telegram live target/permission change and independent
Tailnet paths. The ignored build checkpoint records exact artifacts and tests.
Publish the MicroLink commit before the parent only with release authorization.

## Current handover — per-integration recovery controls

On branch `fix/recovery-command-controls`, Device Registry links to the
integration controls, separated from the monitoring save by standard spacing.
Telegram and ntfy command modes are off, basic, or basic plus verified recovery.
MQTT has its own verified-recovery permission. Existing command polling,
chat/topic restrictions, info options and saved-device checks still apply.

An absent `ops_recovery` key inherits the old shared bit. The first
channel-specific permission save persists all three effective permissions
together, changing only the selected channel. An invalid record denies remote
recovery. Firmware rollback to 3.0.16 reads its old shared bit. Use the retained
settings copy for full configuration rollback. Validate migration and
independent grant/revocation on physical hardware before a release.

## Current handover — Health & Resources layout (local)

Based on published Main at ca7649aca66da0b4b4a6c82ea65b7c0241201f06.
In the local `fix/health-resource-layout` branch, monitoring belongs to Device
Registry, remote commands sit with recovery, expiry notifications sit with
temporary Service Gateway access, and the resource guard is advanced.
Section saves use the existing operations API and preserve unrelated settings
and drafts. Selected devices show an explicit pause when global monitoring
is off. No NVS, version, flash or publication changes. Next: include in a
future authorized candidate and verify on a real device.

## Current handover — 2026-11-09 (after 3.0.13)

3.0.14-beta.3 published as a GitHub pre-release (tag on b7ee3f8, MicroLink
4ea68d1 pushed; 10 asset digests verified; v3.0.13 stays Latest; no site
change). It adds settings search (`tools/test_settings_search.cjs`) and the
load-speed fixes of beta.2. Installed over Tailscale on the owner's test
board, POST-INSTALL PASS; validate_all --build --browser 142
PASS. The owner tests it for some days before a stable 3.0.14.

Local, not pushed: Status page signature (signal line, Client WiFi node,
header rate, calm motion; `tools/test_status_signature.cjs`) and MagicDNS
completion (F46): own name answered, tailnet DNS settings (extra records,
split-DNS routes, override resolvers) behind `dns_config`, gateway's own
lookups through the lwIP netconn resolve hook behind `self_resolve`, both
off by default (`tsn_ext` record). Host tests `tailnet_dns`, `tailnet_names`
and browser suites pass; firmware builds. Pending on board A: AP client and
gateway lookups of a real peer, the own name, a split-DNS route and an extra
record from the admin console; Headscale domains; lookups with the tunnel down.

## Current handover — 2026-11-07

Read [Claude-to-Codex checkpoint](CLAUDE-TO-CODEX-CHECKPOINT.md) first: PERF-09
for 3.0.7-beta.10 is running; 3.0.7-beta.11 source (DERP split header, AP DNS
relay answer matching, STUN bound) is committed with host tests and not yet
built for the board; the disconnect fix still has to be seen on hardware
before a stable 3.0.7. Sections below are historical.

## Active performance handover — 2026-10-29

Read [Codex-to-Claude performance checkpoint](CODEX-TO-CLAUDE-PERFORMANCE-CHECKPOINT.md)
and its **Latest stage** section first: the dev.1 comparison is finished with no
demonstrated speed gain; device is back on 3.0.6. A separate selective-IRAM
dev.2 prototype has host crypto tests; next sanitizer/build/actual memory cost.
No dev.2 install is authorized yet. Older details below are historical.

Previous dev.1 stage: read the checkpoint
first. PERF-01 harness and six INFO/WARN comparisons are complete for their
scoped baseline. The exact RX buffer-adoption candidate source `f17f359`, image
`326c0d8e…8a2d8b51`, is now built and installed under fresh owner authorization,
with verified full backup, original configuration and protected 3.0.5 intact.
Four targeted Linux ASan/UBSan checks pass. A three-transfer candidate campaign
is active; finish/clean it before any USB/reset. RSSI changed after USB was
connected, so next obtain a matching-position 3.0.6 baseline before claiming
any speed improvement. Detailed recovery/authority/live state stays private.
Preserve all dirty files and the local nested commits; no push/flash authority
is implied. Update the checkpoint after every material step.

## Deferred performance investigation — owner request 2026-10-29

Resume [Performance and load-resilience exploration](PERFORMANCE-EXPLORATION-ROADMAP.md)
at PERF-01 when the owner allocates development budget. Planning only: no new
optimization, tests or firmware builds were performed for this roadmap.
The owner explicitly allows justified RAM changes; earlier fixed-RAM constraints
are superseded for this investigation. Concurrent-service load stability is a
blocking gate. No flash or publication authority is implied.
Reuse the completed, explicitly two-segment 500 MB benchmark evidence via
ignored `build/notification-ui/500mb-active-path.txt`. Temporary rule/server
were removed; no benchmark is running. Read the private final 3.0.6 handover
before acting on the older candidate/publication wording retained below.

## Firmware 3.0.6 — bounded update transfer recovery

The owner reported intermittent GitHub downloads and browser uploads. A real
3.0.2 GitHub attempt stopped at 1% after TLS returned no data with EAGAIN;
the protected running slot and settings survived. The owner subsequently
updated manually and via GitHub. See ignored `build/notification-ui/` records
for that board's current identity, fresh backup and exact authorization.

The fix retries only transient reads, with a 30-second inactivity budget
and the existing GitHub 180-second total limit. Local uploads retry server
receive timeouts, cap total reception at ten minutes, erase only the declared
image size, and retain writer exclusion after an unacknowledged abort. Transfer buffers,
task stacks and log allocations keep their existing sizes. Browser progress distinguishes
bytes sent from device verification and ambiguous failures never auto-retry.
Tests reproduce the former failures in actual handlers; host fixtures are not
hardware transport qualification. Do not install or publish a new candidate
using the former authorization for released 3.0.5. Owner bootstrap authorization
and exact release/channel/device status are in the private checkpoint. The
current public stable stays intact until the new image is qualified.

## Firmware 3.0.5 — MQTT power-return automations

The opt-in `mqtt_pwr` preference adds an MQTT/HA power-return event and switch,
plus retained boot metadata. Configuration remains 496 bytes; state uses the
existing manager stack and message budget, with no new worker or persistent
queue. Read `docs/MQTT-POWER-RETURN.md` for automation, deduplication and catch-up
semantics. Preserve the 3.0.4 recovery image and all historical artifacts.

Exact source/image hashes, current device slots, owner authorization, encrypted
Web export, broker/power-cycle results and publication status are recorded in
ignored `build/notification-ui/CHECKPOINT.md` and
`build/notification-ui/CURRENT-OPERATIONS.json`. Read those before further device
writes. Publish only the exact qualified image; never substitute a rebuild.
Do not infer real Home Assistant automation execution from broker delivery.

## Firmware 3.0.4 continuation

The ntfy wording increment replaces numeric reset reasons in startup alerts
and `info` with explicit causes. `(possible blackout)` is conditional on a
power-on reset and its enabled notification option; other restarts remain
separate. The existing task-only event text uses PSRAM without adding a buffer,
configuration key or task. Log-buffer sizes and persistent schema are unchanged.

The exact candidate, installed device, retained recovery slot, backups and
actual qualification/publication state are in ignored
`build/notification-ui/CHECKPOINT.md`. Read it before any device write.
Never infer the protected slot from an older handover. Package only the exact
final-version image qualified there; never relabel a dev image. Preserve all
42 requirements and all historical release artifacts.

## Firmware 3.0.3 continuation

The notification/UI increment is implemented in qualified firmware source
8b15ba6b02b2765b8de464c3b714be7180ef1ee2 (MicroLink unchanged at `fa3153b`).
Exact application SHA-256:
48db108970bc4b0c65c05966360a5d859703cd644eed64946662ec0facdea40e.
Keep this image and its source record; do not substitute a rebuild from a
later documentation/website commit. Source and presentation changes are
separate from actual release and Pages deployment: inspect real GitHub state
and the private `build/notification-ui/CHECKPOINT.md` before continuing.

Power-on and other-restart choices, configurable connectivity timing,
notification queue/resource recovery and draft-preserving forms are retained.
Log buffer allocation remains unchanged (16 KiB live, 4 KiB RTC). All 42
requirements, historical artifacts, private backups and user work remain.
Detailed test and device records belong in the private handover.

The owner merged presentation PR #1 and published Pages (workflow
40565493169 succeeded); do not repeat that completed website work. Keep its
Sponsors/Ko-fi choices when integrating this branch. All 42 requirements,
private backups, COMMUNITY-POSTS and other dirty/unpushed work are preserved.

Product: **ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware **v3.0.3**;
the 2.1.0 migration bridge remains available for 2.x installations.
Follow [Release availability](PRESENTATION-STATUS.md) for public downloads.
Previous stable image source/tag: `fcc6011bab4b2f1aa38d5fb49564f0cef3163378` /
`v3.0.2` (firmware.bin `fdb763c1…85e0`). Do not rebuild or substitute its
qualified image with the unpublished 3.0.2-beta.1 image or a new build from a
later documentation commit. The previous stable 3.0.1 (`9e03f20`) stays
published unchanged.

Read ignored `build/private-device/CLAUDE-TO-CODEX-NVS-ATOMIC.md` (3.0.2) and
`build/private-device/STABLE-301-IN-PROGRESS.md` for the exact
operational checkpoint, device state, acceptance scope, remaining independent
test cases and next authorized action. That record takes precedence over older
beta handovers. Later site/documentation commits are not the image source.
The browser packaging helper now includes original firmware license notices
and their checksum; this change does not alter the qualified application.
Preserve the full feature roadmap, upstream credits and existing configuration.

The exact operational handover, artifact hashes, device qualification records,
owner acceptance and current external-operation state are kept locally under
ignored `build/private-device/`. Read that checkpoint and inspect actual Git
and GitHub state before resuming. Never infer publication from a prepared file
or replace an exact qualified image with an independently rebuilt one.

The original development workspace and private backup bundle are preserved.
Do not merge or push its unsanitized archived history into the public graph.
Keep owner-created untracked files, NVS backups and recovery images intact.

Public release preparation and future changes follow [Quality policy](QUALITY-GATE.md),
[Migration](MIGRATION-RENAME.md), [Release availability](PRESENTATION-STATUS.md)
and the [development roadmap](DEVELOPMENT-ROADMAP.md). Detailed test execution
and remaining-case lists are internal maintainer records, not release content.
