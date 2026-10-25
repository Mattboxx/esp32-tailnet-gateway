# Firmware and installation availability

**ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware **v3.0.1**.
One ESP32. Multiple Tailnet roles. Enable only what you need.

## Current downloads

- [Firmware v3.0.1](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v3.0.1)
  for ESP32-S3 **N8R8** and **N16R8** (8 MB octal PSRAM, at least 8 MB of
  flash; [supported boards](HARDWARE.md)).
- [Browser installer](https://mattboxx.github.io/esp32-tailnet-gateway/install-firmware/)
  for desktop Chrome/Edge and USB-connected boards.
- [Easy Install guide](https://mattboxx.github.io/esp32-tailnet-gateway/easy-install/)
  for the Windows/macOS/Linux ZIP, including a keep-settings update mode.
- [Advanced downloads](https://mattboxx.github.io/esp32-tailnet-gateway/downloads/)
  for OTA, factory images, checksums and manifests.
- [Migration bridge v2.1.0](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v2.1.0)
  for 2.x gateways that move to 3.0 over the network
  ([guide](MIGRATION-3.0.md)).

`firmware.bin` is the application image for Web UI OTA, with every Web UI
language and the W5500 driver (experimental, off until configured).
Factory/new-device erase modes remove settings; do not upload a factory image
through the Web UI updater. Boards with 4 MB of flash stay on 2.x
([v2.0.2](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v2.0.2)).

This edition includes Selective LAN → Tailnet TCP/UDP access, timed rules,
destination tests and Service Watch; device registry and Smart Recovery;
health/diagnostic tools, profiles, event history and trends, settings copies,
tailnet names for local devices and optional MQTT/Home Assistant, ntfy,
Telegram, email and SNMP. Existing subnet routing, AP gateway, exit-node
roles, 4via6, WoL and Tailscale/Headscale functionality remain available as
selectively enabled roles. It is community firmware, not an official
Tailscale client or a Linux router.

## Existing installations and repository migration

The existing repository was renamed to `Mattboxx/esp32-tailnet-gateway`; it was
not replaced by a disconnected repository. The bridge
[0.1.38-Mattboxx-1.100](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v0.1.38-Mattboxx-1.100)
was published under the previous name first. Older firmware that missed this
bridge needs one manual update; see [Migration](MIGRATION-RENAME.md).

Historical releases, source tags, licenses and original Csontikka/MicroLink
credits remain intact. The previous [1.13 release](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v0.1.38-Mattboxx-1.13)
retains its original binaries, installation package and versioned instructions.

The website serves byte-identical copies of the released installer parts
with a manifest and SHA-256 checksums. Firmware qualification logs and detailed
maintainer handovers remain local, outside public release descriptions.
