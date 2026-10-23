# Hardware compatibility

> **1.14 development preview.** This guide includes unreleased features; it
> does not imply a new firmware download. Public stable remains
> [Mattboxx 1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13).


| Item | Requirement / status |
|---|---|
| SoC | ESP32-S3 only (images are built for it). Other ESP32 families are not targets. |
| PSRAM | 8 MB octal PSRAM expected (N16R8/N8R8). Without PSRAM the optional operations worker cannot start: Smart Recovery, Health Monitor, destination tests and Service watch report unavailable; routing and the Web UI still work. |
| Flash | Two 1920 KiB OTA app slots plus NVS/coredump (`partitions.csv`); the default image uses about 93% of a slot. |
| Radio | One 2.4 GHz radio shared by STA and AP. |
| Ethernet | None on typical boards. Optional W5500 SPI module in the separate `esp32-s3-eth` build only, not physically validated: [ETHERNET.md](ETHERNET.md). |
| microSD | Optional log recorder on GPIO38/39/40 (SDMMC 1-bit); those pins are reserved. |
| Power | Independent, reliable supply; no power-consumption measurement is claimed. |

## Board reports

From upstream reports, not a qualification of the current development line:

| Board | Result |
|---|---|
| ESP32-S3-DevKitC-1 N16R8 | Reference board |
| Freenove ESP32-S3-WROOM N8R8 | Community-confirmed (AP, Web UI, setup) |
| Seeed XIAO ESP32-S3 N8R8 | Community-confirmed (AP, direct and DERP data plane); see the first-flash note in the README |
| YD-ESP32-S3 clones | Not working: SoftAP not visible, a board-level RF issue |

## Before buying or flashing

- Check the module marking (N16R8 / N8R8): PSRAM size and type matter.
- Prefer genuine modules; clones vary in RF and flash quality.
- Keep a way to reflash over USB; read [UPDATES.md](UPDATES.md) and keep a
  configuration backup ([BACKUP-RESTORE.md](BACKUP-RESTORE.md)).
- The current development candidate has not been hardware-qualified; the
  stable release is the one to use on a production network.
