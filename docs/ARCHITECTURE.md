# Operational architecture

> **1.14 development preview.** This guide includes unreleased features; it
> does not imply a new firmware download. Public stable remains
> [Mattboxx 1.13](https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery/tree/v0.1.38-Mattboxx-1.13).


## Tailnet authorization (local 1.14-dev.2)

The pinned MicroLink now has an independent bounded `ml_policy` snapshot,
compiled from initial/streaming MapResponse before asynchronous peer updates.
The authenticated WG receive path checks current key/source ownership,
destination ownership and protocol/port rules before 4via6/NAT/queueing.
Outgoing flow tracking is only for exact return traffic, not enforcement of
another node's inbound policy. New map streams/reconnects fail closed until
fresh authority exists. No new task/socket/NVS schema is introduced.
See [supported subset, limitations and test matrix](TAILNET-AUTHORIZATION.md).
This development gate is not full official-client compatibility and has not
been installed on hardware. It changes packet authorization; the passive
diagnostic work below did not.

## Boundaries, not a premature component rewrite

| Area | Existing owners | Boundary |
|---|---|---|
| Network Gateway | microlink, `tailscale_manager`, lwIP hooks, `portmap`, `tailnet_forward`, `fourvia6`, DNS/ACL | Packet path and boot-lifetime VPN ownership. Never block on notifications, web diagnostics or recovery jobs. |
| Recovery & Remote Management | `wol`, direct authenticated web APIs; future recovery state machine | Works locally without MQTT/HA/ntfy. Magic-packet send and observed readiness are different events. |
| Automation & Integrations | MQTT/HA discovery, ntfy worker/stream parser | Optional transports for existing operations. External outage does not disable direct local operations. |
| Monitoring & Diagnostics | metrics, SNMP, reset/log capture, passive rule explanation | Publish evidence and its limits. Do not infer Internet or target health from control-plane status. |

Current modules remain in place. `service_diagnostics.h` is a pure decision
function, not a new service. GET `/api/tailnet-forward` samples the existing
rule/runtime and STA address; it does not take a tunnel handle or initiate I/O.
Existing packet filtering, listener installation, tasks and NVS rule layout
are unchanged by this diagnostic increment.

## Selective service path

```text
allowed LAN source → ESP STA IPv4:listen-port
                   → ingress/CIDR check + receive DNAT
                   → existing Tailnet routing/WireGuard
                   → selected peer:destination-port
```

The destination must be in 100.64.0.0/10 (literal or resolved peer name).
This is not arbitrary routed-remote-LAN port forwarding or transparent L2
bridging. AP-side maps remain a separate configuration and traffic path.
The remote service must authenticate clients as appropriate. With forwarding,
the remote end sees the gateway/tunnel path, not an independently authenticated
identity for the original LAN device. IP source restrictions are not identity.

### Passive evidence contract

| Observation | Supported conclusion | Unsupported inference |
|---|---|---|
| HTTP handler responds | Firmware/web task handled this request | All tasks healthy, independent power/network available |
| STA has IPv4 | Address available for the actual portmap binding | Router/Internet reachable |
| Control session not ready | Control flag currently false | Data path definitely down, credentials definitely wrong |
| Destination unresolved | No valid resolved Tailnet IPv4 is in the rule runtime | Peer offline, DNS service globally broken |
| Mapping installed | Local NAPT mapping installed in the existing runtime | Remote TCP service open, UDP service responding |
| Accepted/rejected counters | Historical local packet admission decisions | End-to-end replies, authenticated identity, present failure cause |

API `diagnostic` fields: `code`, `summary`, `next_step`,
`service_status: not_tested`, `data_plane_status: not_verified`.
Root `observation: passive_snapshot` labels the nature of the observation.
Only the seven rule configuration fields are posted or included in new backups;
runtime explanations/counters never inflate the save or restore request.
The API is authenticated according to the existing web gate and is no-store.
Password-OFF deliberately trusts reachable clients; it is not anonymous-safe
administration. The new fields do not bypass that existing policy.

UI reads do not start probes. Reload is deliberate; failed/malformed reads
retain fields but disable saving until a valid read. Edited drafts lose live
status claims. New UI rules are disabled by default. Enabling requires Save.

## WoL persistence correction

Validate a bounded candidate → serialize NVS write/commit → publish RAM table
only on success. Reads and initialization share a static mutex, avoiding a
second dynamically allocated lazy lock. Keep the legacy record size/layout.
Invalid partial stored records are not commands. Saved device names are not
secrets; operators should avoid putting sensitive information in them.

No automatic wake schedule is introduced. Existing web/MQTT/ntfy entry points
remain; a successful send explicitly does not claim a host has booted.

## Future Smart Recovery contract — not implemented

One explicit operator-started job, bound to a saved target **MAC and table
generation**, not only a mutable index. Separate versioned profile keyed by
that MAC, preserving the current WoL blob. Only an explicitly configured
local unicast target and one optional TCP port may be checked; no scanning,
user-provided arbitrary URLs or redirects. Exclude self, loopback, multicast
and broadcast destinations. Active checks require a real password session.

Proposed states:

```text
precheck → already reachable
         → inconclusive → one requested WoL burst → bounded follow-up checks
                                                  → reachable / inconclusive
```

TCP connect success proves that endpoint/port accepted a connection, not full
application readiness. A refused connection can be evidence of a responding
host with a closed port. ICMP silence/TCP timeout alone cannot prove power-off.
“Not reachable within this check” is an observation, not a power diagnosis.

One active job, no automatic replay after boot, cancellation on target removal,
bounded cadence/deadline, at most one existing three-packet WoL burst per job.
Notification is optional and follows state publication; its failure does not
restart the workflow. A shared worker/resource budget and measured stack/heap
reserve are release gates. Never wait for the workflow in an HTTP handler or
the TCP/IP core. A worker failing admission reports unavailable, not a reboot.

## Bounded health monitoring — experimental dev.5 subset

`health_monitor.c` owns a checksummed `ops_health` sidecar and passive evidence.
The existing PSRAM operations worker serializes active checks with recovery:
no extra task, resident socket or timer. Routing/administration do not wait for
monitoring. Fresh observations replace state only if the configuration generation
still matches. Failed saves leave live settings unchanged; invalid storage starts
disabled. See `NETWORK-HEALTH.md` for exact evidence and missing qualification.

Start with passive evidence: uptime, association/address, control last-receive
age, and available tunnel/peer counters. Preserve unknowns. Add active checks
only for operator-selected essential endpoints, one shared socket at a time,
with backoff/hysteresis and an explicit traffic/privacy setting. No hardcoded
public ping target, mandatory telemetry or external log upload.

Control-plane peer online state is not data-plane/service proof. Route approval
must remain “unknown” unless authoritative approval evidence is available.
Likewise a timeout cannot identify a failed router versus a firewall alone.
