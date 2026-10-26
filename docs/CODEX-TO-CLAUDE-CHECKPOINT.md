# Codex continuation checkpoint — 2026-10-26

## Presentation follow-up

The owner requested a wider README/site copy audit after Getting Started.
The update corrects current six-language descriptions, current ZIP/checksum
links, legacy migration stages (no direct 3.x OTA into old small slots), the
diagnostic export menu and unsupported troubleshooting assumptions. Historical
captures and explicitly versioned documentation are preserved. Website build,
presentation/SEO checks, 25 pages × 9 browser viewports and the source/history
scan pass locally. The ZIP checksum link was compared against the actual
GitHub asset digest. Exact publication status and newer continuation steps
are saved in ignored `build/COPY-AUDIT-CHECKPOINT.*` and the shared private
handoff; these supersede the earlier task checklist below.

## Authoritative source state

Claude completed and published the legal-material repair on `Main`:
`faabf0590b8a94d7ee10e93e8f477d6053469f4d`, followed by the verified
inventory commit `6e543c1323f0c1b81f16d36df90e786a175ac6bd`.
The earlier audit commit is `b212d7a5df7a49e5553d49e296cd70b0650b19f8`.
Read `docs/LICENSE-AUDIT.md` and `licenses/distribution-remediation.json`.
The exact stable application is still 3.0.2; no new image was built/flashed.

**Do not rerun the earlier additive asset publisher:** the ten newest
releases' small legal companions were deliberately relocated, byte for byte,
to `licenses/releases/`. Reattaching them can exceed the existing 2.x
updater's 256 KiB release-list buffer. The live `?per_page=10` response was
201,921 bytes at this checkpoint. Source archives and corrected ZIPs remain
release assets; original artifacts, tags and their checksums are preserved.
Do not apply an old dirty audit-worktree snapshot over the newer public tree.

## Current task and completed edits

The owner asked to update the obsolete public `/getting-started/` page.
Work continues in an isolated worktree based on `6e543c1`; the active firmware
worktree and all owner/private/untracked files remain intact.

- Replaced the old manual-install/AP/password flow with the 3.x first-boot
  wizard: current setup SSID, physical pairing, no default password, tested
  uplink, optional registration, protected recovery Wi-Fi and restart links.
- Removed the obsolete 1.14 screenshot embed and legacy flashing commands;
  image assets and historical downloads themselves were retained.
- Updated the linked repository getting-started guide (3.x title and setup
  language availability).
- Installation/Easy Install pages now use the same current legal-material
  ZIP link helper as Downloads.
- Firmware, protocols, UI code, branding and donation links were not changed.

## Remaining steps before declaring this task complete

Local validation is complete: site build/link checks, presentation and SEO
PASS; browser PASS for 25 pages × 9 viewports; content/artifact/history scanner
PASS with zero findings. Original LICENSE, image assets, firmware and gitlink
are unchanged. Logs are in ignored `build/getting-started-*.log`.

1. Commit locally, fetch current `Main`, and push only a fast-forward update.
   Never overwrite intervening work or push the archived firmware branch.
2. Run the existing manual Pages workflow on `Main`, wait for success and
   verify the live getting-started content and Easy Install links.
3. Update this checkpoint with the real public commit/deployment outcome.

The owner has authorized these website corrections and publication. This is
not authorization to change firmware logic, flash hardware, rewrite tags,
remove old releases or alter network settings. No firmware roadmap has been
discarded; it remains in `docs/DEVELOPMENT-ROADMAP.md` and the implementation
matrix. Claude's already-completed firmware work must not be repeated.

Private operational records and the exact isolated paths are under ignored
`build/` and in the shared `build/private-device/CODEX-LICENSE-CHECKPOINT.md`.
