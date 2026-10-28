# Maintainer continuation

## Local notification/UI candidate — 2026-10-28

Local branch `fix/notification-ui-20261028`, based on public Main `72ef753`,
contains unpublished **3.0.3-dev.1** fixes for short-outage notification noise,
queue identity/task-allocation recovery, notification drafts/refresh and the
firmware donor choice. Read ignored `build/notification-ui/CHECKPOINT.md` in
the isolated worktree for current commit, actual tests/build and remaining
hardware qualification. Do not install/push/release this candidate without
the applicable explicit authorization. The exact published 3.0.2 image below
remains the stable artifact; do not replace or relabel it.

The owner merged presentation PR #1 and published Pages (workflow
40565493169 succeeded); do not repeat that completed website work. Keep its
Sponsors/Ko-fi choices when integrating this branch. All 42 requirements,
private backups, COMMUNITY-POSTS and other dirty/unpushed work are preserved.

Product: **ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware **v3.0.2**;
the 2.1.0 migration bridge remains available for 2.x installations.
Follow [Release availability](PRESENTATION-STATUS.md) for public downloads.
Exact stable image source/tag: `fcc6011bab4b2f1aa38d5fb49564f0cef3163378` /
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
