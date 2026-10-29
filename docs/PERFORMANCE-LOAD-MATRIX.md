# Performance workload and acceptance matrix

Local experimental plan, 2026-10-29. Read the performance roadmap/checkpoint.
Only the scoped baseline marked below has been executed. No complete concurrent
service capacity or candidate stability qualification is claimed.

## Actual configured limits, not measured throughput guarantees

Reference: 3.0.6 configuration, pinned ESP-IDF 5.5.3 and MicroLink `fa3153b`.
Confirm effective config when building any candidate.

| Resource | Configured limit | Interpretation |
|---|---:|---|
| ESP local BSD sockets | 31 | Includes local administration/control/integrations; not a limit of 31 forwarded NAT flows |
| Local active TCP PCBs | 24 | TCP endpoints on the ESP; does not equate to 24 forwarded TCP streams |
| MicroLink active peer slots | 16 | Memory/table ceiling, not demonstrated simultaneous throughput capacity |
| LAN-to-Tailnet rules | 8 | Existing owner rules consume slots; keep them intact |
| AP-side forwarding rules | 16 | Separate function; shares lower-level mapping resources |
| SDK NAPT entries / portmap slots | 512 / 32 defaults | Confirm effective overrides; table size alone does not qualify 512 concurrent flows |
| WG RX / DISCO RX / STUN RX queues | 32 / 8 / 4 packets | Bounded queues, separate from local sockets |
| DERP TX queue | 64 packets | More buffering is not automatically more useful throughput |

## Measurements required

| Workload | Acceptance focus | Current state |
|---|---|---|
| Single bulk TCP + authenticated status/operations sampling | Integrity, speed, CPU, resource reserve, response latency | Six 32 MB baseline transfers complete; candidate pending |
| Same workload with INFO/WARN alternating order | Isolate logging contribution | No justified default change; owner state restored |
| Wired PC versus Wi-Fi PC on same LAN | Separate radio contention from firmware | Wired adapter unavailable in the observed setup; pending |
| Owned geographically remote direct peer; DERP separately | Latency, loss, channel changes, TCP behavior | Pending; do not relabel local direct measurements |
| Increasing TCP streams: initially 1, 2, 4; further only with headroom | Capacity, queue delay, control-plane fairness | Pending; stop at qualified bounds rather than extrapolating |
| Small UDP traffic with bulk TCP | Delivery/latency and source/protocol authorization | Candidate concurrent-load tests pending |
| MQTT/HA + notifications + DNS + monitoring + ordinary UI during traffic | Promised enabled services stay responsive and independent | Broad concurrent qualification pending; no assertion from enabled flags alone |
| SNMP, WoL/Recovery, AP clients/AP-side forwarding, subnet and exit modes | Existing behavior and resource coexistence | Pending scoped lab scenarios; require applicable authority/settings recovery |
| TLS reconnect/command bursts and OTA admission/exclusion under load | Worst transient allocation, socket reserve, predictable refusal | Pending; do not start an update just to measure an unqualified build |
| Queue/socket/flow exhaustion, malformed/denied traffic and recovery | Bounded refusal; no crash, deadlock, leak, policy bypass or reconnect loop | Pending host fault fixtures plus controlled hardware cases |
| Uninterrupted 500 MB + longer combined-service traffic | Hash, persistent memory trend, stack, reconnect/rekey | Candidate pending; earlier 500 MB used two segments |
| Reboot/configuration/NVS/rollback and Wi-Fi/control/DERP interruption | Recoverability and authorization restoration | Pending authorized candidate qualification |

## Pre-candidate acceptance targets

The scoped baseline medians were about 4.60 Mbit/s INFO and 4.69 WARN; ranges
overlap. This is not a hardware maximum. Freeze these experimental targets
before candidate A/B, and document any reason to revise them:

- Throughput optimization: at least 10% improvement in median useful throughput
  and a consistent positive effect across at least three controlled comparisons.
  The margin is intended to exceed the observed short-run variation. A clear
  resource/reliability benefit can instead justify an optimization with unchanged
  throughput, but it must be reported as such, not as a speed improvement.
- Local concurrent status+operations pair: no request failures; p95 below one
  second and no more than 25% above the worst matching baseline run's p95.
  This is a local benchmark target, not a universal WAN/DERP latency promise.
- Full file hash match; no hidden retries/resumes. Record interruptions separately.
- No unexplained reboot, watchdog, OOM, deadlock, sustained memory leak, authority
  loss or starvation in the supported workload. Unexpected failure blocks acceptance.
- Derive final RAM/largest-block/socket/stack reserves from measured concurrent
  workloads and transient recovery needs plus an explicit margin. The harness's
  emergency abort floors are safety stops, **not** validated release reserves.
- Overload outside the measured supported capacity must reject/defer new work
  explicitly and recover without sacrificing essential service or authorization.
- Keep enabled features/configuration equivalent in A/B. Never claim all optional
  services were qualified simply because ordinary traffic and the UI passed.

One prototype can be rejected without blocking other investigations. No new
release is allowed on the strength of these baseline runs alone.
