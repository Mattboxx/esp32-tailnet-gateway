# Selective Tailnet Service Gateway

The primary feature of ESP32 Homelab Gateway — Mattboxx Edition: let ordinary
devices on your existing LAN use **specific** services on your Tailscale or
Headscale tailnet, without a Tailscale client on those devices, without joining
them to the ESP32 access point and without changing your router or default
gateway. The underlying VPN (Tailscale/WireGuard/DERP/MagicDNS) is not a
Mattboxx invention; the value here is making a selective, verifiable and
time-bounded service path easy to set up on a small independent board.

## When to use it — and when not

| Need | Use |
|---|---|
| A few LAN devices must reach one or two remote tailnet services | **Service Gateway rules** (this guide) |
| Tailnet clients must reach your LAN | Subnet router (Tailscale page), approved in your admin console |
| Devices can run a Tailscale client | Install the client on them |
| Isolated IoT devices on their own WiFi | AP gateway, with its separate AP-side forwarding |
| Site-wide routing, bulk transfer, video | A router/server-class Tailscale node, not an ESP32 |

## Five-minute example

Goal: an MQTT sensor hub at `192.168.1.20` (no VPN client) publishes to a
broker on another site, `broker.your-tailnet.ts.net:1883`.

1. Give the ESP32 a fixed LAN address, e.g. `192.168.1.50`, and join it to
   your tailnet. Allow its identity to reach the broker in your tailnet ACL.
2. Status page → **Publish a Tailnet service** (or Network → LAN → Tailnet).
   The guide checks uplink, control connection, web password and a free slot,
   lists the risks and asks you to acknowledge the exposure.
3. Add a rule: TCP, listen `18830`, destination `broker.your-tailnet.ts.net`,
   port `1883`, source `192.168.1.20/32`. It is saved **disabled**.
4. Press **Test destination**. The ESP32 itself makes one bounded TCP
   handshake (2 s limit) with the broker through the tunnel — the same remote
   leg forwarded clients use — while the rule is still disabled.
5. Enable the rule, optionally arm an expiry, and set the hub's broker to
   `192.168.1.50:18830`. Watch installed state and accepted/rejected counters.

## Destination test results (development line)

| State | Meaning | Not a claim of |
|---|---|---|
| `reachable` | TCP handshake completed from the ESP32 | application health, LAN client path |
| `no_tcp_answer` | No handshake in 2 s | which of refusal, filtering or timeout |
| `udp_unverifiable` | UDP has no handshake | either success or failure |
| `control_offline` / `policy_not_ready` | Tunnel prerequisites missing | a remote fault |
| `unresolved` | Not a Tailnet IPv4 from literal/peer cache | the peer being offline |
| `resource_deferred` / `local_error` | Local admission or socket problem | a network fault |
| `rule_changed` | Rule edited before the test ran | anything about the service |

Tests run only on request, one at a time, with a 5 s per-rule cooldown, in
the existing optional operations worker (one socket); the routing core never
waits for them. A result belongs to the rule's exact settings: editing the
destination, port, protocol or source hides it. Requires a board with PSRAM
for the optional worker.

## Activity and reply evidence (development line)

Each rule shows when the gateway last **accepted** and last **rejected** a LAN
packet for it (uptime-based, "never this boot" after a restart), and when the
Tailnet service last **replied**: the newest reply the policy gate admitted on
a flow this gateway sent to that destination IP and port. For UDP that reply is
the only evidence the service answers. Reply evidence belongs to the remote
service tuple, so rules sharing a destination share it; it is not per LAN
client, and it disappears while authority is suspended or after revocation.

## Performance and limits

IPv4 TCP/UDP, up to 8 rules, destination in `100.64.0.0/10`. Clients connect to
the ESP32 address and listen port (port forwarding, not transparent routing).
WiFi plus software WireGuard on a microcontroller suits control, telemetry,
dashboards and SSH; throughput is not measured for the current candidate.

## Experimental dev.5 exposure leases

Network → LAN → Tailnet → **Temporary exposure and expiry** controls saved
rules only. Arm/renew60–604800 seconds or explicitly confirm a permanent rule.
Arming does not enable a disabled rule. Rule tokens are change detectors,
not authentication. Unknown clock/store, expiry or an unconfirmed changed binding
means denied forwarding. Monotonic packet cutoff and persisted UTC bound
validity across restart; detected rollback latches closure. Expired rules are
retained/reserve configured ports by default. Opt in to **Delete rule after
expiry** when arming/renewing to remove it through the shared forwarding
transaction. Failed allocation/save leaves it closed and retries at most once
per minute; it does not reopen the old mapping.

The dev.4 positional timer had a confirmed bug: moving an expired rule into an
untimed slot could make it permanent. Dev.5 uses a stable binding ledger, not
the list position. Reordering preserves expiry; editing a binding cannot shed
its timer by moving it. First timer use records the current permanent bindings;
subsequent new/edited rules require explicit timer/permanent confirmation.
`binding-unconfirmed` means closed, not an expired timer silently renewed.

Lease storage v3 preserves matching v1/v2 timers by rule identity. Untracked
rules in a migrated timed table are deliberately closed until confirmed; their
old identity cannot be inferred safely. Older firmware rejects this newer lease
store rather than treating it as unrestricted forwarding. Hardware migration/
rollback remains unqualified. Expired bindings remain tombstoned even after
automatic deletion, so restoring an old rule does not silently restore exposure.

Home Assistant forwarding command topics now include the binding selector:
`command/tailnet_forward/<index>/<eight-hex-digit-rule-token>`. Old index-only
commands are rejected; refresh HA discovery or update custom publishers. This
prevents delayed commands from toggling a different survivor after compaction.
The selector detects stale configuration; it is not cryptographic client
authentication and does not replace broker authorization.

Physical clock/NVS/power-loss/NAT qualification is pending; already-admitted
bytes are not recalled. AP-side forwarding is unaffected.

## Example: IoT at a second home, broker at the first

The IoT device stays on its normal WiFi and does not install a VPN client.
Configure the broker endpoint it uses as the ESP's uplink-LAN IP and a local
forwarding port. The broker at the other site must be a reachable Tailnet peer;
Home Assistant then uses that broker normally.

| Rule field | Example |
|---|---|
| Name | Remote MQTT |
| Enabled | OFF while preparing; enable and Save deliberately |
| Protocol | TCP |
| Listen port | 18830 |
| Tailnet destination | 100.64.0.2 (example peer address) |
| Destination port | 1883 |
| Allowed source subnet | 192.168.50.42/32 (example local client) |

The device connects to `ESP-LAN-IP:18830`. The forwarder sends to
`100.64.0.2:1883`. If your service uses TLS, retain its certificate/hostname
requirements; pointing a TLS client at a different IP may require correct
SNI/server-name support. Do not disable verification just to make a template
work. Tailnet transport encryption does not encrypt the ordinary LAN hop.

No static route on the home router is needed **for this selected-port path**.
That does not apply to arbitrary site-to-site routing. AP SSID, DHCP, client
membership and AP-side port mappings are independent.

## Explain status and LAN exposure

In development source 1.14, expand a rule's **Explain status & LAN exposure**.
It shows the saved local/remote path, source restriction, passive diagnosis,
runtime report, historical accepted/rejected counts and next step.

- Disabled: explicitly not enabled; not a network fault.
- Uplink has no IPv4: cannot bind the configured STA path. Not proof the router
  itself is broken.
- Control session not ready: inspect authentication/startup state. Existing
  data sessions may still work; control and data are not the same observation.
- Destination unresolved: check the saved Tailnet address/name. Not proof
  the peer is powered off.
- Mapping not installed: review runtime error/listener conflicts and reload
  after the existing manager refreshes.
- Mapping installed: the local mapping exists; the remote service is **not
  tested**. Try from the permitted client, then check remote service/listener,
  authentication, firewall and applicable tailnet policy if it fails.

Development line: evidence refines these states without hiding a passive
fault (an uplink or control problem always wins):

- Ready to enable: rule disabled, destination test reachable.
- Service replied recently: the policy gate admitted a reply from that
  destination on a flow this gateway sent. Not per LAN client.
- Destination test got no TCP answer: check the peer, its listener and the
  Tailnet ACL for this gateway.
- Only rejected LAN packets seen: traffic reaches the listener but not from the
  allowed source (or the expiry closed it). Compare the client with the CIDR.
- Destination test reachable: try from the allowed client.

There is no background probing and no automatic refresh added by this panel;
the destination test runs only when requested.
Save applies edits; an unsaved draft does not inherit an old “working” label.
A failed read retains fields and reports unavailable; retry Reload before Save.

## Security and protocol boundaries

Use `/32` for a single client where practical. `/0` is an explicitly broad
source policy and is warned about. A source CIDR is not authenticated identity:
another host on the local segment may spoof addresses. Authenticate the service
and isolate untrusted LAN clients. Rule enablement is a real exposure decision.

This is an IPv4 TCP/UDP service mapping to a peer in 100.64.0.0/10, not a
transparent LAN bridge or arbitrary remote subnet destination selector. It
does not relay mDNS/SSDP discovery or automatically fix multiport/callback/
embedded-address protocols. Home Assistant compatibility depends on each
integration. The firmware itself is a third-party Tailscale-compatible client;
read the [policy limitation](../SECURITY.md#tailnet-policy-compatibility-boundary)
before relying on fine-grained tailnet authorization.
