# 0.1.38-Mattboxx-1.14-dev.6 — ESP32 Tailnet Gateway (development candidate)

**Channel:** pre-release, local candidate. Not published. Stable remains 1.13.

## What changes for users

- **New name:** ESP32 Tailnet Gateway — Mattboxx Edition (formerly ESP32
  Homelab Gateway). Settings, app identity and updater identity are unchanged;
  updating keeps your configuration.
- **Easier Web UI:** a "What do you want to do?" start with guided goals, a
  simple mode that hides expert sections (switch to advanced at any time),
  an at-a-glance status strip, consistent buttons and 44 px touch targets,
  Service Gateway rules as a table on desktop and cards on phones.
- **Languages:** English, Italiano, Español and 简体中文, detected from the
  browser and selectable in System → Interface mode.
- **Service Gateway:** destination test, Service watch, templates, guided
  setup, sanitized rule transfer, temporary access.
- **Recovery access point** returns 60 s after the saved WiFi disappears.
- **Security:** login and logout now refuse cross-site requests; every
  state-changing request is screened.
- **Repository rename bridge:** the updater finds releases under the new
  repository name and, before the rename, under the old one.
- **Ethernet (experimental):** separate `firmware-eth.bin` image for boards
  with a W5500 module; it updates only from its own asset.

## Upgrade notes

- From 1.13 or older: upload `firmware.bin` in System → Firmware, or use the
  Windows package. After the repository is renamed, 1.13 cannot find updates by
  itself; install this release (or later) once by hand.
- The Web UI starts in simple mode; your settings are not changed.

## What was tested

On one ESP32-S3 N16R8 (USB, home WiFi, hosted Tailscale): flashing to the
second slot, boot, WiFi and tailnet join, direct WireGuard path (~10–15 ms
ping from a tailnet PC), Web UI over LAN and over the tailnet, unauthenticated
API refusal (401), cross-site login/logout refusal (403), reboot with timing
and heap observation (no panic; internal heap 7.8–13 KB). Offline: the full
host test campaign and browser tests at 9 viewports in four languages.

## Not yet tested (blocked or pending)

Authenticated flows on the device (Service Gateway TCP/UDP end-to-end through
a LAN client, rule expiry, Service watch, profiles, NVS persistence, OTA via
the Web UI and rollback), MQTT/Home Assistant, ntfy, SNMP, Wake-on-LAN and
recovery on a real target, the AP fallback by removing the WiFi, W5500
hardware, Linux sanitizers, long soak. Do not treat this candidate as stable.
