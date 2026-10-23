# Repository rename and OTA migration plan

## Current v2 owner decision (2026-10-23)

The approved bridge version is **0.1.38-Mattboxx-1.99**, followed by **2.0.0**.
The owner explicitly chose immediate rename after publishing the bridge rather
than the previously suggested four-week window. Devices still on 1.13 or older
will need a manual Web UI/USB update if they miss that bridge; this limitation
must remain visible. Missing physical tests are accepted risks, not PASS;
see V2-RELEASE-ACCEPTANCE.md. No rename has been performed at this checkpoint.
The historical sequence and version examples below are retained for context,
but this decision and CODEX-V2-RELEASE-PLAN.md govern the v2 publication.

> **1.14 development preview.** This guide includes unreleased features; it
> does not imply a new firmware download. Public stable remains
> [Mattboxx 1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13).


> Presentation publication is separate from firmware publication. Current scope:
> [presentation status](PRESENTATION-STATUS.md). No repository rename yet.

From `Mattboxx/esp32-tailscale-gateway-NAS-recovery` to
`Mattboxx/esp32-tailnet-gateway` (product: ESP32 Tailnet Gateway — Mattboxx
Edition). The README and presentation website may be published early under
the current name. The firmware bridge and rename sequence below have not been
executed; each belongs to the separately authorized firmware release phase.

## Why a bridge release is required

Verified in source (`main/ota_remote.c`, `main/ota_validation.h`) for stable
1.13 and the development line before the bridge:

| Updater step | Behaviour | After a GitHub rename |
|---|---|---|
| Release check | `GET api.github.com/repos/<old>/releases`, redirects disabled, requires HTTP 200 | API answers 301 → *GitHub check failed* |
| Download | Fixed `github.com/<old>/releases/download/<tag>/firmware.bin`; redirects only to the same path or the release-asset CDN | Redirect to `<new>` is refused |

Stable 1.13 and development builds **before bridge commit `5b797f8` cannot
update themselves after the rename**. Some development images already include
the bridge; check the actual source and image, not just a development version
label. Affected older firmware
fails closed (no partial install, no damage): the device keeps running and can
still be updated manually.

## What the bridge firmware does

- Checks releases under the **current** name first; falls back to the
  **previous** name only when the current one answers 404 (before the rename).
  Rate limits, 5xx, redirects and transport errors never fall back.
- Downloads are accepted from either fixed release path, so GitHub's
  previous→current redirect stays inside the allowlist; the CDN rule is
  unchanged. TLS uses the same certificate bundle.
- The release link and the `repository` field reported by the API follow the
  repository that actually answered.
- App identity (`esp32_tsr`), NVS namespace, partitions and version format are
  unchanged, so the image check and settings are unaffected.

Tests: `tools/test_ota_remote.py` (both paths, near-miss URLs, invalid repo
index, actual `check_release()` lookup order and no-fallback cases).
Not yet verified against live GitHub: a real check/install requires an
authenticated session on the device and a published release.

## Sequence (each step needs authorization)

1. Push the branch and publish the bridge as a stable release
   (`v0.1.38-Mattboxx-1.14`) **under the current (old) name**. Release assets
   keep links to the old name, which keep working after the rename.
2. Announce the update (migration message in `docs/launch/`). Suggested window:
   at least 4 weeks so devices with periodic checks pick it up.
3. Verify that the old name has no other dependants (CI badges, Pages, forks
   instructions); confirm `esp32-tailnet-gateway` is still free.
4. Rename the repository in GitHub settings. Never create a new repository
   with the old name: that would break every redirect.
5. Enable GitHub Pages for the `site/` workflow, upload the social preview,
   set description, homepage and topics.
6. Check from a bridge device: *Check for updates* reports the release under
   the new name.

During the window, README badges and the website link that use the new name
return 404 until step 4; everything else uses relative links.

## Devices that missed the bridge

They show *GitHub check failed*. Update manually, settings preserved:
**System → Firmware → upload `firmware.bin`** from the new releases page, or
`UPDATE_KEEP_SETTINGS.bat` from the Windows package. From then on the updater
works again.

## Rollback

The rename can be reverted in GitHub settings while the old name is unused.
Firmware rollback uses the previous OTA slot (bootloader app rollback) or the
previous release's `firmware.bin`.

## Bridge release checklist (for the publishing agent)

- The bridge must be published **under the current (old) repository name**
  while 1.13 devices can still reach it; its `firmware.bin` asset must carry
  the GitHub `digest` the 1.13 updater requires (GitHub adds it to uploaded
  release assets).
- A 1.13 device only installs a release whose tag version is newer and whose
  channel matches its setting (stable unless beta is enabled): publish the
  bridge as a **stable** `v0.1.38-Mattboxx-1.14` (or the agreed number), not
  only as a pre-release, or most devices will not see it.
- Keep the old-name download URL valid for the window; do not delete the
  1.13 release.
- After the rename, verify from one bridge device: *Check now* reports the
  repository `Mattboxx/esp32-tailnet-gateway`.

## Old updater behaviour, verified (2026-10-22)

Checked in the 1.13 release source (`8dbf060`) and in the 1.13 image actually
installed on the bench board (strings of the backed-up `ota_1`), and in the
packaged 1.10 and 1.11 images:

- Every updater-capable release (1.10 → 1.13) uses the same repository name,
  `Mattboxx/esp32-tailscale-gateway-NAS-recovery`, so **one bridge release
  under that name reaches all of them**. Releases before 1.10 have no GitHub
  updater and always need a manual update.
- Request: `GET https://api.github.com/repos/<old>/releases?per_page=10`,
  automatic redirects disabled, HTTP 200 required. After a rename the API
  answers 301 → "GitHub check failed"; nothing is installed.
- Selection: newest non-draft release among the **latest 10**, prerelease only
  with the beta channel on, asset named exactly `firmware.bin` in state
  `uploaded`, with a GitHub `digest` (`sha256:…`) and a size that fits the slot.
- Download: only from `https://github.com/<old>/releases/download/<tag>/firmware.bin`
  or the `release-assets.githubusercontent.com` CDN (≤ 3 redirects); the
  SHA-256 must match the digest; the image's app identity and version must
  match the tag.
- Timing: periodic checks are opt-in (daily when enabled); auto-install is a
  separate opt-in with a ≥ 1 h spacing; *Check now* / *Install latest update*
  work on demand. Devices with checks off will not find the bridge by
  themselves — the announcement must tell their owners to press *Check now*
  or upload `firmware.bin` once.

Consequences for the publishing order: publish the bridge as a **stable**
release, keep it among the 10 newest releases during the window, do not
publish more than nine other releases before the rename, and keep the 1.13
release online.
