# Ethernet uplink (optional, W5500 over SPI)

Most ESP32-S3 boards, including the N16R8 boards this firmware targets, have
**no Ethernet**. Support exists only for an explicitly wired **W5500 SPI
module** and only in the separate Ethernet build. It is implemented and
host-tested, but **not physically validated** on the current candidate.

## Builds

| Build | Ethernet | Notes |
|---|---|---|
| `esp32-s3` (default, releases) | Not compiled | WiFi-only; the Ethernet card shows "not available" |
| `esp32-s3-eth` | W5500 driver compiled, OFF until configured | About 61 KiB more app flash (measured) |

```powershell
& "$env:USERPROFILE/.platformio/penv/Scripts/platformio.exe" run -e esp32-s3-eth
```

`tools/eth_sdkconfig.py` derives the Ethernet configuration from the shipped
`sdkconfig.esp32-s3`, so the two images differ only by the driver.

## Wiring and settings

Network → **Ethernet uplink**: SPI host (SPI2/SPI3), SPI clock (1–40 MHz),
SCLK/MOSI/MISO/CS, INT (or -1 to poll every 10 ms) and RST (or -1). Pins
reserved on N16R8 boards are refused: GPIO0/3/45/46 (straps), 19/20 (USB),
26–37 (flash/octal PSRAM), 38–40 (microSD log), 43/44 (console UART). Use
DHCP or a static IPv4 address, mask, gateway and optional DNS. Settings are
validated, saved and **applied after a restart**; an invalid or damaged saved
record means "Ethernet off".

## Uplink preference

- **WiFi first** (default): Ethernet is used only while WiFi has no address.
- **Ethernet first**: Ethernet becomes the uplink after it has been up with an
  address for three consecutive route-supervisor checks; losing it falls back
  to WiFi immediately.

The selected uplink carries the default route, so Tailscale control/DERP and
WireGuard traffic and AP-client NAT follow it; in exit-node mode the tunnel is
pinned to the selected uplink. With Ethernet disabled the route logic is
exactly the previous WiFi behavior.

## Security

The Ethernet interface gets the same ESP-bound firewall chains as WiFi
(`to_esp`/`from_esp`). The driver is installed first and **started only after
those hooks are in place**; if they cannot be installed, Ethernet stays
stopped and reports why. Administration rules (password, Host/Origin
screening) are unchanged.

## Current limits

- Only W5500. DM9051/KSZ8851SNL drivers exist in ESP-IDF but are not wired.
- LAN → Tailnet rules (and AP-side port forwards) listen on the **selected**
  uplink: the Ethernet address while Ethernet is the uplink, otherwise WiFi.
  Bindings are reinstalled when the selection changes, so clients must use the
  address of the current uplink. Health Monitor and SNMP interface counters
  still observe WiFi only.
- DNS servers are global in lwIP: the last interface to obtain DHCP DNS wins.
- No measurements of throughput, link-flap behavior or power on real hardware.
