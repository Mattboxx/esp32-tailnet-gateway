# MQTT

MQTT is optional. Routing, the Web UI, the Service Gateway and manual
Wake-on-LAN never depend on a broker.

## Setup

Automation → **MQTT**: broker URI (`mqtts://` recommended; `mqtt://` sends
credentials in clear text), optional username/password, base topic and the
state interval. Status shows *Connected*, *Retry in N s* (bounded backoff,
5 s doubling to 5 minutes) or *Incomplete settings*.

## Topics (base topic `B`)

| Topic | Direction | Content |
|---|---|---|
| `B/availability` | device → broker, retained | `online`, last will `offline` |
| `B/state` | device → broker, retained QoS1 | JSON state (below) |
| `B/command/<name>` | broker → device | commands (below) |

The state includes uplink, Tailscale, routes/exit node, AP, resources,
updates, MQTT watchdog, `operations` (recovery, health, resources),
`forwarding_leases` and `tailnet_forward_rules[]` with `enabled`, `installed`,
`status` (same diagnosis code as the Web UI), `destination_check` and
`service_reply_age_s`, plus `service_watch` (ON/OFF) and the active `profile`. The state is fitted to 6 KiB: when larger, detail the
Web UI still serves is dropped and `state_compact_level` (1 or 2) says so.

## Commands

Switches accept `ON`/`OFF` (also `on`, `1`, `true` / `off`, `0`, `false`);
anything else is rejected.

| Command | Effect |
|---|---|
| `status` | publish state now |
| `restart` | controlled restart |
| `reconnect_wifi`, `reconnect_tailscale` | reconnect that link |
| `ap_always_on`, `wifi_power_save`, `tailscale_enabled`, `accept_routes`, `snat_subnet_routes`, `advertise_ap`, `advertise_exit_node`, `exit_node_lan_bypass`, `fourvia6_enabled`, `health_monitor_enabled`, `service_watch_enabled` | switches (`service_watch_enabled` keeps the saved interval/notify) |
| `tailnet_forward/<index>/<8-hex rule token>` | enable/disable one Service Gateway rule; index-only topics are rejected so a delayed command cannot hit another rule |
| `tailnet_test/<index>/<8-hex rule token>` with `PRESS` | run one destination test for that rule (same binding rule as the switch) |
| `wol/<MAC>` | send WoL to a **saved** device only |
| `recovery/<12-hex MAC>` with `PRESS` | Smart Recovery, only if *Allow MQTT/ntfy recovery commands* is on |

## Security

MQTT commands are authorized by your broker, not by this device: anyone who
can publish to `B/command/#` can use them. Use broker authentication, TLS and
ACLs that restrict that topic. The rule token is a change detector, not a
credential.

## Broker watchdog

Optional: after the broker has been silent for the configured time, send one
Wake-on-LAN burst per outage to a saved device (for a broker on a NAS). A sent
packet is not proof the host powered on.

## Power-return automations

Firmware 3.0.5 adds an opt-in possible-blackout MQTT event, switch and boot
diagnostics. See [Power-return automations](MQTT-POWER-RETURN.md) for setup,
non-retained delivery, duplicate suppression and optional catch-up after HA
starts later. Software restarts and broker reconnects do not create the event.
