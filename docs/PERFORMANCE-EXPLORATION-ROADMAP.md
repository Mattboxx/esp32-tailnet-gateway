# Performance and load-resilience exploration roadmap

ESP32 Tailnet Gateway — Mattboxx Edition. Owner-approved planning direction,
2026-10-29. **Investigation active. RX prototype rejected (no gain); IRAM
crypto-loop prototype promising (+14.7 % sequential), confirmation pending.**
Current continuation: [Codex-to-Claude checkpoint](CODEX-TO-CLAUDE-PERFORMANCE-CHECKPOINT.md).

## Objective and revised resource policy

**Owner priorities, 2026-10-31:** crypto efficiency (CPU time per transferred
byte), free internal RAM for every service the firmware offers, and lower
latency matter more than peak throughput. Evaluate candidates first on CPU %
per Mbit/s at comparable throughput, internal free/minimum/largest block under
load, and control/forwarded latency (median and p95); a throughput gain alone
is secondary, and an internal-RAM cost needs a matching efficiency or latency
benefit. Example: dev.3 costs about 1.5 KB of internal RAM, so it must show a
clear CPU-per-Mbit or latency improvement to be worth it.

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

## Results so far (same physical position, INFO, 3×32 MB each, 2026-10-29)

| Image | Runs (Mbit/s) | Median | Internal min | Control p95 |
|---|---|---:|---:|---:|
| 3.0.6 `c371c177…` | 4.639 / 4.183 / 4.558 | 4.558 | 45,703 B | 0.305–0.403 s |
| 3.0.7-dev.1 RX ownership `326c0d8e…` | 4.553 / 4.513 / 4.353 | 4.513 (−1.0 %) | 45,723 B | 0.238–0.282 s |
| 3.0.7-dev.2 dev.1 + IRAM loops `762eedce…` | 4.693 / 5.227 / 5.303 | 5.227 (+14.7 %) | 44,463 B | 0.295–0.405 s |

All 9 files matched their SHA-256, no retries/resumes/reboots, largest internal
block 25,600 B throughout, owner rules/leases/console restored. The three
series ran one after another, not interleaved, so RF/host drift is not
excluded; dev.2 is a candidate, not a qualified improvement. The dev.2 runs
were recorded after the last Codex checkpoint (Claude, 2026-10-31).

## Plan amendments (Claude, 2026-10-31)

1. **Interleaved confirmation before more development.** Decision rule frozen
   now: at least four 3.0.6/candidate pairs in ABBA order at a fixed position,
   RSSI/channel recorded per run (repeat a run whose RSSI differs by more than
   6 dB from its pair); accept a speed gain only if the median paired gain is
   at least 10 % and every pair is positive.
2. **Smallest releasable change.** The RX ownership change showed no gain, so
   build dev.3 = 3.0.6 + IRAM loop placement only (no RX adoption) and confirm
   the gain without it. Ship the smaller diff unless dev.2 is measurably better.
3. **Both directions.** The harness measures LAN client download (Tailnet → LAN:
   decrypt on the ESP). Add the upload direction (encrypt path) before
   attributing the gain or claiming a general speedup.
4. **Profile instead of guessing the next step.** The placement gain points to
   instruction-fetch (flash cache) cost in the packet path. Add a bounded,
   test-only cycle-counter build (compiled out of releases) that attributes
   time to decrypt/encrypt, Poly1305, copies, lwIP forwarding and queueing;
   then rank: further IRAM placement of measured hot functions; the 32 KB
   instruction cache (about 26 KB internal RAM, now allowed by the revised
   policy if headroom is measured); ESP32-S3 SIMD (PIE) ChaCha20 later (PERF-07).
5. **Early stability probe.** Run a small concurrency subset (1/2/4 TCP streams
   + UI/API polling + MQTT) on the leading candidate before stacking further
   optimizations, so a load regression is found while the diff is small.
   **Status 2026-10-31:** dev.3 built from root `1b0e79c` / MicroLink `b9e788c`
   (`firmware.bin` SHA-256 `4ca7e1bc86bf393e90cb2a5c55d95951ec3da7d560e5287367e82e612f8e5729`,
   ELF `eca7013b…`): placement checker PASS with the same IRAM addresses as
   dev.2; `.iram0.text` +1,560 B and `.flash.text` −1,496 B versus 3.0.6;
   static DRAM and `sdkconfig.h` identical to 3.0.6. Not installed; it needs
   its own exact-image authority.
   **Interleaved A/B, board A, 2026-10-31 (4 ABBA pairs, 32 MB down + up per
   phase):** all 16 transfers hash PASS, no reboot, every switch verified
   (outside-ota_0 MD5 unchanged, 3.0.5 intact, configuration preserved), rules
   and leases restored, board left on 3.0.6. RSSI was about −63 dBm (−27 dBm on
   2026-10-29) and throughput about 2 Mbit/s with CPU only 26–32 %: the radio,
   not the CPU, limited this run. Download 3.0.6 median 1.994 vs dev.3 1.912
   (pair gains −1.2/+6.4/−7.0/−2.3 %); upload 1.893 vs 1.928 (−6.7/+11.1/+3.1/
   +0.7 %). **No gain at weak signal; the decision rule is not met.** This does
   not test the CPU-bound case where dev.2 showed +14.7 %; internal minimum was
   about 1.5 KB lower with dev.3 (IRAM placement), control p95 exceeded 1 s once
   for each image at this signal level.
   **Second interleaved A/B, board A near the router, 2026-10-31** (RSSI about
   −49 dBm, CPU 62–81 %: CPU-bound; private `performance-20261031-ab2/`). All 16
   transfers hash PASS, no reboot, all switches verified, board left on 3.0.6.

   | Median, 4 ABBA pairs | 3.0.6 | dev.3 | pairs better |
   |---|---:|---:|---|
   | CPU % per Mbit/s, download | 15.03 | 13.72 (−7.3 %) | 4/4 |
   | CPU % per Mbit/s, upload | 11.62 | 11.26 (−3.1 %) | 3/4 |
   | Throughput, download / upload | 5.065 / 5.901 | 5.246 / 5.906 (+2.9 / +1.7 %) | 3/4, 3/4 |
   | Control latency median, download / upload | 238 / 393 ms | 225 / 370 ms (−1.9 / −13.6 %) | 4/4, 3/4 |
   | Control latency p95, upload | 765 ms | 937 ms | single spikes 1.4–2.3 s with both images |
   | Internal free minimum | 45,739 B | 44,203 B (−1.5 KB) | — |

   Reading against the owner priorities: a repeatable crypto-efficiency gain
   (decrypt path −7 % CPU per Mbit in every pair, encrypt path −3 %) for about
   1.5 KB of internal RAM; throughput effect small (+2–3 %, below the 10 % speed
   threshold; dev.2's sequential +14.7 % was mostly drift). Upload makes control
   latency spiky with both images: a latency target for PERF-05, not a dev.3
   regression. dev.3 is a valid efficiency candidate, not yet a release: decide
   after the profiling build shows where the remaining crypto/copy time goes.
   **Profiling build (amendment 4), 2026-10-31:** root `3426b33`, MicroLink
   `403e596`. Building with `TSR_PERF_PROFILE=1` in the environment links
   `ml_perf` cycle counters per RX/TX stage (queue residence, copy, allocation,
   memset, Poly1305, ChaCha20, output) and reports them in `/api/system/diag`
   `perf_profile`; the benchmark stores them per run (`diag_perf`). Image
   `3.0.7-dev.3-prof` (`firmware.bin` `9cf43414…acf55`), +456 B static RAM.
   Release builds are unchanged: the object code of every touched MicroLink
   file compiled with the exact build command is identical to dev.3 (only
   `__FILE__` text differed in the test), all 3,231 data/BSS symbols have the
   same size, and no profiling symbol or string is present. Final ELF section
   sizes still move by a few bytes between links (`-mlongcalls` relaxation and
   alignment), so compare objects, not linked sizes. Code reading already
   shows two full-packet `memset` passes (RX plaintext buffer, TX output buffer)
   and two RX allocations plus a copy per packet: candidates if the counters
   confirm their cost.
   **Profiling results, board A, 2026-10-31** (`3.0.7-dev.3-prof`, RSSI about
   −50 dBm, 3 downloads + 3 uploads of 32 MB, ~5.2 / ~6.0 Mbit/s, CPU 70–74 %;
   private `performance-20261031-prof/`). Cycles are wall cycles of the core,
   so they include interrupts and preemption by higher-priority tasks.

   | Per ~1.3 KB packet | Download (RX: decrypt) | Upload (TX: encrypt) |
   |---|---:|---:|
   | ChaCha20 | 83k cycles, 66 cyc/B | 63k, 51 cyc/B |
   | Poly1305 (+key) | 69k, 55 cyc/B | 33k, 27 cyc/B |
   | Copy / alloc / memset | 12k / 2.5k / 1.8k | 4k / 4k / 1.2k |
   | UDP hand-off (`tx_output`) | — | 49k, 39 cyc/B |
   | Whole packet path | 320k (`rx_total`, includes `tcpip_input` hand-off and preemption) | 157k (`tx_total`) |
   | WG RX queue wait | mean 12–13 ms, max 83–97 ms | — |

   Crypto is the largest attributable cost: about 17 % of the two-core cycle
   budget during download and 13 % during upload (roughly a quarter of the busy
   CPU). The reference C ChaCha20/Poly1305 run at 51–66 / 27–55 cycles per byte.
   Copies, allocations and both `memset` passes together cost only about 2–3 %,
   so removing them is a small CPU win (it may still help RAM). Under load each
   received packet waits about 12 ms in the WG RX queue: per-packet CPU cost
   directly becomes latency. Verified while profiling: `netif->input` is
   `tcpip_input` (`ml_wg_mgr.c:515`), so decrypted packets are queued to the
   TCPIP thread; the "direct input" comment in `wireguardif.c` is outdated.

   **Next (PERF-07, owner priority on crypto efficiency):** a faster ChaCha20
   core and Poly1305 for the ESP32-S3 (portable C first, measured with the same
   counters; S3 SIMD later), with RFC/independent known-answer, differential,
   tampering, alignment and in-place tests before any device image. Then
   revisit the RX queue depth/latency trade-off (PERF-05).
   **dev.4 (PERF-07 step 1), 2026-10-31:** root `b7f12b3`, MicroLink `db6bcd2`.
   ChaCha20 block function and XOR fused (state in locals, 32-bit word XOR for
   aligned 64-byte blocks); Poly1305 reads each block as four words. Bit-identical
   output: RFC/independent AEAD tests and a 6000-case differential test against
   the previous code (`test_wg_crypto_diff.py`; injected mutants caught). Static
   RAM as 3.0.6; `.iram0.text` +576 B over dev.3 (`chacha20` 1,074 B and
   `poly1305_blocks` 1,060 B in IRAM). Measured with `3.0.7-dev.4-prof` under the
   same conditions as dev.3-prof (`performance-20261031-prof4/`, board left on
   3.0.6), cycles per byte, median of three runs:

   | | dev.3 | dev.4 |
   |---|---:|---:|
   | ChaCha20 decrypt / encrypt | 66.6 / 50.9 | 43.8 / 35.4 (−34 / −30 %) |
   | Poly1305 RX / TX | 54.9 / 26.6 | 47.0 / 26.5 |
   | Whole RX / TX packet path | 250 / 126 | 209 / 112 (−16 / −11 %) |

   The word-load change did not measurably help Poly1305 on TX; the remaining
   cost is the 25 64-bit multiplications per block. Next: Poly1305 arithmetic
   and ChaCha20 register pressure, judged by the same counters.

   **dev.5, 2026-10-31:** root `9223c0b`, MicroLink `d2bcd0c`. Xtensa has no
   rotate: GCC emitted SSAI + SRC per rotation (32 SSAI per double round). The
   four quarter rounds now advance together and one SSAI (same `32 − n`
   encoding as GCC) serves four SRC funnel shifts: 145 instead of 170
   instructions per double round (static count, `xtensa-esp32s3-elf` -O2);
   portable C on other targets, so host tests cover the C path and the device
   path is exercised by authenticated tunnel traffic. Poly1305 completes each
   limb in turn (same arithmetic; 368 vs 374 instructions per 16-byte block,
   still dominated by register spills — hand-written assembly is the remaining
   option). Measured (`performance-20261031-prof5/`): ChaCha20 40.1 / 33.0 cyc/B
   (decrypt/encrypt, −8 / −7 % vs dev.4, −40 / −35 % vs dev.3), Poly1305 unchanged
   (48.5 / 26.5). A test-only `TSR_CRYPTO_IN_FLASH=1` build keeps both loops in
   flash (`.iram0.text` equal to 3.0.6, −2,092 B internal RAM) to price the
   IRAM placement.
   **dev.6 placement choice:** with dev.5 code, keeping both loops in flash
   cost +7/+15 % (ChaCha20) and +16/+29 % (Poly1305) cycles per byte, +7/+8 % on
   the whole path, and saved ~1.8 KB internal RAM (`performance-20261031-prof5f/`).
   dev.6 (`9298d99`) keeps ChaCha20 in flash and only Poly1305 in IRAM
   (+1,068 B `.iram0.text` vs 3.0.6; static DRAM and sdkconfig equal).

   **Interleaved A/B 3.0.6 vs dev.6 (release images), board A, 2026-10-31**
   (`performance-20261031-ab6/`, RSSI −53 dBm, 4 ABBA pairs, 32 MB down + up;
   16/16 hashes PASS, no reboot, switches verified, board left on 3.0.6):

   | Median | 3.0.6 | dev.6 | pairs better |
   |---|---:|---:|---|
   | CPU % per Mbit/s, download / upload | 14.33 / 11.79 | 13.31 / 10.79 (−5.8 / −9.0 %) | 4/4, 4/4 |
   | Throughput, download / upload | 4.82 / 5.66 | 5.14 / 6.26 (+6.5 / +8.5 %) | 4/4, 4/4 |
   | Control latency median, download / upload | 205 / 403 ms | 210 / 369 ms | 1/4, 2/4 (no clear change) |
   | Internal free minimum | 45,727 B | 44,803 B (−0.9 KB) | — |

   Against the owner priorities: a repeatable crypto-efficiency gain in every
   pair for about 1 KB of internal RAM; latency under load is unchanged, so
   the RX queue (PERF-05) is the next lever. Below the 10 % speed threshold as a
   speed claim; accepted as an efficiency candidate for the integrated gate.

   **dev.7 (`d2f4af1`), PERF-05 first step:** the WireGuard manager polled its
   RX queue every 10 ms (`vTaskDelay`), adding up to one tick to every tunnelled
   packet. net_io/DERP now give a binary semaphore per queued WG frame and the
   manager waits on it; the 10 ms rest is still taken while frames remain
   queued or after 40 ms of work without a real rest (#46 protection). Host
   policy simulation: `tools/test_wg_mgr_wake.py`. Not measured on its own; the
   dev.8 campaign below measures tunnel ping (idle and under load) too.

   **dev.8 (`ee56c1d`, MicroLink `4dcf00f`), Poly1305 in Xtensa assembly:**
   `poly1305_xtensa.S` keeps the five limbs in registers and completes one
   64-bit accumulator at a time: 232 instructions per 16-byte block instead of
   368 (of which ~133 were spill loads/stores). `poly1305_blocks()` compares it
   with the C code on 64 fixed inputs before first use and otherwise keeps C;
   unaligned input is copied one aligned block at a time. The C loop moves to
   flash as the fallback, so `.iram0.text` is 110,435 B (−304 B vs dev.7,
   +764 B vs 3.0.6). Host gate `tools/test_poly1305_xtensa.py` interprets the
   actual `.S` against the actual C (808 cases incl. full-range limbs, a carry
   mutant caught) and drives the dispatcher with correct/wrong stubs; the ISA
   reading itself is confirmed only by the on-device check. Images
   `1566d8a0…58c4` and test-only `-prof` `427f2cf9…5087`. Pending: profiling
   run (requires `poly1305_asm == 1` on the device) and interleaved A/B with
   tunnel ping in `performance-20261031-ab8/`.
6. **Lab device.** Do A/B swaps on the test-only board B where possible and
   keep the owner's primary gateway for final exact-image qualification; the
   primary gateway should not keep running an unpublished dev image between
   campaigns without the owner knowing.

## Work packages and execution order

| ID | Priority | Work | Required output | Status |
|---|---|---|---|---|
| PERF-01 | P0 | Reproducible benchmark and resource baseline | Safe harness, capacity/workload matrix, private measurements | Harness + 15 host tests + scoped device transfers; upload direction (`--direction upload\|both`, server-side SHA-256, ABBA order) added 2026-10-31, not yet run on hardware; wider concurrency pending |
| PERF-02 | P0 | Locate the dominant bottleneck | Topology comparison, CPU/task/queue/copy/crypto evidence | CPU/control/TX-cost baseline collected; wired/remote/RX-cost attribution pending |
| PERF-03 | P1 | Reduce logging overhead | Controlled INFO/WARN comparison and restore | Six paired runs complete; approximately 2% median difference inside variability; original INFO restored |
| PERF-04 | P1 | Receive ownership and zero-copy investigation | Small audited receive-path experiment or justified rejection | Host/SDK/sanitizer + scoped device comparisons complete; no demonstrated speed gain, not promoted; raw zero-copy remains OFF |
| PERF-05 | P1 | Bounded event-driven packet scheduling | Lower avoidable delay without starvation/watchdog regressions | Conditional on PERF-02 |
| PERF-06 | P2 | Precision memory/cache/buffer allocation | Measured speed/headroom tradeoff under concurrent services | dev.2 (IRAM placement of `INNER_BLOCK` + WG `poly1305_blocks`) built, placement verified, installed; same-position 3×32 MB median 5.23 vs 4.56 Mbit/s for 3.0.6 (+14.7 %), every run above the baseline maximum; interleaved A/B, isolation from the RX change and concurrency pending |
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
