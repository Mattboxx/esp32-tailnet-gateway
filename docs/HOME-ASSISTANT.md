# Home Assistant

Home Assistant integration uses MQTT Discovery; configure [MQTT](MQTT.md)
first. Home Assistant is optional: nothing on the gateway depends on it.

## Enable

Automation → MQTT → **Home Assistant Discovery** and the discovery prefix
(default `homeassistant`). Discovery is published in small paced batches after
each connection (status: *Discovery in progress*); the gateway cannot confirm
that Home Assistant created the entities.

## Entities

One device with sensors and controls for:

- Uplink, WiFi signal, Tailscale connection, peers, advertised routes,
  exit-node state, AP, 4via6, resources (heap, sockets), CPU, firmware and
  update status, MQTT broker watchdog.
- Operations: recovery state, health, internal largest block, sockets, service
  closures; per-device **Recovery** buttons (honour *Allow MQTT/ntfy recovery
  commands*).
- Service Gateway, per rule: an enable **switch**, **time remaining** for
  temporary rules and **Tailnet rule status** (the diagnosis code: e.g.
  `service_replied`, `destination_no_answer`, `source_rejected`,
  `ready_to_enable`). Totals: configured/enabled/active rules and
  accepted/blocked packets.
- Switches for the same commands listed in [MQTT](MQTT.md).

Entities for removed rules are cleared from retained discovery. Rule switches
use binding-qualified command topics; after editing rules, Discovery is
re-published so Home Assistant uses the new topics.

## Notes

- Controls in Home Assistant can expose networks (routes, exit node, rules):
  restrict who can operate them in Home Assistant and on the broker.
- `state_compact_level` above 0 means the state was trimmed to fit the MQTT
  budget; every field the entities read is kept.
- Real Home Assistant discovery/reconnect behavior is not yet qualified for
  the current development candidate.
