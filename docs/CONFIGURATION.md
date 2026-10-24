# Configuration reference

Every setting below is configured from the device web UI. Changes are
written to NVS; some require a reboot to take effect (the UI flags a
pending reboot when so).

> IP addresses, SSIDs and peer names shown in screenshots throughout the
> docs are generic placeholders.

## Network → Device-wide network

| Field | Meaning |
|---|---|
| **Hostname** | Name advertised on the uplink network (DHCP/mDNS). |
| **DNS mapping TTL override** | `0` = off. Overrides the TTL the device applies to DNS-learned routes, for roaming continuity. |

## Network → Uplink networks (STA)

Up to **5** networks, tried in order. Per network:

| Field | Meaning |
|---|---|
| **SSID** | Upstream 2.4 GHz network to join. |
| **Password** | WPA2/WPA3 PSK. Leave empty to keep the stored one. |
| **Static IP** *(optional)* | `ip` / `mask` / `gw` / `dns`; empty = DHCP. |
| **WPA2-Enterprise (EAP)** *(optional)* | Method, phase-2, identity/username/password, optional CA bundle. |

## Network → Access Point (AP)

| Field | Default | Meaning |
|---|---|---|
| **AP SSID** | — | Network this device broadcasts. |
| **AP password** | — | WPA2 PSK; leave empty to keep current. |
| **Channel** | *auto* | Read-only. The single 2.4 GHz radio is shared with the STA, so the AP automatically follows (and realigns to) the uplink channel — it is not operator-settable. |
| **AP IP / Subnet mask** | `192.168.4.1` / `255.255.255.0` | The AP subnet. Changing it offers to update the advertised Tailscale route. |
| **DNS served to AP clients** | this device | Empty = the on-board forwarder; or push a specific resolver. |
| **On-board DNS forwarder** | on | Resolver + PSRAM response cache for AP clients. |
| **Forwarder upstream** | configured / learned | Upstream resolver the forwarder queries. This fork has no hard-coded public fallback. |
| **Hide SSID** | off | Stop broadcasting the SSID in beacons. |
| **Enable client access point** | on | Off = recovery-only: the AP is up at boot until the uplink connects, then hidden. If the saved WiFi is not found for **60 s** the AP comes back and stays on until the uplink has an address again; shorter drops do not toggle it. |

## Network → DHCP, clients, denylist, port forwarding

- **DHCP reservations** — pin an IP to a MAC (max 16).
- **Connected clients / Active leases** — live tables with per-client signal.
- **Denied MAC addresses** — block specific clients from associating.
- **Port forwarding** — map an external port to an AP-side client.

## Tailscale

| Field | Meaning |
|---|---|
| **Enabled** | Master switch for the tailnet client. |
| **Auth key** | Tailscale auth key (`tskey-…`). Leave empty to keep current. |
| **Hostname** | Node name on the tailnet. |
| **Login server** | Custom control plane (Headscale). Empty = hosted Tailscale. Accepts `host`, `host:port`, `http://host[:port]`, `https://host[:port]` (TLS validates against public CAs only — no self-signed). Requires Headscale ≥ 0.26 (validated on v0.28.0). |
| **Reported client version** | Optional control-plane compatibility override (`IPNVersion`), empty by default. Does not upgrade the implementation or its capabilities. Requires restart. |
| **Advertise the AP subnet** | Compose the configured AP CIDR automatically without changing manual routes. On for fresh installations, opt-in for upgrades from Mattboxx 1.5. Requires restart and Tailscale route approval. |
| **Additional advertised subnet routes** | One CIDR per line, maximum 400 bytes. Combined and deduplicated with the automatic AP, 4via6 and exit-node routes. The UI shows the saved preview; Status shows the boot's active routes. |
| **Source-NAT advertised routes** | Off by default. Masquerades traffic forwarded from the tunnel out to the uplink LAN (or out to the internet when this device is an exit node) to the device's own STA IP — the Tailscale default for subnet routers. **On** = the uplink subnet works the moment you advertise it (upstream hosts reply to this device, which un-NATs back into the tunnel). **Off** = the upstream router needs a static route for the tailnet (`100.64.0.0/10 → this device`) instead. Enabling it offers to add your uplink subnet to the advertised routes. ⚠️ Do **not** advertise *and* accept the same subnet — that loops the inbound route back into the tunnel. |
| **Exit node** | Route AP-client public traffic through this tailnet exit node. Fails closed if unreachable. |
| **Advertise this ESP32 as an exit node** | Opt-in server mode, mutually exclusive with choosing another exit node. Requires restart and Tailscale admin approval. IPv4 Internet egress is masqueraded; IPv6 remains fail-closed. |
| **Max peers** | Upper bound on tracked peers. |
| **Accept peer subnet routes** | Install routes other nodes advertise. |
| **LAN bypass when using an exit node** | RFC1918 destinations stay on the local LAN even with an exit node selected. |

### Tunnel MTU

`Auto (Tailscale 1280)` uses MTU 1280 and TCP MSS 1240 on both direct and
relayed paths to avoid oversized return packets. A fixed MTU can be
forced (576–1500) if a path misbehaves.

### Exit-node DNS (1.9 development / upstream v0.1.31)

Native Tailscale clients using this ESP32 as their exit node discover a separate
DNS PeerAPI at `http://<ESP-tailnet-IP>:41180/dns-query`. It is not the admin UI
and does not use its password challenge. Requests require the local tunnel IP
and a remote IP matching a currently known peer; LAN/AP requests are denied.
Normal tailnet/firewall policy still applies. Only IPv4 and IPv4-mapped socket
addresses are supported by this service.

The DNS server starts only for this boot's enabled exit-node server mode.
Changing the saved switch requires restart; it does not silently change the
running server/NAT policy. If the custom admin port is 41180, DNS uses 41181
and advertises that actual port. New TCP forwarding rules cannot use the
active DNS port. Startup/handler-registration failures are logged locally,
and a failed listener is not advertised. UI, MQTT/HA and ntfy `info` expose
runtime active/running state and the selected port, never resolver credentials.

DNS uses the configured forwarder upstream, otherwise STA's learned resolver:
UDP first with bounded waiting, then TCP for truncation or UDP failure. There
is no automatic public resolver fallback. A missing or unsafe resolver fails
the lookup. The build reserves 31 sockets; saved feature settings are retained.
See [the integration record](upstream/UPSTREAM-0.1.31.md) for testing limitations.

## Firewall

Four chains, **first match wins**; an empty chain allows by default.

| Chain | Direction |
|---|---|
| `TO_ESP` | Internet → ESP |
| `FROM_ESP` | ESP → Internet |
| `TO_AP` | Clients → ESP |
| `FROM_AP` | ESP → Clients |

Per rule: **source** / **destination** (`any` or CIDR), **protocol**
(Any / ICMP / TCP / UDP), **source/dest port** (`0` = any, TCP/UDP only),
**action** (Allow / Deny).

## System

| Field | Meaning |
|---|---|
| **Device name** | Friendly name shown in the UI header and `/api`. |
| **Timezone** | Device TZ; a real change flags a pending reboot. |
| **Outbound telemetry** | Not compiled in. Logs and crash summaries remain local; MQTT publishes only when explicitly configured and enabled. |
| **SD card logging** | Enable + per-sink (console / SD) log level; the on-device flight recorder. |
| **Firmware update (OTA)** | Local binary upload plus Check now / Install latest update from this fork. Optional daily checks, automatic install, beta channel and local-time install window; all switches default OFF. Policy/actions require a password-backed session. See [UPDATES.md](UPDATES.md). |
| **Encrypted backup / restore** | Export/import the full config, encrypted with a passphrase. |
| **Danger zone** | Reboot, factory reset, reset Tailscale identity. |
