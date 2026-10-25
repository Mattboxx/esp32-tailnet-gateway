# Maintainer continuation

Product: **ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware **v3.0.1**;
the 2.1.0 migration bridge remains available for 2.x installations.
Follow [Release availability](PRESENTATION-STATUS.md) for public downloads.
Exact stable image source/tag: `9e03f20d5dd23cd8d42e4e5eea91bf9f9daca8f8` /
`v3.0.1`. Do not rebuild or substitute its qualified image with the earlier
3.0.1-beta.1 image or a new build from a later documentation commit.

Read ignored `build/private-device/STABLE-301-IN-PROGRESS.md` for the exact
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
