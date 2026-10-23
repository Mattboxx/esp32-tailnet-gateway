# Getting started — Firmware v2.0.1

You need an **ESP32-S3 N16R8** (16 MB flash, 8 MB octal PSRAM), a USB data
cable, and a 2.4 GHz WiFi network. Tailscale or Headscale is needed for Tailnet
roles, not for local administration or local Wake-on-LAN.

## 1. Choose an installation method

- **Browser:** [Install firmware](https://mattboxx.github.io/esp32-tailnet-gateway/install-firmware/)
  in desktop Chrome/Edge, connect USB and choose the ESP32-S3 port.
- **Easy Install:** download the Windows/macOS/Linux ZIP from the
  [v2.0.1 release](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v2.0.1).
  Read `START-HERE.txt`. Windows includes esptool; macOS/Linux need Python 3
  and esptool 5. Choose `windows/INSTALL-NEW-DEVICE.bat` for a fresh setup or
  `windows/UPDATE-KEEP-SETTINGS.bat` for an existing gateway.
- **Advanced:** use the factory image for a fresh USB installation, or upload
  **`firmware.bin`** in **System → Firmware** for an existing gateway.

Back up an existing configuration first. Factory/new-device erase modes delete
settings. Never upload a factory image through the Web UI. USB keep-settings
mode is not inactive-slot OTA and must not overwrite a protected recovery slot.
The optional **experimental W5500** image requires its documented hardware;
the standard WiFi package is for WiFi boards.

## 2. Set up a new gateway

A genuinely unconfigured board opens **`ESP32-Tailnet-Setup-XXXX`**. Join it
near the board. If the captive page does not open, visit **http://192.168.4.1/**.

1. Pair physically with **BOOT**, or enter the current eight-digit setup code
   from the USB console. There is no shared default administrator password.
2. Create your admin password.
3. Select and test the 2.4 GHz WiFi uplink.
4. Optionally configure Tailscale or Headscale and select the roles you need.
5. Set a protected gateway/recovery AP name and password, then finish/restart.

Setup requests are sealed, but a malicious lookalike AP is still a risk: use
your own board and a trusted physical location. The setup AP does not forward
LAN/Internet traffic. Setup is English-only; the main UI also offers Italian,
Spanish and Simplified Chinese.

An already configured gateway keeps its settings and does **not** reopen this
initial setup network. See [First boot](FIRST-BOOT-SETUP.md) for details.

## 3. Join the Tailnet

Use the setup wizard or **Tailscale** page to configure your control server,
device name and registration credentials. Keep auth keys private and scoped
to the roles required. Review node expiry and route approval in your Tailnet
administration according to your own access policy.

- [Headscale](HEADSCALE.md)
- [Subnet routing](SUBNET-ROUTER.md)
- [Exit-node roles](EXIT-NODE.md)
- [Authorization and supported policy semantics](TAILNET-AUTHORIZATION.md)

Control connectivity or a visible peer alone does not prove service reachability
or authorization. Use a real destination check and the relevant client path.

## 4. Start with one role

For the **Selective LAN → Tailnet Service Gateway**, reserve the ESP32's LAN
address on your router. Add a rule under **Network → LAN → Tailnet**, choose
the remote Tailnet destination and port, and restrict the allowed source to
the intended client (`/32` where practical). Run **Test destination**, then
enable the rule and test it from that client. AP-side forwarding is separate.
See the [Service Gateway guide](SERVICE-GATEWAY.md).

For **Recovery**, save a compatible device's MAC and follow
[Smart Recovery](SMART-RECOVERY.md). Sending a magic packet is not proof that
the device booted. MQTT, Home Assistant and ntfy are optional integrations,
not prerequisites for routing, local recovery or administration.

## Updates and recovery

Prefer Web UI application updates; keep a configuration backup and a known
recovery image. [Updates](UPDATES.md), [Backup and restore](BACKUP-RESTORE.md)
and [Troubleshooting](TROUBLESHOOTING.md) explain the options.

Firmware 1.13 and earlier installations that missed the OTA bridge need one
manual update after the repository rename; see [Migration](MIGRATION-RENAME.md).
Their [versioned installation guide](https://github.com/Mattboxx/esp32-tailnet-gateway/blob/v0.1.38-Mattboxx-1.13/README.md)
and original downloads remain in the historical release.
