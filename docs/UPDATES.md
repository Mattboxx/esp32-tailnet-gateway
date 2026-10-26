# Firmware updates — ESP32 Tailnet Gateway

> **Firmware 3.x.** Application updates within the same layout preserve the
> existing app identity, NVS namespace and partitions. Keep a configuration
> backup before updating.
>
> **From 2.x to 3.0:** 3.0 uses a new 8 MB flash layout, so the 2.x updater
> skips it (its image does not fit a 2.x slot). Install the **2.1.0 bridge**
> from the 2.x updater and migrate over the network, or install 3.0 once over
> USB without erasing; settings are kept. See [Moving to 3.0](MIGRATION-3.0.md).
>
> **From v2.0.0 or v2.0.1:** upload the **2.1.0 bridge's** `firmware.bin`
> and follow the migration guide, or use the current USB keep-settings
> installer. Do not upload a 3.x application into the old slots. The GitHub
> updater bug in those two releases was fixed in v2.0.2.


System → Firmware → Firmware update supports three independent workflows:

1. Upload a trusted local `firmware.bin`, as before.
2. **Install latest update**: explicitly check GitHub, download the latest
   newer compatible release in the saved channel, verify/install and reboot.
   Works with periodic checking and automatic installation OFF.
3. Enable daily checks, optionally enable unattended installation immediately
   after discovery or during a device-local-time hour. Scheduled installs wait
   for a synchronized clock. Include beta releases only if explicitly selected.

All switches start OFF. **Check now** checks without requiring an install;
if automatic installation is already ON, the normal unattended policy may
then apply to a discovered update. Disabling periodic checks also disables
automatic install. Beta selection still applies to one-off manual installs.
Save channel/policy changes before using manual actions. Beta means GitHub
pre-release inclusion, not an email subscription or registration service.

After a successful check finds no newer compatible release, **Install latest
update** is disabled; **Check now** remains available. Discovering a newer
compatible release enables installation again. Before the first successful
check, the one-click check-and-install workflow remains available. Invalid or
unavailable local status disables both actions until a successful refresh.

No new image is fetched simply because the System page is opened: the page
reads local status. The worker is off/idle unless opted in or explicitly
requested, runs outside the web server, and does not hold the HTTP request
open while downloading. Settings persist in an atomic `ota_fork_v1` NVS blob.
Legacy upstream preferences stay erased/inert. Backup snapshots record policy
as information; restore cannot activate it through the ordinary System API.

## Repository rename

The repository has moved to `Mattboxx/esp32-tailnet-gateway`. Firmware before
the bridge release cannot follow the rename automatically; see the
[migration plan](MIGRATION-RENAME.md).

## Web UI languages

The current 3.x `firmware.bin` carries all six Web UI languages (English,
Italiano, Español, 简体中文, Français and Deutsch) and the W5500 Ethernet driver. The 2.x line
shipped one image per language (`firmware-it.bin`, `firmware-es.bin`,
`firmware-zh.bin`) and a separate `firmware-eth.bin`; those names are not
used by 3.x releases.

## Release channels

Each version is tested as numbered betas before it becomes stable:
`3.0.0-beta.1`, `3.0.0-beta.2`, … then `3.0.0`. Betas are published as GitHub
pre-releases; the stable is a normal release.

| Device setting | Receives |
|---|---|
| Stable channel (default) | Stable releases only |
| Beta channel | The highest version overall: a newer beta replaces an older one (`beta.2` after `beta.1`), the stable of that version replaces all its betas, and the next version's betas follow |

The highest stable always ranks above every beta of the same version, and a
device never downgrades. A device running a beta on the stable channel moves
to the next stable release.

## Which releases qualify?

Fixed repository:
[Mattboxx/esp32-tailnet-gateway](https://github.com/Mattboxx/esp32-tailnet-gateway/releases),
with the previous-name fallback described in the migration guide.
The worker scans the ten most recent release entries and selects the highest
compatible version, not the first JSON entry. A release must:

- Be published, not a draft. Stable-only skips all GitHub pre-releases.
- Have a product tag such as `v2.0.0` (stable), or `v2.1.0-beta.1` marked as
  a GitHub pre-release. Legacy bridge tags are also understood. Supported
  prerelease suffixes are dev, alpha, beta and rc with optional numeric serial.
- Be numerically newer than the running version, comparing upstream triple,
  Mattboxx major/minor, then dev < alpha < beta < rc < stable. No downgrade.
- Include uploaded **firmware.bin**, not a factory image or flashing ZIP.
  Its size must fit the inactive OTA slot (1920 KiB on 2.x, 3584 KiB on 3.x;
  this is why 2.x gateways skip 3.x releases), and GitHub must supply its
  `sha256:` asset digest. Missing/unsupported metadata is not silently trusted.
- Contain an ESP32-S3 app image whose project name matches the running build
  and whose embedded version exactly matches the release tag without `v`.
  A stable tag with a `-dev` binary is rejected; build and tag must agree.

For maintainers: publish the matching app image under the exact asset name
`firmware.bin`. GitHub supplies the asset digest automatically. Other binary
and Windows ZIP assets can still be attached for manual USB flashing; they are
never selected by this updater. Tags must fit the ESP app descriptor's version
length (31 characters including the tag's optional `v` in the selector).
The published `v0.1.31-Mattboxx-1.10-dev.10` candidate is explicitly marked as
a GitHub pre-release. Older compatible builds need beta selection enabled to
discover it; an identical/newer installed version reports no update. It does
not replace the stable 1.8 release. Older stable assets remain available for
explicit local rollback. See [candidate coverage](releases/RELEASE-1.10-dev.10.md).

## Download and trust safeguards

Use the public GitHub releases API without a token; send only a generic
updater User-Agent, not device identity, keys, settings or logs. GitHub still
sees the public source IP. Automatic polling is once per day; failed checks
do not hammer the API. A failed install retries at most hourly, refreshing
metadata first. Rate limiting and network errors are shown locally.

Downloads require certificate-verified HTTPS and a locally constructed fork
release URL. Redirects are bounded and restricted to GitHub's release asset
CDN; plaintext, credentials, custom ports and unrelated hosts are rejected.
The image prefix is checked before erasing the inactive slot. Exact download
length, complete transfer, SHA-256 and ESP-IDF OTA image validation must pass
before the boot partition is changed. Failure aborts the transaction without
rebooting or replacing the running image. Local/remote updates share an
exclusive writer; successful installs retain ownership until reboot.

GitHub SHA-256 binds the payload to trusted metadata; it is not independent
publisher signing. Compromise of the trusted GitHub account remains a risk.
Existing bootloader rollback handles startup failure within its validation
window, not arbitrary failures after the image has already been marked valid.
Automatic installation means accepting future firmware replacement and
gateway downtime; beta selection means accepting less-tested code.

Policy changes and manual actions require the password-backed UI session.
Re-enable the password gate if it is off and a critical action is rejected.
Home Assistant exposes read-only policy/update/version/status/progress
diagnostics; ntfy `info` includes the update policy and result. Neither adds
a password-bypassing install command.

## Validation scope

The host fixture compiles the real C version/release guards and downloader
decision path with real cJSON and simulated HTTP, hash and flash operations.
It exercises numeric ordering, stable/beta exclusion, drafts, invalid assets,
missing digests, oversized images, hostile redirects, partial reads,
incompatible image headers, concurrent writer exclusion, interrupted transfer,
hash mismatch, begin/write/end/boot failures and commit-before-reboot.
CI runs address/undefined-behavior sanitizers. SPA tests exercise manual install
with checks OFF, saved beta selection, busy-state locking, honest failed reads
and unsafe-link rejection. Earlier feature-preservation and ntfy guards remain.

These do not test real HTTPS downloads/flash writes on a board or certify
stability. Hardware validation must use the exact candidate image and a newer
published matching release; do not activate unattended beta installs on an
important gateway before testing. Existing stable downloads are unchanged.

Primary API references:
[GitHub release assets and digest](https://docs.github.com/en/rest/releases/assets),
[Espressif HTTP client](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-reference/protocols/esp_http_client.html)
and [OTA validation/rollback](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-reference/system/ota.html).

## Downgrading from the 1.14 development line

Stable 1.13 ignores the settings added in 1.14 development builds. **Disable
or delete temporary LAN → Tailnet rules before downgrading**: 1.13 has no
expiry engine and would keep such a rule enabled permanently. Details per key:
[NVS-KEYS.md](NVS-KEYS.md).
