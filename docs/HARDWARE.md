# Hardware compatibility

Firmware 3.x runs on **ESP32-S3 with 8 MB octal PSRAM and at least 8 MB of
quad flash**. One image serves every supported board: it uses the first
8 MB of flash, so a 16 MB board works the same way.

## Supported ESP32-S3 boards

| Module / board | Flash · PSRAM | Status |
|---|---|---|
| ESP32-S3-DevKitC-1 **N16R8**, ESP32-S3-WROOM-1/1U-N16R8 | 16 MB quad · 8 MB octal | **Tested** (reference board) |
| ESP32-S3-DevKitC-1 **N8R8**, ESP32-S3-WROOM-1/1U-N8R8 | 8 MB quad · 8 MB octal | Supported, same layout; not yet tested on 3.x |
| Freenove ESP32-S3-WROOM N8R8 / N16R8 | 8–16 MB · 8 MB octal | Supported; community-confirmed on earlier firmware |
| Seeed XIAO ESP32S3 (8 MB flash, 8 MB PSRAM) | 8 MB · 8 MB octal | Supported; community-confirmed on earlier firmware (AP, direct and DERP data plane) |

The module marking tells you the variant: `N` = flash in MB, `R` = PSRAM in
MB. You need `N8` or more and `R8`.

## Not supported

| Board | Why |
|---|---|
| 4 MB flash (N4, N4R2, N4R8) | 3.x needs 8 MB. These boards stay on the 2.x line. |
| 2 MB quad PSRAM (N8R2, N16R2) or no PSRAM (N8, N16) | The image expects 8 MB octal PSRAM. |
| Octal-flash modules: ESP32-S3-WROOM-2, N16R16V, N32R8V, N32R16V | The image uses quad flash (DIO) and does not configure octal flash. |
| ESP32, ESP32-S2, ESP32-C3/C5/C6, ESP32-H2, ESP32-P4 | Other chips; the installers refuse anything that is not an ESP32-S3. |
| YD-ESP32-S3 clones | Reported not working: access point not visible, a board-level RF issue. |

## Requirements and options

| Item | Requirement / status |
|---|---|
| Flash layout | 3.x: two 3.5 MB update slots, settings, core dump and a 832 KB storage area (`partitions.csv`). 2.x gateways move with the [migration guide](MIGRATION-3.0.md); settings are kept. |
| Radio | One 2.4 GHz radio shared by uplink and access point. |
| Ethernet | Optional W5500 SPI module, driver in the standard image, off until configured; not validated on real hardware: [ETHERNET.md](ETHERNET.md). |
| Cellular | Optional UART modem with a SIM, off until configured; experimental, not tested with a real modem: [CELLULAR.md](CELLULAR.md). |
| microSD | Optional log recorder on GPIO38/39/40 (SDMMC 1-bit); those pins are reserved. |
| Power | Independent, reliable supply; no power-consumption measurement is claimed. |

## Before buying or flashing

- Check the module marking (N8R8 / N16R8): PSRAM size and type matter.
- Prefer genuine modules; clones vary in RF and flash quality.
- Keep a way to reflash over USB; read [UPDATES.md](UPDATES.md) and keep a
  configuration backup ([BACKUP-RESTORE.md](BACKUP-RESTORE.md)).
- Please report other boards with the *Hardware report* issue form.
