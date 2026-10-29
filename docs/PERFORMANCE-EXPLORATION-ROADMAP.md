# Performance and load-resilience exploration roadmap

ESP32 Tailnet Gateway — Mattboxx Edition. Owner-approved planning direction,
2026-10-29. **Investigation active; RX prototype implemented, not qualified.**
Current continuation: [Codex-to-Claude checkpoint](CODEX-TO-CLAUDE-PERFORMANCE-CHECKPOINT.md).

## Objective and revised resource policy

Improve sustained throughput, latency and efficiency while every supported
enabled service remains reliable under concurrent load. Preserve the full
product roadmap, capabilities, licenses and upstream attribution.

**Owner clarification, 2026-10-29:** RAM usage is not required to remain unchanged.
Earlier absolute RAM-neutrality instructions are superseded for this work.
Use precision engineering and measured resource budgets: a justified increase
is acceptable if performance improves and the device retains sufficient memory,
stack, socket and CPU headroom to run its promised concurrent services.
Reducing RAM is also useful when it improves resilience or frees a bottleneck.

**Load stability is a blocking acceptance gate.** A faster benchmark does not
qualify a candidate that crashes, deadlocks, starves essential services, loses
authorization enforcement or enters reconnect loops. Publish measured capacity
and operating conditions rather than implying unlimited connections/traffic.
Beyond capacity, reject or defer new work predictably and preserve established
essential service. Bound queues, retries and processing; never silently weaken
security, drop persistent configuration or promise successful work not performed.

No flash, production configuration change, push or publication is authorized by
creating this plan. Obtain fresh applicable authority before device writes.
Keep raw addresses, credentials, backups and captures ignored/private.

## Starting evidence — reuse before doing new work

- Application source: `4071c7eb63ec774a19e23218f80ee627d8074158`, firmware 3.0.6.
- MicroLink: `fa3153b6892d00d0c9a9c42f11c8f1a89c6ea910`.
- Subsequent local documentation HEAD: `c3234d9f058eb4de4fecac6d489abfc78688f057`.
  Inspect actual current root/nested HEAD and dirty files before resuming.
- Effective release config already enables CPU 240 MHz, performance compiler
  optimization, RX/TX AMPDU and TX AMSDU, with tuned Wi-Fi/TCP buffers.
- Live reference device had Wi-Fi power saving OFF, INFO console logging and
  SD logging OFF. Verify current settings rather than assuming they persist.
- A real 500,000,000-byte Service Gateway file transfer matched the full on-disk
  SHA-256, averaging about 4.35 Mbit/s (0.54 MB/s) over active transfer time.
  A host-session interruption stopped the first connection at 475,004,928 bytes;
  the remainder was explicitly resumed. This was not an uninterrupted 500 MB
  qualification, a WAN benchmark or proof of the hardware's maximum throughput.
- Client and server ran on the same owned PC: client forced onto physical LAN,
  server bound to its Tailnet address and restricted to the ESP Tailnet source.
  PC and ESP shared Wi-Fi. Direct peer path was observed at start and end.
- Periodic observations: internal free about 45–46 KB, largest block 25,600 bytes,
  no new historic heap low or ESP reboot. These measurements do not identify the
  dominant bottleneck and do not establish worst-case concurrent-service limits.

Private evidence: follow `build/notification-ui/500mb-active-path.txt` to
`RESULT.md` and the final `CHECKPOINT.md`. Test server and temporary rule were
removed; owner rules and leases were preserved. No benchmark remains active.
The previous private performance note's fixed-RAM rule is superseded by this plan.

## Work packages and execution order

| ID | Priority | Work | Required output | Status |
|---|---|---|---|---|
| PERF-01 | P0 | Reproducible benchmark and resource baseline | Safe harness, capacity/workload matrix, private measurements | Harness + 12 host tests + six scoped device transfers complete; wider concurrency pending |
| PERF-02 | P0 | Locate the dominant bottleneck | Topology comparison, CPU/task/queue/copy/crypto evidence | CPU/control/TX-cost baseline collected; wired/remote/RX-cost attribution pending |
| PERF-03 | P1 | Reduce logging overhead | Controlled INFO/WARN comparison and restore | Six paired runs complete; approximately 2% median difference inside variability; original INFO restored |
| PERF-04 | P1 | Receive ownership and zero-copy investigation | Small audited receive-path experiment or justified rejection | Host/SDK/sanitizer + scoped device comparisons complete; no demonstrated speed gain, not promoted; raw zero-copy remains OFF |
| PERF-05 | P1 | Bounded event-driven packet scheduling | Lower avoidable delay without starvation/watchdog regressions | Conditional on PERF-02 |
| PERF-06 | P2 | Precision memory/cache/buffer allocation | Measured speed/headroom tradeoff under concurrent services | Separate selective-IRAM loop prototype; host/ASan crypto PASS; actual build/placement/RAM and hardware comparison pending |
| PERF-07 | P2 | Crypto hot-path improvements | Compatible, licensed, verified implementation improvement | Conditional on crypto cost |
| PERF-08 | P2 | MTU/MSS/loss investigation | Correct packet sizing only when evidence supports it | Conditional on loss evidence |
| PERF-09 | Blocking final gate | Integrated load/fault/regression qualification | Exact-image evidence and accept/reject decision | Not started |

Dependencies matter more than the numbering: select the measured bottleneck,
not every possible optimization. Implement on a dedicated experimental branch;
preserve stable artifacts and record exact baseline/candidate binary/ELF hashes.

### PERF-01 — Safe, short and repeatable comparison harness

Reuse `tools/lab_echo.py`, bound HTTP utilities and private benchmark patterns.
Do not execute a broad device campaign just to measure speed: some drivers
change profiles, integrations or reboot. Keep test scope explicit.

1. Preserve original rules and leases. Use one uniquely named temporary rule,
   restricted to the LAN test client's `/32`, with expiry and guaranteed cleanup.
   Bind the owned server to its Tailnet address; validate the ESP source/path.
2. Force the client socket onto physical LAN. Record server-observed source and
   rule counters to prove forwarding; do not change global routes/Tailnet ACLs.
3. Handle cancellation, bounded stall/total deadlines and process interruption.
   Recover read-only first and detect concurrent owner edits before cleanup.
4. Record bytes, hash, interruptions/resumes and throughput in fixed windows.
   Collect existing CPU per core, internal free/minimum/largest block, PSRAM,
   socket occupancy, stack margins, queue drops and API latency/errors. Label
   observation gaps, raw stack units and instrumentation overhead honestly.
5. Start with 30–60-second runs and consistent warmup. Use at least three paired
   A/B comparisons when practical, alternating order. Determine baseline noise
   before defining a worthwhile gain; reject changes supported only by noise.

Build a workload/capacity matrix: bulk TCP; several TCP flows; small UDP traffic;
active peers; established routing; ordinary authenticated UI/API polling;
MQTT/HA and command handling; notification delivery; SNMP; DNS; enabled logging
and monitoring. Exercise the supported service combination concurrently, not
only each feature alone. Identify socket/TCP/NAT/rule/queue limits from actual
code/config and reserve capacity for essential administration and reconnects.
Include OTA resource coexistence/exclusion as applicable to existing behavior.

### PERF-02 — Separate radio, crypto, copies and scheduling

Compare a wired LAN PC with the previous Wi-Fi PC topology if available. Keep
ESP signal/channel, destination, path and enabled services controlled. Removing
the extra Wi-Fi endpoint's airtime contention may change the result; measure it.
Keep local direct, real remote direct and DERP results separate. Use only owned
peers; lack of a remote test peer blocks that case, not independent local work.

Measure busy cores/tasks, queue residence/drops, allocations, copying and crypto
time with bounded test-only instrumentation or existing counters. Average CPU
across two cores is insufficient to prove spare critical-path capacity. Do not
infer thermal throttling from temperature spot checks alone.

### PERF-03 — Logging overhead

Compare INFO versus WARN without removing crash/recovery evidence, then restore
the owner's setting. Per-packet WG logs are already DEBUG; expected benefit may
be small. Retain user-configurable diagnostics. Any log-path optimization must
avoid additional unbounded buffering or blocking the routing/control path.

### PERF-04 — Receive-copy and ownership optimization

Inspect pinned MicroLink `src/ml_net_io.c`, `src/ml_wg_mgr.c`,
`src/ml_zerocopy.c`, `include/microlink_internal.h`, `Kconfig` and the nested
`wireguard_lwip/src/wireguardif.c`. Ordinary RX allocates/queues data and makes
a further owning-pbuf copy. TX already includes custom pbuf/in-place encryption
work; preserve it rather than duplicating it.

`ML_ZERO_COPY_WG` exists but is OFF. Its presence does not prove it is safe or
faster. Audit pbuf ownership/chains/alignment, in-place decryption lifetime,
callback context, locking, source ownership, replay/policy checks, teardown,
reconnect and direct/DERP fallback. Moving crypto onto the TCPIP thread may
degrade all network services. Do not simply enable the flag and call it done.

Implement the smallest justified improvement, or reject the alternate path with
evidence. Add actual-code OOM, malformed/tampered input, lifetime and concurrency
tests and applicable sanitizers. Keep host tests distinct from real-device
proof. Nested changes need a reviewed commit and coherent parent gitlink before
future publication.

### PERF-05 — Scheduling without starvation

The manager's bounded drains and 10 ms yield protect against earlier watchdog/
starvation failures. If measured wakeup delay is significant, evaluate a bounded
queue/event-driven wait that wakes for data and still services periodic work,
discovery, handshakes, rekey and shutdown. Avoid busy spinning, missed wakeups
and indiscriminate priority increases. CPU affinity changes require profiling.
Test empty/full queues, floods and concurrent optional services.

### PERF-06 — Precision resource tradeoffs, not fixed RAM neutrality

Revisit cache/IRAM placement, Wi-Fi buffers, queue sizing and PSRAM placement
only against the identified bottleneck. Previous project notes record about
26–28 KB internal-memory costs for cache/IRAM experiments; these are costs to
evaluate, not an automatic ban or an assumed current result.

Measure each change separately, including allocation timing, fragmentation,
largest contiguous block and transient reconnect/TLS/OTA peaks. Free PSRAM is
not equivalent to internal/DMA-capable memory. Larger buffers may add queueing
latency and worsen control responsiveness. Prefer eliminating unnecessary
copies/allocations before adding queue capacity.

Accept additional RAM only with repeatable worthwhile benefit **and** demonstrated
headroom for all supported concurrent services and recovery. Compare static RAM,
runtime peaks, stack and socket use; record the tradeoff explicitly. Establish
headroom thresholds from measured worst-case operations plus a justified margin,
not arbitrary percentages or a single idle snapshot.

### PERF-07 — Crypto only when profiling warrants it

The stack uses reference C ChaCha20/Poly1305. Consider compatible compiler/code
improvements or a licensed optimized backend only if crypto is dominant. AES
acceleration is not automatically useful for WireGuard's ChaCha20 data path.
Preserve the algorithm/protocol and authentication strength.
Require known-answer/differential tests, tampering rejection, length/alignment/
in-place boundaries, replay, concurrency, timing-property review and measured
code-size/stack/resource impact. Assembly/SIMD is a later candidate.

### PERF-08 — Packet sizing and losses

Only investigate MTU/MSS/fragmentation/retransmission tuning when counters or
traces support it. Distinguish forwarded end-to-end TCP from ESP-local sockets:
larger local windows do not automatically enlarge the forwarded client's window.
Preserve direct/DERP behavior; no guessed MTU change or blanket MSS rewriting.

### PERF-09 — Integrated acceptance; stability first

Select worthwhile candidates, integrate, then run consolidated relevant host,
sanitizer, browser and firmware regression/build checks. Intermediate development
uses targeted checks; avoid repeated full campaigns. Hardware qualification needs
fresh explicit authority, verified backups and a concrete recovery procedure.

Required final evidence:

- Repeatable speed/latency improvement outside baseline variability, with exact
  image/source/config hashes and a documented resource tradeoff.
- An uninterrupted 500 MB file transfer with full hash verification, plus
  representative sustained concurrent-service traffic. Label resumed tests.
- Responsive administration and enabled MQTT/HA, notifications, SNMP, DNS,
  monitoring and recovery during traffic; no OOM, watchdog, deadlock, unexplained
  reboot, persistent leak or reconnect loop within the supported load envelope.
- Bounded, explicit overload behavior: new jobs/connections may be refused or
  deferred, but established essential service and authorization remain intact.
  Test floods/bursts, full queues, resource exhaustion and recovery afterward.
- Low-memory/fragmentation cases and transient TLS/reconnect peaks; socket,
  stack and CPU reserves supported by measurements, not just idle free heap.
- Positive/negative authorization for direct ESP access, subnet routing and
  LAN-to-Tailnet TCP/UDP; separate two-real-identity/direct/DERP tests from mocks
  and same-client source-CIDR tests. No official-client policy-parity claim.
- NVS, OTA/rollback, Wi-Fi/recovery AP, AP-side forwarding, exit-node modes,
  WoL/Recovery and integrations retain their required behavior. No invented
  Ethernet or N8R8/N16R8 hardware qualification.

Set numeric throughput, API-latency, reconnect and reserve acceptance thresholds
after baseline measurement and before accepting candidates. If a supported
combination cannot meet them, fix or explicitly narrow the proposed optimization;
do not silently discard promised existing functions. Reject gains that rely on
starvation, weaker checks or unsafe memory margins. A measured decision to keep
the existing implementation is valid. Release eligibility is a separate gate.

Current pre-candidate targets and remaining workload cases are recorded in
[Performance load matrix](PERFORMANCE-LOAD-MATRIX.md). Detailed device observations
and paths remain in the ignored session records.

## Resume instruction

Resume from the **current performance checkpoint**, using the completed private evidence. Do not repeat broad
architecture audits, old publication work or the 500 MB download as the first
action. Prepare harness/profiling offline; then run only authorized experiments.
Update this status table and private findings at each meaningful decision. Keep
the revised resource policy above: RAM can change, reliability under load cannot
be traded away. Planning alone does not implement or qualify any package.

Reference: [ESP-IDF 5.5.3 lwIP performance guidance](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-guides/lwip.html).
