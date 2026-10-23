# Presentation preview and release availability

This update publishes the **ESP32 Tailnet Gateway — Mattboxx Edition** identity,
existing black/green artwork, README, public user guides and static website.
It publishes no new firmware, embedded sources, dependency commits or releases.
The repository name and OTA update paths remain unchanged.

## Available now

Public stable firmware remains
[0.1.38-Mattboxx-1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/releases/tag/v0.1.38-Mattboxx-1.13).
Its [versioned source and instructions](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13)
remain intact. It includes LAN-to-Tailnet TCP/UDP forwarding, source restrictions,
MagicDNS, subnet routing, AP gateway, exit-node roles, 4via6, saved WoL devices,
MQTT/Home Assistant, ntfy, read-only SNMP and opt-in updates. See its unchanged
[release notes](RELEASE-1.13.md) for the precise scope.

Published assets: firmware.bin, firmware-factory.bin,
ESP32-S3-router-0.1.38-Mattboxx-1.13-windows.zip, RELEASE-SHA256SUMS.txt and
FIRMWARE-LICENSES.txt. No forthcoming download or manifest is implied.

## Preview, not a stable release

New user guides, diagrams and feature pages also describe Firmware v2.0.0:
Smart Recovery, timed access, destination tests, Service Watch, layered Health
Monitor, diagnostic export, profiles, the refreshed UI, physically paired first
boot and browser/Easy Install options. They are not in the
current stable download. The optional W5500 variant is experimental and has
not been hardware-qualified. No full official-client authorization parity,
long-term reliability, signing or out-of-band recovery is claimed.

`NEXT_PUBLISHED=False` and `RENAMED=False` remain unchanged. No v2 firmware,
manifest or download button may be activated before a qualified public release.

The existing published source remains in Main until the firmware qualification
and separate release process are complete. Internal development ledgers, private
logs, credentials, backups, candidate firmware and dependency changes are not
part of this presentation publication.

## Temporary site and future migration

The site currently belongs at
https://mattboxx.github.io/esp32-tailscale-gateway-NAS-recovery/.
Only its deployment workflow is manual. Existing releases/tags are untouched.
Any later repository rename must follow the OTA bridge and migration process
before changing paths; see [migration plan](MIGRATION-RENAME.md).

When firmware is ready, update the release availability matrix, download assets,
guide labels and qualification scope. After an authorized rename, update the
site/repository constants, README badges, canonical/OG URLs, sitemap, robots,
metadata and Homepage together, then verify the real deployed paths again.
