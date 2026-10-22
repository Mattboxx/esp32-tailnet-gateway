# Repository rename and OTA migration plan

From `Mattboxx/esp32-tailscale-gateway-NAS-recovery` to
`Mattboxx/esp32-tailnet-gateway` (product: ESP32 Tailnet Gateway — Mattboxx
Edition). Nothing here has been executed on GitHub; every public step needs
the owner's explicit authorization.

## Why a bridge release is required

Verified in source (`main/ota_remote.c`, `main/ota_validation.h`) for stable
1.13 and the development line before the bridge:

| Updater step | Behaviour | After a GitHub rename |
|---|---|---|
| Release check | `GET api.github.com/repos/<old>/releases`, redirects disabled, requires HTTP 200 | API answers 301 → *GitHub check failed* |
| Download | Fixed `github.com/<old>/releases/download/<tag>/firmware.bin`; redirects only to the same path or the release-asset CDN | Redirect to `<new>` is refused |

So firmware up to 1.14-dev.6 **cannot update itself after the rename**. It
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
