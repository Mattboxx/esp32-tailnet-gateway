# Exit node

> **1.14 development preview.** This guide includes unreleased features; it
> does not imply a new firmware download. Public stable remains
> [Mattboxx 1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13).


Two separate, mutually exclusive modes.

## Use another node as exit (AP clients)

Tailscale page → **Exit node**: pick a tailnet exit node. Public traffic from
devices on the gateway's **AP** is routed through it; if it becomes
unreachable the path fails closed instead of leaking to the local Internet.
**LAN bypass** keeps RFC1918 destinations local. The tunnel is pinned to the
current uplink while this mode is on.

## Offer this gateway as an exit node

Tailscale page → **Advertise this ESP32 as an exit node** (opt-in), restart,
then approve it in the admin console / Headscale. IPv4 Internet egress is
masqueraded through the uplink. Native clients also discover the exit-node
DNS service (CONFIGURATION.md → Exit-node DNS).

Cautions: everything a client sends goes through your uplink and ISP; the
ESP32's throughput is modest and not measured for the current candidate; only
IPv4 egress is provided. Status and MQTT/HA report the runtime state, not
controller approval or verified Internet egress.
