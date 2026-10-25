# Moving a 2.x gateway to 3.0

Firmware 3.0 uses a new 8 MB flash layout (3.5 MB update slots and a
storage area). 2.x gateways still have the 4 MB layout of 2.x, so 3.0
cannot be installed over the air like a normal update: the 2.x updater skips
it because it does not fit its slot. There are three ways; all of them
**keep every setting** (WiFi, Tailscale identity, admin password, rules),
because the settings area stays at the same place.

**Supported boards:** ESP32-S3 with 8 MB octal PSRAM and at least 8 MB of
quad flash (N8R8, N16R8). Boards with 4 MB of flash stay on 2.x. See
[Hardware](HARDWARE.md) for the full list.

## 1. Over the network, no cable (2.1.0 bridge)

1. In **System → Firmware update**, press **Check now** and install
   **2.1.0**. It is a normal 2.x update, offered on the stable channel.
   (From 2.0.0 or 2.0.1, whose GitHub updater does not work, upload the
   2.1.0 `firmware.bin` by hand once.)
2. After the restart, turn on the **web UI lock** if it is off — *Require
   the admin password* in **System → Access** — and sign in. **The migration
   needs it**: without a signed-in session the button stays off and the card
   says so.
3. In **System → Maintenance**, the card **Move to the 3.0 flash layout**
   appears. Make sure the power supply is stable, tick the confirmation and
   press **Migrate to 3.0**.
4. The gateway may restart once to prepare, then downloads the newest stable
   3.x from GitHub, checks every file, writes 3.x next to the running
   firmware, rewrites the boot loader and the partition table, and restarts
   into 3.x. It takes a few minutes.

2.1.0 is the only bridge release: it always installs the newest stable 3.x,
so there is no newer bridge to wait for.

If anything fails before the last step, nothing changes and the bridge keeps
running as a normal gateway; the card shows the reason. If 3.x does not
start, the gateway returns to the bridge. **Do not cut the power during the
last step** (well under a second, shown as "keep the power on"): if that
happens, reinstall over USB with option 2 — settings are still kept.

## 2. Over USB with Easy Install

Run `UPDATE-KEEP-SETTINGS` (Windows) or `sh macos-linux/install.sh update`
(macOS/Linux) from the 3.0 Easy Install package. It writes the boot loader,
the new partition table and 3.0 without touching the settings area.

## 3. Over USB from the browser

Use the [web installer](https://mattboxx.github.io/esp32-tailnet-gateway/install-firmware/)
in desktop Chrome or Edge with **Erase device unticked**.

## After the move

Updates work over the air again (System → Firmware update). The new
features of 3.0 — event history, trends, settings copies, tailnet names,
Telegram and email notifications — are off until you switch them on.

## Tested

On an N16R8: the network migration from a 2.x gateway through the 2.1.0
bridge to 3.0.0-beta.1 downloaded from the real GitHub releases (including the
preparation restart), and the USB migration with Easy Install. Settings, the
tailnet identity and Tailscale connectivity were kept. N8R8 boards use the
same layout but have not been tested yet.
