# ESP32 Tailnet Gateway — Mattboxx Edition

_Formerly ESP32 Homelab Gateway. Tagline: One ESP32. Multiple Tailnet roles. Enable only what you need._

## Identity and mission

A compact autonomous embedded gateway for connecting, accessing, diagnosing,
monitoring and managing small homelab/IoT networks through Tailscale/Headscale.
It remains a separate operational node while a NAS, Home Assistant or managed
server is off; it still needs power and functioning network/VPN infrastructure.
It is not a Linux/pfSense/OPNsense replacement, KVM or fully out-of-band system.

Primary audiences: homelabs, NAS/home-server owners, Home Assistant users, small
network administrators, IoT and remote sites, including devices without a VPN
client. NAS recovery is a major use case, not a prerequisite for using it.

Product hierarchy (owner decision, 2026-10-22):

1. **Selective Tailnet Service Gateway (LAN → Tailnet)** — the primary reason
   to choose this firmware: existing LAN devices reach specific remote tailnet
   services without a client, without the ESP AP and without a gateway change;
   easy to create, verify, keep time-bounded and secure.
2. **Remote Recovery & Diagnostics** — second distinctive pillar.
3. **Automation, Monitoring & Management** — complementary ecosystem (MQTT,
   HA, ntfy, SNMP, Ethernet, profiles and the rest).

Never present it as exclusive technology or unlimited routing; always explain
subnet routing/AP gateway alternatives, ESP32 performance and the security
model. The hierarchy orders emphasis, not scope: all 42 items remain. Do not attribute underlying protocols or upstream
features to Mattboxx. Preserve original credits and the current repository URL.

## Approved final scope and traceability

The complete user mandate is [the archived Master Prompt](docs/MASTER-DEVELOPMENT-PROMPT.md).
No requirement may disappear. [The roadmap](docs/DEVELOPMENT-ROADMAP.md) sequences
all scope across 1.14–1.19 and stabilization; [the matrix](docs/FEATURE-IMPLEMENTATION-MATRIX.md)
tracks source, dependencies, tests, limitations and candidate per requirement.
Actual unavailable/impossible work stays blocked with evidence, not erased.

Six architectural areas: Connectivity Core; Network Gateway; Recovery & Device
Management; Monitoring & Diagnostics; Automation & Integrations; Configuration
& Management. Prefer small existing-module extensions over new frameworks.

## Acceptance criteria (all required, not current completion claims)

| Area | Final evidence required |
|---|---|
| Authorization | Document and verify supported PacketFilter/PacketFilters, ACL/grants network matches, current keys/AllowedIPs, IPv4/IPv6, revocation, incremental/full maps and stateful replies. No known supported-path bypass; unsupported semantics explicit, never widened. |
| Network paths | Positive and negative tests with real authorized/unauthorized visible clients over direct and DERP; ESP services, subnet/NAT/exit, LAN→Tailnet, 4via6, peer/key/policy changes and reconnects. A block-everything filter is not compatibility. |
| Protocol correctness | Bounded safe fragment handling, IPv6 extensions, ICMP/PMTU and malformed/truncated input; explicit unsupported jumbogram/protocol behavior. Measure state and preserve legitimate supported traffic. |
| Administration/privacy | Protect Web/API sessions, sensitive actions, credentials and remote commands; review CSRF/rate limiting/access across LAN/AP/Tailnet and honest HTTP/HTTPS boundary. No mandatory telemetry/log upload; signed/encrypted hardware claims require actual implementation. |
| Reliability | Measured heap/minimum/largest block, PSRAM, task high-water marks, sockets/limits, peers/flows/alloc/network/reset counters. Measured resource admission and isolated bounded optional services; no broker-triggered reboot loop. |
| Persistence/OTA | Validate before saving; atomic RAM/NVS consistency, compatible migration, failed writes, backup/restore, interrupted updates and actual supported rollback. Preserve WoL failed-save regression and existing settings. |
| Recovery | Full registry and bounded explicit Smart Recovery state machine, local UI plus authenticated integration control, service checks/history/notifications. Distinguish accepted command, sent WoL, observed host and service state; no power-cut/destructive actions or recovery guarantee for a hung host. Works without NAS/HA/MQTT. |
| Monitoring | Distinct local association/uplink/gateway/DNS/Internet/control/data/DERP/direct/peer/service/routing/forwarding/policy evidence; unknown/not configured/not verified/operational/degraded/down states. Configurable light checks and truthful guided next steps. |
| Service gateway | Separate AP-side and LAN→Tailnet rules, strict endpoints/ports/protocols/CIDRs/conflicts, resolution/mapping/counters/errors, safe import/export/guided setup and optional expiry. Expiry survives reboot/clock/NVS uncertainty safely; no accidental indefinite exposure. |
| Operations UX | Non-destructive Gateway/Recovery/IoT/Monitoring/Advanced presets, preview/confirmation/backup/rollback, all requested wizards, single-source capability manifest and local opt-in sanitized export. Responsive accessible lightweight coherent UI, no required CDN or heavy poller. |
| Integrations | Preserve/consolidate MQTT, HA Discovery, ntfy and SNMP; meaningful events, authorized bounded commands, replay/duplicate/abuse controls, privacy and independence from external outages. |
| Hardware | Explicit compatible-board/driver/pin configuration; conditional Ethernet DHCP/static IP, routing/uplink selection/change/reconnect/diagnostics. WiFi-only boards remain safe; physically unvalidated variants labeled. |
| Quality/release | Source/SDK/dependency/build/artifact provenance, actual-code host/UI/fault/sanitizer regressions, hardware upgrade/recovery and mixed-load soak, performance/resource evidence, refreshed threat model/dependency audit, no sensitive data, coherent docs/packaging. No stable release without essential qualification. |

## Completion and authority boundaries

Compilation, a UI button or offline fixture does not complete a feature.
Keep hardware testing, real two-client experiments and synthetic tests distinct.
Current development continues at local `0.1.38-Mattboxx-1.14-dev.5` from dev.4; public stable
1.13 is not upgraded or requalified by local work. Baseline tests are historical
evidence until rerun for changed paths. Unsupported policy/fragment behavior
still blocks stable qualification.

Ordinary local development is approved for the whole roadmap. Push, physical
flash/OTA installation, publications, destructive external operations and remote
URL changes require explicit authorization. Work around a scoped hardware
blocker with meaningful offline work and continue independent approved tasks.
