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

The current 3.x application does not fit these old OTA slots. Do not upload
its `firmware.bin` directly to a 1.x/2.x layout.

1. Back up your configuration and check the [3.x hardware requirements](HARDWARE.md).
2. For a cable-based upgrade, use the current [Easy Install keep-settings
   option](https://mattboxx.github.io/esp32-tailnet-gateway/easy-install/).
3. For the staged network route, first upload `firmware.bin` from the
   [legacy 1.100 bridge](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v0.1.38-Mattboxx-1.100)
   in **System → Firmware**. This is the old-layout bridge, not the latest 3.x image.
4. Continue through the **2.1.0 bridge** and its **Move to the 3.0 flash layout**
   action as described in [Moving to 3.0](MIGRATION-3.0.md).

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
- Application identity `esp32_tsr` and the NVS namespace remain stable.
  Ordinary application updates within a compatible layout preserve settings;
  moving to the 3.x layout requires the separate migration procedure above.
- Periodic checks, automatic installation and beta participation remain
  explicit opt-ins. **Check now** and **Install latest update** are on demand.

Historical 1.13 downloads remain available for recovery. Firmware rollback
depends on the valid previous OTA slot; serial recovery can use an appropriate
saved image. See [Updates](UPDATES.md) and [Backup and restore](BACKUP-RESTORE.md).
