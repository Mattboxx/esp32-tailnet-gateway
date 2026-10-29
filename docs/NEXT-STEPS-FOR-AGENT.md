# Maintainer continuation

## Local ntfy wording increment — 3.0.4-dev.1

Branch `fix/ntfy-reset-description-20261029` starts from released Main
`97f6bdb618e3238822749f2cabfce3a94bc75195`. It replaces numeric ntfy reset
reasons with explicit cause text and appends `(possible blackout)` only for
opted-in power-on events. Other restarts and faults stay distinct. No NVS,
configuration layout, log-buffer or task change is required.
The public release, installer and installed image remain 3.0.3. Read the
ignored `build/notification-ui/CHECKPOINT.md` for exact source, build, tests
and any subsequent owner authorization; do not reuse the 3.0.3 qualification
or overwrite its release assets.

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
