# ESP32 Tailscale Gateway & NAS Recovery 1.13

**Stable · `v0.1.38-Mattboxx-1.13` · ESP32-S3 N16R8**

All published upstream improvements from v0.1.34 through v0.1.38, combined
with the Mattboxx automation, NAS recovery and gateway features.

## What's improved

- **Safer relay connections:** DERP TLS certificate and hostname verification,
  with upstream WireGuard key, replay, handshake and packet-counter fixes.
- **More reliable connectivity:** corrected relay measurements and reporting,
  sticky relay selection, recovery of silent peer sessions and quicker
  detection of closed or stalled control connections.
- **Network lifecycle fixes:** completion-waiting TCP/IP cleanup from v0.1.38,
  while retaining the mod's startup recovery and initialization safeguards.
- **More efficient packet transmission:** upstream copy-free WireGuard TX,
  with additional authenticated local diagnostics and up to 32 relay results.
- **Stable-channel updates:** a matching stable firmware version and release
  tag, discoverable without beta enrollment. Automatic updates remain opt-in.

## All Mattboxx features remain

- An independent NAS/homelab companion with saved, named Wake-on-LAN devices.
- Subnet routing, exit-node selection/advertising and 4via6 controls.
- Separate **LAN → Tailnet TCP/UDP forwarding** and **AP-side port forwarding**,
  including source restrictions, MagicDNS destinations and port conflict checks.
- Optional WiFi access point/gateway with automatic AP-off policy.
- MQTT/Home Assistant controls and discovery, plus ntfy notifications and
  remote commands with configurable availability policies.
- Configurable Web UI port, password/session policy, encrypted backups,
  CPU/temperature status, local diagnostics and optional read-only SNMP.
- Optional WiFi power save, OFF by default in this mod. Ethernet uplink is not
  implemented in this application; generic SNMP ETH counters are not a driver.
- No external telemetry/log/crash uploads or forced update checks. Configured
  VPN, MQTT/ntfy and explicitly requested GitHub updates still use the network.

WoL requires compatible hardware and standby power; it is not a hard reset,
KVM or file recovery service. The Web UI belongs on a trusted LAN or tailnet,
not the public Internet.

## Update or install

- **Existing installation:** use **System → Firmware update → Check now**,
  then **Install latest update**, or upload `firmware.bin` manually. Settings
  are preserved. An installed 1.13-dev.1 candidate can update to this stable
  version without joining the beta channel.
- **Easy Windows USB update:** download and extract the Windows ZIP, close
  serial monitors, then double-click `UPDATE_KEEP_SETTINGS.bat`.
- **Fresh installation only:** use `CLEAN_INSTALL_ERASE_ALL.bat` in the ZIP;
  this erases saved settings after confirmation. `firmware-factory.bin` is
  for a fresh-board flash, **not** Web UI OTA.

Assets also include `RELEASE-SHA256SUMS.txt` and original component license
notices. This package targets ESP32-S3 N16R8 with 8 MB octal PSRAM and the
existing 4 MB partition layout; it is not a universal binary for every ESP32
or Ethernet wiring configuration. Previous releases remain available.

## Credits and optional support

Based on [Csontikka's ESP32 Tailscale router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink), originally by Cameron
Malone. Upstream improvements belong to their authors and contributors;
original copyright, license notices and support links are retained. This is
a community modification, not an official Tailscale client.

If this mod helps your homelab, you can optionally
[support Mattboxx on Ko-fi](https://ko-fi.com/mattboxx).
Support for the original project remains separate:
[GitHub Sponsors](https://github.com/sponsors/Csontikka) ·
[Buy Me a Coffee](https://buymeacoffee.com/csontikka).
All features remain free.
