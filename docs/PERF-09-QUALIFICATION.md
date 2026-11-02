# PERF-09 hardware qualification: 3.0.7-dev.8

Procedure and acceptance thresholds for the integrated gate of
[PERFORMANCE-EXPLORATION-ROADMAP.md](PERFORMANCE-EXPLORATION-ROADMAP.md),
fixed on 2026-11-01 **before** the run, from the measured 3.0.6/dev.8 baselines
(ab6, ab8, conc8). Candidate: `3.0.7-dev.8`, source `ee56c1d`, MicroLink
`4dcf00f`, firmware.bin SHA-256 `1566d8a025eef08c99d15170a612a4663fdb014bdb0f15f7ca435587a94058c4`.

## Preconditions

- Fresh explicit owner authorization for this image and this step list
  (recorded in the private performance state; the launcher refuses without it).
- Offline consolidated validation of the candidate source: done 2026-11-01,
  107/108 (`--build --browser`); the remaining `easy_install` check passed in a
  targeted rerun after the v3.0.6 checksum asset was fixed.
- Board A (production gateway, USB on the bench PC) on 3.0.6 in ota_0, 3.0.5 in
  ota_1. Only ota_0 is ever written; every switch verifies the USB MAC, that
  ota_1 still holds the verified 3.0.5 image and that every byte outside ota_0
  is unchanged, then that the selected configuration survived the boot.

## Steps (one launcher, one hidden password prompt)

| # | Step | What it exercises | Changes, all restored |
|---|---|---|---|
| 0 | Data-partition backup over USB | NVS, otadata, phy, coredump, storage read twice, equal SHA-256 | none (one reset) |
| 1 | Install dev.8 in ota_0, 240 s warm-up | verified switch procedure | ota_0 |
| 2 | 500 MB download + 500 MB upload | uninterrupted transfer, full hash, read-only UI/MQTT polling | temporary /32 rule |
| 3 | 4 concurrent streams × 32 MB, 2 rounds, both directions | sustained concurrent traffic, fairness, reserves | temporary rule |
| 4 | 2 streams + burst of 48 idle connections to the rule port and 16 parallel status reads, both directions | bounded overload while traffic runs, recovery afterwards | temporary rule |
| 5 | SNMP operational OIDs over LAN and Tailnet | SNMP agent | agent enabled temporarily |
| 6 | ntfy info commands (3) | notifications/commands over HTTPS | command setting temporarily |
| 7 | Web request screening; web sessions | administration security paths | none (invalid bodies only) |
| 8 | Two software restarts | startup, policy, recovery-only setting | restarts |
| 9 | Candidate qualification: identity, MQTT OFF→reboot→activation, lab broker MQTT/HA Discovery, strict commands, broker outage, WoL HTTP+MQTT (synthetic target), 2 Wi-Fi and DERP/control reconnect cycles, 30 min observation | integrations, reconnects, continuity | MQTT pointed at the lab broker, then exact settings restored |
| 10 | Back to 3.0.6 | verified switch | ota_0 |

After every step the launcher records status/operations, waits 60 s and records
them again (sockets and heap must settle). It stops on an unexpected reboot, a
different running version, an unreachable board or a benchmark that could not
remove its temporary rule; otherwise a failed step is recorded and the next one
runs. A `STOP` file stops before the next step.

## Acceptance thresholds

| Criterion | Threshold | Basis |
|---|---|---|
| 500 MB transfers | complete, hash PASS, ≥ 4.5 Mbit/s download, ≥ 5.0 Mbit/s upload | ~85 % of dev.8 single-stream medians at −52 dBm |
| Every transfer in steps 2–4 | hash PASS | — |
| Administration during traffic | 0 failed reads, p95 ≤ 2.0 s, max ≤ 5.0 s | conc8: p95 ≤ 1.25 s, max 2.2 s |
| MQTT during traffic | connected in every sample | conc8 |
| Internal RAM during traffic | minimum ≥ 40,000 B, largest block ≥ 16,384 B | conc8: ≥ 44,831 B, 28,672 B |
| Overload burst | every connection accounted (connected/refused/timeout, none hung); ≤ 2/16 admin reads failed during, 0/16 after; the concurrent transfer hash PASS | bounded, explicit refusal allowed |
| Settling | sockets ≤ baseline + 1 sixty seconds after each non-restart step; reaper fallbacks 0 | — |
| Stability | no reboot except steps 8–9; module restarts not above baseline | — |
| Integration tools | exit 0 | their own pass criteria |

The verdict (ACCEPT/REJECT) is computed by the session's `perf09_analyse.py`. A
REJECT is recorded with the failing criteria; thresholds are not loosened
after the run.

## Result (run 2026-11-01, board A, RSSI about −53 dBm)

**Verdict: REJECT (47/49 criteria).** 86 minutes, all steps executed. A
verified data backup was taken first. The board was back on 3.0.6 at the end:
the switch verified that the protected regions were unchanged and that the
configuration was preserved. Thresholds were not changed after the run.

Failed criteria:

1. **Step 3, round 2 upload (4 streams).**
   - One of the four LAN→Tailnet TCP flows stopped making progress for more than
     15 s, which is the client's per-operation socket timeout. The benchmark
     therefore failed with `URLError: timed out` about 55 s into the round.
   - That flow had carried the fewest bytes (7.5 MB, against 10–15 MB for the
     others). The other three were then cancelled.
   - The status sampling also showed one 15 s gap during the round.
   - Round 1 download (4 streams) passed: 5.385 Mbit/s, fairness 0.91, hash PASS.
     The benchmark stopped before the remaining runs.
2. **Step 4, download overload.** After the 48-connection burst, 1 of 16
   status reads exceeded the 10 s timeout. The other 15 succeeded, with a
   maximum of 7.2 s.
   - During the burst, 16/16 reads succeeded.
   - Of the 48 forwarded connections, 47 connected and 1 timed out; none hung.
   - In the upload direction everything passed, both during and after the burst.

Passed criteria:

| Area | Result |
|---|---|
| 500 MB transfers | download 5.314 Mbit/s, upload 6.249 Mbit/s, hash PASS |
| Administration during traffic | 0 UI failures, p95 ≤ 1.26 s, max ≤ 1.63 s |
| MQTT | connected in every sample |
| Internal RAM during traffic | minimum ≥ 43,831 B, largest block 25,600 B |
| Sockets | back to baseline (9) after every step |
| Reaper fallbacks | 0 |
| Module restarts | 0 |
| Tools | SNMP, ntfy, web screening, web sessions, runtime restarts and the full candidate qualification (MQTT/HA lab, WoL, 2 Wi-Fi/control reconnects, 30 min observation) exited 0 |

Reboots: none occurred outside steps 8–9. For steps 2–7 the uptime advanced
with wall time, so no reboot was hidden. In step 9 the expected reboot
happened about 5 s after the step started. The launcher's simple uptime
comparison does not flag that case, but it is an allowed restart.

The lifetime internal minimum fell to 39,523 B after the ntfy step (TLS). This
is outside the traffic criterion and is recorded for information.

Not established:

- Whether 3.0.6 shows the same single-flow stall: this run measured only dev.8.
  ab8 and conc8 had completed 4-stream uploads on both images.
- The root cause. The likely explanation is TCP retransmission backoff on one
  flow under saturation (core 1 at about 93 %), but this is not proven.

Next: an interleaved 3.0.6/dev.8 repetition of the 4-stream upload and of the
burst, to classify both failures as regression or pre-existing before any
release decision.

## Follow-up A/B result (run 2026-11-01, 75 min, board A back on 3.0.6)

The campaign completed. All 24 benchmarks ran and 23 exited 0. Every phase
started from a fresh boot, every hash passed and there was no reboot.

| Per image (8 U + 4 B runs) | 3.0.6 | dev.8 |
|---|---:|---:|
| U events (flow wait ≥ 5 s or failure) | 2 | 5 (1 timeout) |
| Longest flow wait per U run, median / max | 2.88 / 9.46 s | 5.21 / 11.76 s |
| 4-stream upload Mbit/s, median | 5.97 | 6.64 (+11 %) |
| Fairness, median | 0.89 | 0.85 |
| B events (status read failed after burst) | 1 | 1 (2 reads) |
| UI failures during traffic | 0 | 1 |
| Internal minimum during traffic | 44,351 B | 42,327 B |
| Tunnel ping under load, median / lost | 43 ms / 633 | 30 ms / 675 |

**Classification** (fixed rule):

- **4-stream upload stall:** *pre-existing, more frequent on dev.8.* 3.0.6
  also leaves single flows waiting 8.8–9.5 s. dev.8 moves about 11 % more data
  through the same path and stalls more often.
- **Status read after burst:** *pre-existing.*

Under saturating 4-flow upload, both images lose about 22 % of the tunnel
pings. The likely cause is drops in the forwarding/encryption path when the
offered load exceeds it: TCP backs off on the flow that lost its
retransmissions. This is not yet proven.

The fix target is therefore the saturation behaviour shared by both images,
not a dev.8 code error.

## Follow-up A/B (prepared 2026-11-01)

This follow-up classifies both failures as regression or pre-existing. It does
not re-qualify dev.8: the REJECT above stands until the PERF-09 gate is rerun.

**Setup**

- Images: the same exact 3.0.6 and dev.8 images, on board A.
- Order: A B B A, one cycle.
- Each phase starts from a fresh boot. That is an app-only USB switch, or one
  software restart when the image is already running. A 240 s warm-up follows.
- Each phase runs six benchmarks in the order U B U U B U:
  - **U:** 4 concurrent uploads × 32 MB.
  - **B:** 2 concurrent downloads × 32 MB plus the 48-connection burst with
    16 status reads before and after.
- Every benchmark runs with read-only UI/MQTT polling and 120 tunnel pings.
- Totals: 8 U runs and 4 B runs per image.

**Handling of failures**

- A failed benchmark is counted and the campaign continues.
- The campaign stops on a reboot, a version change or an uncleared rule.
- The campaign always ends on 3.0.6.

**New measurement**

The benchmark now records each flow's longest wait for a single read or send
(`max_gap_s`; the longest across all streams is `max_stream_gap_s`). Stalls
that recover before the 15 s socket timeout are therefore counted as well.

**Classification rule** (fixed before the run, in the session's `ab_analyse.py`)

An event is one of:

- **U event:** a U benchmark failed, or any flow waited ≥ 5 s.
- **B event:** a B benchmark failed, or at least one status read failed after
  the burst.

Classification:

| Outcome | Condition |
|---|---|
| pre-existing | 3.0.6 shows at least one event. "More frequent on dev.8" is added when dev.8 shows at least 3 more. |
| regression | dev.8 ≥ 3 events and 3.0.6 none |
| inconclusive | dev.8 has 1–2 events and 3.0.6 none |
| not reproduced | neither image shows an event |

Throughput, fairness, gap distribution, UI, internal minimum and ping are
reported per image as supporting data.

## Not covered by this run (stated, not claimed)

- Two independent real Tailnet identities, ACL positive/negative between them,
  forced DERP and official-client policy parity: only one real client.
- Service Gateway source-refusal/expiry/reboot lab (`test_gateway_campaign_device.py`):
  needs exactly one original rule, Service Watch OFF and an echo peer.
- OTA upload/rollback through the updater: it would overwrite the 3.0.5
  recovery image in ota_1. dev.8 does not change OTA, NVS or updater code; that
  path keeps its offline tests.
- Ethernet, N8R8, multi-day soak, low-memory/fragmentation injection, TLS peak
  injection: separate gates.

## Recovery

Session folder `build/private-device/perf09-dev8/` (private): `RECOVERY.md`,
`campaign.log`, per-step `state-private.json`. A benchmark interrupted with its
rule present: `benchmark_gateway_device.py --recover-only <folder>` with the
same host arguments. Application-only rewrite of the archived 3.0.6 image at
0x20000 if ota_0 does not boot; data partitions from the step-0 backup only by
the owner's decision.

## Run on 3.0.7-beta.1 (2026-11-01, lab runner, board A, RSSI about −51 dBm)

Image `1331cf48…0f03`, source `9d90b8f`, MicroLink `77eb8a4`: the contents
of 3.0.7-dev.15 with only the version changed. The run took 86.8 min, every
step exited 0, there was no unexpected reboot and the board ended on 3.0.6.

**Verdict: REJECT (48/49).** Thresholds were not changed.

Passed:

| Criterion | Result |
|---|---|
| 500 MB transfers | 7.825 Mbit/s download, 6.362 Mbit/s upload (dev.8: 5.31 / 6.25) |
| UI during traffic | p95 ≤ 0.52 s and max ≤ 0.90 s in every step (dev.8: p95 ≤ 1.26 s) |
| Burst | 48/48 forwarded connections connected, none refused or timed out |
| Status reads | 0/16 failed during either burst |
| Sockets and reaper | sockets back to 9 after every step; reaper fallbacks 0 |
| Internal RAM | minimum ≥ 43,475 B |
| Integrations and tools | all exited 0 |

**Failed:** after the upload-direction burst, 1 of 16 parallel status reads
exceeded 10 s (p50 1.16 s, maximum of the others 7.2 s). The same criterion
failed on dev.8 and on 3.0.6 in the morning A/B (pre-existing).

**Cause** (configuration reading, not separately measured): the HTTP server
serves 4 clients with `backlog_conn` 5, and the lwIP accept queue holds 6.
Further SYNs are dropped and the client retries after 3 s and 6 s.

**Fix in 3.0.7-beta.2:** `backlog_conn` 12 and
`CONFIG_LWIP_TCP_ACCEPTMBOX_SIZE` 12. beta.1 is not published; PERF-09 is
rerun on the exact beta.2 image.

## Run on 3.0.7-beta.2 (2026-11-01, image `7a7d2047…9878`, source `468c901`)

**Verdict: REJECT (48/49).** 86.5 min, every step exited 0, no unexpected
reboot, board back on 3.0.6.

- 500 MB transfers: 7.789 / 6.453 Mbit/s.
- UI p95 ≤ 0.53 s in every step.
- 48/48 burst connections connected.
- Internal minimum ≥ 42,763 B.

The only failure this time came after the **download**-direction burst:
2 of 16 parallel status reads failed. The upload burst passed (0/16). The
backlog change alone did not remove the failure.

Successful reads are served about 4 at a time and complete in up to about
7.2 s. The benchmark did not record why the reads failed. It now records
each failure's type and time, and a burst-only diagnosis run on beta.2
(`perf-burst1`) separates timeouts from connections closed by the server's
LRU purge.

**Burst diagnosis on beta.2** (`perf-burst1`, 11 min, 3 overload-burst
benchmarks in both directions):
- every failed status read was a `ConnectionResetError` 0.2–0.5 s after it
  started;
- no read timed out; the successful reads took at most 1.31 s;
- 48/48 forwarded connections every time.

The server's LRU purge closes the least-recently-used session to admit a new
connection. That session is typically one accepted a moment earlier and
still waiting for its request bytes. The longer backlog of beta.2 admitted
more connections and so produced more of these resets.

**Fix in 3.0.7-beta.3** (`main/web_idle.c`):
- LRU purge is off, and new connections wait in the 12-entry backlog;
- sessions idle for 5 s in both directions are closed by a once-a-second
  sweep run as httpd work;
- host test `tools/test_web_idle.py`.

## Run on 3.0.7-beta.3 (2026-11-01, image `4e3abb98…2b0e`, source `08bc3e2`)

**Verdict: REJECT (48/49).** 86.5 min, every step exited 0, no unexpected
reboot, board back on 3.0.6.

- **Both bursts passed:**
  - 16/16 status reads during and after the burst, no failure;
  - 48/48 forwarded connections.

  The burst diagnosis before the run (`perf-burst2`, 12 bursts) had also
  read 192/192 with no reset. The LRU-purge fix works.
- UI p95 ≤ 0.71 s; internal minimum ≥ 43,239 B; all integrations exited 0.
- **Failed:** 500 MB upload 4.968 Mbit/s against the ≥ 5.0 threshold
  (download 5.23).

Between the beta.2 run and this one the access point moved the uplink from
**channel 11 to channel 1**, and RSSI dropped from −50/−51 to −56/−58 dBm
(−61 dBm at the end). On channel 11 beta.2 had moved the same 500 MB at
7.79 / 6.45 Mbit/s.

The thresholds were fixed for about −52 dBm and are not changed. Two runs
are queued:
1. an interleaved 3.0.6 / beta.3 A/B under the current radio (`perf-ab-b3`);
2. a PERF-09 rerun on the same image that starts only when the uplink is
   back on channel 11 at ≥ −54 dBm (`perf09-beta3b`, radio gate, up to 10 h).

**3.0.6 / beta.3 A/B under the channel-1 radio** (`perf-ab-b3`, 2026-11-02,
49 min, A B B A, RSSI −52…−62 dBm, 16/16 benchmarks exited 0, board back
on 3.0.6). Medians, 3.0.6 against beta.3:

| Metric | 3.0.6 | beta.3 |
|---|---:|---:|
| One stream, download / upload | 4.52 / 5.10 Mbit/s | 6.26 / 5.65 Mbit/s |
| Four-stream upload | 5.22 Mbit/s | 5.63 Mbit/s |
| U events (flow wait ≥ 5 s) | 2/4 | 0/4 |
| Tunnel ping during U | 89 ms | 47 ms |
| UI p95, worst run | 1.52 s | 0.65 s |
| UI p95, single-stream median | 0.27 s | 0.30 s |
| Internal minimum | 45,423 B | 43,307 B |

On the same radio beta.3 is ahead of 3.0.6 on every metric except
single-stream UI p95, which is 25 ms higher. The 500 MB upload shortfall in
the PERF-09 run comes from the link, not from a firmware regression. The
radio-gated PERF-09 rerun is still required before publication.

**Rerun on beta.3** (`perf09-beta3c`, 2026-11-02 05:22–06:59, channel 1,
RSSI −52/−48 dBm). **REJECT (48/49).**
- 500 MB transfers: 5.219 / 5.192 Mbit/s (pass).
- Both bursts: 0/16 status reads failed after the burst (pass).
- **Failed:** the candidate qualification's 30 min observation. 1 of 60
  status samples over the Tailnet address raised `URLError`. The previous
  and next samples were normal and connected, and uptime never went back
  (no reset).

The tool recorded only the error class. It now records the reason and a
follow-up probe 2 s later; the pass rule is unchanged. PERF-09 is rerun
in full on the same image (`perf09-beta3d`).
