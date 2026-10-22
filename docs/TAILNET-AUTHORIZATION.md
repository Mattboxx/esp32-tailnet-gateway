# Tailnet authorization — development boundary and reproducible tests

Applies to local **0.1.38-Mattboxx-1.14-dev.5**, retaining earlier private candidates and the
MicroLink submodule at `1dd50f6c5348e979b07ca4f569b1a3c0e9726b6c`, with
**uncommitted local submodule changes**. A clean checkout of that hash does
not contain this fix. No push, tag, flash or publication is part of this work.

## Confirmed source findings

1. That pinned MicroLink did not parse `PacketFilter` or `PacketFilters` in
   either initial or streaming MapResponse handling. The WG receive path
   authenticated/decrypted data, checked replay and IPv4 source ownership,
   then delivered to lwIP/4via6 without per-port/protocol policy enforcement.
   Peer pruning is necessary but not equivalent to service authorization.
2. Its IPv6 branch set `dest_ok = true` without checking the inner IPv6 source
   against the authenticated peer's prefixes. The translator's configured
   destination check did not establish source identity or port permission.
3. Peer removal/update was asynchronous and allocation/queue failure could
   leave a stale WG peer or AllowedIPs. NVS cached peers were also not fresh
   control-session authority. The new independent authorization snapshot
   denies stale keys/prefixes even if WG teardown is delayed.

These are code-path findings, not a claim that unauthorized access was
demonstrated against the owner's physical board or Tailscale production.

## Three independent boundaries

`authenticated WG peer key → current source-prefix ownership → locally owned
destination → inbound protocol/port permission or bounded outbound reply`.

- WG AllowedIPs selects an outgoing peer and constrains incoming source
  addresses. It does **not** express allowed destination service ports.
- The new gate runs **after authenticated decryption/replay validation and
  before 4via6 translation, NAT or input queueing**. IPv6 uses original IPv6
  source/destination, not a synthesized IPv4 identity.
- Source-prefix ownership is checked against the fresh control map, including
  longest-prefix selection and rejection of ambiguous equal-length owners.
  Broad exit/subnet routes cannot claim unassigned Tailnet node addresses.
- The destination must be in this node's current `AllowedIPs` (or `Addresses`
  if AllowedIPs is omitted/null). This bounds subnet/exit/4via6 reachability
  to control-plane-delivered ownership, not just the existence of a local route.
- Local STA/AP ACLs remain additional, separate policy. They are not proof
  that decrypted WG ingress has been authorized. Web login remains separate.

LAN → Tailnet forwarding still first checks its local listener, interface,
source CIDR and destination restrictions. Its outgoing Tailnet identity is
the ESP/advertised source subnet, **not the LAN user's identity**. This ESP's
inbound filter must not be applied as if it were the remote peer's filter.
Remote service access also depends on the receiving node enforcing its policy
and on application authentication. A visible remote peer is not proof of it.

## MapResponse state contract

Dev.5 transport clarification: an interrupted/new control stream suspends all
data admission immediately. Cached peers, keepalives and deltas cannot unblock
it. A complete fresh Node/Peers/filter map is compiled from empty state. Only
identical authority returning within 30 seconds may preserve existing bounded
return tuples; their normal timeouts still run. Changed/malformed authority,
queue/parser failure and explicit disconnect clear it. This is NOT permission
to continue forwarding while the control connection is lost. Real reconnect
interleavings/server compatibility remain unqualified.

## Tunnel ingress fragment subset — dev.5

`ml_reassembly.c` runs after decrypt/replay and before source/port policy,
translation and input queueing. It consumes each fragment pbuf and retains
bytes only in two lazy PSRAM slots (9,496 bytes on the host ABI), no borrowed
pbuf, lwIP reassembly timer or blocking lock. A complete result owns a new
PBUF_RAM and must still pass current key/ownership/original-port policy.
The final policy gate is mandatory: fragment retention is not a port grant.

Limits: 4,096-byte reconstructed datagram, 32 fragments/datagram, five-second
non-sliding lifetime, exact key/source/destination/ID/protocol/policy generation,
no eviction of another live context, no overlaps or duplicates. OOM, malformed
length/checksum, unknown source/current authority, changed header or contention
deny. IPv4 fragment options and IPv6 non-atomic fragment headers preceded by
extensions remain unsupported; IPv6 atomic headers use the existing decoder.
Jumbograms remain denied. Fixed storage can remain allocated idle, but retains
no pbuf; its contents expire at the next fragment or interface lifecycle reset.

Actual-code host tests cover IPv4/IPv6 TCP/UDP reassembly and WG receive with
mock crypto/netif, including denied ports, wrong key, revoke/epoch, timeout,
overlap, capacity, OOM and balanced pbuf ownership. This is not real encrypted
direct/DERP/PMTU evidence. Fragmented TX/return-flow recording and large
UDP/4via6/exit interoperability still require implementation/qualification;
the ingress subset does not establish full protocol or Tailscale policy parity.

## Base filter semantics

Implemented against the primary [tailcfg wire definitions](https://github.com/tailscale/tailscale/blob/main/tailcfg/tailcfg.go).
Legacy non-null `PacketFilter` replaces `base`; named filters replace/delete
their own group; `"*": null` clears all groups before other named entries.
Legacy is applied first. Missing/null fields retain state **within one map
response stream**. An empty legacy list clears `base`; other named groups
remain. An empty effective union denies new inbound traffic.

- Boot and explicit disconnect invalidate authority/return flows. A new stream
  or transport reconnect blocks **before backoff** using the complete-map
  suspension barrier above; it never grants access from cache alone.
- Fresh Node, full Peers and explicit filter authority are required before
  data traffic. Keepalives, a filter alone or cached WG keys cannot unblock it.
  A successful control connection alone is not an authorization-ready signal.
- Initial and incremental maps use the same compiler. Complete updates are
  published atomically. Invalid input, unsupported authorization syntax, limit
  overflow, allocation failure and lost/invalid JSON framing reset authority
  and cause the coordinator to reconnect. No partial or allow-all fallback.
- `Peers`, `PeersChanged`, numeric `PeersRemoved`, key/expiry patches,
  explicit Expired/IsJailed/UnsignedPeerAPIOnly states and shrinking AllowedIPs
  feed the gate independently of the WG update queue.
- A patch that changes a node key forces a blocked full-map reconnect, because
  the parent's endpoint-only WG patch handler does not install rotated keys.
  The new key becomes usable only after a fresh complete map/WG installation;
  an old authenticated session cannot retain its prior permission meanwhile.
- Canonical spelling of security fields is required. Alternate-case aliases
  are rejected to avoid disagreement with the older case-insensitive peer
  parser. Named filter additions/deletions are order-independent at capacity.
- Nonempty full `Peers` overrides peer deltas. For genuine deltas, numeric
  removals precede upserts in the private candidate; an upsert for the same
  removed ID wins. This follows the reference
  [mapSession peer-state update](https://github.com/tailscale/tailscale/blob/main/control/controlclient/map.go).
  Empty/null `Peers` plus nonempty deltas preserves unaffected peers. A lone
  explicit empty `Peers` is still a conservative clear extension, not a claim
  of matching the official zero-length slice semantics in every context.
- `KeepAlive:true` does not mutate or initialize peer/filter authority, even
  if other fields accompany it. It cannot unblock an incomplete session.
- The WG task reconciles obsolete peers before processing additions, including
  at the 16-peer limit. It consults the immutable authority rather than a
  coordinator-side table sweep; a known-empty map needs no allocated remove
  job. Unknown authority retains the fast-boot cache but grants no data access.
  Delayed obsolete adds/removes cannot undo the current key membership.
  Queue/allocation failure resets authority and requests a full-map refresh.
  Metadata/endpoint ordering and real task interleavings still need testing.
- Expiring keys require a usable wall clock; unsupported expiry encodings fail
  closed. Zero UTC expiry means no expiry. No Tailnet Lock/signature claim.
- Actual authority changes invalidate return-flow state. Identical refreshes
  and Online/endpoint-only patches preserve it; otherwise normal map activity
  would unnecessarily break forwarded connections.
- Packet admission is linearized at the pre-translation gate. A packet already
  admitted/queued is **not recalled** after a subsequent revocation. No claim
  is made that already delivered bytes, socket queues or local application
  sessions are retroactively erased. This must be considered in revocation tests.
- Loss of control connectivity is acted on when the coordinator detects an
  error or its existing stream watchdog expires, not instantaneously when
  a remote policy is edited. No client can apply a map it has not received.

## Supported subset, conservative restrictions and compatibility risks

Supported network match forms: literal IPv4/IPv6, CIDR, inclusive IP ranges,
wildcard; TCP/UDP destination-port ranges and protocol numbers. Omitted/empty
IPProto uses TCP, UDP and ICMP. Pure application CapGrant records do not grant
IP access. Deprecated SrcBits/Bits, source `cap:` matching, unknown network-rule
fields and malformed combinations are not silently widened; unsupported
network rules invalidate the snapshot. This is deliberately **not full policy
parity** with Tailscale/Headscale or the official filter.

Dev.4 accepts TCP/UDP, echo and bounded related ICMP errors, plus bounded
IPv6 Hop-by-Hop/Destination padding/Router Alert and atomic fragment headers.
Header walking is capped at four supported extension headers and 256-byte
option lengths; routing/AH/ESP/unknown options and non-atomic fragments remain
denied. IPv4 source-route/unknown options are refused. No TSMP/SCTP exception.
Existing local listener reassembly is not fragmented **tunnel ingress** support.

ICMP error admission follows the original IP quote format of
[RFC 792](https://www.rfc-editor.org/rfc/rfc792) and
[RFC 4443](https://www.rfc-editor.org/rfc/rfc4443): require original current
peer/source ownership, local outer destination, a matching quoted destination
owner and an exact successfully-sent reverse tuple/key/epoch. Error traffic
does not create or refresh return state. Outgoing errors require an authorized
quoted incoming tuple. Truncated/foreign/unrelated quotes are refused; there is
no blanket ICMP allow. This is a constrained implementation, not full PMTU,
IPv6, exit/NAT/4via6 or official-filter qualification. Real compatibility and
large UDP/fragment handling remain release blockers.

Return flows are bounded exact key/address/port/protocol tuples: outgoing TCP
SYN, UDP and echo requests create state only after WG send success. Unknown
inbound TCP ACK/SYN-ACK is not automatically trusted. Timeouts are 120 s TCP,
30 s UDP, 10 s echo; outbound continuation can refresh existing TCP state.
Unsolicited SYN never passes merely because of a reverse tuple. Eviction or
policy change can interrupt existing connections; there is no unbounded table.
This is stricter than some [official-client filter paths](https://github.com/tailscale/tailscale/blob/main/wgengine/filter/filter.go),
not a line-for-line port or a full TCP state machine.

Bounds: 8 named groups (names under 64 bytes), 128 expanded source/destination
matches, 16 peers, 16 prefixes per peer/local node, 32 return flows. Large
source×destination products consume multiple entries; no truncation is allowed.
Snapshots and flow state use PSRAM only; lack of PSRAM denies data. The policy
gate itself introduces no new task, socket or NVS key. Readers hold immutable snapshots under short
reference locks, not a parser lock. Publication and mutable-flow locking are
short; matching is outside the critical section. A retired snapshot survives
until its last in-flight reader exits, so normal two-snapshot update memory is
not a universal peak bound. Board timing/heap minima remain unmeasured.

## Offline regression commands and evidence classes

```
python tools/test_tailnet_authorization.py
python tools/test_peer_convergence.py
python tools/test_policy_protocols.py
python tools/test_gateway_operations.py
python tools/test_runtime_recovery.py
python tools/test_upstream_038.py
python tools/test_tailnet_sdk.py
```

Set `CJSON_SOURCE` to the pinned SDK's `cJSON.c` on Windows, or install
`libcjson-dev` on Linux. Set `LWIP_SOURCE` to the SDK lwIP root for the last
test. `POLICY_SANITIZE=1` enables ASan/UBSan for the authorization tests;
`POLICY_NO_PIE=1` is a host-executable-only workaround for older GCC ASan/WSL
address-layout collisions, not a firmware/security-setting change.

The authorization driver compiles actual `ml_policy.c`; it also extracts and
executes the actual WG receive C function with **mock decryption/replay and
netif delivery**. Cases cover visible-but-denied peers, ports/protocols, direct
ESP/subnet/4via6 destinations, named deltas, removals/ownership, reconnects,
outbound replies, limits, malformed packets, OOM and concurrent publication.
Structural wiring checks are labeled as such. The separate SDK driver uses
real pinned lwIP input/NAPT/pbuf with synthetic interfaces. Neither test is an
encrypted two-real-client experiment. Existing crypto/replay fixtures are
additional unit evidence, not proof of a live authorization boundary.

The peer-convergence driver compiles actual policy, coordinator parser/map
application and manager find/remove/prune/drain functions. It tests full-table
and delta replacement, same-ID key replacement, full-map/keepalive precedence,
stale work and every one of 16 allocation/queue failure points. Queue delivery,
WG installation and NVS removal are explicit bounded sinks; actual FreeRTOS
scheduling, complete WG add/handshake and physical persistence are not tested.

## Required two-real-client and LAN test matrix — NOT YET EXECUTED

Use an isolated test Tailnet/Headscale setup with actual clients **A and B**,
the candidate ESP **G**, a LAN client **C**, a subnet test host **L**, and a
remote Tailnet service host **R**. A and B must remain mutually distinguishable
principals, both visible to G because each has at least one real permitted
service. Do not use peer omission as the only negative case. Obtain explicit
permission before changing real policies, routes or the board firmware.

Keep a local serial/recovery path. Export a private configuration backup; do
not commit it, map payloads, credentials, tailnet identities or packet captures.
Record exact binary hash, server version, policy revision, run ID and clocks.

| Path | Positive control | Required negative control |
|---|---|---|
| A/B → ESP TCP Web UI | A connects to configured UI port (login still required) | B stays visible but TCP UI is denied; separately allow B one other service |
| A/B → ESP UDP | A gets a real enabled DNS/SNMP response | Same live service denied to B; use controlled settings, not an absent listener |
| A/B → L TCP via G | A reaches L:22222 over approved subnet route | A:22223 denied; B:22222 denied while B remains visible |
| A/B → L UDP via G | A receives echo on L:53530 | A:53531 and B:53530 denied with live echo servers |
| C → G listener → R TCP | Allowed C source reaches R:22222 through configured listener | Disallowed LAN source; disabled rule; wrong port; AP/WG ingress; remote policy denies G |
| C → G listener → R UDP | Allowed C source receives nonce echo from R | Same local and remote-policy negatives as TCP; prove return flow is exact |
| 4via6 → L TCP/UDP | Correct original IPv6 source/destination/port allowed | Wrong source, site, destination, port or protocol denied before translation |
| Policy transition | Start working direct and DERP flows, then revoke one port | New attempts denied without hiding peer; test pre-existing traffic separately |
| Reconnect | Repeat after WiFi outage, control reconnect and new map stream | No data admitted from old keys/filter while fresh authority incomplete |

Procedure for each row:

1. On L or R, start bounded echo fixtures on **explicit test interface IPs**:
   `python tools/probe_authorization.py serve --bind <test-interface-IP>`.
   The default loopback bind is intentionally not reachable remotely.
2. On A (then independently B), run for example:
   `python tools/probe_authorization.py probe --host <L-IP> --port 22222 --protocol tcp --expected allow --client A --phase restricted --run-id <ID>`.
   Use `--protocol udp --port 53530` for nonce-echo UDP. Use `--kind connect`
   for ESP TCP UI, or `--kind dns` for a deliberately enabled DNS listener.
3. Repeat the exact live target from B with `--expected deny`, and A's denied
   second TCP/UDP ports. Recheck the positive control immediately before/after.
   The helper **does not label a timeout as a proven authorization pass**:
   exit 2 is inconclusive. Confirm receive-side observations and effective map
   permissions, not just an application login error or a down service.
4. Exercise remove/re-add, AllowedIPs shrink, named-filter replacement/deletion,
   key rotation/expiry, incomplete map and reconnect on a controlled server.
   Run TCP and UDP separately over confirmed direct and relay paths. Keep tests
   bounded and record stream/connection transitions; do not poll aggressively.
5. Restore test policy/services and compare persistent configuration. No success
   may be inferred from the dashboard's peer visibility or connected indicator.

Do not change production grants just to make a negative test pass. The helper
only probes and serves on test hosts; it does not edit policies, reboot or flash.

## Candidate validation/release gate

Offline NVS fault fixtures, OTA decision/hash/parser fixtures, feature-surface
regressions, SDK packet tests, native sanitizers and target compilation are
necessary but not sufficient. Before a future publication:

- Flash/OTA only with permission, retain a recovery image and validate actual
  migration dev.1/stable→dev.4, unchanged NVS identities/settings and rollback.
- Measure internal/external heap minimum, largest internal block, free socket
  headroom and task stack high-water marks under routing + MQTT/ntfy + Web/OTA.
  Compare before/after; static linker RAM is not runtime free heap.
- Exercise repeated control/WiFi/DERP reconnections, policy churn and table
  exhaustion with concurrent integrations. Fail closed must not become a
  whole-device reboot loop. A blocked data plane may require LAN/serial recovery.
- Complete the real authorization matrix, IPv6/4via6, exit-node Internet/DNS,
  AP gateway and LAN forwarding return paths. Resolve/document required
  fragment/ICMP/PMTU limitations and actual map compatibility first.
- Run at least a 24-hour mixed-load soak after bounded fault tests, watching
  resets, reconnect counters, socket/heap/stack minima and forwarding loss.
  This is a proposed qualification interval, not an executed test or guarantee.

**Current decision: development/testing only, not ready for stable release.**
No assertion of complete Tailscale/Headscale policy compliance is justified.
