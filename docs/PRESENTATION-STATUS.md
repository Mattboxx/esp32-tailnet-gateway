# Firmware and installation availability

**ESP32 Tailnet Gateway — Mattboxx Edition**, Firmware **v2.0.1**.
One ESP32. Multiple Tailnet roles. Enable only what you need.

## Current downloads

- [Firmware v2.0.1](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v2.0.1)
- [Browser installer](https://mattboxx.github.io/esp32-tailnet-gateway/install-firmware/)
  for desktop Chrome/Edge and USB-connected ESP32-S3 N16R8 boards.
- [Easy Install guide](https://mattboxx.github.io/esp32-tailnet-gateway/easy-install/)
  for the Windows/macOS/Linux ZIP, including a keep-settings update mode.
- [Advanced downloads](https://mattboxx.github.io/esp32-tailnet-gateway/downloads/)
  for OTA, factory images, checksums and manifests.

`firmware.bin` is the WiFi application image for Web UI OTA. The separate
`firmware-eth.bin` and Ethernet factory image are **experimental W5500** builds
requiring compatible hardware and pin configuration. Factory/new-device erase
modes remove settings; do not upload a factory image through the Web UI updater.
Use v2.0.1 for new installations: it corrects first-boot pairing and setup
restart handling. The WiFi image keeps four UI languages; W5500 is English-only.

This edition includes Selective LAN → Tailnet TCP/UDP access, timed rules,
destination tests and Service Watch; device registry and Smart Recovery;
health/diagnostic tools, profiles and optional MQTT/Home Assistant, ntfy and
SNMP. Existing subnet routing, AP gateway, exit-node roles, 4via6, WoL and
Tailscale/Headscale functionality remain available as selectively enabled roles.
It is community firmware, not an official Tailscale client or a Linux router.

## Existing installations and repository migration

The existing repository was renamed to `Mattboxx/esp32-tailnet-gateway`; it was
not replaced by a disconnected repository. The bridge
[0.1.38-Mattboxx-1.100](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v0.1.38-Mattboxx-1.100)
was published under the previous name first. Older firmware that missed this
bridge needs one manual update; see [Migration](MIGRATION-RENAME.md).

Historical releases, source tags, licenses and original Csontikka/MicroLink
credits remain intact. The previous [1.13 release](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v0.1.38-Mattboxx-1.13)
retains its original binaries, installation package and versioned instructions.

The website serves byte-identical copies of the released WiFi installer parts
with a manifest and SHA-256 checksums. Firmware qualification logs and detailed
maintainer handovers remain local, outside public release descriptions.
