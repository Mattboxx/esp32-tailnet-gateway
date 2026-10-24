# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] — in development

In development: 8 MB partition table for ESP32-S3 N8R8 and N16R8, one
firmware image with every language and Ethernet, optional cellular uplink.
2.x gateways move over with the 2.1 bridge (over the network) or with one
USB install; settings are kept ([guide](docs/MIGRATION-3.0.md)). Work so far
(2.0.4-beta.3 was cancelled before publication and continues here):

### Added

- **Move from 2.x without a cable:** the 2.1 bridge, installed by the 2.x
  updater, downloads 3.x from GitHub, verifies it and rewrites the boot
  loader and partition table; settings are kept and a 3.x that does not
  start returns to the bridge. Tested end to end on a N16R8.
- **One image** with every Web UI language and the W5500 Ethernet driver
  (OFF until configured), on a new 8 MB layout with 3.5 MB update slots.
- **Cellular uplink (experimental):** UART modem with a SIM, primary or
  failover, write-only SIM PIN and APN password ([guide](docs/CELLULAR.md)).

### Changed

- **One Web UI language per firmware image.** The standard image
  (`firmware.bin`, also used by the browser installer) is English only;
  `firmware-it.bin`, `firmware-es.bin` and `firmware-zh.bin` carry English
  plus one language. This frees about 65 KB of app flash (98.2 % to 94.9 %
  for the English image). A gateway keeps its language on GitHub updates;
  **System → Firmware update → Firmware language** chooses another one, and
  choosing a different language offers the installed version again in that
  language (never an older one). The Easy Install package contains every
  language and its scripts ask which one to install. The Ethernet image stays
  English only. Coming from an earlier 2.0.x with the Italian, Spanish or
  Chinese interface: the first update installs the English image; choose the
  language and install once more.
- Application tables (scan cache, firewall lists, saved networks, Service
  Gateway rules, 4via6 flows, DHCP reservations, WoL devices, Devices &
  Recovery store, console capture) moved from internal RAM to PSRAM, leaving
  more internal RAM for WiFi, lwIP and the VPN.
- Faster execution from PSRAM: instruction cache 16 → 32 KB and 64-byte
  data-cache lines. Net static internal RAM still about 23 KB lower than
  beta 2 (build report); speed and free heap to be confirmed on hardware.
- Resource admission guard defaults: 8 KB free internal RAM and a 4 KB
  largest block (were 16 KB / 8 KB). Estimates, not measured limits; saved
  settings are unchanged.

### Fixed

- MQTT and ntfy stopped connecting with no explanation when the resource
  admission guard was on: at the normal ~17 KB of free internal RAM the old
  default threshold paused all optional work. The Health & resources card now
  warns while the guard is pausing work, the MQTT badge reads *Paused by the
  resource guard* and the ntfy test says the same.
- *Check now* answered `ESP_ERR_INVALID_STATE — refresh before another
  action`. Refusals now say why (another check running, the same device
  checked less than a minute ago, or the resource guard) and the page keeps
  working.
- The configuration profile selector showed *Gateway* whatever was active; it
  now shows the active profile, or *No profile applied*.
- Network: the *Device-wide network* card touched the *Uplink networks* card.

## [2.0.4] — beta 2, 2026-10-24

### Improved

- The Service Gateway card on the Status page appears only while a service
  rule is **enabled** or temporary access is open, just above *What do you
  want to do?*. Choosing the role during setup, or saving a disabled rule,
  no longer brings it back.
- iPhone and iPad: the sign-in, password and setup screens no longer show the
  dashboard underneath when the on-screen keyboard opens.
- Menu order follows the setup flow: Status, Network, Tailscale, Firewall,
  Devices & Recovery, Automation, Diagnostics, System. Devices & Recovery has
  its own icon.
- Phones: the menu button opens and closes the menu; the menu opens below the
  bar so the button stays visible.
- Devices & Recovery: cards are spaced like the other pages, switches sit one
  per line, fields use columns on wide screens and each device profile has a
  header with its state. In simple mode the guard thresholds are an advanced
  setting and the connectivity checks card keeps its title.
- Field rows on Network, Automation and System use the same column layout.
- Devices & Recovery: *Check now* and *Recover with WoL* show the result live.
  While a job runs the page re-reads its state every 2 s, updates only the
  device badge and job line (unsaved edits stay), and stops when the job ends.
  Badges read *Reachable · 12 ms*, *Not reachable*, *Checking the service…*.
- Devices & Recovery: every field explains what it is for and shows an
  example while empty; optional ports are empty instead of 0.
- The `.local` name is easier to change: *Change* next to *Name on this
  network* on the Status page opens the hostname field, which previews the
  address it gives and says when a restart is needed. Status and Network show
  the name that answers now until the restart.
- Status refresh pauses while the browser tab is hidden and catches up at once
  when you return, instead of waiting up to 30 s.

## [2.0.3] — 2026-10-24 (beta)

### Improved

- **Status page:** live status comes first. The Service Gateway card appears
  only when service rules exist, a temporary rule is open or that role was
  chosen in the first-boot wizard; *What do you want to do?* moved to the end
  of the page and still offers every guide.
- The Uplink card shows the board's own name on the network
  (`esp32-tailnet-xxxx.local`, as a link).
- A recovery-only access point is shown as **Standby** (it turns on if the home
  WiFi is lost) instead of *Disabled*.
- Internal RAM: the summary says *Free internal RAM*, and its bar is coloured by
  absolute headroom, so the normal ~20 KB is no longer shown as an alarm.
- Firewall in simple mode shows a summary of active rules instead of an empty page.
- Network: the hostname hint describes the actual behaviour (DHCP name and
  `name.local`; empty uses the board's own name, shown in the field) and the
  TTL override moved to the advanced settings; the LAN → Tailnet card is named
  *LAN → Tailnet service gateway*.
- Long values in status rows wrap at natural points instead of mid-word on phones.
- No guide opens by itself at sign-in any more: the roles chosen during setup
  are highlighted in *What do you want to do?*. The exposure acknowledgement
  of a guide is asked once per browser; new service rules still start disabled.
- New strings translated into Italian, Spanish and Simplified Chinese.

## [2.0.2] — 2026-10-23

### Fixed

- GitHub firmware installation could restart with a panic while beginning the
  update. Cache-sensitive flash operations now use the existing internal-stack
  admin server, separately from the HTTPS downloader's PSRAM stack, without
  reserving another task stack at the expense of VPN startup. This applies to
  both **Install latest update** and scheduled automatic installation.
- An affected 2.0.0/2.0.1 installation needs one manual firmware upload or USB
  update to receive the correction; keep existing settings when using USB.
- A firmware update could hang until restart when the admin server's internal
  work message was lost under low memory. The updater now notices an operation
  that never started, retries it once and then reports a timeout; an operation
  already running is always completed.
- Restore VPN startup memory headroom with the SDK's standard panic handler.
  Reset history and pre-crash capture remain; full reporting after an
  unrecoverable cache fault is best-effort.

### Preserved

- Existing settings, app identity, partition layout and update verification.
- English-only Web UI in the experimental W5500 image; WiFi translations stay.

## [2.0.1] — 2026-10-23

### Fixed

- First-boot setup could not pair on real hardware: every setup request was
  refused with "setup is only available through the device AP". The web
  server receives IPv4 clients as IPv4-mapped IPv6 addresses; the same defect
  made the sign-in attempt limit treat all clients as one address.
- The BOOT-button watcher of the setup could overflow its stack and restart
  the gateway, which also discarded the pairing in progress.
- A restart during setup after the Wi-Fi test (power loss, unplugging) could
  leave the gateway in normal mode without an admin password. The Wi-Fi test
  is no longer stored before Finish; the setup simply starts again.

### Added

- Each gateway answers to its own name on the home network,
  **esp32-tailnet-xxxx.local** (the code of its setup Wi-Fi), and uses it as
  its DHCP name unless a hostname is set. The setup summary and final page
  link to the address received during the Wi-Fi test and to this name.

### Improved

- Pairing window extended to 10 minutes, with clearer messages when the
  gateway restarted or the setup was opened in a second window.
- Crash diagnostics keep working when code cannot be fetched from external
  memory (panic handler in internal RAM).

### Changed

- The **experimental W5500** image serves the Web UI in English only, to fit
  the application partition with the new name responder. The WiFi image keeps
  the Italian, Spanish and Chinese translations.

## [2.0.0] — 2026-10-23

### Added

- ESP32 Tailnet Gateway — Mattboxx Edition identity, black/green artwork,
  documentation website and three installation paths: browser, Easy Install
  for Windows/macOS/Linux, and advanced firmware downloads.
- Physically paired first-boot wizard for an unconfigured ESP32-S3, with
  sealed setup requests, a user-created admin password and guided WiFi,
  Tailnet and role configuration. Existing installations retain their settings.
- Selective LAN → Tailnet destination tests, timed rules, Service Watch,
  rule guides, counters and sanitized rule transfer, separate from AP forwarding.
- Device registry and bounded Smart Recovery, layered health checks,
  connectivity guidance, configuration profiles and local diagnostic export.
- Responsive Simple/Advanced administration, capability-aware controls,
  MQTT/Home Assistant, ntfy events and operational SNMP metrics.
- Optional **experimental W5500 Ethernet** image with explicit hardware setup.

### Improved

- PSRAM-backed optional task stacks and a shared task reaper reduce internal
  RAM pressure across service start/stop cycles. VPN startup requests are
  coalesced and task-start failures are explicit rather than silently lost.
- Increase the MQTT manager's PSRAM stack headroom for synchronous transport
  error handling during WiFi reconnection.
- Original-packet authorization, bounded flow/fragment handling, API origin
  screening, persistent-setting validation and optional-service isolation.
- Existing Tailscale/Headscale, direct/DERP, subnet routing, AP gateway,
  exit-node roles, 4via6, firewall, WoL and user-controlled OTA are preserved.

### Migration

- Legacy bridge **0.1.38-Mattboxx-1.100** adds the 2.x version/update path while
  retaining the app identity, NVS namespace and partition layout.
- Repository renamed to `Mattboxx/esp32-tailnet-gateway`. Installations on 1.13
  or earlier that missed the bridge need one manual update with `firmware.bin`
  or the Easy Install keep-settings option; historical releases remain intact.
- Original Csontikka firmware and MicroLink credits and licenses are preserved.
  Version 2.0.0 identifies this edition, not an upstream firmware release.

## Development history incorporated into 2.0.0

### 0.1.38-Mattboxx-1.14-dev.8 — local stability correction, not released

- Move the optional SNMP task stack to PSRAM on supported builds, with matching
  SDK teardown, so a fragmented internal heap need not allocate its 4 KiB stack.
  The control block still requires internal RAM; failed starts remain explicit.
- Correct local SNMP qualification to walk all 109 current objects and detect
  worker-creation failures separately from generic allocation log messages.
- Preserve the stable OTA slot with explicit LAN-bound test transport and
  pinned-version/image/layout guards. No policy or authentication relaxation.

### 0.1.38-Mattboxx-1.14-dev.7 — local correction candidate, not released

- Request a fresh peer map when the streaming coordinator starts without
  current policy authority. Retry incomplete initial registration instead of
  declaring a usable connection based on cached peers or keepalives. Data
  authorization remains fail-closed; hardware reconnection qualification pending.
- Display pending policy separately from connected control transport in Status
  and Tailscale cards, including EN/IT/ES/ZH wording.
- Prefer current rule source-refusal evidence over shared destination reply
  observations; do not confuse a gateway destination test with LAN delivery.
- Harden local qualification tools: explicit Windows LAN probe interface,
  exact echo validation, honest interrupted-soak analysis, private no-reset
  capture, isolated Linux sanitizer runner and hidden password prompt.

### 0.1.38-Mattboxx-1.14-dev.6 — ESP32 Tailnet Gateway, local candidate

- Rename the product to **ESP32 Tailnet Gateway — Mattboxx Edition** (formerly
  ESP32 Homelab Gateway) with a new original logo, banner, diagrams and README.
  NVS namespace, app identity (`esp32_tsr`) and updater identity are unchanged.
- Service Gateway: per-rule destination test, Service watch, evidence-aware
  diagnosis, templates, guided setup and sanitized transfer.
- Configuration profiles with preview, binding token and rollback; capability
  manifest drives UI gates; optional-module supervisor.
- Web security: cross-origin/cross-site screening for every state-changing
  handler including login and logout, DNS-rebinding Host check without a
  password, device-wide login budget shared with the remote console.
- MQTT state budget and strict command parsing; ntfy system events; SNMP
  operational subtree; optional W5500 Ethernet uplink in a separate
  `esp32-s3-eth` build (not hardware-validated).
- Recovery access point returns 60 s after the saved WiFi disappears and
  stays until it is back.
- Web UI: one design system for old and new screens (standard button size,
  44 px touch targets, 16 px inputs on phones), Service Gateway rules as a
  table on desktop and cards on phones with an editor, a goal-based start,
  simple/advanced mode, an at-a-glance strip, and English/Italian/Spanish/
  Simplified Chinese with browser detection. The embedded page is minified
  at build time (about 25 KB smaller before translations).
- Hardware campaign fixes: a stream restart no longer suspends a complete
  Tailnet policy (hosted-control deltas were rejected and tunnel data blocked);
  login/logout now refuse cross-site requests.

### 0.1.38-Mattboxx-1.14-dev.5 — bounded fragments and health, local/unqualified

- Reassemble a bounded IPv4/IPv6 tunnel-ingress subset before original-address
  policy/NAT checks. Require current key, source ownership and policy generation;
  reject overlaps, stale/oversized/over-capacity input. Not full fragment parity.
- Block traffic on control transport loss; only a complete fresh identical map
  within 30 seconds can retain prior return-flow state. Explicit disconnect,
  invalid authority and changed policy still revoke state. No offline bypass.
- Disable stale operational UI actions on refresh errors and distinguish an
  unconfirmed/possibly partial WoL send from a confirmed local send or boot.
- Add OFF-by-default gateway TCP, DNS lookup and configured Internet/Tailnet TCP
  checks sharing the recovery worker. Persist settings, bound cadence/backoff,
  expose evidence/guidance, sanitized export, HA sensors and optional ntfy alerts.
  No default public target, application-health promise or automatic reset.

### 0.1.38-Mattboxx-1.14-dev.4 — operational integration, local/unqualified

- Add bounded related ICMP error handling and IPv6 option/atomic-fragment
  decoding; retain current key/ownership/return-flow authorization. Non-atomic
  tunnel fragments and unsupported headers remain denied, not silently widened.
- Refuse cross-origin browser writes in authenticated administration handlers.
- Add MAC-bound registry profiles and an explicit, cancellable, bounded WoL /
  TCP host/service recovery worker, IPv4 DNS/cache and local/Tailnet scopes.
- Add opt-in monitoring/resource admission, socket counts and policy-authority
  diagnostics. Optional jobs remain independent of routing and MQTT/ntfy.
- Add persisted LAN→Tailnet exposure leases with monotonic/clock/restart guards,
  changed-rule denial, explicit renewal/permanent action and retained closed
  records. Automatic deletion is not implemented in this increment.
- Integrate Devices & Recovery UI, Network lease controls, MQTT/HA state and
  recovery controls, opt-in ntfy commands/results, capability and sanitized
  operational export APIs. No automatic upload or mandatory public probe.
- Prepare one log-saving offline validation runner and additional actual-C /
  synthetic-browser tests. Final consolidated/hardware validation is pending;
  this entry is not a completed-roadmap or stable-release claim.

### 0.1.38-Mattboxx-1.14-dev.3 — bounded peer convergence, local candidate only

- Fix valid replacement at the 16-peer limit: remove revoked identities in the
  private policy candidate before upserts; reconcile the owning WG task before
  installation without increasing capacity or trusting cached keys for access.
- Suppress obsolete queued adds/removes against current authority. Propagate
  coordinator allocation/queue failures into a blocked full-map refresh instead
  of silently dropping work. Visibility is never a service-port permission.
- Match reference nonempty full-peer precedence and ignore authorization/peer
  mutations in keepalives. Preserve unrelated peers when an empty/null Peers
  field accompanies a genuine delta.
- Add actual-C peer/compiler/coordinator/manager regression fixtures with
  explicitly simulated WG installation, queue and NVS boundaries.
- Preserve the complete Master Prompt as a permanent development mandate,
  goals, dependency-ordered roadmap, implementation matrix and exact handoff.
- Add an opt-in external, read-only resource/continuity sampling tool. Its
  offline tests are not a physical soak or a policy-compliance claim.
- No push, flash, release, new firmware-facing feature or stable promotion.

### 0.1.38-Mattboxx-1.14-dev.2 — bounded Tailnet authorization, local candidate only

- Confirm and address missing per-port/protocol MapResponse enforcement in the
  pinned MicroLink receive path. Separate peer cryptographic/source ownership,
  locally owned destinations and inbound service authorization before NAT/4via6.
- Compile legacy and incremental named filters atomically with bounded PSRAM
  storage. Empty filters deny new inbound traffic; malformed, unsupported or
  oversized policy updates fail closed, including allocation failure.
- Invalidate authority and bounded return-flow state on new streams/reconnects;
  process peer revocations/AllowedIPs independently of the asynchronous WG queue.
- Add actual-C policy and receive-path regressions (mock crypto/netif), resource
  bounds, and a separate two-real-client validation procedure. This is not a
  claim of full Tailscale policy compliance or hardware qualification.
- No new user-facing feature, automatic policy bypass, push, flash or release.

### 0.1.38-Mattboxx-1.14-dev.1 — operational clarity, no new public release

- Rename product-facing documentation/UI to ESP32 Homelab Gateway — Mattboxx
  Edition, preserving repository URL, app identity, NVS layout and user names.
- Add passive LAN → Tailnet rule diagnostics, saved exposure path/source
  explanations and next steps. Do not equate installed mappings or counters
  with service reachability. No new task, probe, socket or automatic poller.
- New UI rules start disabled. Failed/malformed reads report unavailable,
  preserve draft fields and prevent an unknown-state save. Drafts do not retain
  misleading live-state labels. Add authenticated, no-store diagnostic fields.
- Save/export/restore only forwarding configuration, not read-only runtime
  diagnostics, keeping the saved request bounded independently of explanations.
- Publish WoL address-book changes only after successful NVS persistence;
  retain its original record layout, validate bounded records and malformed
  API fields, and synchronize lazy initialization/read/save paths.
- Strictly parse MAC octets/separators without signed or partial hex coercion.
- Distinguish a sent magic packet from verified power/service state.
- Correct the Ethernet support claim: no application driver/uplink integration
  exists. Document upstream ownership of SNMP/metrics and protocol features.
- Add code-backed product audit, architectural boundaries and prioritized
  roadmap. No stable promotion, OTA upload or factory flash accompanies this work.

## [0.1.38-Mattboxx-1.13] - 2026-10-20

Stable release of the 1.13 integration, with matching firmware/tag version
and eligibility for the opt-in stable update channel. Runtime source remains
the same as 1.13-dev.1; only the embedded version/build metadata changes.

- Integrate relay TLS certificate/hostname verification, WireGuard replay,
  key/handshake lifetime, nonce serialization, strict key/Noise parsing and
  monotonic timestamp corrections, retaining custom routing/reply hooks.
- Correct STUN measurement and relay reporting, preserve explicit policy,
  recover unanswered peer sessions and bound dead/stalled control sessions.
- Import v0.1.38's completion-waiting TCPIP netif lifecycle and copy-free TX,
  not the v0.1.37 teardown regression. Preserve custom startup/rollback and
  restart-based published-instance lifetime; guard local SD snapshots.
- Add authenticated WG TX profiling/diagnostic control with strict validation;
  expand relay measurement visibility to 32 entries.
- Add actual-C upstream integration regressions and keep existing feature,
  browser, routing, ntfy, SNMP and updater coverage.

See [source mapping, retained behavior and test scope](docs/upstream/UPSTREAM-0.1.38.md).
User-facing changes and download instructions: [release notes](docs/releases/RELEASE-1.13.md).

## [0.1.33-Mattboxx-1.12-dev.1] - stable promotion, 2026-10-20

- Mark the existing 1.12 beta GitHub release stable/latest at the maintainer's
  request, without rebuilding, changing the tag/assets or flashing the board.
  The retained dev.1 tag is intentionally ineligible for the current automatic
  updater; use manual OTA/download. Installed identical builds need no flash.
- A fresh authenticated Tailnet check observed 251,771 seconds of uptime;
  32 samples over a bounded 180-second check observed no reboot or integration
  disconnect. This is not a new multi-day continuous observation.
- Retain upstream v0.1.32/v0.1.33 fixes, persistent optional WiFi power save
  (OFF by default), all custom controls and original support/credit links.
- Make the NAS recovery use case and its hardware, power, network and WoL
  limitations explicit. Add a recovery checklist and community post drafts.
- Correct stale build-directory/download links, distinguish upstream board
  reports from current fork validation, and derive the flashing README's
  upstream version from the release instead of hard-coding v0.1.31.
- Remind reporters that logs still need manual redaction before publication.

See [stable release notes and verification](docs/releases/RELEASE-1.12.md).

### 0.1.33-Mattboxx-1.12-dev.1 — upstream fixes and optional WiFi policy (beta)

- Integrate all published v0.1.32/v0.1.33 runtime changes: reduce WireGuard
  logging overhead, support legacy manual exit-node DNS/NAT, guard partial
  DERP queue initialization and make the DERP connection wait interruptible.
- Add live/persistent WiFi modem-sleep control, preserving the fork's OFF
  default. Expose saved/runtime policy in UI, MQTT/HA and ntfy info, retain
  it in backups and report driver/persistence failures honestly.
- Offer a one-click, user-initiated Ko-fi payment window on desktop and
  a normal tab on mobile. No embedded payment form or third-party preloading.
- Preserve all Mattboxx features, upstream credits and the stable 1.11 release.
See [beta release notes and limits](docs/releases/RELEASE-1.12-dev.1.md).

## [0.1.31-Mattboxx-1.11] - 2026-10-13

- Add a quiet, optional Mattboxx Ko-fi tip button in the Web UI footer, README
  and GitHub funding menu. Keep all features free and original upstream credits
  and support links clearly separate.
- Use a plain outbound link with no embedded widget, remote assets, tracking,
  popups or background calls. Keep the existing dark theme; include mobile,
  keyboard and touch-friendly styling and suppress the device-page referrer.
- Retain all upstream v0.1.30/v0.1.31 and Mattboxx features and the verified
  1.10 startup/AP, relay-reply, SNMP and login fixes. The withdrawn 1.10 tag is
  preserved; the new version lets previously installed 1.10 devices update.
See [release notes and verified scope](docs/releases/RELEASE-1.11.md).

## [0.1.31-Mattboxx-1.10] - 2026-10-13

Withdrawn on October 13 before adding the Mattboxx support link. Source tag
retained; replaced by 1.11. This section records its runtime verification.

Stable promotion of the verified dev.18 runtime, with a stable version/tag and
no functional code change. Includes upstream v0.1.30/v0.1.31, opt-in GitHub
stable/beta/manual/automatic updates, ntfy transport/streaming improvements,
forwarding packet/configuration fixes and all earlier Mattboxx additions.
See [release notes and verified scope](docs/releases/RELEASE-1.10.md).

### Startup, AP control, relay replies and logins

- Create Microlink worker stacks largest first and hold coordination/cache
  work behind an all-workers-ready barrier. Clean up partial startup before
  bounded retries; show an explicit startup error instead of endless Registering.
- Reserve one static 8KB AP-policy worker at boot. Coalesce repeated requests,
  retain grace periods and retry mode changes without allocating new stacks.
  Suppress AP recovery during intentional restart/shutdown.
- Prefer PSRAM for the previous-boot log and ordinary buffers above 1KB;
  initialize the process-wide JSON allocator once before application workers.
  Keep DMA/task stacks internal and retain their original stack sizes.
- Separate authenticated direct-path activity from DERP activity. Receiving
  relay traffic no longer preserves a stale direct endpoint indefinitely:
  nonempty relay-delivered packets select relay replies immediately. Empty
  relay keepalives retain a recently healthy direct path. No session is discarded.
- Treat an unknown zero STUN baseline port as uninitialized, not symmetric NAT.
  Label the retained log Previous-boot log: a normal software restart is not
  evidence of a panic. Log numeric WiFi disconnect reasons and memory budgets.
- Add actual-C allocation/retry/endpoint regressions, two-restart device checks
  and opt-in private tunnel-counter diagnostics. Preserve every existing custom
  feature, upstream v0.1.31 alignment and saved settings. Dev.12–17 were local
  test candidates, not published releases; see the dev.18 validation record.
- Fix session eviction with the idle timer OFF: all expiries were identical,
  so every additional login replaced slot zero, even immediately after use.
  Track activity independently; prefer empty/expired slots, then true LRU.
  Keep four sessions, token validation, optional timeout and password unchanged.

### 0.1.31-Mattboxx-1.10-dev.11 — fix SNMP/Tailnet input recursion

- Resolve the reported alternating `ts_input_hook` / `wg_input_hook` crash.
  Periodic network and SNMP installers captured each other's input callbacks,
  causing unbounded recursion, stack exhaustion and a watchdog/panic restart.
- Remove the redundant transparent WireGuard input shim. Listener policy stays
  enforced by the IPv4-core wrapper; SNMP retains tunnel RX/TX counters and
  physical STA/AP ACL, TTL and MTU hooks remain unchanged.
- Test the actual SNMP and network installers together, not just individually:
  4,000 alternating refreshes, both installation orders, reconnect/address reuse,
  exact-once counting and 20 disable/enable cycles. The same test fails against
  the published dev.10 source before invoking the recursive callback chain.
- Add an opt-in long-running SNMP hardware soak with uptime and connection checks.
  Preserve all custom controls and configuration; this remains a beta candidate.

### 0.1.31-Mattboxx-1.10-dev.10 — preserve admin access and legacy AP rules

- Reserve both the running Web UI TCP listener and its next-boot configured
  port until restart. Saving a new web port cannot expose the still-active
  listener to AP-side or LAN-to-Tailnet DNAT rules.
- Put web-port conflict checking and NVS persistence in the same configuration
  transaction as both forwarding tables. Reject the exit-mode PeerAPI listener
  as an admin port too. Preserve the old port and report failure if saving fails.
- Do not install legacy TCP forwarding records over either admin listener.
  Keep their saved records; report a Tailnet listener conflict instead of
  replacing the management service.
- Validate JSON type, whole-number range and bounds before converting a web
  port to an integer. Reject null, strings, fractions and oversized numbers
  without modifying settings.
- Compact occupied legacy AP forwarding slots on load. Validate active flags,
  protocols, ports, bounded labels and duplicate listeners; ignore inconsistent
  tables without deleting NVS. Reject nonterminated labels on save.
- Add actual-C/cJSON request and persistence regressions, plus pthread-backed
  AP/web/Tailnet save ordering tests and live-listener installation checks.
  Preserve dev.9 packet handling and all earlier custom features. This is a
  development candidate; no stable/beta release or device validation is implied.

### 0.1.31-Mattboxx-1.10-dev.9 — reliable receive-DNAT packet handling

- Normalize fragmented TCP/UDP datagrams before the pinned ESP-IDF SDK applies
  receive DNAT. Enforce the installed listener policy on the complete datagram,
  rather than treating a later fragment's payload as a transport header.
- Add a private bounded reassembly pool keyed by input interface, protocol,
  source, destination and identification. Keep local-service/native reassembly
  separate; expire incomplete datagrams and reject overlapping or invalid pieces.
- Expire the private pool with allocation-free packet-time checks and a
  best-effort callback from the existing manager. A full callback queue or memory
  shortage cannot require a new per-packet timer or assert during its allocation.
- Validate minimum transport header lengths and coalesce split headers before
  the SDK reads or rewrites them. If memory is insufficient, release the packet
  without handing an incomplete header to NAPT. Preserve legitimate small first
  fragments, out-of-order arrival and fragmented TCP/UDP payloads.
- Enable IPv4 reassembly in the canonical build configuration. Reject builds
  using old generated configurations with reassembly disabled. Fragmented IPv4
  option headers remain unsupported, consistent with the pinned native reassembler.
- Add actual pinned lwIP/NAPT/pbuf regressions using synthetic interfaces, plus
  isolation, expiry, overlap and capacity tests for the private pool. Run the
  memory-instrumented suite in CI alongside the existing fork regressions.
- Preserve AP forwarding, LAN-to-Tailnet forwarding, MQTT/Home Assistant, ntfy,
  WOL, remote updates and existing saved settings. This development candidate
  is not a hardware validation or a new stable/beta release.

### 0.1.31-Mattboxx-1.10-dev.8 — serialize forwarding configuration transactions

- Serialize AP-side and LAN-to-Tailnet conflict checks, NVS writes/commits and
  in-memory publication with one static configuration mutex. Two simultaneous
  saves can no longer commit in one order and publish in the opposite order,
  or both reserve the same protocol/listen port across the independent tables.
- Keep a Tailnet ON/OFF command's read-modify-save operation in that same
  transaction, so simultaneous commands for separate rules preserve both changes.
- Snapshot both forwarding tables together for TCP/IP installation, rather than
  combining tables from opposite sides of a configuration publication. Release
  the configuration mutex before queueing a TCP/IP callback or mutating lwIP;
  retain the separate, immutable installed packet policy introduced in dev.7.
- Add pthread-backed actual-C concurrency regressions with a deliberately
  suspended NVS completion. Reproduce persistence/publication disagreement,
  lost ON/OFF changes and AP/Tailnet double reservations before fixing them;
  also check an installation racing a pending save. Run with ASan/UBSan in CI.
- Preserve NVS record layouts, existing rules, AP-independent Tailnet forwarding
  and all previous fork features. These software checks are not a device test,
  fragment-forwarding certification or a new stable/beta release.

### 0.1.31-Mattboxx-1.10-dev.7 — enforce forwarding policy at IPv4 processing time

- Move Tailnet listener enforcement from early Wi-Fi/WireGuard input callbacks
  to the TCP/IP core's IPv4 input, before the SDK performs receive DNAT. A packet
  queued before a rule is activated is checked against the installed policy
  when processed, not against a now-obsolete receive-time decision.
- Install NAT bindings and their source/interface restrictions from the same
  immutable table snapshot. Configuration/resolution tasks cannot change live
  permissions or the NAT response classification while old bindings remain.
- Associate install completion with its configuration generation and resolved
  destination; an obsolete callback cannot mark a newly saved rule as active.
- Preserve local AP DNS/services when AP NAPT is enabled, where the SDK does
  not apply receive DNAT. Keep Tailnet listeners restricted to the STA uplink
  when receive DNAT is eligible on another interface.
- Keep early ACL/counter/TTL/MSS hooks and the original queued input chains.
  Apply Tailnet-specific authorization once, on the core, and free denied
  packets without entering the SDK's IPv4/NAT processing.
- Add an actual-C core-wrapper/queue regression, reproducing the activation
  timing failure first. Cover saved-versus-installed policy, obsolete callback
  status, denied packet ownership, accepted return values, WG restriction and
  AP DNS behavior with NAPT ON/OFF. Retain existing packet, NVS and API tests.
- Preserve dev.6 and earlier fork features; no hardware/fragment-forwarding
  certification or new stable release is implied by these software checks.

### 0.1.31-Mattboxx-1.10-dev.6 — Tailnet forwarding policy and saved-rule validation

- Apply LAN-to-Tailnet listener filtering only to packets addressed to the
  receiving interface, matching the pinned SDK's receive-side DNAT condition.
  Same-numbered services on routed LAN/AP/Tailnet hosts remain independent.
- Inspect bounded header copies across pbuf chains instead of unaligned raw
  pointers into the first segment; preserve source-CIDR and installed-state
  checks and fail closed on an invalid stored prefix before any bit shift.
- Validate stored rule flags, protocols, ports, bounded labels/destinations,
  normalized source CIDRs, Tailnet literal destinations and duplicate listeners.
  Compact occupied slots; ignore an inconsistent whole table without deleting
  its NVS record or automatically broadening its source policy.
- Use a static rule mutex, removing the old unchecked heap-allocation path.
  Log failure to create the forwarding manager instead of silently ignoring it.
- Require an explicit JSON boolean for `enabled`; reject mistyped or omitted
  values instead of treating a string such as `"false"` as ON. Reject oversized
  destinations/labels before truncation and return HTTP 500 for storage errors.
- Add actual-C packet, NVS and HTTP/cJSON regressions. Reproduce destination
  interference, missing occupied slots and implicit enablement before fixing
  them; cover 53 pbuf splits, all valid prefix widths, 50,000 malformed packets,
  corrupted saved rules, failed writes, ON/OFF and HTTP/auth error handling.
- Preserve dev.5 and earlier fork features. This software-tested candidate is
  not a new stable release or hardware/fragment-forwarding certification.

### 0.1.31-Mattboxx-1.10-dev.5 — network hook and forwarding persistence fixes

- Identify the WireGuard input interface by its pinned driver's `wg` name
  as well as its Tailnet address. Never hook a CGNAT Wi-Fi, Ethernet or AP
  interface as a raw-IP tunnel; preserve the physical input/ACL chain.
- Keep the AP-side forwarding table unchanged until its NVS write and commit
  succeed. Failed saves cannot show or later install unpersisted rules.
- Publish and snapshot the AP table with a short cross-core critical section,
  without holding it across NVS, Tailnet resolution or lwIP operations.
- Remove stale AP/Tailnet bindings and clear installed status on a refresh
  with no STA address; restore the saved mappings when the uplink returns.
- Add actual-C regressions for delayed tunnel discovery on CGNAT uplinks,
  idempotence, input/drop chaining, NVS open/write/commit failures, in-flight
  rule visibility, subsequent refresh, port conflicts and uplink loss/recovery.
  Both new regressions reproduced failures before their fixes. Run with
  ASan/UBSan in CI; this candidate has not been flashed or hardware-certified.
- Retain all dev.4 update, ntfy privacy/transport and existing fork features.

### 0.1.31-Mattboxx-1.10-dev.4 — opt-in fork updates and ntfy transport/state hardening

- Disable Install latest update after a successful check finds no newer
  compatible release; re-enable it when an update is found. Preserve one-click
  initial installs and reject incomplete/invalid update-status responses.
- Prevent ntfy redirects from replaying bearer tokens, private notification
  bodies or command requests to another origin or downgrading HTTPS. Use the
  final ntfy server URL; redirect responses fail without executing commands.
- Reject ntfy token header-control characters and stop before network access
  if the Authorization header cannot be allocated. Anonymous topics still work.
- Discard obsolete ntfy poll replies after settings changes, including a
  disable/re-enable cycle, and recheck the offline-only policy before dispatch.
- Persist ntfy settings and their endpoint-bound command cursor in one validated
  NVS record; migrate legacy settings automatically and fail closed on corruption.
- Reject missing/unsafe/oversized command IDs and defer command execution when
  its replay cursor cannot persist. Keep encrypted token backup/restore working
  with the authoritative configuration; report storage failures as HTTP 500.
- Add actual-C settings-change, cursor-write failure, state reload and migration
  regressions. Commands already accepted may finish; this is not WOL cancellation.
- Fix ntfy command starvation when cached responses exceed 8 KiB: read complete
  JSON events progressively into a fixed heap batch and resume at its durable ID.
  Large notifications and metadata no longer require whole-frame allocation.
- Validate JSON nonrecursively with bounded nesting, UTF-8/Unicode escapes,
  duplicate-field and embedded-NUL rejection. Preserve command edge trimming;
  reject oversized commands while still advancing past their notification IDs.
- Add 200-command multi-poll replay, fragmented/large-frame/HTTP failure tests
  and 100,000 parser mutations compared with cJSON; run the parser with sanitizers.
- Remove local log reads/uploads from ntfy outage alerts, independently of the
  private-info setting. Alerts now contain a connectivity warning only. Keep
  local diagnostics and explicitly requested info/WOL responses available.
- Make the alert builder allocation-free and test that a synthetic private log
  marker is never read or published; correct the UI hint to match this policy.
- Default-OFF periodic GitHub checks, automatic install, stable/beta channels
  and optional device-local-time hourly window, with graphical System switches.
- Manual Check now and Install latest update perform asynchronous GitHub
  checks/downloads even when periodic checks are OFF. Local upload remains.
- Select only newer compatible Mattboxx releases, excluding drafts, upstream
  builds, unsupported assets, missing SHA-256 and excessive image sizes.
- Validate HTTPS certificates and redirect hosts, image chip/project/version,
  exact download length, SHA-256 and OTA image before committing the boot slot.
- Share exclusive flash-writer ownership between local and remote OTA. Abort
  failed writes; preserve settings and the running image; reboot only on success.
- Require a password-backed session for update policy/actions; expose diagnostic
  status in MQTT/Home Assistant and ntfy info without remote install commands.
- Keep old poller keys inert. Save new policy atomically under a separate NVS
  key; backup snapshots cannot silently activate unattended updates on restore.
- Add actual-C downloader failure/selection tests, sanitizer CI and UI scenarios.
  No board has been flashed or declared stable as part of this implementation.

### 0.1.31-Mattboxx-1.9-dev — upstream alignment

- Integrate published upstream v0.1.30 and v0.1.31, without importing later
  unreleased main-branch commits or removing Mattboxx features.
- Preserve known tailnet peer /32 priority on CGNAT uplinks while keeping
  non-peer local destinations, DNS resolvers and DHCP servers on the uplink.
- Serialize route supervision with the VPN lifecycle and execute netif/default
  and accepted-route publication in the TCP/IP task; retain cross-core snapshots.
- Port microlink's bounded netcheck shutdown, complete-stop cleanup and
  PSRAM-backed received IPv4 tunnel packet queue.
- Add separate exit-node DNS PeerAPI with GET/POST DNS wire messages, UDP-first
  resolver forwarding, TCP fallback and advertised Hostinfo services.
- Require a known peer and the local tunnel address for DNS; no public resolver
  fallback. Check registration failures and advertise only a running listener.
- Preserve custom Web UI ports; DNS uses 41181 when administration uses 41180.
  Reject new TCP forwarding rules conflicting with the active DNS port.
- Add exit-server/DNS runtime status to Tailscale settings, MQTT/HA and ntfy info.
  Keep saved exit policy separate from the running boot's NAT policy.
- Correct CGNAT NAT handling: only actual tunnel TCP egress skips translation;
  local CGNAT LAN egress honors subnet SNAT and exit-server masquerading.
- Increase the socket budget from 26 to 31; preserve the 1.8 ntfy stack fix.
- Add actual-C CGNAT/NAT and DNS authorization/parser tests, 50,000 decoder
  mutations, UI status tests and fixed-baseline feature-preservation guards.
- Build/test details and hardware limitations: [integration record](docs/upstream/UPSTREAM-0.1.31.md).

## [0.1.29-Mattboxx-1.8] — 2026-10-04

### Fixed

- ntfy HTTPS command reception reboot loop (`vApplicationStackOverflowHook`):
  separate no-inline worker/report/poll frames, heap-backed alert log buffer,
  12 KiB worker stack, checked task creation and minimum-stack diagnostics.
- Failed `info` publications now increment command errors instead of success.
  Oversized ntfy responses are rejected rather than partially assembled.
- Mutex-protected ntfy status and independent alert-result accounting.
- Panic popup points to the pre-crash log card in Diagnostics.

### Tests

- Exact-ELF frame budgets detect the old 1.7 regression; actual-C callback,
  command accounting, alert allocation/failure tests run with sanitizers in CI.
- Opt-in HTTPS/info hardware soak without logging private payloads.
- Coverage, limitations and downloads: [release record](docs/releases/RELEASE-1.8.md).

## [0.1.19-Mattboxx-1.4] — 2026-09-05

### Added

- Optional **exit-node advertising** publishes the standard IPv4 and IPv6
  default routes, automatically masquerades IPv4 Internet egress, requires
  normal Tailscale admin approval, and is exposed in the web UI, MQTT/Home
  Assistant and `ntfy info`.
- Exit-node server and client modes are mutually exclusive in the UI, API,
  MQTT control path and boot-time configuration recovery, preventing a
  tunnel routing loop.

### Fixed

- CPU load no longer remains at 0% on dual-core ESP32-S3 boards. Runtime
  statistics now compare both idle tasks with the aggregate capacity of both
  cores and tolerate tasks appearing while a sample is collected.

## [0.1.19-Mattboxx-1.3] — 2026-09-05

### Security

- Rate-limit old-password verification on the password-change endpoint even
  when the ordinary web login gate is disabled, closing an online guessing
  path for operators who intentionally expose the rest of the UI.
- Wipe plaintext password request buffers after first-time setup, password
  changes and remote-console authentication.
- Reject credentials and control characters embedded in MQTT/ntfy URLs so a
  password or token cannot be exposed later through URI diagnostics or logs.
- Scan every tracked file in the sensitive-data workflow, closing the
  multi-commit-push blind spot of checking only `HEAD~1`.

### Documentation

- Reworked the project landing page around its three gateway modes, complete
  Mattboxx feature matrix, privacy improvements and toolchain-free download.
- Renamed and retagged the GitHub project for clearer ESP32/Tailscale gateway
  discovery while retaining prominent upstream credit.

## [0.1.19-Mattboxx-1.2] — 2026-09-04

### Added

- A dedicated **LAN → Tailnet Port Forwarding** table exposes individual TCP
  or UDP services from a Tailnet peer on the ESP32 uplink address. It is
  independent of the ESP access point, supports Tailscale IPv4 and MagicDNS
  peer names, requires an allowed-source CIDR, and reports rule state/counters
  through the web UI, MQTT/Home Assistant and `ntfy info`.
- The web UI TCP port is configurable under System. Saves reject collisions
  with either forwarding table before changing any settings.
- `ntfy info` always lists saved WOL device names; MAC addresses remain behind
  the optional private-details switch.

### Fixed

- LAN → Tailnet rules no longer fail with `incomplete rule` when browser
  number inputs arrive as JSON strings. The browser now emits integer ports
  and the API also accepts strictly numeric strings for compatibility.
- Disabling the web password gate no longer dims the entire Web session card;
  the session-timeout controls remain readable and usable.
- The LAN → Tailnet regression test now uses the public API field name.
- Port-map startup logs now report the number of mappings actually installed
  instead of subtracting configured/disabled entries.

### Changed

- Normal browser login now uses a one-time PBKDF2/HMAC challenge. The costly
  password derivation runs in the browser and the ESP verifies the proof in
  about a network round trip. Plaintext login is accepted only for migrating
  legacy verifier records; modern records require the non-blocking proof path.
- Plain-HTTP login uses a specialised allocation-light PBKDF2-HMAC-SHA256
  fallback instead of SJCL's generic bit arrays. It keeps all 60,000 rounds
  while reducing the measured browser-side derivation from seconds to tens of
  milliseconds on a typical desktop.
- The web server now reserves socket capacity for DERP, ntfy, MQTT and DNS
  instead of allowing idle browser connections to exhaust the global lwIP
  descriptor table.
- The dashboard retries its first status read after login, avoiding a false
  `Unreachable` badge when the browser races a just-closed login connection.
- WiFi modem sleep is disabled and the socket pool is raised from 10 to 16
  for lower forwarding latency and reliable concurrent UI/MQTT/ntfy traffic.

## [0.1.19-Mattboxx-1.1] — 2026-09-04

### Fixed

- **Repeated web-UI unlocks no longer rerun the full password KDF.** The first
  successful login after boot still verifies the NVS record with 60,000-round
  PBKDF2-HMAC-SHA256. It then seeds a salted, RAM-only exact-match cache so
  later correct unlocks after an idle timeout return promptly. Cache misses
  still take the PBKDF2 path, and changing or clearing the password invalidates
  the cache.

## [0.1.19] — 2026-08-15

Stable release. Promotes the 0.1.19-beta1 DERP-liveness work to a stable
build after an eight-day beta bake; **no functional changes versus
0.1.19-beta1** (the only delta is the version string).

Bake evidence: the reference device ran 168 hours without a single reboot
or crash, during which the new control-plane map-stream watchdog caught and
self-healed **eight** silently dead map sessions — roughly one per day, each
one an outage that earlier firmware would have ridden out as a wedged
control plane until someone power-cycled the board. A second device on a
different continent ran the same build with no faults reported.

## [0.1.19-beta1] — 2026-08-07

**Beta pre-release** — DERP relay liveness. Ports the esphome-tailscale
v0.5.5 fix bundle and the HTTP/2 reassembly series into the microlink
submodule (reported and analyzed by timmills in esphome-tailscale#31/#32/#33,
bench-verified there), plus two earlier fixes those trees had and ours
didn't.

### Fixed

- **A dead DERP relay connection now recovers on its own.** Previously 3
  failed connect attempts parked the relay task forever with nothing left to
  re-arm it — the device stayed "connected" while relay-only peers could
  never reach it again. Now: endless exponential backoff (5 s → 60 s cap),
  a 90 s RX-liveness watchdog on a "connected" relay, and every connect
  failure path tears the TLS context down completely (each leaked ~17 KB
  before, eventually killing all later handshakes). (microlink submodule.)
- **ACL revocation reaches the device.** A full `Peers` list in a
  MapResponse is now authoritative — table entries omitted from it are
  swept, and peer removal also drops the NVS boot-cache entry, so revoked
  peers stay gone across reboots instead of resurrecting.
- **Large MapResponses no longer corrupt the long-poll stream.** HTTP/2
  frames that span a read boundary are reassembled instead of dropped
  (a big netmap deterministically desynced the stream parser).
- **Control-plane map-stream watchdog** (silent mapSession death behind a
  live HTTP/2 front end → automatic re-register within ~5 min) and the
  register-after-stream-read ordering fix — catch-up ports of
  esphome-tailscale v0.5.4/v0.5.2 fixes that predate this repo's submodule
  pin.
- `DISCO decrypt failed` now names the claimed sender and arrival path.

### Added

- **Per-cause reconnect counters in telemetry** (`rcs`/`rct`/`rcd`/`rcr`):
  map-stream watchdog fires, coord transport deaths, DERP RX-watchdog
  fires, and failed DERP connect attempts — so the fleet can distinguish
  watchdog saves from ordinary transport flaps (a single combined connect
  count overcounts).

### Known limitation

- The opt-in netcheck home-DERP override (`tailscale_netcheck_override`,
  default OFF) still announces the *configured* region in
  `NetInfo.PreferredDERP` while connecting to the measured one — peers
  would dial the announced region. Leave the override OFF (the default)
  until the announce-before-move rework (esphome-tailscale#36) lands
  upstream and gets ported.

## [0.1.18] — 2026-08-06

Stable release. Promotes the 0.1.18-beta1 changes (end-to-end Headscale
support, netmap via the streaming long-poll, discoverable first-boot AP) to a
stable build after a five-week beta bake with no regressions reported; no
functional changes versus 0.1.18-beta1. Also folds in the GCC 14 build fix
(#10): the false-positive `-Wmaybe-uninitialized` in ESP-IDF's
`esp_driver_i2c` is downgraded to non-fatal for that one component, so fresh
builds succeed on hosts whose toolchain trips it.

## [0.1.18-beta1] — 2026-07-03

### Added

- **Headscale support works end-to-end.** (#7) The login-server field now
  accepts `host`, `host:port`, `http://host[:port]` and `https://host[:port]`
  (TLS via the ESP-IDF public-CA bundle — Let's Encrypt works, self-signed
  does not), and the device fetches the control plane's Noise public key from
  `/key?v=88` instead of assuming the hosted-Tailscale key, so the ts2021
  machine-key handshake succeeds against Headscale. Validated live against
  Headscale v0.28.0 over both plain HTTP (`http://host:8080`) and HTTPS
  behind a Let's Encrypt proxy; the hosted-Tailscale path re-validated over
  both plain TCP and `https://controlplane.tailscale.com`. (microlink
  submodule; ports esphome-tailscale `5ecc5ee` + `9be7d81`.)

### Fixed

- **Netmap arrives via the streaming long-poll (Headscale ≥ 0.26).**
  Headscale only delivers the full netmap on a streaming map request — the
  old one-shot fetch got an empty response and reconnect-looped ("Empty
  MapResponse"). The initial netmap is now consumed from the long-poll
  stream; the hosted-Tailscale flow is unchanged.
- **First-boot AP is discoverable.** (#9) Default SSID renamed `myssid` →
  `ESP32-TSR-Setup`, the README now documents the default credentials and
  `http://192.168.4.1`, and boot prints the AP name + web-UI URL on serial
  at the default log level.

## [0.1.17] — 2026-06-11

Stable release. Promotes the 0.1.16 fixes (exit-node TAI64N handshake timestamps,
DNS-relay task-stack hardening, OTA beta-channel JSON buffer) to a stable build;
no functional changes versus 0.1.16.

## [0.1.16] — 2026-06-11

This release folds in the fixes that had only been serial-flashed since 0.1.12
(0.1.13–0.1.15 were test builds, never published).

### Fixed

- **Exit node now establishes itself reliably (WireGuard handshake timestamps).**
  The handshake's TAI64N timestamp is now sampled from the SNTP wall clock on every
  emit, instead of a per-boot counter that could fall behind the value a peer had
  already stored and get every initiation silently dropped as a replay. The ESP now
  brings up an exit-node tunnel on its own and self-heals across reboots, so AP
  clients keep their internet through the exit node. (microlink submodule.)
- **DNS relay no longer crash-loops at boot under verbose logging.** The relay
  listener/worker task stacks were enlarged (to 8 KB) so enabling INFO-level SD
  recording at boot can no longer overflow them into a panic loop.
- **Firmware-update check on the beta channel no longer fails to parse.** The
  `/releases` JSON the beta channel scans had grown past the 32 KB download buffer
  and was being truncated, so "Check now" reported `parse failed (no firmware.bin
  asset?)` even though every release ships the asset. The buffer is now 128 KB.

## [0.1.9] — 2026-06-04

### Added

- **Source-NAT advertised routes** — an opt-in toggle (Tailscale settings, off by
  default) that masquerades tunnel→LAN forwarded traffic to this device's uplink
  IP, the way Tailscale's `--snat-subnet-routes` does. With it on, advertising the
  uplink subnet makes that LAN reachable from the tailnet out of the box (the
  upstream router no longer needs a route back to the tailnet). Enabling it offers
  to add the live uplink subnet to the advertised routes.
- **Subnet prefix in the Status cards** — the Uplink and Access Point cards now
  show the address with its CIDR prefix (e.g. `192.168.4.1/24`, `192.168.32.1/24`).
- **Factory-reset dialog recommends a backup** — the confirmation now highlights
  that you should download an encrypted config backup first, with a one-click
  "Back up first" link into the backup flow.
- **Project logo in the header** — the web UI nav brand icon now uses an inline
  chip + WiFi mark (crisp vector, stays sharp at small sizes) instead of the
  generic placeholder icon.
- **Mascot in the Support card** — a small hand-drawn mascot next to the
  "Buy me a coffee" button, centred with it.

### Changed

- **OTA version compare is pre-release-aware** — the updater now follows SemVer
  pre-release precedence (`0.1.9-beta1 < 0.1.9-beta2 < … < 0.1.9`), so a device on
  one beta is offered the next beta and the final stable release supersedes every
  beta of that version. Beta builds carry the pre-release tag in their version
  string. Previously the suffix was ignored, so successive betas of the same
  `x.y.z` were never offered.

## [0.1.8] — 2026-06-03

### Added

- **OTA beta channel** — an opt-in toggle (System → Firmware update) that makes
  the updater also offer GitHub **pre-releases** (highest semver wins), so test
  devices can pull beta builds before they go stable. Off by default, so
  production devices keep tracking only stable releases (`/releases/latest`).
  Promote a beta by publishing it as a full (non-pre-release) release.

## [0.1.7] — 2026-06-03

Reliability-focused early-access update: over-the-air updates are now
dependable, crash reports are actionable, and the Tailscale client (microlink)
is consolidated. No breaking changes — settings and tailnet identity are
preserved across the update.

### Fixed

- **OTA updates are now durable** — the running image marks itself valid after a
  healthy boot, so the bootloader rollback no longer reverts a fresh update on
  the next reboot.
- **OTA downloads from GitHub Releases succeed** — the updater's HTTP buffer was
  too small to hold the release-asset redirect header (it failed with
  `ESP_FAIL`).
- **A failed OTA no longer crashes the device** — the install path used to panic
  and reboot on any download error (risking a loop with auto-install enabled); it
  now surfaces the error and keeps running.
- **Crash signatures are debuggable** — panic reports captured only the generic
  `abort()` frames; they now record the backtrace through to the real fault
  (Diagnostics → Reset history, and telemetry).

### Changed

- **AP channel is read-only**, auto-following the uplink channel (single radio).
  Removed the non-functional manual channel control and the dead "Disable web
  interface" placeholder.
- **microlink** consolidated onto a single maintained line.
- **Telemetry hardened** — the anonymous device hash now carries an integrity
  check so the collector can drop spoofed/garbage events; the collector keeps
  only coarse country/region and never stores a raw IP.

### Known limitations

- **Headscale does not currently work** — the ts2021 control-plane Noise
  handshake fails (tracked in
  [#7](https://github.com/Csontikka/esp32-tailscale-subnet-router/issues/7));
  supersedes the "untested" note in 0.1.0. Hosted Tailscale is unaffected.
- Carried over from 0.1.0: single 2.4 GHz radio (channel realign after a roam),
  MCU-class throughput, tailnet lock unsupported.

## [0.1.0] — 2026-05-31

First public early-access release. The firmware turns one ESP32-S3 into
a WiFi NAT router and a Tailscale subnet router, configured entirely
from a built-in web UI.

### Added

- **Dual role**: simultaneous WiFi STA uplink + AP (NAPT, DHCP, DNS
  forwarder) + Tailscale subnet router.
- **Tailscale stack** via [microlink](https://github.com/Csontikka/microlink):
  DISCO discovery, direct paths with DERP relay fallback, NAT traversal,
  exit-node client and gateway, DERP-aware automatic MTU.
- **Exit-node aware routing** with fail-closed behaviour, and DERP
  re-handshake on the WireGuard data plane so an exit-node session
  survives a direct↔DERP transition.
- **ACL firewall**: four hook points (Internet↔ESP, Clients↔ESP),
  first-match-wins rules by protocol / CIDR / port / action, per-rule
  hit counters.
- **DNS forwarder** for AP clients with a PSRAM-backed response cache,
  worker pool, and cache stats.
- **Diagnostics**: on-device ping, traceroute, route-explain, a 1 MB
  download/upload speed test (cancellable), live WiFi scan, and a
  microSD "flight recorder" for control-plane stalls.
- **DHCP**: reservations, live lease table with per-client signal, MAC
  denylist; **port forwarding**.
- **Web UI**: responsive single-page admin served from the device —
  first-run password setup, WiFi join, tailnet enrolment, firewall,
  diagnostics, system.
- **Operations**: encrypted config backup/restore, OTA updates, per-sink
  (console + SD) log levels with an INFO ceiling, pre-crash log capture,
  auto AP-channel realign on STA roam.
- **Anonymous telemetry** (on by default, one-toggle opt-out): daily
  salted one-way device hash + boot/flash counters + reboot/crash cause +
  firmware/chip/uptime; no SSIDs/IPs/MACs/tailnet/peers. Fully inspectable
  in `main/telemetry.c`.
- **Project hardening**: SECURITY policy, CodeQL (C/C++ + Python),
  Dependabot, secret scanning, and a custom Sensitive Data Check.

### Known limitations

- Single 2.4 GHz radio shared by STA and AP (channel realign needed
  after an upstream roam).
- MCU-class throughput (a few Mbit/s through the tunnel).
- **Headscale is untested**; only hosted Tailscale has been validated.
- Tailnet lock is unsupported.

[Unreleased]: https://github.com/Csontikka/esp32-tailscale-subnet-router/compare/v0.1.9...HEAD
[0.1.9]: https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.9
[0.1.8]: https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.8
[0.1.7]: https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.7
[0.1.0]: https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.0
