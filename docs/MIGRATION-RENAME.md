# Repository rename and OTA migration

The project is **ESP32 Tailnet Gateway — Mattboxx Edition**.
The existing repository has moved from
`Mattboxx/esp32-tailscale-gateway-NAS-recovery` to
[`Mattboxx/esp32-tailnet-gateway`](https://github.com/Mattboxx/esp32-tailnet-gateway).
Its history, fork relationship, issues, tags and historical releases remain.
Do not create another repository at the old name: it would break redirects.

## Bridge release

The bridge **0.1.38-Mattboxx-1.100** was published under the previous repository
name before the rename. Its legacy version can be selected by 1.10–1.13
updaters, while the bridge's updater also understands **Firmware v2.0.0**.
The repository was renamed immediately afterward, without a migration window.

## Devices still running 1.13 or earlier

Older updaters require HTTP 200 from the fixed previous GitHub API endpoint.
GitHub's repository rename returns a redirect, which those versions refuse.
Their updater can therefore report **GitHub check failed** after the rename.
The installed firmware keeps running; this does not erase settings or partially
install an image. Releases before 1.10 have no GitHub updater.

Update once manually:

1. Back up your configuration.
2. Download **`firmware.bin`** from the [latest release](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/latest).
3. Upload it in **System → Firmware** and allow the gateway to restart.
4. Alternatively use the Easy Install **keep-settings** option over USB.

Do not upload a factory image in the Web UI. New-device/erase installation
deletes settings. USB keep-settings installation writes the first app slot
and initial OTA selection; it is not an inactive-slot OTA operation and must
not overwrite a deliberately protected recovery image.

## New update behavior

- The bridge and 2.x updater check the new repository first and fall back to
  the previous name only on HTTP 404. Rate limits, 5xx and transport failures
  do not silently select another repository.
- Release downloads accept the fixed old and new repository paths and the
  approved GitHub asset CDN, retaining TLS verification and SHA-256 checks.
- Application identity `esp32_tsr`, NVS namespace and partition layout remain
  unchanged; an ordinary application update preserves configuration.
- Periodic checks, automatic installation and beta participation remain
  explicit opt-ins. **Check now** and **Install latest update** are on demand.

Historical 1.13 downloads remain available for recovery. Firmware rollback
depends on the valid previous OTA slot; serial recovery can use an appropriate
saved image. See [Updates](UPDATES.md) and [Backup and restore](BACKUP-RESTORE.md).
