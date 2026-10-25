# Moving a 2.x gateway to 3.0

Firmware 3.0 uses a new 8 MB flash layout (larger update slots, a storage
area). Older 2.x gateways have the 4 MB layout of 2.x, so 3.0 cannot simply
be installed over the air like a normal update. There are three ways; all of
them **keep every setting** (WiFi, Tailscale identity, admin password,
rules), because the settings area stays at the same place.

Supported boards: ESP32-S3 with 8 MB octal PSRAM and at least 8 MB of flash
(N8R8, N16R8). Boards with 4 MB of flash stay on 2.x.

## 1. Over the network, no cable (2.1 bridge)

*Not published yet: until the 2.1 bridge release is out, use option 2 or 3.*

1. In **System → Firmware**, check for updates and install **2.1.0**. It is a
   normal 2.x update.
2. After the restart, **System** shows **Move to the 3.0 flash layout**. Make
   sure the power supply is stable, tick the confirmation and press
   **Migrate to 3.0**.
3. The gateway may restart once to prepare, then downloads 3.0 from GitHub,
   checks every file, writes 3.0 next to the running firmware, rewrites the
   boot loader and the partition table, and restarts into 3.0. It takes a
   few minutes.

If anything fails before the last step, nothing changes and the bridge keeps
running as a normal gateway. If 3.0 does not start, the gateway returns to
the bridge. **Do not cut the power during the last step** (well under a
second, shown as "keep the power on"): if that happens, reinstall over USB
with option 2 — settings are still kept.

## 2. Over USB with Easy Install

Run `UPDATE-KEEP-SETTINGS` (Windows) or `install.sh update` (macOS/Linux) from
the 3.0 Easy Install package. It writes the boot loader, the new partition
table and 3.0 without touching the settings area.

## 3. Over USB from the browser

Use the web installer with **Erase device unticked**.

## Tested

The network migration (from 2.0.4-beta.2 with the bridge in the second slot,
including its preparation restart) and the USB migration were run on a
N16R8: settings and Tailscale connectivity were kept. N8R8 boards follow the
same layout but have not been tested yet.
