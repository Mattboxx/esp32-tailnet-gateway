# Ethernet uplink (optional, W5500 over SPI)

Most ESP32-S3 boards, including the N8R8 and N16R8 boards this firmware
targets, have **no Ethernet**. Support exists only for an explicitly wired
**W5500 SPI module**; from 3.0 the driver is in the standard image. It is implemented and
host-tested, but **not physically validated** on the current candidate.

## Builds

| Build | Ethernet | Notes |
|---|---|---|
| `esp32-s3` (3.x, releases) | W5500 driver compiled, OFF until configured | One image for every board and language |
| 2.x `esp32-s3-eth` (historical) | W5500 driver compiled | Separate English-only image of the 2.x line |

## Wiring and settings

Network → **Ethernet uplink**: SPI host (SPI2/SPI3), SPI clock (1–40 MHz),
SCLK/MOSI/MISO/CS, INT (or -1 to poll every 10 ms) and RST (or -1). Pins
reserved on N8R8/N16R8 boards are refused: GPIO0/3/45/46 (straps), 19/20 (USB),
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
  address of the current uplink. Health Monitor gateway checks also use the
  selected uplink; SNMP interface counters still observe WiFi only.
- DNS servers are global in lwIP: the last interface to obtain DHCP DNS wins.
- No measurements of throughput, link-flap behavior or power on real hardware.
- From 2.0.1 the Web UI of this image is English only (no Italian, Spanish or
  Chinese translations): the image must fit the same 1920 KiB application
  partition as the WiFi build. The `.local` name answers on the WiFi uplink only.
