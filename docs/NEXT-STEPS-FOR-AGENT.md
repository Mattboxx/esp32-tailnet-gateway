# Maintainer continuation

Product: **ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware v3.0.0 (stable; 2.1.0 migration bridge for 2.x).
In progress: **3.0.1-beta.1** (pre-release). Candidate source and exact
image, campaign results, board checks still to run, packaging and
publication steps are listed one by one in the ignored
`build/private-device/HANDOFF-3.0.1-beta.1.md`; follow its checkpoints in
order and do not rebuild the candidate image.
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
