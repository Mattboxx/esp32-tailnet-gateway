# Cellular uplink (GSM/LTE with a SIM) — experimental

Firmware 3.0 can use an external cellular modem as its Internet uplink: as the
main uplink, or only while WiFi and Ethernet are down (failover). It is **off
by default**, never dials until you enable it and acknowledge the data-use
notice, and it has **not yet been validated with a real modem**. Report what
works and what does not with your modem model.

## What you need

- An ESP32-S3 N8R8 or N16R8 running firmware 3.0 or later.
- A modem with a UART AT interface and PPP data calls, for example SIMCom
  SIM7600/SIM7670/A7670 or Quectel EC2x/EG91 boards. Modems without PPP
  (AT-socket-only) are not supported.
- A data SIM and its **APN** (from your operator, for example `internet`).
- A power supply for the modem able to deliver **2 A peaks** at its own
  voltage. Never power an LTE modem from the ESP32's 3.3 V pin.
- Logic levels that match: the ESP32-S3 uses 3.3 V. Many modem boards have a
  level shifter; bare modules running at 1.8 V need one.

## Wiring

| ESP32-S3 | Modem |
|---|---|
| TX GPIO (default 17) | RXD |
| RX GPIO (default 18) | TXD |
| GND | GND (common ground is required) |
| PWRKEY GPIO (optional) | PWRKEY, directly or through the board's transistor |
| RTS / CTS GPIO (optional, both or none) | CTS / RTS |

Usable pins on N8R8/N16R8: 1, 2, 4–18, 21, 41, 42, 47, 48. The firmware refuses
flash/PSRAM, USB, console, strapping and microSD pins, and any pin already used
by an enabled Ethernet module.

## Settings (Network → Cellular uplink)

- **I understand that mobile data may cost money** — required to enable.
- **Use**: *Only when WiFi and Ethernet are down* (failover) or *As the main
  Internet uplink*. LAN services (the LAN → Tailnet service gateway, health
  checks of the home network) stay on WiFi or Ethernet.
- **Allow roaming** — off by default: on a foreign network the modem waits.
- **APN**, optional **user name** and **password** (sent with PPP PAP).
- **SIM PIN** — optional. It is sent **once per start**: a wrong PIN stops the
  modem with a message instead of retrying towards a PUK lock. The password and
  PIN are write-only: the page shows only that they are saved.
- **UART**, **baud rate** (115200 for most modems), **TX/RX** pins, optional
  **RTS/CTS** and **PWRKEY** (pulsed at start and when the modem stops
  answering AT; *active high* for boards with a transistor driver).

Settings apply after a restart.

## Status

The card shows the modem state (starting, SIM, looking for the network, data
call, connected), operator, signal in dBm, the cellular IP address, whether it
carries the Internet traffic now and the data used since boot. After a failure
it retries after 30 s, doubling up to 10 minutes. A SIM that needs a PIN or is
PUK-locked stops until you fix it and restart.

## Security and costs

- The ESP-bound firewall lists (ACL *to ESP* / *from ESP*) apply to the
  cellular link too; the link does not start if those hooks cannot be
  installed.
- Tailscale over mobile networks usually runs through DERP relays because of
  carrier NAT: it works, with higher latency.
- Everything that uses the Internet uses mobile data while cellular carries the
  traffic: Tailscale, GitHub update checks, MQTT/ntfy, and Internet traffic of
  access-point clients. Use failover mode on limited plans.
