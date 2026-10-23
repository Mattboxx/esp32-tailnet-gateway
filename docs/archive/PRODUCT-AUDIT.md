# Product and source audit — October 21, 2026

## Verdict

This fork is substantially different at the application/operations layer,
not an independent implementation of Tailscale. Its strongest existing
difference is **selective LAN-to-Tailnet services for VPN-less clients**,
combined with local target management and optional automation in a standalone
firmware. It should exist if that combination is easier to configure and
keep operational than assembling several components. Feature count alone is
not a justification; protocol security/performance improvements remain credited
to upstream.

An existing always-on Linux router with official Tailscale may be the better
choice: it can supply port forwarding, WoL and monitoring with more resources.
Do not claim the ESP32 invents these network functions or replaces Linux at
high throughput. The target is a small **additional** access/control node,
especially where the managed server is otherwise the only always-on computer.

## Inspected revisions and evidence

- Mattboxx stable source: `8dbf06081392b292f37746a4858cf5a09f289757`, plus the
  explicitly unreleased changes in this worktree.
- [Csontikka router v0.1.38](https://github.com/Csontikka/esp32-tailscale-subnet-router/tree/42ec1081c5abb2166c429b038373aa13fa268bc0):
  application CMake sources, manager/routing/NAPT, UI, metrics, SNMP,
  telemetry, password and OTA implementations; compared with the fork.
- [microlink](https://github.com/Csontikka/microlink/tree/a85e8c42ee2ed3223f8c3bd3766fc37af1985384):
  config, peer information, coordination parsing and WG manager. Custom pinned
  merge: `1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`.
- [esphome-tailscale](https://github.com/Csontikka/esphome-tailscale/tree/0a34e85f1a0483e8bf4cb9951dbf1ac531f9fcf0):
  `components/tailscale/{__init__.py,tailscale.cpp,tailscale.h,telemetry.cpp}`
  and packaged ESPHome configuration. Its config/client lifecycle makes the
  ESP itself a node; no router/port-forwarding service is implemented there.
  Do not mistake that for lack of WoL in the ESPHome ecosystem: ESPHome has
  an existing [WoL button](https://esphome.io/components/button/wake_on_lan/).
- [ds220plus-proxmox](https://github.com/Csontikka/ds220plus-proxmox/tree/6474d903b47b00702d8279e6984862bb8fa6786f):
  `tools/bootguard/syno-bootguard-check` actually checks gateway and Proxmox
  web readiness. Its Linux/DOM/ZFSBootMenu recovery is host-specific, not a
  reusable ESP32 recovery implementation.
- [ha-mikrotik-extended](https://github.com/Csontikka/ha-mikrotik-extended/tree/d81c333e6a0dcf63b3a618aefa5fd0d36c1b4434):
  inspected `custom_components/mikrotik_extended/coordinator.py` and integration
  structure. It is a Home Assistant/RouterOS integration, not an independent
  embedded fallback if that HA host is down. It demonstrates why simply adding
  more HA entities is not an independent product advantage.

Methods: actual source paths/configuration and Git diffs, not only README
feature lists. The audit is a scoped static review, not a formal security
assessment, exhaustive protocol proof or compatibility certification.

## Identity and audience

**Recommended name: ESP32 Homelab Gateway — Mattboxx Edition.**

One-line promise: *Keep a small access, control and diagnostic node available
independently of the servers it manages.*

Primary users: small homelabs, two-location IoT installations, and operators
needing a separate WoL/management entry point. A NAS is one target, not a
requirement. Core local operations must not require MQTT, HA or ntfy.

The promise still depends on power, relevant LAN equipment, and—when used
remotely—the Internet/VPN infrastructure. No out-of-band, KVM, physical power
control or file recovery claim. Choose another solution when those are needed.

### Naming choices and limits

| Candidate | Decision |
|---|---|
| ESP32 Tailscale Gateway & NAS Recovery | Describes current functions but overweights NAS and can suggest recovery guarantees. |
| ESP32 Homelab Gateway | Recommended: understandable audience/function, room for recovery/diagnostics without claiming a new protocol. |
| ESP32 Tailnet Gateway | Good technical descriptor, less clear to newcomers and close to the upstream's generic role. |
| ESP32 RemoteOps Gateway | Distinctive but jargon-heavy; implies a broader operations platform than presently implemented. |
| ESP32 Tailscale Management Gateway | Long and more likely to suggest official Tailscale management/authorization capabilities. |

Exact-name Web/GitHub searches on the audit date did not identify a separate
exact-name project for the recommendation; that is **not trademark clearance**
or proof of exclusivity. A nearby project, `tailnet-mcu`, also exists; do not
claim uniqueness for the generic gateway idea. No repository URL, app project
identifier, update repository or history is renamed. Mattboxx identifies the
edition, not ownership of upstream inventions.

Tailscale is used descriptively for compatibility, not as an official product
badge. The new wordmark contains no Tailscale corporate logo. Original
licenses, copyright, credits and author support links remain. Tailscale's
[press page](https://tailscale.com/press) links brand assets, but this review
does not establish permission to adopt their branding. Existing
[third-party notices](../../NOTICE.md) and non-endorsement statements remain.

## Code-backed feature matrix

“Fork addition” means added to this router fork, not invention of the concept.
“Missing” means absent in the inspected revision, not promised by a roadmap.

| Capability | Original router / ecosystem | Mattboxx implementation and status | Actual reason to choose this edition |
|---|---|---|---|
| Tailscale/Headscale, WG, DERP, DISCO/STUN | microlink/upstream | Shared protocol stack; custom startup/lifetime/reply hooks in manager/submodule | Not a unique feature. Keep compatibility and upstream maintenance. |
| AP/STA NAT gateway, subnet routing, firewall, DNS, AP-side maps | Router implementation | Shared; fork changes lifecycle/conflict/transaction and source-boundary handling | Operational safeguards, not a new router design. |
| LAN → Tailnet selected TCP/UDP services | Not implemented in inspected router or ESPHome component | `tailnet_forward.*`, `tailnet_input.c`, reassembly, portmap and route hooks; eight rules, CGNAT/MagicDNS, ingress/CIDR checks | Local clients use an ESP LAN port without VPN software, AP membership or router static routes for this path. Upstream needs new code or another proxy/router. |
| Saved, named local WoL targets | Not in router; readily composed in ESPHome | `wol.*`; 12 targets, web/MQTT/ntfy commands | Editable standalone address book with direct local/Tailnet management. WoL alone does not justify a separate fork. |
| Verified recovery workflow | Neither this router nor this fork | **Missing:** send succeeds != host awake/service ready | Strong next differentiation, not an existing claim. |
| MQTT/HA discovery and controls | Not in router; native HA support in ESPHome | `mqtt_integration.*`; state, LWT, controls, named WoL, per-rule discovery, broker watchdog | Router operations integrated without hand-building ESPHome/router glue. Native HA integration alone is not unique. |
| ntfy commands/alerts | Not in router | `ntfy_integration.*`, stream parser; replay cursor, optional details, saved-target commands | Optional command/alert path when HA/broker is unavailable; depends on its configured server. |
| Optional AP policy | Original AP gateway | `ap_policy.*` plus configuration/dashboard changes | Preserve the AP as an actual client gateway, or automatically stop it when not needed. |
| 4via6 overlap handling | Not in inspected router application | `fourvia6.*`, route hooks, UI/HA | Overlapping LAN use cases; not general IPv6 Internet transit. Needs topology testing. |
| Exit-node operation | Original router already provides exit functionality | Fork server policy validation, separate DNS PeerAPI, selection/advertising and automation integration | Improved operational surface, not an original VPN capability. |
| SNMP, CPU/temp, local logs/diagnostics | Present upstream | Shared SNMP; runtime switch/hardening and integrations; fork CPU sampling | Shared/improved. Do not market these as uniquely created here. |
| Configurable UI port, auth/session policy | Upstream UI/password baseline | `web_port.*`, password component and UI validation; backup/secret-export guards | Recovery flexibility with explicit tradeoffs; password-OFF is increased trust, not a security improvement. |
| Local and GitHub OTA | OTA/update path upstream | Custom `ota_remote.*`: opt-in fork-only stable/beta/manual/automatic policy and strict asset checks | Operator control and custom-release discovery; no application telemetry requirement. Not publisher signing. |
| Ethernet uplink | Generic SNMP can inspect an ETH netif | **Missing in this application:** no driver initialization, uplink selection or forwarding adaptation | Remove support claims. A counter for an optional netif does not create hardware support. |
| Guided per-rule status/exposure | Raw installed/error/counters existed in fork | **This increment:** passive diagnostic code/summary/next-step, saved path, truthful unknown states | Explains the differentiating feature without pretending to probe peers or services. |
| Internet/control/data/service health separation | Partial status/diagnostic signals | **Incomplete:** control connected flag is not a data-plane test | Needs evidence contracts and opt-in bounded checks, not more green LEDs. |

### Concrete user paths

- A client at site B uses `ESP-LAN-IP:18830`; the rule targets a Tailscale
  peer broker at site A on TCP 1883. HA consumes that broker. The broker must
  be reachable/authorized, and the IoT device must allow endpoint configuration.
- A management PC without a VPN client uses one allowed `/32` source and
  one local port to reach a remote SSH service. The service still authenticates
  users; the ESP source filter is not client identity.
- An independently powered node provides direct Web UI/WoL while the NAS and
  its HA/MQTT services are down. No “host is online” result is implied by send.

Do not describe these as a transparent LAN bridge. Discovery/broadcast,
callbacks, embedded addresses, overlapping subnets and multiport protocols may
require additional work. General [Tailscale site-to-site networking](https://tailscale.com/docs/features/site-to-site)
already exists; this fork's value is the constrained service-entry workflow.

## Alternatives and when not to choose this firmware

| Alternative | Better fit | Reason to choose this project instead |
|---|---|---|
| Original Csontikka router | Core AP/subnet gateway with fewer application integrations | Need the integrated LAN service-entry and local/automation operations surface. |
| ESPHome + esphome-tailscale + WoL | Custom sensors/actuators and native HA API; configurable YAML ecosystem | Need a standalone router/forwarder with editable local administration, not just the ESP as a node. |
| Official Tailscale on Linux/OpenWrt | Full resources, mature client policy handling, scripts/packages and higher routing demands | Want a separate small embedded companion rather than another maintained Linux host. No measured price/power advantage claimed here. |
| [GL.iNet Tailscale router](https://docs.gl-inet.com/router/en/4/interface_guide/tailscale/) | Appliance routing, Ethernet and broader network administration | Already have the supported S3 and prefer this constrained service/automation workflow. Do not claim it replaces the appliance. |
| [PiKVM](https://docs.pikvm.org/) / IP-KVM hardware | Screen/keyboard/BIOS/ATX recovery | Not equivalent. This project is network access and WoL, not KVM. |

## Existing defects and architectural risks

1. **Fixed here:** WoL published a new RAM table before NVS success, so an
   unsuccessful save changed subsequent commands. Now validation/persistence
   precedes RAM publication; corrupt/partial records are not exposed. The
   original 60-byte entry format remains. Flash power-loss guarantees are not
   established by a synthetic NVS fixture.
2. **Fixed here:** fractional/ambiguous WoL send indices and truncating/wrong-
   type save fields were accepted; API now rejects them before side effects.
   A successful response explicitly states `device_state: not_verified`.
3. **Fixed here:** failed forwarding reads were silent and “Active” meant only
   installed mapping. Unknown/unsaved states and exposure now remain explicit.
4. **Confirmed P0 policy gap, local mitigation in dev.2:** the pinned parent
   did not enforce PacketFilter/PacketFilters per-port permissions, and IPv6
   source ownership was incomplete. The local bounded authorization gate now
   separates current key/prefix ownership from service permission before WG
   input translation. See [scope and real-client matrix](../TAILNET-AUTHORIZATION.md).
   Conservative protocol restrictions, production-map compatibility and hardware
   qualification still block a stable release; no official-client parity claim.
5. Internal heap is scarce despite PSRAM; historical bounded board checks
   in 1.13 observed roughly 16 KB free. That is not a new measurement. TCP/TLS
   integrations and 31 sockets can compete with routing. No new permanent
   task/socket is added here; resource admission is prioritized over new services.
6. Broad C/UI modules and duplicate API/HA/ntfy configuration surfaces increase
   drift. Keep transport/state-machine changes small; do not start a four-way
   component rewrite just to match the product areas.
7. Synchronous diagnostic handlers can monopolize HTTP handling. New active
   checks must be bounded asynchronous jobs, not longer handler loops.
8. Existing manual broker-watchdog WoL is opt-in and one burst per outage;
   that is not verified recovery and must not be duplicated by another automatic
   retry loop. Integration errors must not escalate to whole-device reboot.
9. Ethernet claims exceeded application support; fixed in current docs.
   The already published 1.13 release body is not remotely edited by this local
   development work. Reconcile that wording before the next publication.

Use [the roadmap](../ROADMAP.md) for decisions/gates, not this list as implied
authorization to implement every proposed feature or publish new firmware.
