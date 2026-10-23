# Architecture decision ledger

Decisions are explicit, revisable with evidence and never remove approved scope.

## ADR-030 — Remote OTA separates HTTPS and cache-sensitive flash work (2026-10-23)

ESP-IDF 5.5.3 requires an internal-RAM stack when it freezes caches for flash
mapping. The GitHub downloader's 16 KiB PSRAM stack therefore cannot safely
call OTA operations, including the metadata mapping in `esp_ota_begin`.
Moving the entire TLS stack into scarce internal RAM is not an acceptable fix.

`ota_flash` reserves a 4 KiB internal stack, static TCB, one mailbox and static
synchronization objects at boot. The HTTPS worker synchronously dispatches slot
lookup, begin/write/end/abort, boot selection and restart to that task. No jobs
are allocated, and its runtime stack-domain check fails closed without a
caller-stack fallback. Admission is bounded; accepted operations retain their
borrowed data until acknowledged. Consuming end/abort calls wait for ownership
instead of abandoning a live SDK handle on an admission timeout. Stack/resource
measurements belong to exact-image qualification, not estimates of TLS needs.

The existing global OTA writer exclusion, image identity/chip/version checks,
HTTPS verification, redirect allowlist and SHA-256 verification are preserved.
The local HTTP upload remains a separate path on the internal HTTP server
stack. An already affected installation must use local upload or USB once to
receive the fix; its old GitHub install path cannot repair itself.

## ADR-029 — First-boot setup: open AP, physical pairing, sealed requests (2026-10-23)

The owner asked for an AP + captive-portal first boot with no default admin
password. A secured setup AP would need a pre-shared secret the board cannot
show (no display or label), so the setup AP is open but only on a truly
unconfigured device (no admin password, Wi-Fi, tailnet key or `setup_done`
marker); every existing installation writes the marker once and never opens it.
Abusive configuration is blocked by physical presence (BOOT button, or an
8-digit console code with five attempts per boot), one pairing at a time.
Interception is blocked by an X25519 session key and AES-256-GCM sealing of
every setup request with an increasing sequence; plain WebCrypto is not
available on http, so the page uses the bundled SJCL for GCM/SHA-256 and a
TweetNaCl-derived X25519, the firmware MicroLink's X25519 and mbedTLS. All
other APIs answer 403 in setup mode and the AP forwards nothing. The final
apply saves the protected AP and the admin password first, then the rest, then
the marker, and restarts. Residual risk accepted and documented: an attacker
present during setup can impersonate the AP and serve a modified page. The
recovery AP is unchanged and always protected. Existing `/api/auth/setup`
stays for configured devices without a password (1.13 behaviour) but is
refused in setup mode. Flash cost about 30 KB (WiFi 97.1 %, Ethernet 99.9 %).

## ADR-028 — WithCaps workers exit through a persistent reaper (2026-10-23)

ESP-IDF 5.5.3 `vTaskDeleteWithCaps(NULL)` (a task deleting itself) creates a
temporary clean-up task with an internal `configMINIMAL_STACK_SIZE` stack at
that moment and calls `abort()` if the allocation fails. The SNMP worker, the
exit-route supervisor, the DNS relay worker and, with ADR-027, the esp-mqtt
worker and `ts_connect` all exit that way, so an ordinary disable or stop on a
fragmented internal heap could reset the device. `components/task_reaper`
creates one reaper at boot (PSRAM stack, internal fallback, static queue of
8). An exiting worker queues its own handle and suspends; the reaper deletes it
with `vTaskDeleteWithCaps(handle)`, which suspends, deletes and frees without
allocating. A full queue or a missing reaper falls back to the SDK path and is
counted (`/api/operations`: `task_reaper_pending`, `task_reaper_fallbacks`).
Tasks created without caps keep `vTaskDelete`. Actual-code host tests cover
init, fallbacks, queue bound and direct deletion; hardware exits (SNMP OFF,
MQTT OFF/reconfigure) must be qualified on the installed image. The version
moves to dev.10 so this image is never confused with Codex's dev.9 build.

## ADR-027 — Scoped task-memory adaptation for MQTT and VPN startup (2026-10-23)

Dev.8's 3456-byte largest internal block cannot satisfy the SDK MQTT worker's
6144-byte internal stack. Its optional manager and the 4096-byte VPN startup
task also competed for internal stacks. Use the paired SDK caps allocation /
deletion APIs with PSRAM stacks on the supported N16R8/XIP build; TCBs remain
internal and failures remain possible. No smaller stack or global allocator
override. esp-mqtt has no task-capabilities setting in this pinned SDK, so a
project-local adapter is applied only to that component. A source hash guard
requires reviewing ownership before upgrading it; both pinned and unpinned
task paths and the sole self-delete were reviewed and behavior-tested with
host fixtures. No SDK file is changed. Tracked defaults enable external stacks.

Reserve VPN startup before spawning and skip it after instance publication.
This removes duplicate GOT_IP allocations while leaving coordinator reconnect
and policy authority to MicroLink. Allocation failure is logged and releases
the reservation for a later request; existing startup backoff remains bounded.
Hardware runtime activation, stack margins and stability need separate evidence
for this exact new image; host tests do not establish physical safety.

## ADR-026 — Package the exact tested image; builds are not bit-reproducible (2026-10-23)

Four consecutive links of unchanged dev.8 sources produced four different
`.flash.text` sizes (1,178,720 / 1,178,548 / 1,178,324 / 1,178,328 B) and
hashes, also with `PYTHONHASHSEED=0`. The verbose link commands contain the
same 372 arguments in a different library order. That order comes from the
PlatformIO espidf builder (`find_lib_deps`), outside this repository. The
symbol set and types are identical (12,410 symbols); only placement changes,
and with it the Xtensa linker relaxation (`call8` versus `l32r`+`callx8`,
narrow versus wide instructions). The bootloader, partition table and OTA data
images are reproducible.

Decision: a package contains the byte-identical image that was installed and
tested, never a rebuild of it. `package_release.py` already refuses a build
whose `firmware.bin` differs from `--tested-sha256`; for a candidate whose build
directory has since been relinked, stage the saved snapshot with the same-source
bootloader/partition/OTA data and build description, and record that staging.
Any rebuild, including a version-string change for a stable release, is a new
image that needs its own install and qualification. Do not patch the
third-party PlatformIO builder in place. Library order within one
`--start-group` is not a functional dependency today; if duplicate global
definitions are ever introduced, the varying order could select a different
one, so the identical-symbol check stays part of the comparison.

## ADR-025 — Optional SNMP stack uses PSRAM on supported builds (2026-10-23)

Dev.7 physically failed its 4096-byte internal task-stack allocation while the
largest observed internal block was 3328 bytes. Move that stack, not its TCB,
to PSRAM using the SDK caps create/delete pair when external stacks are enabled.
Do not fall back to consuming scarce internal routing memory on those builds.
Keep existing OFF/configuration/failed-start semantics and bound buffers. Actual
helper tests cover both compile-time paths, OOM reservation release and matching
deletion; both targets compile. Dev.8 real v1/v2c walks, malformed rejection and
three enable/disable cycles pass with original settings restored. Longer stack/
cache/resource qualification remains separate; this does not guarantee all task
allocation failures are eliminated. Evidence: DEV8-VALIDATION.md.

## ADR-001 — Preserve the complete mandate and stable identity (2026-10-21)

Status: accepted. Archive the user's Master Prompt verbatim; map every section
and required feature into goals/roadmap/matrix. The older five-idea selection
is superseded: temporary rules, sanitized export and Ethernet are approved
future work, not discarded. Keep the six functional areas without forcing a
large framework rewrite. Preserve branding, NVS/app/update identity, attribution
and public stable; no implicit remote rename, publication or flash permission.

## ADR-002 — Qualification is not source implementation (2026-10-21)

Status: accepted. Compilation, UI, mocked crypto, synthetic pbuf/netif/NVS/OTA
and native sanitizers have separate evidence classes from two real principals
and actual ESP tests. Record exact source/image and test scope. Missing hardware
cannot justify a false success or stopping all independent roadmap work.

## ADR-003 — Bounded peer replacement without a permissive window (2026-10-21)

Status: accepted; implemented and offline tested in dev.3, hardware pending.
Reproduced policy rejection and lost WG installation at the 16-peer limit.
Remove before upsert in the private candidate, matching the reference
[mapSession semantics](https://github.com/tailscale/tailscale/blob/main/control/controlclient/map.go);
same-ID upsert wins, nonempty full Peers excludes deltas and KeepAlive cannot
mutate authority. Empty/null Peers with genuine deltas preserves other peers;
the existing standalone-empty conservative clear remains an explicit extension.

The owning WG task prunes obsolete keys from its cache before adds and even
with no queued jobs. Current immutable membership rejects obsolete add/remove
jobs; unknown authority retains fast-boot cache but never admits packets.
Initial/stream map application propagates parser allocation/queue failures,
resets policy and requests a complete refresh. Do not increase peer slots or
use membership as per-port authorization. Endpoint/metadata freshness and
full live interleavings are not solved by this key-membership guard.

Actual-C policy plus extracted coordinator/manager functions pass native and
ASan/UBSan fixtures, including all 32 addition allocation/queue failures.
WG add, NVS storage and queue scheduling are sinks, not hardware evidence.
Policy remains 27,080 PSRAM bytes; no new socket/task/NVS key. The 288-byte
removal job is stack-local; target prune frame is 320 bytes, not a whole-stack
high-water guarantee. Runtime overhead/headroom remain unmeasured.

## ADR-004 — Conservative protocol gate is temporary, not compatibility (2026-10-21)

Status: accepted limitation, implementation pending. Dev.2 blocks unsupported
fragments/extensions/ICMP errors/other protocols. Keep that safety boundary
until bounded, reviewed, positively tested support exists. Develop fragment/
PMTU and precise transport-outage semantics as P0 work. Do not call blanket
denial full Tailscale compliance or introduce unauthenticated ICMP exceptions.
The current reconnect reset must be reviewed for unnecessary availability loss.

## ADR-005 — External observation cannot qualify unseen behavior (2026-10-21)

Status: accepted; tool offline tested, physical collection pending.
Reuse existing authenticated GET diagnostics and a strict output allowlist
instead of adding a new firmware polling task. Default status cadence is 60 s,
diagnostics every fifth sampling slot; requests are serial and duration bounded.
Do not save raw JSON/exceptions/identifiers/credentials or overwrite reports.
The control status is not data-plane health; socket limits are not usage;
unknown metrics stay null; stack units remain raw until verified. Version
mismatch stops collection and sampling gaps are counted. Successful collection
does not imply stable, secure, uninterrupted or load-qualified firmware.

## ADR-006 — Related ICMP is evidence, not a blanket exception

Dev.4 requires current key/source/local ownership and exact sent quote tuple/
epoch for incoming errors; errors never refresh state. Header walking is bounded;
non-atomic fragments/routing/AH/ESP/unknown options stay denied. Host subset
tests pass, not full PMTU/NAT/4via6 or official policy parity.

## ADR-007 — One optional worker and MAC-bound registry sidecar

Preserve WoL layout and persist metadata before RAM. Snapshot authorized MAC/
target into one bounded job, lazy PSRAM worker/probe, cooldown/check/deadline/
cancel and finite DNS. Guard thresholds are uncalibrated; no hard reservation
or application/power-health claim. Routing never depends on optional services.

## ADR-008 — Leases close first, never silently retarget

Dev.4 checks monotonic deadlines on packet admission, UTC at boot/tick, exact
rule binding and known storage. Unknown or changed authority denies. Closure
is latched before persisting with bounded retry; failed NVS cannot reopen RAM.
Keep expired records until explicit renewal/permanent action. Automatic delete
requires safe shared rule/lease reindex ownership, not unsynchronized saves.

Dev.5 amendment: positional lookup was insufficient—an expired binding moved
to an empty slot became permanent in the reproduced host test. Leases now form
a strict identity ledger. First opt-in snapshots current permanent bindings;
new/edited bindings require explicit confirmation. Migration of an existing
timed v1/v2 table does not invent the identity of untracked rules. v3 adds an
optional delete mask; expiry closes first, then the existing forwarding owner
can persist one compacted table transaction. Retain tombstones; recycle only
under an explicit configuration action. Failed housekeeping backs off 60 s.
MQTT rule commands include the expected binding and check it within the same
configuration transaction; legacy index-only commands are intentionally rejected.

## ADR-009 — Reassemble owned plaintext, then authorize the whole datagram

Dev.5 uses two bounded PSRAM slots, current key/source/local ownership plus
policy epoch, five-second lifetime and strict overlap denial. No borrowed pbufs
or lwIP/TCPIP-core reassembly state cross the manager task boundary. The final
RX gate checks original addresses/protocol/ports before translation. This is a
4-KiB ingress subset, not broad IPv6/fragment/TX/PMTU compatibility. All real
crypto/direct/DERP/IPv6/NAT interoperability and target resource costs remain gates.

## ADR-010 — Transport suspension is distinct from revocation

An outage/new stream blocks data immediately. Only a complete freshly compiled
identical authority map within 30 s may retain existing return tuples, whose
own timeouts continue. Malformed authority, explicit disconnect and changed
permissions reset state; cache/keepalive/delta cannot resume it. Do not claim
offline operation or eliminate the real server/reconnect qualification gate.

## ADR-011 — Layered health is bounded evidence, not global availability

The existing optional operations worker serializes one configured check with
recovery, default OFF and no public target. Persist health separately without
changing registry/WoL layout. Typed reasons/next steps distinguish local address,
gateway, lookup, control, authority, cache and TCP outcomes; leave route approval
and global data plane unknown. SDK DNS can be cached and delay manual work until
its finite lookup returns. Backoff, generation checks, sanitized state, HA and
best-effort configured ntfy notifications must not become routing dependencies.

## ADR-012 — Open administration needs a trusted Host, not only same origin (2026-10-22)

A DNS-rebinding page is same-origin with its own Host, so Origin equality alone
does not protect a device without a web password. Every request screened by
`require_auth`, initial setup, login and the secret-session gate refuses
mismatched Origin and cross-site fetches on writes. When no password gates
access (and always for initial setup) any method also needs a Host that a public
rebinding attacker cannot serve: IP literals, single labels and non-public or
Tailscale suffixes (`web_host_trusted`). Custom public domains then require a
web password; the 403 says so. Native clients omitting headers stay supported.
A device-wide failed-login budget (10 burst, one per 3 s) complements per-client
backoff so cycling addresses cannot reset guessing; under sustained attack the
operator also waits, but nothing is persisted or permanently locked. This is
not authentication, TLS or proof against an on-path LAN attacker.

## ADR-013 — Profiles are enable-only presets with a token-bound preview (2026-10-22)

Profiles reuse the existing setting owners (operations settings, Health
Monitor) and never get their own copy of configuration. A profile may only
switch ON device monitoring, service-expiry notifications or the Health worker;
it never disables, deletes or opens exposure (routes, exit node, AP, forwarding
stay manual steps with their own confirmation). Resource Guard is excluded: its
uncalibrated thresholds could defer optional services silently. Apply requires
the preview token (profile + current values + record generation), persists a
checksummed backup record before any change, undoes a failed apply, and records
any setting it could not undo. Rollback is one level and restores only settings
the profile switched on that are still on. Invalid records mean "no profile, no
rollback". Physical NVS power-loss behavior is not qualified.

## ADR-014 — Wizards guide existing forms instead of duplicating writes (2026-10-22)

Each of the 12 guides is a data row (goal, live read-only prerequisite checks,
risks, exposure flag, target form fields, optional verification). Writes stay in
the existing validated forms and endpoints, so there is one write path per
setting. Exposure guides (subnet router, exit node, LAN to Tailnet) cannot start
without an explicit acknowledgement. On start the guide snapshots the touched
non-secret settings with the same transforms as the backup export; "check
result" shows a secret-free diff and "restore" re-posts that snapshot in
reverse order. Secrets are never read or rewritten by a guide. A guide's
verification is evidence about one layer, never a guarantee of reachability.

## ADR-015 — Service Gateway first; destination test on request (2026-10-22)

Owner decision: the Selective Tailnet Service Gateway is the primary feature,
Remote Recovery & Diagnostics the second pillar, the rest complementary. No
repository, firmware, NVS or updater identity changed. Its verification is an
on-request destination test: the ESP32 opens one bounded TCP connection
(2 s) to the rule's Tailnet destination from the existing operations worker,
one at a time, 5 s cooldown per rule identity (`service_lease_token`). Because
forwarded clients are translated to the gateway's identity, this exercises the
same remote leg and ACL; it does not test the LAN client's path, the local
source filter or the application, and UDP is reported unverifiable. Results
bind to the rule identity, so edits hide stale evidence; it works for disabled
rules so a service can be verified before exposure is enabled.

## ADR-016 — Reply evidence comes from admitted return flows (2026-10-22)

The policy gate already keeps bounded return flows for traffic this node sent.
A flow now records when a reply was actually *admitted* (normal RX path only;
related-ICMP quotes do not count; a reused slot clears it). A read-only query by
protocol, remote IPv4 and port returns the newest current-epoch reply age and
nothing while suspended. It is evidence, never a grant, and not per LAN client.
Per-rule last accepted/rejected stamps are uptime seconds set under the
forwarder lock on the TCP/IP path (no extra I/O). No new task, socket or timer.

## ADR-017 — The MQTT state degrades to fit, never silently fails (2026-10-22)

The retained QoS1 state shares an 8 KiB client outbox. A host measurement of
the actual rule array showed 8 worst-case rules alone take 3,783 bytes, so a
full state could exceed it and never be delivered. The state is now fitted to
6,144 bytes: level 1 drops detail the Web API still serves (device list,
events, duplicate leases); level 2 publishes rules without names, destinations
and ports. Every field a Home Assistant template reads is kept, and
`state_compact_level` tells consumers. A still-oversize state is published
and logged, never dropped silently or retried in a loop.

## ADR-018 — ntfy system events are opt-in and downgrade-safe (2026-10-22)

Boot (firmware and reset reason), "Tailscale restored" (only after an outage
alert was actually delivered) and "update available" (announced once per
version, never installed) are sent by the existing ntfy worker, one message per
event with a 60 s retry and nothing queued while disabled. The switch lives in
a separate NVS key: the versioned ntfy record keeps its flag mask, so stable
1.13 still accepts it after a downgrade and simply ignores the new key.

## ADR-019 — Ethernet is a separate, explicit build and fails closed (2026-10-22)

The W5500 SPI driver costs about 61 KiB of app flash (measured: 92.9% to 95.7%
of the slot), too much for an option most boards cannot use, so release images
stay WiFi-only and `env:esp32-s3-eth` adds the driver; one source tree, same
app/NVS/updater identity. Runtime is OFF by default with explicit pins and
validated settings applied at boot. The netif is prepared before the ACL hooks
are installed and started only after them. Uplink choice reuses the route
supervisor (and event-driven updates when Tailscale is off): "legacy" when
disabled, otherwise WiFi-first or Ethernet-first with a three-sample stability
window. While creating the second environment we found the shipped sdkconfig
diverged from `sdkconfig.defaults` in four options inherited from IDF 5.3.1;
they are now pinned so fresh checkouts build the same image.

## ADR-020 — One password-guessing budget for every channel (2026-10-22)

The failed-login budget now lives in the shared `web_password` component and is
charged by the web login, password change and the TCP remote console; an
exhausted budget refuses the console before any password check. The console's
"VPN" binding now means the connection arrived on this node's tunnel address
(a 100.64/10 local address that is not the STA, AP or Ethernet address), not
that the client address looks like 100.64/10, which CGNAT-addressed LANs
(LTE/Starlink) would satisfy.

## ADR-021 — Service watch reuses the destination test slot (2026-10-22)

The opt-in watch adds no task, timer or socket: when due, the operations
worker queues the next enabled TCP rule into the existing single destination
test slot (never displacing a manual request). Only handshake outcomes move its
two-miss/one-recovery state; tunnel, policy and resource states are not service
evidence. Settings live in their own validated NVS blob; missing or invalid
means OFF. Notices are best-effort through ntfy/MQTT and never change rules.

## ADR-022 — Optional workers are re-started by the operations worker (2026-10-22)

If the MQTT or ntfy task cannot be created (typically low internal memory at
boot), the PSRAM operations worker is started and retries the missing worker
after 60 s, doubling to 15 minutes, until both run; `module_restarts` counts
successful restarts. No task, timer or internal RAM is added for supervision,
routing and the Web UI never wait on it, and a module that is merely
disconnected (not crashed) keeps its own bounded retry. ntfy init became
retry-safe (it no longer recreates its mutex).

## ADR-023 — Recovery-only AP returns after 60 s without the saved WiFi (2026-10-22)

Owner request. With the client AP switched off (recovery-only), a lost uplink
now arms a 60 s window before the AP is re-enabled instead of 100 ms; the AP
then stays on until the uplink has an address again. Disconnect events
repeated by STA retries never postpone the deadline, and a reconnect inside
the window cancels it, so brief drops do not toggle the AP. Boot is unchanged
(AP up until the first connection) and always-on mode is unaffected.

## ADR-024 — Fresh authority before reconnect completion (2026-10-22)

Real dev.6 soak showed a server-ended map session followed by an empty fetch
and a timed-out initial stream. The control socket became connected while
policy stayed suspended; authority returned only after a later full map, about
five minutes after the loss. Cached peer visibility and DERP are insufficient.

Streaming MapRequest now omits peers only if current complete authority is
already active. An unavailable/incomplete initial map follows coordinator
reconnection/backoff, not CONNECTED publication. Existing policy suspension,
epoch/revocation and complete-map checks are unchanged. No extra allocation,
task or timer. Status/Tailscale show pending authority separately if observed.
Actual coordinator branch/request host tests (mock transport) and Linux
sanitizers pass; real Tailscale/Headscale reconnect qualification of dev.7 is
still required. This is not evidence of official-client policy parity.
