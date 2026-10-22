<div align="center">

<img src="assets/logo/homelab-gateway.svg" alt="ESP32 Homelab Gateway — Mattboxx Edition" width="100%">

# ESP32 Homelab Gateway

**Mattboxx Edition · Selective LAN → Tailnet service gateway for Tailscale and Headscale**

### Selective Tailnet Service Gateway · Remote recovery & diagnostics · Subnet router · Exit node · MQTT/Home Assistant

**Let an ordinary device on your existing LAN use one specific service on your
Tailscale/Headscale tailnet — without installing Tailscale on it, without
joining it to the ESP32 access point and without changing your main router or
default gateway.**

Based on the original
[Csontikka/esp32-tailscale-subnet-router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and its [microlink](https://github.com/Csontikka/microlink) Tailscale stack.
This Mattboxx edition adds a selective LAN → Tailnet service gateway, remote
recovery and diagnostics, automation, privacy hardening and a ready-to-flash
release. Tailscale, WireGuard, DERP and MagicDNS are not Mattboxx inventions.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: ESP32-S3](https://img.shields.io/badge/platform-ESP32--S3-7c3aed.svg)](#hardware)
[![ESP-IDF](https://img.shields.io/badge/ESP--IDF-5.5.3-e7352c.svg)](https://docs.espressif.com/projects/esp-idf/)
[![CodeQL](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/actions/workflows/codeql.yml/badge.svg)](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/actions/workflows/codeql.yml)
[![Latest stable release](https://img.shields.io/github/v/release/Mattboxx/esp32-tailscale-gateway-NAS-recovery?label=stable)](../../releases/latest)
[![Support the Mattboxx mod on Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20the%20Mattboxx%20mod-374151?logo=kofi&logoColor=ffffff)](https://ko-fi.com/mattboxx)
[![Support upstream on GitHub](https://img.shields.io/badge/Upstream-GitHub%20Sponsors-ea4aaa.svg?style=plastic&logo=githubsponsors)](https://github.com/sponsors/Csontikka)
[![Support upstream on Buy Me a Coffee](https://img.shields.io/badge/Upstream-Buy%20Me%20a%20Coffee-yellow.svg?style=plastic)](https://buymeacoffee.com/csontikka)

</div>

---

## The problem it solves

You have a device on your home or office LAN — an IoT controller, a printer
dashboard, a backup client, an MQTT sensor hub, an old PC — that needs to reach
**one** service at another site on your tailnet: a broker, a NAS share's web UI,
an SSH host. You cannot or do not want to install Tailscale on it, you do not
want to move it onto a separate WiFi network, and you do not want to replace
the router or advertise whole subnets to everyone.

Put an ESP32-S3 on the same LAN. It joins your tailnet once, and you publish a
single rule: *this LAN device may use this Tailnet service on this port.*

```
LAN client 192.168.1.20 ──TCP──▶ ESP32 192.168.1.50:18830 ══WireGuard══▶ broker.tailnet.ts.net:1883
           (no Tailscale)              (rule: source 192.168.1.20/32)       (Tailnet peer, its ACL applies)
```

## Try it in a few minutes

1. Flash the [stable release](../../releases/latest) and join the ESP32 to your
   WiFi and tailnet (Web UI → Tailscale; Headscale: set the login server).
2. Give the ESP32 a fixed LAN address (DHCP reservation on your router).
3. Web UI → **Network → LAN → Tailnet**: add a rule — protocol TCP, listen port
   `18830`, Tailnet destination `broker.your-tailnet.ts.net` (or `100.x.y.z`),
   destination port `1883`, allowed source `192.168.1.20/32`. Rules start
   disabled. Save.
4. Make sure the destination peer's tailnet ACL allows the ESP32's identity.
5. Enable the rule and point the LAN client at `192.168.1.50:18830`. The rule
   shows installed state and accepted/rejected packet counters.

In the current development line (not yet in a stable release) the same page
also offers a **Test destination** button — the ESP32 performs one bounded TCP
handshake with the Tailnet service, before you enable any LAN exposure — plus
a guided setup, optional expiry for temporary access and service-rule
export/import with preview. See the [Service Gateway guide](docs/SERVICE-GATEWAY.md).

## How it compares

| Approach | What LAN devices need | What it exposes | Best for |
|---|---|---|---|
| **Selective Service Gateway** (this firmware, LAN → Tailnet) | Nothing: they connect to `ESP-IP:port` | One TCP/UDP service per rule, only to the allowed source CIDR | A few LAN devices that must reach specific remote services |
| Tailscale on each device | A Tailscale client | That device as a full tailnet node | Devices that can run a client |
| Subnet router (also in this firmware) | Nothing, but reverse direction | Whole local subnets *to* the tailnet (after admin approval) | Reaching your LAN from tailnet clients |
| AP gateway (also in this firmware) | Join the ESP32 WiFi network | AP-side devices routed via the ESP32 | Isolated IoT devices on their own WiFi |
| Router/gateway replacement | Change of default gateway | Depends on the router | Whole-site routing |

## Limits and security model, plainly

- **Not unlimited routing.** IPv4 TCP/UDP only, up to 8 rules, one Tailnet
  IPv4 destination (`100.64.0.0/10`, literal or MagicDNS name) per rule. LAN
  clients connect to the ESP32's address and listen port; it is a port
  forwarder, not transparent routing.
- **ESP32 performance.** WiFi plus software WireGuard on a microcontroller:
  suited to control, telemetry, dashboards and SSH, not bulk transfers or
  video. Throughput has not been measured for the current candidate.
- **Source filter is not identity.** A rule admits packets from its source
  CIDR; prefer one device (`/32`). Anyone who can use that address can use the
  service. Remote peers see the ESP32's tailnet identity, and their own ACLs
  still decide what it may reach. Protect the Web UI with a password.
- **Verification is evidence, not a guarantee.** "Installed" means a local
  mapping exists; a destination test proves one TCP handshake from the ESP32
  only; UDP cannot be verified without an application reply.
- Community microlink-based firmware, not an official Tailscale client; no
  claim of full official-client policy parity.

## Three pillars

1. **Selective Tailnet Service Gateway** — LAN → Tailnet rules with source
   restriction, per-rule state and counters, guided setup, destination tests
   and temporary access (development line), safe import/export.
2. **Remote Recovery & Diagnostics** — an independently powered tailnet node:
   reach its Web UI when your NAS (and its Tailscale) is off, send Wake-on-LAN,
   run bounded Smart Recovery and layered health checks with honest evidence.
   [NAS recovery checklist](docs/NAS-RECOVERY.md).
3. **Automation, Monitoring & Management** — MQTT, Home Assistant Discovery,
   ntfy, SNMP, profiles, subnet router, exit node and AP gateway. All optional:
   direct Web UI access and manual WoL need none of them.

WoL needs compatible hardware, configuration and standby power; it cannot
hard-reset a frozen NAS, recover files or provide KVM/BIOS access. Power the
ESP independently of the NAS and keep the router/Internet available. This is
not fully out-of-band management.

**[Download stable firmware and the guided Windows flashing ZIP](../../releases/latest)** ·
**[Supported hardware](#hardware)** ·
**[What's new in stable 1.13](docs/RELEASE-1.13.md)** ·
**[See every change from upstream](CUSTOM_BRANCH.md)** ·
**[Read the security model](SECURITY.md)**

## One board, three network gateways

| Traffic path | What it unlocks |
|---|---|
| **Uplink LAN → Tailnet service** | Let an ordinary LAN device reach a selected TCP/UDP service on a Tailnet peer through the ESP32 — no Tailscale client and no ESP access-point connection required. |
| **Tailnet → LAN/AP subnet** | Reach sensors, switches and legacy devices remotely through the ESP32 subnet router. |
| **AP-side device → Tailnet/Internet** | Give devices with no VPN client their own simple WiFi gateway, optionally through a Tailscale exit node. |

The LAN → Tailnet forwarder is completely independent from the AP-side port
forwarding.

## Why the Mattboxx edition is different

The networking protocol stack is upstream work; this edition's value is a
standalone service gateway and operational UI around it, not a new VPN protocol.
See the [code-backed comparison and positioning](docs/PRODUCT-AUDIT.md),
[architecture](docs/ARCHITECTURE.md) and
[permanent development roadmap](docs/DEVELOPMENT-ROADMAP.md).

**Development source: 0.1.38-Mattboxx-1.14-dev.5.** Adds passive per-rule
exposure/diagnostic guidance and transactional WoL address-book fixes.
New UI rules start disabled; an installed mapping is not called a verified
service. This source is not a new published binary. Stable downloads below
remain 1.13. [Service gateway guide](docs/SERVICE-GATEWAY.md).

Local development also includes bounded Smart Recovery, temporary service-rule
leases and opt-in layered connectivity checks with MQTT/HA/ntfy evidence.
See [health monitoring](docs/NETWORK-HEALTH.md) for the limits; neither a control
connection nor one successful TCP check proves that the entire tunnel is healthy.

The local 1.14 candidate also addresses a confirmed missing Tailnet service-
authorization gate in the pinned MicroLink parent. It is **not hardware-
qualified or fully policy-compatible**: conservative protocol/fragment limits
and two-real-client tests remain release blockers. Read the
[authorization findings and validation matrix](docs/TAILNET-AUTHORIZATION.md)
before relying on fine-grained Tailnet permissions; peer visibility is not
port authorization. The public 1.13 binary does not contain this local fix.
Dev.3 additionally fixes at-capacity peer replacement, stale queued peer work
and map/keepalive precedence. Development is tracked in the
[goals](GOALS.md), [implementation/validation matrix](docs/FEATURE-IMPLEMENTATION-MATRIX.md)
and [current checkpoint](docs/NEXT-STEPS-FOR-AGENT.md). Planned capabilities
in those documents are not claims about the stable download. Dev.4 integrates
experimental MAC-bound recovery/device checks, opt-in monitoring/resource
admission, LAN→Tailnet exposure leases, capability/diagnostic APIs and their
UI/MQTT/HA/ntfy integration. Related ICMP and bounded IPv6 header handling are
expanded. These are **development source, not fully validated features**;
non-atomic tunnel fragments, full policy compatibility, remaining roadmap
features and consolidated/hardware qualification are still outstanding.
See the [experimental Smart Recovery guide](docs/SMART-RECOVERY.md).

**Latest stable: 0.1.38-Mattboxx-1.13.** Integrates all published
upstream v0.1.34–v0.1.38 changes: verified relay TLS, WireGuard protocol/nonce
fixes, correct sticky relay selection/reporting, faster silent-peer recovery,
bounded control stalls and the v0.1.38 TCPIP teardown/copy-free TX fixes.
Keeps every custom feature and privacy removal. See the
[complete integration record](docs/UPSTREAM-0.1.38.md) and
[stable release notes](docs/RELEASE-1.13.md).
The stable tag and embedded firmware version match, so the optional GitHub
updater can offer 1.13 without beta enrollment. Existing settings are retained
when updating with the application image. Update checking and installation
remain opt-in; nothing is silently enabled.

Also retains upstream logging/throughput, legacy manual exit-node DNS/NAT,
startup/shutdown fixes and optional live WiFi power-save control (OFF remains
the low-latency default), MQTT/HA and ntfy visibility, and a user-initiated
Ko-fi payment window with no background embed. All custom features and
original credits remain. Previous releases stay available for manual rollback.

Retained reliability fixes include ntfy command reboot loops, startup stuck
on **Registering**, AP-worker allocation failures, SNMP/Tailnet recursion,
stale direct-endpoint replies, login eviction with timeout disabled and false
Automation disabled states. The build uses pinned ESP-IDF 5.5.3 and 31 sockets.
No external log uploads or forced update polling are restored.

Updates stay opt-in; **Install latest update** also works as a one-off action
with periodic checks OFF. Stable does not require beta enrollment. See
[update policy](docs/UPDATES.md), [ntfy test coverage](docs/NTFY-TRANSPORT.md),
[release history](CHANGELOG.md) and [previous stable validation](docs/RELEASE-1.11.md).
Stable is a release channel, not a security certification.

| Area | Added or improved in this edition |
|---|---|
| **LAN → Tailnet forwarding** | Multiple TCP/UDP rules to a Tailscale IPv4 or MagicDNS destination, mandatory allowed-source subnet, live resolution/install state and conflict protection. Works even with the ESP client WiFi/AP disabled. |
| **WiFi gateway policy** | Keep the client AP always available, or automatically place it in standby while the uplink works and restore it after an outage. The dashboard makes disabled state unmistakable. |
| **Wake-on-LAN** | Save up to 12 named devices and wake them from the web UI, MQTT, Home Assistant or replay-protected ntfy commands. |
| **MQTT + Home Assistant** | Retained availability and device state, Last Will, broker watchdog, inbound commands and automatic discovery for AP, routes, SNAT, LAN bypass, Tailscale, 4via6, reconnect, restart, WOL and every LAN → Tailnet rule. |
| **ntfy remote operations** | Optional connectivity outage alerts, `info` replies and WOL commands with durable polling and replay protection. Local logs are not uploaded; private info details stay hidden unless explicitly enabled. |
| **Tailscale 4via6** | Optional bidirectional TCP/UDP/ICMP translation for overlapping IPv4 LANs, with calculated advertised prefix, flow counters and Home Assistant controls. |
| **Exit-node server** | Advertise the ESP32 itself as a Tailscale exit node, with automatic IPv4 egress masquerading, admin-approval guidance, fail-closed IPv6 behavior, a separate DNS PeerAPI and Home Assistant/ntfy visibility. Server mode cannot conflict with selecting another exit node. |
| **Web administration** | Responsive dark UI, graphical feature switches, clear disabled cards, configurable web port, optional password gate and session timeout, local OTA and encrypted backup/restore. Opt-in fork-only GitHub updates, stable/beta channels and one-click latest install. |
| **SNMP monitoring** | Upstream read-only v1/v2c agent, hardened and integrated with System/MQTT/HA/ntfy in this edition; disabled by default. This is an improved shared capability, not a newly invented monitoring protocol. |
| **Fast, safer login** | Salted 60,000-round PBKDF2-HMAC-SHA256 verifier plus a one-time browser challenge; no plaintext password for modern records and no multi-second ESP-side unlock delay. |
| **Reliability fixes** | Repairs WiFi scan/save and HTTP 431 failures, ntfy reboot loops and missed commands, false post-login offline state, forwarding-table startup counts and web/Tailscale socket starvation. |
| **Privacy cleanup** | Removes anonymous telemetry, external crash/log uploads, forced GitHub polling, Cloudflare speed tests and the hard-coded public DNS fallback. GitHub checks/downloads run only as explicit opt-in or user-triggered actions. The Ko-fi support link makes no request until clicked. |
| **Easy installation** | Releases include one factory image, one update image and a Windows ZIP with Espressif `esptool` plus guided clean-install/update batch files. No toolchain required. |

The complete technical comparison is in [`CUSTOM_BRANCH.md`](CUSTOM_BRANCH.md).
This remains community firmware rather than a formally audited network
appliance; read [Known limitations](#known-limitations) before deployment.

| Product area | Operational purpose |
|---|---|
| Network Gateway | Selective LAN → Tailnet services, subnet routing, optional AP gateway and advanced routing. |
| Recovery & Remote Management | Local saved WoL targets and direct management independent of managed servers. Verified boot/service recovery is still planned. |
| Automation & Integrations | Optional MQTT/Home Assistant and ntfy; never prerequisites for the core local tools. |
| Monitoring & Diagnostics | Evidence-based state, local logs and optional SNMP. Missing observations stay unknown, not “healthy”. |

## What it is

This firmware turns one ESP32-S3 board into three things at once:

1. **A WiFi NAT router.** It joins your existing 2.4 GHz network as a
   client (STA) and re-broadcasts its own access point (AP). The IoT
   devices on that AP reach the internet through the upstream WiFi, with
   NAPT, DHCP, and an on-board DNS forwarder.
2. **A Tailscale subnet router.** It runs a userspace WireGuard +
   Tailscale (`ts2021`) stack, so any peer on your tailnet can reach the
   devices behind its AP — and the AP-side devices can use the ESP as a
   Tailscale **exit node** gateway. No client software on the IoT
   devices, no cloud account on the LAN.
3. **A selective Tailnet service gateway.** Ordinary devices on the ESP32's
   uplink LAN can connect to its LAN address and reach individual services on
   Tailnet peers. Per-rule source CIDRs expose only the ports you choose,
   without installing Tailscale on the local client.

Everything — WiFi credentials, the tailnet auth key, advertised routes,
firewall rules, diagnostics — is configured from a phone or laptop
browser. There is no app and no serial console required after the first
flash.

<div align="center">
<img src="docs/images/status_v3.png" alt="Web UI — Status dashboard" width="88%">
<br><em>The Status dashboard: uplink, access point, Tailscale node and peers at a glance.</em>
</div>

## Why

Most "put a sensor on Tailscale" setups need either a Raspberry Pi
acting as a subnet router or per-device Tailscale clients. This project
collapses that into a small ESP32-S3 board you can leave plugged into a USB
charger: it bridges a whole IoT subnet onto your tailnet *and* gives
those devices internet through an exit node, while staying small enough
to ignore.

## Where it fits

Typical setups people use it for:

- **Weekend house / cabin.** A Tasmota/Shelly AC, water heater or
  freeze-guard on the cabin's existing WiFi — your home Home Assistant
  sees and controls it, with no public IP, port-forward or VPN server on
  the cabin's router.
- **Parents' / grandparents' place.** A couple of sensors (temperature,
  door/window, water-leak) pulled into your own HA so you can watch them
  and get alerted, without ever touching their router.
- **CGNAT / mobile-broadband locations.** Sites with no public IP (4G
  routers, shared building internet) that you could never reach before —
  the tailnet bridges the CGNAT, so HA sees everything anyway.
- **Garage / workshop / shed.** There's WiFi, but you don't want to set up
  a VLAN or VPN; the garage door, irrigation or a frost guard just show
  up in HA.
- **Rentals / networks you don't own.** Not your router, no right to
  port-forward — the ESP puts your gadgets on the tailnet as a node, done.

The common thread: there's WiFi on site, but you can't (or don't want to)
touch the router. That's exactly where this fits.

## What it's for — and what it isn't

This is a **micro-controller** doing userspace encryption and NAT on a
single shared 2.4 GHz radio. Its job is **reach, not throughput** — size
your expectations accordingly.

**✅ What it's for**

- IoT / home-automation gear: **sensors, smart switches, plugs,
  thermostats**, energy/environmental monitors, ESPHome / Zigbee / MQTT
  bridges — anything small and low-bandwidth.
- Low-rate control and status traffic: bursty, tiny payloads that are perfectly
  happy with around a megabit.
- Reaching a device stuck behind NAT/CGNAT so you (or Home Assistant) can
  poll it, flip a relay, or SSH in from anywhere on your tailnet.

**🚫 What it's not for**

- Being the everyday internet uplink for your **phone or laptop**.
- **Streaming, video calls, or watching a camera feed in high resolution.**
- Large downloads, backups, OTA images for other devices — anything
  bandwidth-heavy.
- A general-purpose VPN gateway for fast clients.

Real-world throughput through the tunnel runs **roughly 0.3–1.4 Mbit/s**,
depending on the path — plain STA routing is at the top of that range, a
**direct** exit node in the middle, and a **DERP-relayed** exit node at
the bottom. Plenty for switches and sensors, not for media. If you need
real bandwidth, put a Raspberry Pi (or similar) on that job instead. *(Configuring the device from a
phone or laptop browser is of course fine — that's just the admin UI, not
traffic you route through it.)*

## Features

- **Dual role** — simultaneous WiFi STA (uplink) + AP (NAT router) +
  Tailscale subnet router.
- **Expose the upstream LAN too** — beyond its own AP subnet, an optional
  Source-NAT (à la Tailscale `--snat-subnet-routes`) lets tailnet peers reach
  the network the device is *connected to*, with no static route needed on the
  upstream router.
- **Web UI for everything** — optional password gate and session timeout, WiFi join,
  tailnet enrolment, routes, firewall, diagnostics. Dark, responsive,
  single-page; served straight off the device.
- **Tailscale, the real protocol** — DISCO peer discovery, direct paths
  *and* DERP relay fallback, NAT traversal, MagicDNS-aware, exit-node
  client, exit-node server and gateway. Powered by [microlink](https://github.com/Csontikka/microlink).
- **Exit-node advertising** — optionally offer the ESP32 uplink as an IPv4
  Internet exit for authorized tailnet peers. The firmware announces the
  standard default routes, automatically applies egress NAT, and prevents
  simultaneous exit-node client/server modes. Approval in the Tailscale admin
  console is still required. IPv6 is fail-closed on the current IPv4 data plane.
- **Exit-node aware routing** — AP clients' internet traffic can be
  forced through a chosen Tailscale exit node; when the exit node is
  unreachable the firmware **fails closed** (traffic stops) rather than
  silently leaking to the local uplink.
- **Stateful-ish ACL firewall** — four hook points (Internet↔ESP,
  Clients↔ESP) with first-match-wins rules by protocol / CIDR / port /
  action, plus per-rule hit counters.
- **DNS forwarder with cache** — on-board resolver for AP clients with a
  PSRAM-backed response cache and configurable upstream.
- **Operations toolbox** — on-device ping / traceroute / route-explain,
  live WiFi scan, and a microSD "flight recorder" for catching
  control-plane stalls.
- **DHCP niceties** — reservations, live lease table, per-client signal,
  and a MAC denylist.
- **Selectable client WiFi** — use the ESP access point as a simple gateway for
  devices that need Internet and tailnet access; keep it always available or
  place it in standby while the uplink is connected. It returns automatically
  after an uplink failure so administration remains possible.
- **Wake-on-LAN address book** — save up to 12 devices and send their UDP
  magic packets from the web UI, MQTT, or Home Assistant.
- **MQTT + Home Assistant** — retained health/network/Tailscale state,
  inbound AP/routing/Tailscale/reconnect/restart/WOL commands, Last Will
  availability, and automatic Home Assistant discovery (including one Wake
  button per saved device).
- **Optional Tailscale 4via6** — maps a configurable IPv4 LAN and site ID
  into Tailscale's 4via6 prefix, advertises it alongside normal IPv4 routes,
  and translates TCP, UDP and ICMP traffic in both directions.
- **Optional ntfy integration** — alerts when the internet uplink works but
  Tailscale remains down without uploading local logs, and accepts
  replay-protected `info` and WOL commands. It is disabled by default.
- **Robust by design** — encrypted config backup/restore, local manual
  OTA upload and optional fork-only GitHub updates, per-sink (console + SD) log levels, auto AP-channel realign on
  STA roam, and pre-crash log capture.
- **Private by design** — no usage reports or crash uploads. Periodic release
  checks/downloads are OFF unless explicitly enabled; manual GitHub actions
  authorize one check/download. Other outbound application traffic goes to
  Tailscale and the MQTT/ntfy endpoints configured by the operator.

## Hardware

| | |
|---|---|
| **Target** | ESP32-S3 with PSRAM (8 MB octal, 80 MHz) |
| **Reference board** | ESP32-S3-DevKitC-1 **N16R8** (16 MB flash / 8 MB PSRAM) |
| **Radio** | Single 2.4 GHz — STA and AP share one radio (see [limitations](#known-limitations)) |
| **Storage (optional)** | microSD for the log flight-recorder |
| **Power** | Reliable USB supply, independently powered from managed servers; no board power-consumption measurement is claimed here. |

**The published binary targets ESP32-S3 N16R8 with 8 MB octal PSRAM.**
Other ESP32 families and Ethernet-specific boards are not drop-in targets.
Ethernet uplink is **not implemented in this application**: SNMP's generic
ETH interface counters are not an Ethernet driver. Adding it needs hardware,
driver initialization and routing/forwarding integration. No Ethernet-capable
release is provided here. Community ports are welcome, but
do not flash this image onto an unrelated board.

### Upstream board compatibility reports (not current fork certification)

The following reports come from upstream, not a fresh test of this custom
release on every listed board (see [upstream #9](https://github.com/Csontikka/esp32-tailscale-subnet-router/issues/9) and
[upstream #10](https://github.com/Csontikka/esp32-tailscale-subnet-router/pull/10)
— thanks @bobcroft and @markvovo):

| Board | Result |
|---|---|
| **ESP32-S3-DevKitC-1 N16R8** (genuine) | ✅ Reference — developed and tested on this |
| **Freenove ESP32-S3-WROOM N8R8** | ✅ Community-confirmed: AP, web UI, full setup |
| **Seeed XIAO ESP32-S3 N8R8** | ✅ Community-confirmed: AP join, plus the WireGuard/DERP data plane (both a direct peer-to-peer session and a relayed one). Web UI wasn't separately re-verified. See the first-flash note below |
| **YD-ESP32-S3 ("YD32") clones** | ❌ SoftAP never visible on air — fails even with a minimal ESP-IDF AP example, i.e. a board-level RF problem, not this firmware |

> **First flash on a XIAO:** one tester's board wouldn't accept the default AP
> password until they ran a full `esptool erase_flash` followed by a
> `factory_reset --confirm`, allowing a little extra time before retrying the
> join. No log survives from the failed first boot, so this is a known rough
> edge rather than a diagnosed bug. If you hit it, erase the flash and retry.
> The `firmware-factory.bin` asset on the
> [latest release](../../releases/latest) is a full-flash
> image and rewrites the NVS region too, so it sidesteps this as well.

## Quick start

### 1. Flash it — no build tools required

Download the latest
[Windows flashing ZIP from the latest stable release](../../releases/latest),
connect the ESP32-S3 over USB and run one of the included guided batch files:

- `UPDATE_KEEP_SETTINGS.bat` updates an existing installation without erasing its configuration;
- `CLEAN_INSTALL_ERASE_ALL.bat` performs a fresh installation and removes every old setting.

The release also provides `firmware-factory.bin` for other flashing tools and
`firmware.bin` for the local web updater.

### Build from source instead

```bash
git clone --recurse-submodules https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery
cd esp32-tailscale-gateway-NAS-recovery

# PlatformIO (recommended)
pio run -e esp32-s3 -t upload

# …or ESP-IDF (>= 5.5.3)
idf.py set-target esp32s3
idf.py build flash monitor
```

> The web assets are embedded into the firmware at build time from
> `main/index.html`, so a single flash carries the whole UI.

### 2. First-time setup

On first boot the device brings up its own access point:

- SSID: **`ESP32-TSR-Setup`** (builds before v0.1.18: `myssid`),
  password: **`mypassword`**
- Connect to it and open **http://192.168.4.1** — set an admin password
  there, then rename the AP to your liking.

<div align="center">
<img src="docs/images/login.png" alt="First-run admin password" width="46%">
</div>

### 3. Join your WiFi

On **Network → Access Point / Uplink networks**, point the device at your
existing 2.4 GHz network and (optionally) rename the AP it broadcasts.

<div align="center">
<img src="docs/images/network-ap_v2.png" alt="Access Point configuration" width="80%">
</div>

### 4. Enrol on your tailnet

This is the one step with a couple of non-obvious Tailscale details — do
them once and the device stays on your tailnet for good.

#### 4a · Create a Tailscale auth key

Log in to the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
→ **Settings → Keys** and click **Generate auth key…**.

<div align="center">
<img src="docs/images/tailscale-keys-page.png" alt="Tailscale admin — Keys page" width="80%">
</div>

Fill in the dialog:

<div align="center">
<img src="docs/images/tailscale-auth-key-create.png" alt="Generate auth key dialog" width="70%">
</div>

| Option | Value | Why |
|---|---|---|
| **Description** | `esp32-router` | so you can find it later |
| **Reusable** | ✅ On | re-flash without regenerating a key |
| **Ephemeral** | ❌ **Off** | ephemeral nodes get garbage-collected when offline — bad for a device that reboots |
| **Pre-approved** | ✅ On *(if your tailnet uses device approval)* | lets the device join without a manual click |
| **Tags** | `tag:esp32` *(optional)* | handy for ACL targeting |
| **Expiration** | 90 days *(max)* | Tailscale caps this — you make the node **permanent** in 4c below |

Copy the key (it starts with `tskey-auth-…`).

#### 4b · Paste it into the device

On the device's **Tailscale** tab, paste the auth key, set a **hostname**,
and list the **subnet(s) to advertise** (your AP subnet is offered
automatically). Pick an **exit node** here too if you want AP clients to
egress through it. Save — the device registers with your tailnet on its
next connect.

<div align="center">
<img src="docs/images/tailscale_v2.png" alt="Tailscale configuration and peers" width="88%">
</div>

> **Approve the route.** A newly advertised subnet shows up in the Tailscale
> admin (Machines → your device → **Edit route settings**) and must be
> **approved** before peers can use it. And if you later change the AP subnet,
> re-approve the new route there — the old approval stays but no longer matches,
> so the subnet silently becomes unreachable until you do.

> **Reaching the *uplink* LAN (not just the AP subnet).** To expose the network
> the device is connected to (its STA/uplink side), advertise that subnet too and
> turn on **Source-NAT advertised routes**. That masquerades tunnel→LAN traffic to
> the device's own uplink IP (Tailscale's `--snat-subnet-routes` default), so
> upstream hosts can reply without a route back to the tailnet. Without it, the
> upstream router would need a static route (`100.64.0.0/10 → this device`).

> **🔑 Auth key vs. node key — read this once**
>
> - The **auth key** (`tskey-auth-…`) is a *one-time ticket*: the device uses
>   it only on first registration. After that it has its own private **node
>   key** (stored in NVS) and no longer needs the auth key — so it's fine if
>   the auth key later expires.
> - The **node key** is the device's long-term identity, and Tailscale expires
>   it after ~180 days by default. When it expires the device drops off the
>   tailnet — exactly what you *don't* want on an unattended sensor.
>
> So once the device shows up in your tailnet, **disable its node-key expiry**
> (next step). Skip it and everything looks fine for months, then the device
> silently falls off and you won't know why. Do it for every device you flash.

#### 4c · Disable node-key expiry (do this — always)

1. Open the [Tailscale **Machines** page](https://login.tailscale.com/admin/machines).
2. Find the new `esp32-router` entry.
3. Click the `⋯` menu → **Disable key expiry**.

<div align="center">
<img src="docs/images/tailscale-disable-key-expiry.png" alt="Tailscale admin — Disable key expiry" width="80%">
</div>

4. **Reboot the device** (Reboot on the **System** tab, or power-cycle). The
   expiry status is only re-fetched on a fresh control-plane login, so a plain
   reconnect isn't enough.

That's it — remote tailnet peers can now reach the IoT devices on the AP
subnet, and those devices can use the tailnet (and any exit node you picked).

## Web UI tour

The single-page UI has seven sections:

| Section | What's there |
|---|---|
| **Status** | Uplink, AP, Tailscale node + peer list, memory, uptime |
| **Network** | Uplink networks, AP (SSID/IP/DNS), DHCP, MAC denylist, AP-side forwarding, and separate LAN → Tailnet service forwarding |
| **Tailscale** | Auth key, hostname, advertised routes, exit node, MTU, peer table |
| **Firewall** | The four ACL chains, rule editor, hit counters |
| **Diagnostics** | Route-explain, ping, traceroute, WiFi scan, live + SD logs |
| **Automation** | Wake-on-LAN address book, MQTT status/commands, broker watchdog, Home Assistant discovery, optional ntfy alerts and commands |
| **System** | Device name, web password gate + idle timeout, manual firmware upload, SD-card logging, backup, danger zone, privacy status |

### Firewall / ACL

Four chains, evaluated first-match-wins; an empty chain allows by
default. Rules match on protocol, source/destination CIDR, ports, and
action, with live hit counters.

<div align="center">
<img src="docs/images/firewall_v2.png" alt="Firewall — four ACL chains with example rules" width="88%">
</div>

| Chain | Direction |
|---|---|
| `TO_ESP` | Internet → ESP |
| `FROM_ESP` | ESP → Internet |
| `TO_AP` | Clients → ESP |
| `FROM_AP` | ESP → Clients |

### Diagnostics

Route-explain answers "where would a packet to *X* actually go —
uplink, WireGuard, or DERP?", which is the fastest way to reason about
exit-node and subnet routing.

<div align="center">
<img src="docs/images/tools-route.png" alt="Route explain" width="80%">
<br>
<img src="docs/images/tools-ping.png" alt="On-device ping" width="80%">
</div>

## How it works

```
             Internet                   Tailnet peers/services
                │                               │
      ordinary uplink-LAN client ──┐            │ WireGuard / DERP
                                   ▼            ▼
                            ┌────────────────────────┐
                            │       ESP32-S3         │
                            │ NAPT · DHCP · DNS · ACL│
                            │ LAN→Tailnet forwarding │
                            └───────────┬────────────┘
                                  AP   │  optional IoT gateway
                              ┌────────┼──────────┐
                            sensor   switch   thermostat
```

> The AP is for **IoT gear** — sensors, switches, low-bandwidth control —
> not for routing your phone's or laptop's everyday internet. See
> [What it's for](#what-its-for--and-what-it-isnt).

- **Data plane vs control plane.** WireGuard moves packets; Tailscale's
  DISCO/`ts2021` control plane decides *how* (direct UDP vs DERP relay).
  The firmware watches the WireGuard data plane and re-handshakes over
  DERP when a direct path dies, so an exit-node session survives a
  direct↔DERP transition without dropping.
- **Exit-node routing.** A route hook forces AP-client public traffic
  into the WireGuard tunnel when an exit node is set; CGNAT (`100.64/10`)
  always goes to the tunnel. If the exit node is down, traffic stops —
  it is **not** silently rerouted to the local uplink.
- **microlink.** The Tailscale-compatible stack lives in its own repo,
  [Csontikka/microlink](https://github.com/Csontikka/microlink) — itself
  based on the original [CamM2325/microlink](https://github.com/CamM2325/microlink) —
  attached here as a git submodule and pinned to the integration commit.
  Its `docs/ARCHITECTURE.md` and `docs/TAILSCALE_REFERENCE.md` go deeper.

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for a field-by-field
configuration reference.

## Tailscale & Headscale

The device authenticates with a standard **Tailscale** auth key and has
been validated against the hosted Tailscale control plane.

**Headscale is supported** (validated against Headscale v0.28.0; requires
Headscale ≥ 0.26): set **Login server** to your server and authenticate
with a Headscale pre-auth key. Accepted forms:

- `host` or `host:port` — plain TCP, port defaults to 80
- `http://host[:port]` — e.g. `http://192.168.1.42:8080`
- `https://host[:port]` — TLS, port defaults to 443. The certificate is
  validated against the ESP-IDF public-CA bundle (Let's Encrypt works);
  **self-signed / private-CA certificates are not supported**.

The device fetches the server's Noise public key from `/key?v=88` and
reads the initial netmap from the streaming long-poll, matching what
current Headscale versions require.

`tailnet lock` is not supported (the device cannot sign its own node
key); disable it for the tailnet or pre-authorize the node.

## Known limitations

- **Single radio.** STA and AP share one 2.4 GHz radio and channel. If
  the upstream AP is on a different channel after a roam, throughput
  collapses until the device realigns (it auto-reboots to do so).
- **Throughput.** This is an MCU doing userspace crypto + NAT; expect
  roughly **0.3–1.4 Mbit/s** through the tunnel (plain STA highest, direct
  exit node mid, DERP-relayed exit node lowest), not gigabit. Plenty for
  IoT and remote-admin traffic.
- **Exit node fails closed.** By design — when a selected exit node is
  unreachable, AP-client internet traffic stops rather than leaking to
  the local uplink. Clear the exit node to restore direct internet.
- **Exit-node server egress is IPv4-only.** The device advertises both
  standard default routes so a client cannot leak IPv6 around the chosen exit,
  but the current microlink data plane only forwards IPv4 Internet traffic.
  IPv6 through this ESP32 therefore fails closed instead of bypassing it.
- **Tailnet lock unsupported.** Headscale over HTTPS needs a public-CA
  certificate (self-signed is rejected).
- **Local web UI uses HTTP.** Tailscale still encrypts tailnet transport, but
  administer the device only from a trusted LAN/AP or through Tailscale. A
  hostile client on the same local network can otherwise observe HTTP traffic.
  Browser hardening headers reduce injection/clickjacking exposure but cannot
  provide transport encryption.
- **Physical extraction is not prevented.** The portable factory image leaves
  ESP32-S3 Secure Boot, flash encryption and NVS encryption disabled. Someone
  with physical access can read stored credentials or replace the firmware.
- **Remote automation is as trusted as its transport.** Use MQTT/ntfy TLS,
  private topics and broker/server ACLs, especially when commands are enabled.
  The dashboard warns on plaintext transports, and ntfy `info` hides private
  network details unless they are explicitly enabled.
- **ESP-IDF 5.5.3.** PlatformIO Espressif32 is pinned to 6.13.0 for reproducible
  SDK selection. Builds reject cached socket limits below 26. Release-specific
  hardware coverage and untested scenarios are listed in the release notes.
- **SNMPv1/v2c is unencrypted.** It is off by default. If enabled, restrict UDP
  161 with the firewall and use a private community; do not expose it publicly.
- **2.4 GHz only**, single AP subnet.

## Privacy and outbound traffic

This build contains no usage reporting or external crash/log upload.
GitHub updates are OFF by default: the operator can enable periodic checks,
automatic installs and beta releases independently, or request a one-off
check/install. Those actions contact GitHub and its release-asset CDN without
sending settings, keys or logs; GitHub sees the public source IP and a generic
updater User-Agent. See [the update trust model](docs/UPDATES.md).
Other application-level connections are Tailscale/Headscale and,
when enabled by the operator, the configured MQTT broker and ntfy server. DNS, DHCP and NTP
remain available as infrastructure needed to resolve and establish those
connections. Diagnostic ping and traceroute run only when explicitly started.

For the complete, explicit comparison with upstream `main`, see
[`CUSTOM_BRANCH.md`](CUSTOM_BRANCH.md). A ready-to-use Windows flash package is
available from the [latest stable release](../../releases/latest), alongside
the OTA binary, factory image, checksums and original license notices.
Instructions are included inside the ZIP; obsolete package names are not
the recommended installation path.

## Security

Please report vulnerabilities privately — see [`SECURITY.md`](SECURITY.md).
The repo runs CodeQL, Dependabot, secret scanning, and a custom
[Sensitive Data Check](.github/workflows/sensitive-check.yml) on every
push.

## Development

```
main/                 firmware entry, web server + embedded SPA (index.html)
components/
  acl/                the ACL firewall engine
  sdlog/              microSD flight-recorder
  …                   DNS relay, DHCP server, etc.
external/microlink/   Tailscale/WireGuard stack (git submodule, MIT)
docs/                 configuration reference, images
tools/                helper scripts
```

The entire web UI is the single file `main/index.html`, embedded into
the firmware by `main/CMakeLists.txt` at build time.

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for build/flash setup and pull-request
guidelines, and **[docs/TESTING.md](docs/TESTING.md)** for the test harness.

## Support the Mattboxx edition

Found a bug or have an idea? Open an
[issue](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/issues).
Star the repository, share it or help test new versions to support the custom
edition's development. Financial support is optional; the firmware and all
features remain freely available.

Enjoying the Mattboxx edition? A small tip helps keep this mod moving — fixes,
new features and testing. No subscription or payment is needed to use anything.

[![Leave a small tip for the Mattboxx mod](https://img.shields.io/badge/Ko--fi-Leave%20a%20small%20tip-374151?style=for-the-badge&logo=kofi&logoColor=ffffff)](https://ko-fi.com/mattboxx)

### Support the original upstream project

These links support **Csontikka**, the original author, not the Mattboxx edition:
[Buy Me a Coffee](https://buymeacoffee.com/csontikka) or
[GitHub Sponsors](https://github.com/sponsors/Csontikka).

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/bunny.png">
    <img alt="Csontikka" src="assets/logo/bunny_dark.png" width="52">
  </picture>
</p>

## Credits & license

This firmware is [MIT](LICENSE) licensed. It builds on:

- **[microlink](https://github.com/Csontikka/microlink)** — Tailscale
  `ts2021` client (MIT), based on the original
  [CamM2325/microlink](https://github.com/CamM2325/microlink)
- **wireguard_lwip** — userspace WireGuard for lwIP (BSD-3-Clause),
  vendored inside microlink
- **[ESP-IDF](https://github.com/espressif/esp-idf)** — Espressif RTOS &
  networking (Apache-2.0)

See [`NOTICE.md`](NOTICE.md) for the full third-party attribution list.

> *Tailscale* and *Headscale* are trademarks of their respective owners.
> This is an independent, unaffiliated community project.
