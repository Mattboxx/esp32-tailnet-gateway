# Maintainer continuation

## Local 3.0.6 candidate — bounded update transfer recovery

The owner reported intermittent GitHub downloads and browser uploads. A real
3.0.2 GitHub attempt stopped at 1% after TLS returned no data with EAGAIN;
the protected running slot and settings survived. The owner subsequently
updated manually and via GitHub. See ignored `build/notification-ui/` records
for that board's current identity, fresh backup and exact authorization.

The local fix retries only transient reads, with a 30-second inactivity budget
and the existing GitHub 180-second total limit. Local uploads retry server
receive timeouts, cap total reception at ten minutes, erase only the declared
image size, and retain writer exclusion after an unacknowledged abort. Buffer,
transfer-buffer, task, stack and log allocations are unchanged. Browser progress distinguishes
bytes sent from device verification and ambiguous failures never auto-retry.
Tests reproduce the former failures in actual handlers; host fixtures are not
hardware transport qualification. Do not install or publish a new candidate
using the former authorization for released 3.0.5. Public 3.0.5 stays intact.

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
