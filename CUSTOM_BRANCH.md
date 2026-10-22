# Custom ESP32-S3 router branch

## Development identity and operational increment: 1.14-dev.1

Product name: **ESP32 Homelab Gateway — Mattboxx Edition**. The repository
URL, app/update identity, licenses and existing NVS formats are unchanged.
[Code-backed audit](docs/PRODUCT-AUDIT.md), [architecture](docs/ARCHITECTURE.md)
and [value/risk roadmap](docs/ROADMAP.md) distinguish upstream protocol work
from the fork's selective service gateway and operations surface.

New passive rule explanations separate mapping installation from service
reachability, show saved LAN exposure and distinguish unknown/draft states.
WoL address-book changes now publish only after successful persistence; sent
packets are not claimed as successful recovery. No extra monitoring worker,
socket or mandatory service is introduced. This is unreleased source; stable
1.13 assets and the device are not changed by this increment.

## Current stable: 0.1.38-Mattboxx-1.13

All published v0.1.34–v0.1.38 changes are merged/adapted without replacing
custom microlink hooks or application services. Includes relay TLS verification,
WireGuard state/nonce/Noise fixes, corrected relay measurement/reporting,
silent-peer recovery, bounded control stalls, synchronized TCPIP teardown and
copy-free TX. Retain restart-based published-instance lifetime and add guarded
local SD snapshots. [Full change mapping and limits](docs/UPSTREAM-0.1.38.md).

The stable tag matches the embedded version and is eligible for the opt-in
stable updater without beta enrollment. Manual OTA preserves saved settings.
See [release notes and download instructions](docs/RELEASE-1.13.md).

## Previous release: 0.1.33-Mattboxx-1.12-dev.1

The existing release was marked stable/latest on October 20 without changing
the tag or assets. Its retained development-form tag requires manual download/
OTA with the current updater. An installed identical build needs no flash.

Integrates the published upstream v0.1.32/v0.1.33 fixes and optional live WiFi
power-save policy, preserving this fork's low-latency OFF default. Includes
MQTT/HA and ntfy policy visibility and the optional one-click Ko-fi window.
All custom forwarding, AP, automation, routing, privacy and update controls
are retained. See [release validation and limits](docs/RELEASE-1.12.md) and
the [upstream integration record](docs/UPSTREAM-0.1.33.md).

The [NAS recovery checklist](docs/NAS-RECOVERY.md) explains independent power,
WoL requirements and why this is not a hard-reset/data-recovery appliance.

## New in 1.10 development: operator-controlled GitHub updates

User-requested replacement for the removed always-on upstream poller:
fork-only HTTPS release checks, automatic install, optional local-time window,
stable/beta selection, Check now and Install latest update. All switches start
OFF; manual GitHub actions work without enabling periodic checks. Local binary
upload remains. Require compatible newer Mattboxx tags, firmware.bin, GitHub
SHA-256, board/project/version validation and exclusive OTA writing. Configuration
and actions require the password-backed UI session; HA and ntfy expose status,
not unauthenticated install commands. [Full policy and limits](docs/UPDATES.md).

## Upstream v0.1.31 alignment (1.9 development)

All changes in the published v0.1.30/v0.1.31 tags are accounted for in
[the integration record](docs/UPSTREAM-0.1.31.md). This includes CGNAT LAN,
resolver and DHCP routing exceptions; lifecycle-leased TCP/IP route updates;
microlink stop/netcheck cleanup; received UDP packet storage in PSRAM; and
the exit-node DNS PeerAPI with control-plane service advertisement.

Existing AP policies, WOL, MQTT/HA, ntfy (including the 1.8 stack hotfix),
independent LAN-to-Tailnet forwarding, AP-side port maps, 4via6, exit-node
selection/advertising, web-port/password/session policies, encrypted backups,
SNMP, metrics, diagnostics and privacy removals remain. Regression checks
compare endpoint, UI, HA entity and command identifiers with the previous fork.
The socket budget is raised to 31 for the separate DNS server. Configurable
admin ports remain supported, including 41180 (DNS then advertises 41181).
The stable 1.8 release and its existing binaries are unchanged. No new board
flash or hardware stability claim accompanies this source alignment.

## Upstream v0.1.29 alignment (1.8 stable)

The v0.1.20-v0.1.29 improvements are integrated on top of the Mattboxx features. See
[the latest integration record](docs/UPSTREAM-0.1.29.md),
[the preceding integration record](docs/UPSTREAM-0.1.28.md) and
[the earlier integration record](docs/UPSTREAM-0.1.27.md). MQTT/HA, ntfy,
WOL, AP policy, LAN-to-Tailnet forwarding, 4via6, exit-node advertising,
authentication and privacy removals remain in place. No Ethernet driver or
automatic external telemetry/update service is introduced by this alignment.

This branch starts from upstream `main` at `v0.1.19` and targets the ESP32-S3
N16R8 used during development. Hardware validation is revision-specific; the
current release coverage is in [the 1.8 release record](docs/RELEASE-1.8.md).

## New in the 1.8 stable hotfix

- Fix the ntfy stack-overflow reboot loop during HTTPS command reception.
  Heavy functions cannot be inlined into the worker; its compiled frame drops
  from 4,240 to 496 bytes. Alert logs are heap-backed and freed before TLS.
- Give the worker a 12 KiB stack, check task creation and expose its running
  state/minimum remaining stack through the authenticated ntfy API.
- Synchronize status counters, propagate failed `info` replies, and reject
  oversized command responses instead of parsing a silently damaged stream.
- Correct the panic popup's pre-crash log location to Diagnostics.
- Add exact-ELF stack budgets, actual-C regression tests with sanitizer CI,
  and an opt-in HTTPS/info hardware soak. Previous features remain intact.

## Previously added in the 1.7 stable release

- Upstream v0.1.29 routing fixes: identify the tunnel by its `wg` interface
  name, not a CGNAT IP; skip down/link-down LAN interfaces in bypass and Tools.
  HTTP registration checks and local favicon were already included in 1.6.
- Additional route-table synchronization: build a complete peer-route generation
  first, publish under a cross-core critical section, and snapshot it for web
  diagnostics. Default-route updates are marshalled into the TCP/IP task even
  when the SDK disables its optional core-locking macros.
- Correct Web Session label: no idle timeout no longer implies no password.
- Regression harness compiles the real route hook and diagnostic functions,
  exercising CGNAT/missing tunnel, disconnected interfaces, exit-node split,
  accepted-route snapshots and invalid prefix lengths. CI runs sanitizers.
- Existing features/privacy removals and the IDF 5.5.3/26-socket budget remain.

## Previously added in the 1.6 stable release

- Upstream read-only SNMP agent, OFF by default, with a graphical switch,
  neutral failed-load state, plaintext-protocol warning and password-masked
  community field. New SNMP enabled/running and socket-limit diagnostics in
  MQTT/Home Assistant and ntfy info do not disclose the SNMP community.
- Pinned IDF 5.5.3 with 26 socket slots and a build guard against stale local
  SDK configurations. Hardware diagnostics verify the compiled budget.
- Authentication-gated Automation reads, independent WOL/MQTT rendering,
  bounded retryable reads and explicit stale/unavailable configuration states.
- Checked registration of every HTTP endpoint, extra handler-table capacity,
  and a locally served/embedded favicon; no new CDN or browser tracking.
- SNMP descriptors are closed only by their owning task; disable wakes that
  task without recycling a socket number during receive/send. Configuration
  is mutex-protected during replies. Invalid versions/integers and overflowing
  OID arcs are rejected, in addition to upstream's bounded BER parsing.
- Ready-to-flash binaries and Windows package include checksum verification,
  a settings-preserving update and an explicitly confirmed erase-only install.

## New in the 1.5 stable release

The tested `1.5-dev` binary is promoted unchanged as release 1.5; its embedded
version intentionally retains that suffix. See [release notes](docs/RELEASE-1.5.md).

- Background CPU monitoring, total and per-core Home Assistant sensors, and
  CPU readings in ntfy `info`, including counter-rollover handling.
- Strict MQTT switch/index validation; malformed messages cannot silently
  switch a feature off or select forwarding rule zero.
- Coalesced restart/reconnect requests, no-op suppression, and safe full-device
  restart for MQTT actions that reinitialize Tailscale. Saved credentials and
  hostname no longer invalidate the running VPN's retained configuration.
- ntfy command whitespace handling and bounded command length.
- DHCP request validation before lease mutation, complete pbuf-chain copying,
  bounded packet allocations and graceful lease-allocation failure handling.
- Secret checks now inspect reachable Git history and never print matched
  secrets. Host regression tests also run in the security workflow.

## Added

- Stable ESP32-S3 setup UI and WiFi scanning/saving, including the HTTP 431 fix.
- Selectable client WiFi / tailnet gateway: always available, or placed in
  standby while the uplink is connected and restored after a disconnect.
  Dashboard and Network explicitly show Disabled when it is not running.
- A separate Automation page for Wake-on-LAN and MQTT/Home Assistant.
- A WOL address book with saved name, MAC, broadcast and port, plus web, MQTT
  and Home Assistant triggers.
- MQTT retained state, Last Will, commands and watchdog.
- Home Assistant discovery for network/Tailscale/AP/system/MQTT diagnostics and
  AP, routes, SNAT, LAN bypass, Tailscale, reconnect, restart, publish and WOL.
- Optional Tailscale 4via6 routing for overlapping IPv4 LANs: configurable
  LAN CIDR and site ID, calculated/advertised prefix, bidirectional TCP/UDP/
  ICMP translation, flow counters and Home Assistant status/control.
- Optional Tailscale exit-node advertising with automatic IPv4 egress NAT,
  Tailscale admin-approval guidance, MQTT/Home Assistant control and status in
  `ntfy info`. Server mode is mutually exclusive with selecting another exit
  node, preventing a tunnel routing loop; IPv6 fails closed on the IPv4 data
  plane instead of leaking outside the selected exit.
- Correct dual-core CPU load reporting. The FreeRTOS idle counters are now
  normalized against both ESP32-S3 cores instead of being clamped to 0%.
- Optional ntfy alerts for a Tailscale outage while the uplink is working,
  plus replay-protected `info` and saved/direct-MAC WOL commands.
- Fixed the ntfy command-poll reboot loop: the HTTP response buffer is now
  heap-backed instead of exhausting the ntfy task stack on its first poll.
- Fixed ntfy commands being permanently missed because the old 10-second
  history window was shorter than the default 15-second poll interval. The
  first eligible poll is immediate and subsequent polls use a durable cursor.
- Graphical on/off switches and visibly dimmed disabled cards/settings for AP,
  Tailscale, 4via6, MQTT, Home Assistant, watchdog, ntfy and web authentication.
- Optional web password gate and session timeout. Passwords of at least four
  characters are accepted, with a visible warning for weak choices. Password
  verifiers use salted PBKDF2-HMAC-SHA256 and legacy records upgrade on login.
  Browser login uses a one-time PBKDF2/HMAC challenge: the browser performs
  the costly derivation and the ESP verifies a short proof, so even the first
  unlock after reboot is prompt and the normal UI does not transmit the
  plaintext password. Plaintext login is retained only to migrate legacy
  verifier records; modern records require the challenge proof.
- Manual local OTA upload and explicit privacy/outbound-traffic reporting.
- Dedicated uplink-LAN → Tailnet TCP/UDP service forwarding, separate from the
  existing uplink → AP-client table. Each rule has an enable switch, friendly
  name, listen/destination ports, Tailnet IPv4 or MagicDNS target, mandatory
  allowed-source CIDR, counters and live resolution/install status.
- Configurable web UI TCP port, with two-way conflict checks against both
  forwarding tables.
- MQTT/Home Assistant status and per-rule switches for LAN → Tailnet rules;
  `ntfy info` includes their state and always lists saved WOL device names.
- Router-oriented network tuning: WiFi modem sleep is disabled to reduce
  forwarding latency, and the ESP-IDF maximum of 16 lwIP sockets is used with
  a bounded web-client pool so UI, Tailscale, MQTT, ntfy and diagnostics do not
  exhaust the descriptor table.

## Removed from upstream main

- Built-in anonymous telemetry and its hard-coded Cloudflare Worker. No boot,
  usage, reconnect, reset or crash event is uploaded.
- Forced upstream GitHub release polling and downloads. Replaced in 1.10
  development by explicit, default-OFF checks/install for the Mattboxx fork.
- Cloudflare speed test and its hard-coded public DNS fallback.
- Browser-side automatic GitHub release requests.

Historical telemetry entries remain in `CHANGELOG.md` only because it records
older upstream releases. The source is deleted and not linked into the firmware.

## Security and privacy hardening

- Persistent warning logs omit peer names, key prefixes, private endpoint IPs
  and endpoint ports.
- The remote TCP console refuses to start without a configured admin password.
- Login attempts are rate-limited across a larger per-client guard table;
  initial password setup is only
  accepted through the ESP's own access point.
- Changing the stored password uses the same progressive per-client rate
  limit even when the ordinary web password gate is disabled, and plaintext
  password buffers are wiped after web or remote-console verification.
- The web page sends CSP, anti-framing, MIME-sniffing, referrer, permissions
  and same-origin resource-policy headers.
- Dynamic toast text is inserted as text rather than HTML, preventing stored or
  reflected script injection through device names and server error messages.
- HTTP request bodies are read completely before JSON parsing instead of
  assuming one TCP read contains the entire save request.
- Retained or duplicate MQTT commands are ignored so an old restart/WOL command
  cannot execute again every time the broker reconnects.
- DHCP packet address fields are defensively initialized and lease eviction is
  safe even when its list-size invariant is violated in a release build.
- Secrets, OTA, factory reset, crash trigger and Tailscale identity reset always
  require a password-authenticated session, even when the UI gate is disabled.
- The compiled image contains no fixed telemetry, update or speed-test target.
- ntfy `info` replies omit SSIDs, addresses, routes, peer identities, client
  MACs and WOL target details unless the operator explicitly enables them.
- The UI shows an inline security warning whenever enabled MQTT or ntfy uses a
  plaintext transport.
- MQTT and ntfy base URLs reject embedded credentials and control characters;
  passwords/tokens must use their separate write-only fields and cannot leak
  through a displayed or logged URL.

## Expected outbound traffic

The remaining functional traffic is limited to:

- the selected Tailscale/Headscale control plane, DERP and STUN endpoints;
- NTP (`pool.ntp.org`) for time required by authenticated/TLS connections;
- the operator-configured MQTT broker, only when MQTT is enabled;
- the operator-configured ntfy server, only when ntfy is enabled;
- targets explicitly requested by ping, traceroute, WOL or routed clients.

No hidden path that adds tailnet devices or uploads local logs was found in the
reviewed source or compiled image. Peers come from the configured control plane.
This source audit is not a formal proof; tailnet and broker ACLs remain important.

## Remaining security boundaries

- The web UI is HTTP, so use it only on a trusted AP/LAN or over encrypted
  Tailscale transport.
- Every LAN → Tailnet rule deliberately exposes a Tailnet service to its
  allowed uplink subnet. Use the narrowest possible CIDR, keep the peer service
  authenticated, and enforce Tailnet ACLs as a second boundary.
- Secure Boot, flash encryption and NVS encryption remain disabled so one
  generic factory image can be flashed on ordinary boards. Physical access can
  therefore expose saved credentials and replace the firmware.
- Four-character passwords are accepted by operator choice. Online guesses are
  throttled and offline guesses are slowed with PBKDF2, but a strong unique
  password is still recommended.
- MQTT/ntfy commands trust the configured broker/server, token and topic. Prefer
  TLS transports, private random topics and restrictive ACLs.

## Flashing

`flash-package` contains tested binaries, Espressif's official standalone
`esptool.exe`, and guided Windows batch files. See `flash-package/README.txt`.
