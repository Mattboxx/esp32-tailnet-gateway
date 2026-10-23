# Firmware v2.0.0 — Codex publication checkpoint (2026-10-23)

**FIRMWARE NOT READY — REMAINING BLOCKERS. Nothing new pushed or deployed.**
This checkpoint supersedes older dev.8/dev.9 handoff status, without changing
the original roadmap or deleting historical evidence.

## Source and isolated presentation

- Taken over from `mattboxx` commit `3b53adafefe7c1aaa0597ab083ca6bd64943c97b`.
- MicroLink remains clean at `fa3153b6892d00d0c9a9c42f11c8f1a89c6ea910`.
- Public Main queried: `a85681a9920cffa4d21cf9602a4027c6cce47bb3`; unchanged.
- Site worktree `../esp32-tailnet-site-v2`, branch `site-v2`, now
  `791e6bf17a5de2e2daf3af958bb94f79ebbbf6b6`, based on Claude's `b965dcd`.
- README title remains **ESP32 Tailnet Gateway — Mattboxx Edition**. Version
  appears as **Firmware v2.0.0**, not a replacement product name. Browser,
  Easy Install and advanced-download paths are described, with clear current
  stable 1.13 versus unreleased firmware availability. Existing branding,
  diagrams, attribution and licenses retained. No new visual redesign.
- `NEXT_PUBLISHED=False` and `RENAMED=False`. No firmware copied into the site,
  installer activated, repo renamed, release/tag/bridge published or Pages run.

Site checks actually executed: build **23 pages + 404 + 8 redirects PASS**,
browser installer manifest/erase/checksum/Chromium fixtures **PASS**, full site
**23 pages × 9 viewports PASS**, presentation/README/current-path guard PASS;
current site content scan **350 paths / 16 payloads / zero findings**. Logs in
the site worktree's ignored `build/v2-*` files. Synthetic browser firmware is
not a real USB flash or first-boot hardware test.

## B1 — resolved for the prepared publication graph, originals retained

Owner requested the best of the two proposed approaches. Chosen: prepare only
the four unpublished commits after `92ff5d8` with the two reviewed synthetic
credential fixtures replaced; no scanner exemption and no public-history rewrite.

Independent publication repository:
`C:/Users/mattb/.codex/workspaces/tailnet-v2-publication-20261023`, initial branch
`publication/v2-sanitized`, prepared HEAD
`0e0e28f6260667a20dac6fe5169f0b9ad239b33e`.
Its current tree is **identical** to original `3b53ada` (Git tree hash checked).
Historical authors, dates, messages and the earlier history were preserved.
The rewritten commit map is:

| Original local commit | Prepared local commit |
|---|---|
| `de341c34967cc6b34b4e5c8c3f4a7a7ffbbf3e1e` | `a757b775dca4c890edad55d5616fcf4fb12c1259` |
| `3e6e41eed0dd23b08cd8e72d313b9ce518d22284` | `6d765282b87afd026b5144d5c9dc051b08872667` |
| `cc6c0cbfcb298a3b04ae3fee8165137b41edd318` | `a1b6fce397d2e5d26025b4de58c68deec1940cfb` |
| `3b53adafefe7c1aaa0597ab083ca6bd64943c97b` | `0e0e28f6260667a20dac6fe5169f0b9ad239b33e` |

Prepared history scan: **448 paths, 16 artifact payloads, 2022 historical blobs,
zero findings**. Original root history scan still reports the two preserved
synthetic fixtures: this is expected, NOT a root scan PASS. **Do not push or
merge raw `mattboxx` into the sanitized graph**, which would reintroduce them.
Subsequent local changes must be replayed as reviewed patches, not old parents.

Original branches and tags are intact. Complete verified backup bundle, exact
blob/commit map and execution logs stay private in ignored
`build/private-device/release-preparation-v2/`. No force push, reset, cleanup,
original-ref move or submodule rewrite was performed. Existing tested rc.1
provenance still references its original source SHA; the rewrite does not make
a rebuilt/new-commit image the same qualified artifact (ADR-026).

## Qualification actually available so far

Exact installed WiFi rc.1 remains
`d879529206c92660b12b8cbb3e0343b2d9b6c707c183144cefe0e1266938cd16` on ota_0;
stable 1.13 remains in ota_1. **No device operation by Codex in this continuation.**

Read the phase `passed` fields in the private qualification JSON, not just the
owner's console report. Identity, activation from OFF and lab phases are PASS
with original integration settings restored. Observation is still RUNNING at
this checkpoint. Serial collector (75-minute target) is also RUNNING and owns
COM3. Do not open COM3 or run another qualification/flash while they run.
Partial rows show control/authority present and no reaper fallback; they are
not a completed soak or a final stability verdict. Collect the final JSON and
serial completion summary before changing their status.

## Remaining Quality Gate

| Gate | Current status |
|---|---|
| B1 synthetic history fixtures | Prepared publication graph PASS; original private graph deliberately retained |
| B2 MQTT/lab/continuity | Three phases PASS; observation and serial collection RUNNING |
| B3 first boot on spare, Android/iOS/Windows captive portals | BLOCKED: only the configured reference board is available; do not erase it or substitute desktop emulation |
| B4 independent identities, direct/DERP authorization | BLOCKED: no second independent owner-provided lab identity/peer environment |
| B4 recovery AP after a controlled prolonged uplink outage | BLOCKED: no approved isolated outage arrangement; short reconnects are not this test |
| B4 interrupted power during OTA/NVS | BLOCKED: no controlled power-cut/recovery fixture; reset/serial reconnect is not power loss |
| B5 README/site | Local preparation and tests PASS; no publication |
| B6 exact final 2.0.0 image | NOT BUILT/INSTALLED/QUALIFIED; do not relabel rc.1 |
| B7 exact legacy-compatible bridge and migration window | NOT BUILT/QUALIFIED/PUBLISHED; keep repository's current name |
| W5500 | Compile-only / experimental; rc.1 fits, all existing languages retained |

No runtime Ethernet failure was established. High flash occupancy alone is not
a reason to remove translations. A final build must still fit and be checked;
Ethernet cannot be described as hardware-qualified.

One packaging defect was corrected locally: release-manifest and Easy Install
notes URLs must use the current repository during the migration window, with
an explicit known-name selection only after actual rename. Metadata/variant/
version/checksum/archive tests and actual Easy Install shell-script tests PASS
with Git Bash (stub esptool, no board). The first shell test selected an unusable
WSL launcher; rerun with Git Bash PASS. This was an environment failure, not a
firmware failure. Logs: `build/v2-packaging-checks-gitbash.log` and its referenced
targeted validation directory. These tool-only changes require no candidate
firmware rebuild by themselves; a final version change always does.

## Next publication sequence — still gated

1. Collect already-running qualification and serial results; correct genuine
   failures, preserving recovery/credentials. Resolve the missing physical
   test arrangements above, or retain this NOT READY verdict.
2. Integrate the clean site-v2 history into the sanitized publication repository
   by function, preserving firmware and public Main presentation. Run final
   regression/scans there. Do not merge the old raw-history parent.
3. Only when the gate is satisfied and owner publication authority is explicit:
   build/qualify exact final `2.0.0` and legacy bridge `0.1.38-Mattboxx-1.99`;
   package the exact qualified images and source provenance, publish bridge
   under old name, publish v2 assets, then allow a migration window.
4. Activate site firmware only for an actually available qualified release;
   deploy and verify. Rename the **existing** repository after the window;
   only then flip RENAMED, redeploy and verify public redirects/OTA/downloads.

Owner COMMUNITY-POSTS, private-device data, backups and historical public
releases remain untouched. Keep all 42 roadmap rows and their missing tests.
