# Architecture decision ledger

Decisions are explicit, revisable with evidence and never remove approved scope.

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
