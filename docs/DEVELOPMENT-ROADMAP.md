# Permanent development roadmap

Authoritative execution plan for the complete [Master Prompt](MASTER-DEVELOPMENT-PROMPT.md).
This supersedes selection/defer wording in the earlier `ROADMAP.md`; no requested
function is removed. Milestone numbers are development targets, not releases,
dates or authorization to publish. Preserve stable 1.13 and all existing features.

## Product emphasis (owner decision, 2026-10-22)

F21/F22 (Selective Tailnet Service Gateway) is the primary feature; F16–F20
(Remote Recovery & Diagnostics) the second pillar; integrations, profiles,
Ethernet and the rest complementary. Within each priority tier, prefer work
that completes the Service Gateway experience (guided creation, source
restriction, destination verification, real state, counters, expiry, security).
This changes emphasis only; P0 safety order and all 42 items remain.

## Execution rules

1. Verify both worktrees, effective source/SDK and current checkpoint.
2. Select first incomplete available work by safety/dependency, not UI appeal.
3. Reproduce, implement a scoped increment, test, fix and record real evidence.
4. Continue the next available increment without a feature-choice question.
5. Hardware/credentials/permission blocks stay open; prepare their procedure
   and continue independent offline work. Never call a synthetic test hardware.
6. Keep `FEATURE-IMPLEMENTATION-MATRIX.md`, `VALIDATION-STATUS.md`, decisions and
   `NEXT-STEPS-FOR-AGENT.md` synchronized. No silent scope deletion or stub completion.

## 1.14 — P0 Security & Reliability (current, not release-ready)

Dev.5 extends dev.4 with bounded key/epoch-bound ingress reassembly, fail-closed
transport suspension/full-map resumption, opt-in layered health with evidence
guidance and a stable exposure ledger with transactional optional deletion.
An expired-rule reindex bug was reproduced and corrected. Broader fragment TX,
IPv6 extensions/interoperability, live policy churn and all final gates remain.

Dev.4 integration checkpoint: related-ICMP/bounded-header and browser write-
origin guards; shared registry/recovery/monitor/resource implementation and
LAN→Tailnet leases are in source, with API/UI/MQTT/HA/ntfy integration. The
matrix distinguishes implemented subsets from missing work. Full validation
is consolidated, not repeated after every function; no scope or final test cut.

Baseline dev.2 contains a bounded experimental policy gate, passive forwarding
diagnostics, WoL save fixes and branding; see `TAILNET-AUTHORIZATION.md` and the
ignored exact-image validation record. **P0-PEER-DELTA** is corrected and tested
offline in dev.3 (F42), not hardware-qualified. Current continuation is bounded
ICMP/PMTU and fragment/protocol compatibility (F05/F06), followed by precise
control-outage lifecycle (F03/F07). The read-only F15 observation harness is
available; its fake-clock tests are not a measured physical run.

- **F01–F09, F38:** complete supported PacketFilter/PacketFilters semantics,
  ACL/grants distinction, source/destination/protocol/ports, key ownership,
  IPv4/IPv6, full/delta maps, timely removals/revocations/key rotation and no
  stale authority. Test TCP continuations, exact UDP replies and NAT sessions.
  Cover direct WG, DERP, ESP services, subnet/exit/NAT, LAN→Tailnet, 4via6 and
  fast-path/lwIP callbacks before transforms. Do not assert official parity.
- **F05/F06:** bounded IPv4/IPv6 fragment handling, extension headers, ICMPv4/v6,
  PMTU, malformed/incomplete packets and explicit unsupported jumbograms.
  Never authorize later fragments solely because a superficially similar flow
  existed; no blanket ICMP exception. Keep state/time/quantity limits explicit.
- **F03/F07:** atomic validated bounded policy publication, OOM/oversize/error
  handling, no permissive intermediate window. Specify/test transient transport
  outage versus invalid/revoked authority; avoid unnecessary loss of already
  authorized connections when safe. Dev.2's blanket reset is not final design.
- **F08:** Web/API auth, CSRF where applicable, sensitive-action authorization,
  session/timeout/brute-force protection, secret/NVS handling, LAN/AP/Tailnet
  boundaries, actual HTTP/HTTPS, MQTT/ntfy command auth and OTA URL/origin trust.
- **F10–F12:** initial Resource Monitor (internal free/minimum/largest block,
  PSRAM, fragmentation indicators, stack, socket use/limits, peers/flows/state,
  alloc/network failures and reset causes); bounded UI and useful SNMP/MQTT
  exposure. Resource Guard thresholds require measurements. Isolate optional
  TLS/HTTP/MQTT/ntfy/HA/SNMP with limits, scheduling, backoff/timeouts/rate limits,
  queue/priority/stack sizing and circuit breakers when justified; no global
  restart or infinite retry caused by a secondary integration.
- **F13/F14:** config validation/atomicity/migrations/RAM-NVS coherence, failed
  write and power-loss recovery, incompatible config, backup/restore, interrupted
  OTA and actual supported rollback. Preserve transactional WoL tests.
- **F15/F33:** real and host duration/fault harnesses: repeated VPN/peer/policy,
  WiFi/Internet/router/ESP/service restarts, simultaneous integration load,
  routing/forwarding load; measure heap/PSRAM/stack/socket/temperature where
  meaningful, resets, throughput/latency and reconnection stability. No invented
  hours or unsupported-board claims.
- Retain WoL fixes, LAN→Tailnet diagnostics and existing upstream/fork behavior;
  review build, API/UI/ntfy/MQTT/HA contracts and privacy regression.

Gate: meaningful host/sanitizer/SDK/browser tests plus separately completed
two-real-client/direct+DERP, physical NVS/OTA/resource/reconnect/soak checks for
the exact future image. If physical checks are unavailable, do not publish;
continue independent implementation without pretending P0 qualification is done.

## 1.15 — P1 Smart Recovery

Dependencies: safe admin commands, persistence/resource/job ownership from P0.

- **F16 Device Registry:** preserve/extend WoL address book with name/MAC/IP or
  hostname/type/interface/local network/WoL parameters/reachability method/
  optional TCP check ports/timeouts/retry policy/current state/last attempt/
  last result/notification preference. No redundant secrets; migrate compatibly.
- **F17 Smart Recovery:** explicit request→authorization→precheck→one bounded
  WoL action→wait→reachability→optional service verification→success/failure/
  inconclusive/cancelled workflow. Local UI and authorized integration entry.
- Enforce timeout/retry/rate/concurrency/cancellation bounds, no loops,
  destructive command or repeated reboot/power control. Work without NAS,
  MQTT and HA. Do not claim a hung non-WoL-responsive host can be recovered.
- Show accepted/rejected, sent/not sent, host/service observed or not, duration
  and evidence-supported failure cause. Bounded history, diagnostics and optional
  outcome notifications; notification failure cannot replay recovery.

## 1.16 — P1 Health & Diagnostics (and completed P0 guard)

- **F18/F19:** Network and Tailnet Health Monitor: boot, association, uplink,
  local gateway, DNS, Internet, control/data plane, DERP/direct, essential peer/
  service, local routing/forwarding and auth/policy observations. Reuse passive
  counters first; operator-configurable active cadence/timeout/backoff/budgets.
  Distinguish unknown, unconfigured, unverified, operational, degraded, down.
- **F20:** Connectivity Diagnostics Assistant integrates passive rule guidance
  with evidence/observed item/status/probable cause/next check. Cover WiFi,
  gateway/DNS, unauthenticated VPN, absent/unreachable peers, route approval,
  firewall, disabled/conflicting/uninstalled rule, unverified service, missing
  uplink, low resources, MTU, MagicDNS, policy denial and target/service outage.
  Unsupported conclusions remain hypotheses/unknown, not definitive diagnoses.
- **F10–F12/F32:** measured Resource Guard, optional-service recovery/isolation,
  useful SNMP/HA/resource metrics and integrated diagnostics. Monitoring itself
  must not starve routing or administration.

## 1.17 — P1 Selective Service Gateway and temporary rules

- **F21:** preserve distinct AP-side forwarding. LAN→Tailnet TCP/UDP rule CRUD,
  enable/disable, strict endpoints/ports/CIDRs/protocols/destinations, MagicDNS
  resolution, conflicts, mapping state, accepted/blocked counters/errors,
  security exposure preview, guided templates and safe rule import/export.
  New rules OFF; distinguish configured/enabled/installed/peer reachable/service
  verified. Local source filter is not Tailnet identity. Respect both local
  policy and the receiving peer's independent network/service authorization.
- **F22:** optional duration/expiry, remaining time, automatic disable/event,
  optional notification, explicit renewal, retain-disabled versus delete choice.
  Handle restart, unsynchronized/changed clock, NVS failures and upgrades.
  Unprovable validity must not leave a temporary exposure open. No cloud clock
  dependency or silent expiry extension from backup restore/reboot.

## 1.18 — P2 Configuration & Operations

- **F23:** Gateway, Recovery, IoT, Monitoring and Advanced non-destructive
  profiles in one firmware. Preview/confirmation/backup/rollback; no silent
  removal of currently used capabilities or preset-specific binary variants.
- **F24:** wizards for first boot, Tailscale/Headscale, subnet router, exit node,
  LAN→Tailnet, WoL, Smart Recovery, MQTT, Home Assistant, ntfy, Health Monitor
  and failed-connectivity troubleshooting. Explain goal/prerequisites, validate,
  show risks/diff, explicitly confirm new exposure and roll back failures.
- **F25:** one API/UI Capability Manifest distinguishes compiled, hardware-
  supported, configured, active, verified, experimental and unavailable. Cover
  board/flash/PSRAM/WiFi/Ethernet/IPv6/routing/exit/4via6/forwarding/recovery/
  integrations/OTA/diagnostics. Counters alone do not establish Ethernet support.
  Use the manifest to disable unavailable controls without duplicating truth.
- **F26:** locally generated on-request bounded/streamed Sanitized Diagnostic
  Export: firmware/hardware/capabilities/reset/module/error/counter/resource/
  connection/config-summary/recent-event evidence. Automatically test exclusion
  of private/auth keys/passwords/MQTT-ntfy-OTA tokens/cookies/sessions/credentials/
  PII and unnecessary identifiers/IPs/hostnames. Never upload it automatically.
- **F27–F29/F32:** consolidate MQTT, HA Discovery, ntfy/SNMP. Events: boot,
  VPN up/down, essential peer/service degraded, recovery start/WoL/result,
  expiry, low resources and opt-in update availability. Commands: authorized
  recovery, enable/disable diagnostic checks, state queries, temporary rules
  only with strong authorization/limits. Prevent replay/duplicate/abuse/floods;
  critical config must not be changed by unauthenticated messages.
- **F30:** lightweight responsive mobile/keyboard-accessible coherent UI with
  clear errors, risk indications, honest evidence and no costly poll/CDN/heavy
  framework requirement. Dashboard covers overall/VPN/uplink/peer/routing/
  gateway/device/recovery/events/resources/needed actions. Navigation intent:
  Dashboard, Network, Tailnet, Service Gateway, Devices & Recovery, Monitoring,
  Diagnostics, Automations, Security, System, Updates; adapt existing layout
  when it is more sustainable, without dropping any capability.

## 1.19 — P3 Hardware & Advanced Connectivity

- **F31:** conditional Ethernet for explicit compatible ESP32-S3 hardware,
  including appropriate SPI modules: driver/pins/initialization, DHCP/static
  addressing, routing, Tailscale, diagnostics, reconnect, WiFi/Ethernet uplink
  preference and safe interface transitions. Test host faults and actual boards;
  untested physical variants remain labeled. Do not destabilize WiFi-only units.
- **F43 (owner request, 2026-10-24):** optional cellular (GSM/LTE) data uplink
  with a SIM: an external UART modem (for example SIMCom SIM7600/A7670 or
  Quectel EC2x) driven by ESP-IDF `esp_modem` as a PPP network interface, used
  as primary uplink or as failover when WiFi/Ethernet is lost. Settings: APN,
  optional user/password, SIM PIN (secret, write-only like other passwords),
  failover-only versus always-on, data-use notice. OFF by default; never dial
  without explicit configuration (data costs). Tailscale over carrier NAT is
  expected to use DERP; label direct-path results by evidence. Needs its own
  image variant like Ethernet (flash budget, UART pins, modem power of about
  2 A peaks) and real-modem qualification; until then experimental. Nearest
  alternative today: a phone hotspot or USB/WiFi LTE router as the WiFi uplink.
- **F40:** deeper flow diagnostics/peer management, useful SNMP/HA metrics,
  configurable critical-service checks, recovery of optional modules, OTA
  refinements, network-path optimization, fewer allocations/less memory, IPv6
  improvements, UI/API hardening and remote-maintenance UX. Experimental work
  OFF and labeled, with tests. No gratuitous cloud/AI/external services.

## Overall stabilization — mandatory, not a feature-cut milestone

**F33–F37/F41:** full regression/load/soak, measured resources/performance,
updated threat model and dependency audit, exact pins/artifacts/packaging,
upgrade/rollback and documentation review. Preserve upstream/fork delta and
attribution; no automatic critical-submodule bumps. Preserve persistent app/
NVS/update identity and coherent product naming/screenshots/package descriptions.

Required guide coverage: Quick Start; Installation; Tailscale; Headscale;
Subnet Router; Exit Node; LAN→Tailnet; NAS & Homelab Recovery; Smart Recovery;
Network Monitoring; MQTT; Home Assistant; ntfy; Security Model; Troubleshooting;
Firmware Updates; Backup and Restore; Hardware Compatibility; Ethernet;
Development and Testing. Existing guides may be reused after verifying their
accuracy; missing guides remain tracked, never implied complete.

Release notes and stable eligibility only follow evidence and explicit publish
permission. Detailed test records remain internal. Each checkpoint reports
completed modules, files/behavior/security fixes, actual tests/regressions,
remaining risks, roadmap state and next actions without declaring the entire
project complete.

## Master mandate coverage index

| Master sections | Permanent owner |
|---|---|
| 0–3, 25–30 | `AGENTS.md`, `GOALS.md`, next steps, decisions and validation ledger |
| 4 | Six areas above and `ARCHITECTURE.md`; no mandatory framework rewrite |
| 5 | F01–F09, F38; 1.14 security paths and protocol work |
| 6 | F10–F15; 1.14 reliability and 1.16 measured admission |
| 7 | F16/F17; 1.15 complete registry/workflow/result/security |
| 8–11 | F18–F22; health, assistant, advanced forwarding, timed expiry |
| 12–17 | F23–F30; all profiles/wizards/manifest/export/integration/UI scope |
| 18–19 | F31/F40; conditional Ethernet and advanced evolution |
| 20–21 | Matrix, F15/F33 and validation; all automatic/network/hardware cases |
| 22–24 | F34–F37/F41; upstream, credits/branding, every guide and release gate |

The archived full mandate remains normative for detailed subrequirements;
this index and milestone grouping do not narrow it.
