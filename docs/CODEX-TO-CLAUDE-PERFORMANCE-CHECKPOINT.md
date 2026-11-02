# Codex to Claude — performance continuation

Updated 2026-10-29. This is local experimental work, not a published release.
Read this before the older notification/release handovers.

## Claude update, 2026-10-31 — overrides the stage below

The dev.2 same-position campaign finished after the last Codex entry: 3×32 MB,
median 5.227 Mbit/s (4.693–5.303) versus 3.0.6 4.558 and dev.1 4.513; hashes,
control and cleanup PASS, no reboot; internal minimum about 1.2 KB lower. Not
interleaved, so not qualified. No benchmark/esptool/PlatformIO process is
running and no serial port is present. The primary gateway answers with its web
password on; per the records it still runs **3.0.7-dev.2** in ota_0 (3.0.5 in
ota_1) — not re-verified, needs the owner's sign-in or USB. Plan amendments are
in the roadmap ("Plan amendments"). Next: interleaved 3.0.6/dev.2 (and dev.3 =
placement only) A/B on a USB-connected board under existing exact-image
authority for 3.0.6/dev.2; dev.3 needs new exact-image authority.

Later the same day: root branch `perf/hotloop-only-20261031` (`1b0e79c`) with
MicroLink `perf/hotloop-only-20261031` (`b9e788c` = `fa3153b` + the identical
placement patch). dev.3 exact image archived in ignored
`build/development-3.0.7-dev.3/` (`firmware.bin` `4ca7e1bc…5e8729`). The
benchmark gained `--direction upload|both`; 15 host tests PASS. No device
write, no push.

Then, with the owner's authority for exact dev.3 on board A: interleaved A/B
(private `build/private-device/performance-20261031-ab/`). All checks PASS, board
left on **3.0.6** (ota_1 3.0.5). RSSI −63 dBm, ~2 Mbit/s, CPU ~30 %: radio-bound;
no difference between 3.0.6 and dev.3 (download −1.8 %, upload +1.9 % median
pair gain, mixed signs). The CPU-bound regime (strong signal) remains untested
for dev.3; prefer the cycle-counter profiling build (amendment 4), which does
not depend on RF, or repeat the same campaign at the 2026-10-29 position.

Second A/B near the router (`performance-20261031-ab2/`, RSSI −49 dBm, CPU-bound):
dev.3 −7.3 % CPU per Mbit on download (4/4 pairs), −3.1 % upload (3/4),
throughput +2.9/+1.7 %, control latency median −1.9/−13.6 %, internal minimum
−1.5 KB; upload causes 1.4–2.3 s control-latency spikes with both images. Board
A on 3.0.6. Owner priorities (2026-10-31): crypto efficiency, internal RAM
headroom and latency over peak speed. Next: cycle-counter profiling build.

Profiling done (root `3426b33`/MicroLink `403e596`, image `3.0.7-dev.3-prof`,
board A back on 3.0.6, all switches verified): crypto ≈ 17 %/13 % of the
two-core budget (download/upload), ChaCha20 51–66 cyc/B, Poly1305 27–55 cyc/B;
copies/memset/alloc ≈ 2–3 %; WG RX queue wait ≈ 12 ms mean under load. Next:
PERF-07 faster ChaCha20/Poly1305 (host-tested first). Details in the roadmap.

## Latest stage — overrides older experiment descriptions below

The first RX candidate comparison is complete: median 4.513 Mbit/s versus
same-position 3.0.6 baseline 4.558, with overlapping ranges. **No demonstrated
speed gain; do not promote it.** Device is deliberately back on 3.0.6 in ota_0;
3.0.5 remains protected in ota_1. No benchmark or serial test is active.

Root and nested branches are now `perf/crypto-hotloop-20261029`. Previous
experiment branches and commits are preserved. The second prototype holds the
RX path fixed and places only existing `INNER_BLOCK` and WG `poly1305_blocks`
in IRAM on S3. It changes no cipher arithmetic, protocol, buffers or workers.
Portable + ESP-attribute-fixture real-C RFC/independent AEAD tests pass, including
zero/one/max 64-bit nonce cases; the Linux ASan/UBSan crypto driver now also
passes. Nested selective-placement commit is
`ac0e545c39b33e206ad0ee476535acb4bac0ae88` (on top of retained RX prototype).
Next: exact build, actual ELF placement and measured IRAM/DRAM cost.
`3.0.7-dev.2` is not yet built/installed and has **no flash authority**. The
owner's exact-image authority applies only to dev.1 `326c0d8e…8a2d8b51`.

Read ignored `build/notification-ui/PERFORMANCE-STATE.json` and the numbered
private step journal for the latest result. No push/release is authorized.

## Current ownership and Git

- Root branch: `perf/gateway-profile-20261029`; starting HEAD
  `c3234d9f058eb4de4fecac6d489abfc78688f057`. Uncommitted changes are intentional;
  inspect current HEAD/status instead of resetting to that starting point.
- Exact prototype source commit: `f17f359e8f2c1167b6a364fdd6f2fccdb9615d1c`.
  Later documentation checkpoints do not change or relabel its image.
- MicroLink branch: `perf/owned-rx-pbuf-20261029`, local HEAD
  `c2acf70b4478c339ba4549d776148dc5a1bdf571`; based on published `fa3153b`.
  The first semantic commit is `9c0c34e`; two follow-ups preserve inherited
  line endings. Review the **combined** `fa3153b..HEAD` diff: 24 added/9 removed
  lines in `ml_wg_mgr.c`, not a deliberate whole-file refactor.
- No push or publication. The root source commit records the new parent gitlink.
  The exact prototype is now installed under fresh explicit owner authorization
  recorded privately. Do not publish a parent whose nested commit is unavailable
  remotely, and do not reuse this authority for a different image.
- Original Documents/Claude workspaces, private backups and COMMUNITY-POSTS
  were not changed. Keep all pre-existing documentation changes.

## Completed, with actual evidence

1. Added the deferred performance roadmap, then started execution after the
   owner requested it. RAM may increase when measurements justify it; stability
   with concurrent supported services is a blocking gate.
2. Added `gateway_benchmark.py` and opt-in `benchmark_gateway_device.py`:
   LAN-bound file transfer; source/path-restricted Tailnet server; expiring
   temporary /32 rule; progress/resources/API latency; optional INFO/WARN pairs;
   cleanup/recovery preserving unrelated owner work. No silent resume/retry.
3. Twelve host/loopback behavior tests pass. They are not physical ESP tests.
4. Ran six real 32 MB transfers on the existing 3.0.6 image, alternating INFO
   and WARN. All six hashes pass, no ESP reboot. Medians: INFO 4.600 Mbit/s,
   WARN 4.694 Mbit/s. About 2% is inside observed variability: **no logging
   default change justified**. Original rule/leases and INFO were restored.
5. Implemented a narrow experimental RX optimization: adopt the queued owned
   allocation in an owning custom pbuf instead of copying the full packet into
   another allocation. It stays on the existing WG manager thread. No policy,
   crypto, replay, NAT, queue-budget or scheduler change. Full raw zero-copy
   stays OFF; its TCPIP execution/lifetime/concurrency risks remain unaudited.
6. `test_wg_rx_owned.py` executes actual adoption/dispatch C with host allocator/
   pbuf/consumer fixtures: retained lifetime, exact pointer identity, failures,
   direct/DERP source preservation and 4000 cycles PASS.
7. `test_wg_rx_sdk.py` executes adoption with actual pinned SDK pbuf functions:
   custom flags/refcounts/header adjustment/final free/OOM/size limits PASS.
   Its first failure was an invalid host IPv4/IPv6 fixture configuration; fixed
   the fixture and reran successfully. No firmware defect inferred from that.
8. Existing authorization and real-SDK forwarding targeted checks PASS on
   Windows. These do not replace two-real-identity or physical tests.
9. Linux ASan/UBSan targeted run now PASS for all four selected drivers:
   `wg_rx_owned`, `wg_rx_sdk`, `tailnet_authorization`, `tailnet_sdk`. The runner
   uses disposable Git metadata from root/nested HEAD-ancestry bundles; private
   build/device data and host Git control/config directories are not mounted.
   Host all-ref history scans remain a separate scope.
10. Exact source build/provenance PASS. App SHA-256:
    `326c0d8eea71061c0b0199335b2ca139dda3b6bcfb0a4099d87d06b28a2d8b51`.
    Static RAM 55,764 bytes versus reference 55,740 (+24); SDK config identical.
11. USB device identity matched the live reference device. Standard bulk reads
    truncated; an installed-esptool-5.6, 512-byte/window-1 read-only procedure
    produced a full 16 MB backup with matching device MD5 before/after and host
    SHA-256, with no corrupt chunks in the successful pass. Both slot backups
    were extracted and checked. Do not weaken verification or repeat failed reads.
12. Owner authorized that exact candidate, preserving data/recovery. Installed
    only ota_0 over 3.0.6; ota_1 remains 3.0.5. MD5 of every region outside ota_0
    was identical before/after. No NVS, otadata, partition or bootloader write.
    Candidate booted with matching source ID, selected configuration unchanged,
    Tailnet connected and authority ready. This is direct app-only USB flashing,
    not an automatic OTA rollback qualification.

## Changes to preserve

`CMakeLists.txt` identifies the prototype as `3.0.7-dev.1`; that exact image is
currently running on the reference test device. Public stable remains 3.0.6.
The original 3.0.6 exact image is archived and matches its verified slot backup;
3.0.5 remains untouched in the recovery slot. New tools/tests above,
`test_gateway_benchmark.py`, `test_wg_rx_owned.py`, `test_wg_rx_sdk.py`, and their
`validate_all.py` registrations are local. Roadmap/next-steps/matrix/validation
documents are modified. The Linux runner now normalizes the Bash here-string
to LF; Windows CRLF otherwise broke its commands.

## Active/blocking work and exact next action

**Historical dev.1 continuation (completed; use latest stage above): finish the active three-transfer candidate campaign, verify cleanup,
then obtain a new 3.0.6 baseline at the current physical position using only
ota_0. Do not reset/open a resetting serial monitor during the active campaign.**

The board's observed RSSI changed materially after connection to USB. Old
INFO/WARN baselines cannot establish a causal prototype speed gain. Candidate
runs are in private `candidate-info-position2/`; active session/process details
are in the private state/journal. Controlled restoration of archived exact 3.0.6
and reinstallation of the same authorized candidate are part of the comparison;
never touch ota_1. Stop if backup/identity/geometry/data checks fail.

Docker Desktop was initially stopped and has now been started. The first
Windows PowerShell invocation was blocked by execution policy; no policy was
changed. Bundled `pwsh` executes the runner. After fixing Bash CRLF, the runner
reached a separate failure: the Windows linked-worktree `.git` path is invalid
inside Linux `/work`. That intermediate run exited 128 before tests. Both
environment issues were corrected with LF normalization and disposable metadata
from ancestry bundles; the subsequent four-driver run PASSED. Host Git metadata
was not rewritten. Full Linux/browser regression remains a later integrated gate.

Root content/history scan: zero findings. Nested current content: zero findings.
Nested history scan flags nine old example placeholders, recorded privately;
they predate this work. Do not rewrite history or weaken scanner rules silently.
No publication is authorized by the performance task.

Source/gitlink/config/binary/ELF hashes and recovery procedure are recorded.
Do not request the same image authorization again; do request it for a new
candidate. Hardware speed gains,
concurrent-feature load resilience, forced DERP, real remote/wired comparisons,
NVS/OTA and an uninterrupted 500 MB candidate test remain pending.

## Evidence and operational safety

Private session folder is pointed to by
`build/notification-ui/performance-active-path.txt`. It contains original state,
paired-run reports/samples, host-test logs, scan triage and Linux wrapper logs.
Linux container logs are under ignored `build/linux-validation-*`.
The earlier completed 500 MB test is a separate private pointer and used two
segments after a host interruption; never relabel it uninterrupted qualification.

All three completed campaigns are cleaned up; read the latest private state
before any USB/reset/cleanup operation. Before new
experiments check processes and device settings again. If interrupted mid-test,
use the benchmark's STOP file/recovery procedure and exact saved rule identity;
never overwrite a stale whole table. Update this checkpoint after every material
operation; detailed step journal and exact live paths belong in the private
`build/notification-ui/PERFORMANCE-CHECKPOINT.md`.

## Claude checkpoint, 2026-10-31 evening

- Crypto work on root `perf/crypto-fast-20261031` (`9298d99`, dev.6), MicroLink same branch.
  dev.5 IRAM vs flash measured: flash costs ChaCha20 +7/+15 %, Poly1305 +16/+29 %,
  whole path +7/+8 %, saves ~1.8 KB internal RAM. dev.6 = ChaCha20 in flash,
  Poly1305 in IRAM (+1,068 B IRAM vs 3.0.6), image `512d57d1…16b5`.
- Interleaved A/B 3.0.6 vs dev.6 prepared in private `performance-20261031-ab6/`
  (run_ab.ps1 asks the owner for the password; analyse with `python ab_eff.py .`
  inside that folder). Board A ends on 3.0.6.
- Lease-notification fix: branch `fix/lease-orphan-notify-20261031` (`d768ef0`) from
  3.0.6 in worktree `tailnet-lease-fix-20261031`; tests PASS, builds.
- Remaining: analyse ab6, then PERF-05 (RX queue latency), concurrency probe,
  Poly1305 assembly option, PERF-09 integrated qualification. Nothing pushed.

## Claude checkpoint, 2026-10-31 night

- ab6 recorded (dev.6: CPU/Mbit −5.8/−9.0 %, 4/4 pairs, −0.9 KB internal).
- dev.7 `d2f4af1`: wg_mgr waits on a per-frame semaphore instead of 10 ms polling
  (rest kept when frames remain queued or after 40 ms busy).
- dev.8 `ee56c1d` (MicroLink `4dcf00f`): Poly1305 block function in Xtensa
  assembly with on-device check and C fallback in flash; IRAM 110,435 B.
  Host: `test_poly1305_xtensa`, `wg_crypto_hotloop`, `wg_crypto_diff` PASS.
- ab8 completed (owner run): `poly1305_asm == 1` on the device; Poly1305 −10/−27 %
  cycles per byte; dev.8 vs 3.0.6 CPU/Mbit −3.5/−10.5 %, throughput +8.4/+11.6 %,
  tunnel ping median 8→5 ms idle and 21→14 ms under load (4/4 pairs), internal
  min −0.6…−0.8 KB. Board A left on 3.0.6. ab7 (dev.7 alone) superseded, not run.
- Remaining: concurrency/stability probe on dev.8 (1/2/4 streams + UI/MQTT),
  then PERF-09 integrated qualification. Nothing pushed.
- Concurrency probe prepared: `benchmark_gateway_device.py --streams 1..4` (each
  stream the whole file, hash-checked; server slots bounded, extra requests 429)
  and `--ui-load` (read-only status/operations/forwarding/MQTT polling once a
  second; latency, failures, MQTT connection recorded). Private session
  `performance-20261031-conc8/`: ABBA 3.0.6/dev.8, per phase 1/2/4 streams both
  directions, 16 MB per stream, tunnel ping alongside; `python conc_analyse.py .`.
- conc8 completed 2026-11-01: dev.8 faster and lower CPU/Mbit at 1/2/4 streams in
  both directions, lower tunnel ping, 0 UI failures, MQTT always connected, no
  reboot, internal cost ~0.85 KB constant. Board A on 3.0.6.
- Next: PERF-09. Offline consolidated validation can run now; its hardware part
  (500 MB transfer, faults/overload, integrations, DERP/authorization) needs
  fresh explicit owner authority, a verified backup and a recovery procedure.
- Offline consolidated validation at `e3de27f` (`validate_all.py --build --browser`,
  `build/validation-20261101-010353-426379`): 107/108 PASS incl. firmware build,
  browser and site checks. The one FAIL is `easy_install`'s LF regression guard
  on the private `build/release-v3.0.6-staged/assets/SHA256SUMS.txt`, which is
  byte-identical to the **published** v3.0.6 release asset: that asset has CRLF
  line endings (v3.0.2/v3.0.4/v3.0.5 are LF; the listed hashes are correct and
  nothing pins the file's own hash). Not a performance-branch regression.
  Fixing it means replacing that one release asset with the LF version
  (sha256 `5cfe3436…85cc`): an external write that needs owner authorization.
- 2026-11-01, owner authorized ("Yes, replace it"): the v3.0.6 `SHA256SUMS.txt`
  asset was replaced with the LF version (853 B, `5cfe3436…85cc`; every listed
  hash re-checked against the published asset digests, all 9 match; the
  re-downloaded file is byte-identical). No other asset changed (10 assets).
  The private staged copy was synced (old CRLF copy kept beside it as
  `.crlf-published-20261029.bak`); `--only easy_install` now PASS.
- PERF-09 hardware run prepared, not run: procedure and thresholds in
  `docs/PERF-09-QUALIFICATION.md` (fixed before measuring). Benchmark gained
  size-scaled deadlines (500 MB) and `--burst` (bounded idle-connection burst to
  the rule port plus parallel status reads during a transfer); three device
  tools accept the launcher's process-local password. Private session
  `build/private-device/perf09-dev8/` (verified USB data backup first, then
  dev.8, steps 2–9, back to 3.0.6; `python perf09_analyse.py .` gives the
  verdict). The launcher refuses until `perf09_dev8_authorized` is recorded.
- PERF-09 run 2026-11-01 (86 min, board A, back on 3.0.6 with config
  preserved): **REJECT 47/49**. Failed: step 3 round-2 4-stream upload (one
  flow stalled >15 s, client timeout; earlier rounds and conc8 had passed) and
  1/16 status reads timing out (10 s) after the 48-connection burst during
  download. Everything else passed: 500 MB at 5.31/6.25 Mbit/s, UI 0 failures,
  MQTT always connected, traffic internal min >= 43.8 KB, sockets back to 9,
  integrations/reconnects/30 min observation exit 0, no unexpected reboot.
  Next: interleaved 3.0.6/dev.8 repetition to classify regression vs
  pre-existing; no release decision before that.
- Follow-up A/B prepared (not run): benchmark records per-flow `max_gap_s` /
  `max_stream_gap_s` (tested); private session `build/private-device/perf09-ab-dev8/`
  (A B B A, fresh boot per phase, U B U U B U, 8 U + 4 B runs per image), launcher
  `run_ab.ps1`, fixed classification in `ab_analyse.py` (rule also in
  PERF-09-QUALIFICATION.md), dry-run on synthetic data for all four outcomes.

## Claude checkpoint, 2026-11-01 midday

- ab9 completed (lab runner, board A back on 3.0.6). dev.9 (ChaCha20 in IRAM)
  is the fastest image:
  - one stream: +9.7 / +10.8 % against 3.0.6 and +4.3 / +1.1 % against dev.8;
  - 4-stream upload: +9.5 % against 3.0.6;
  - tunnel ping under load: 25 ms against 31.5 ms on 3.0.6;
  - internal minimum: 43,675 B.
  Details are in the roadmap.
- dev.10 (`a52701a`, MicroLink `ccc93a2`) adds:
  - **ChaCha20 block function in Xtensa assembly.** It runs 116 instructions
    per double round against about 140 from GCC.
    - The device compares it with the C code before first use.
    - The C fallback is in flash.
    - Host test: `tools/test_chacha20_xtensa.py`, which interprets the actual
      `.S` file against the RFC 8439 vector and the C code, and rejects 5
      mutants.
  - **`forward_drops` counters** in `/api/operations`. The benchmark now records
    their increase per run.
- Next: build dev.10, run the placement and provenance gates, then a lab-runner
  A/B (3.0.6 / dev.10 / dev.9). That measures the speed and shows where packets
  are dropped under the 4-stream upload.
- **Packet-loss root cause measured (dev.10, perf-ab10f phase 1, board A).**
  `forward_drops` per run:
  - 1-stream upload: `sta_input_refused` 183;
  - 4-stream upload: 3,609–4,179;
  - `sta_output_refused`, `wg_tx_send_failed` and `wg_tx_alloc_failed`: 0.

  The TCPIP thread mailbox (`CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=32`) overflows.
  Wi-Fi delivers A-MPDU bursts of up to 32 frames, and decrypted WireGuard
  packets (`tcpip_input`) share the same mailbox. Refused TCP segments explain
  the 8–12 s flow stalls (retransmission backoff), and refused tunnel packets
  explain the ping loss. The Wi-Fi TX side and WireGuard TX never failed.
- **dev.11** (`657561d`, MicroLink `91b5000`, firmware.bin `c2bddccf…4c42`):
  - TCPIP mailbox 64 (+128 B);
  - UDP mailbox 16;
  - the WireGuard/DISCO socket is drained up to 16 datagrams per `select()`
    instead of one;
  - new counters: `wg_rx_queue_full`, `wg_rx_input_refused`, `wg_rx_seq_gap` /
    `wg_rx_seq_late` (authenticated counter gaps = packets lost before
    decryption).
  - sdkconfig.h differs from dev.10 only in the two mailbox sizes.
  - Queued on the lab runner as `ab11-1` (dev.11 vs dev.10, A B B A).
- **perf-ab10f completed** (45 min instead of ~95, same runs per image). dev.10
  against dev.9:
  - 1 stream: 5.53 / 6.38 against 5.44 / 6.37 Mbit/s;
  - CPU: 73 / 67.5 % against 75 / 69.5 %, about −4 / −3 % CPU per Mbit/s;
  - 4-stream upload: 6.73 against 6.44 Mbit/s (+4.6 %);
  - internal minimum: 43,903 B;
  - 0 failures, board back on 3.0.6.

  The ChaCha20 assembly gain is consistent with the lower CPU. Its on-device
  check is not visible in this image (status was profile-only; dev.12+
  reports `crypto_asm` in diag). `sta_input_refused` was identical on both
  dev.10 phases: 181–261 per 1-stream upload and 3,609–4,179 per 4-stream
  upload.
- **dev.12 acceptance rule** (fixed 2026-11-01 before its results). The owner
  requires that web UI responsiveness must not drop noticeably, or the
  firmware feels slower than competitors. dev.12 (data-plane priority 18)
  replaces dev.11 only if all of the following hold:
  1. 4-stream upload: no failed run, and fewer U events (flow wait ≥ 5 s)
     than dev.11.
  2. UI p95 during traffic is at most dev.11's × 1.25 and at most 1.5 s, in
     the worst run of each image.
  3. 0 UI failures, MQTT connected in every sample, internal minimum
     ≥ 40,000 B.
  4. Single-stream throughput is not lower than dev.11 by more than 3 %.

  If (2) fails, the alternative is a core split: the TCPIP thread on core 0,
  the receive tasks on core 1 at their old priority.
- **perf-ab11 completed** (41.5 min, board back on 3.0.6). dev.11 against dev.10:

  | Median | dev.10 | dev.11 |
  |---|---:|---:|
  | 1 stream, Mbit/s | 5.70 / 6.74 | 6.79 / 6.86 (+19 / +2 %) |
  | 4-stream upload | 6.78 Mbit/s | 7.55 (+11 %) |
  | Tunnel ping under load | 30.5 ms | 48 ms |
  | U events (flow wait ≥ 5 s) | 1/4 | 4/4, plus 1 timeout |
  | UI p95, worst run | 1.35 s | 1.57 s |

  - 1-stream `sta_input_refused` dropped to 0.
  - The 4-stream upload still refuses about 3,400–3,700 frames at the
    mailbox.
  - The receive side now shows `wg_rx_queue_full` about 8,500 and
    `wg_rx_seq_gap` about 17,400 per run: returning ACKs are starved by the
    priority-7 receive tasks.
  - The deeper mailbox adds queueing latency. **dev.11 alone is not a release
    candidate.** dev.12 (receive priority) and dev.13 (overload shedding)
    address the two remaining causes.
- **perf-ab12 completed** (41.7 min, board back on 3.0.6). dev.12 against
  dev.11:
  - 1 stream: 7.45 / 6.75 against 6.90 / 6.71 Mbit/s;
  - 4-stream upload: 6.96 against 7.49 Mbit/s;
  - U events: 0 against 2; longest-wait median 1.0 s against 4.8 s;
  - `wg_rx_queue_full`: ~300 against ~6,600 per U run;
  - **UI p95, worst run: 1.74 s against 1.55 s**; single-stream UI p95 about
    0.5 s against 0.3 s.

  **Rejected by the fixed rule (criterion 2).** The HTTP server at priority 5
  waited behind the receive tasks at priority 18. dev.13 (shedding) was
  withdrawn before its run. dev.14 (`f5c2ed6`, firmware.bin `3fd773b0…ebd2`)
  adds the HTTP server at priority 18 on top of dev.13 and is queued as
  `ab14-1` against dev.11 under the same rule.
- **perf-final1 completed** (66 min, 24/24 benchmarks exit 0, board back on
  3.0.6). Direct comparison in one session, phase order 3.0.6, dev.15, dev.14,
  dev.14, dev.15, 3.0.6:

  | Median | 3.0.6 | dev.14 | dev.15 |
  |---|---:|---:|---:|
  | 1 stream, Mbit/s | 5.10 / 5.74 | 7.56 / 6.50 | 7.68 / 6.32 |
  | 4-stream upload, Mbit/s | 5.92 | 6.73 | 6.25 |
  | U events / longest-wait median | 3 / 5.66 s | 0 / 0.64 s | 0 / 1.77 s |
  | Tunnel ping idle / load / U | 9 / 34 / 53 ms | 5 / 42 / 56 ms | 4.5 / 31 / 34 ms |
  | UI p95, 1-stream median / worst run | 0.24 / 1.50 s | 0.43 / 0.73 s | 0.32 / 0.40 s |
  | Internal minimum | 45,519 B | 43,507 B | 43,607 B |

  dev.15 4-stream-upload totals: `sta_input_refused` 0, `sta_input_shed`
  29,204 (bulk only), `wg_rx_queue_full` 6, `wg_rx_seq_gap` 3,716 (about
  17,400 per run on dev.11).

  **Selected: dev.15** (latency and UI better than 3.0.6, no stalls). It
  becomes 3.0.7-beta.1 with only the version string changed. Next: build,
  `validate_all --build --browser`, then PERF-09 on the exact beta image.
- **Published 2026-11-02: v3.0.7-beta.3 pre-release**
  (https://github.com/Mattboxx/esp32-tailnet-gateway/releases/tag/v3.0.7-beta.3).
  - Tag target `08bc3e2`, firmware.bin `4e3abb98…2b0e`.
  - PERF-09 ACCEPT 49/49 on this exact image.
  - 10 assets; the GitHub digests match the local files. v3.0.6 stays Latest.
  - Pushed branches: `perf/crypto-fast-20261031` to the project fork and to
    Mattboxx/microlink.
  - Owner's decision: the ping constraint was dropped in favour of the best
    trade-off. The release notes state the about 6 ms higher single-stream
    tunnel ping.
  - beta.4 (small-packet receive lane) is under the ping A/B `perf-ping1`; if
    it wins, it needs its own PERF-09 before publication.
- **Daily Tailnet loss investigation (2026-11-02).** Read-only dump of board A
  (`diag-dump1`, running 3.0.7-beta.4 from ota_1, which the owner installed
  with the GitHub updater).
  - Boot 146, uptime 22,051 s: Tailnet lost with no uplink loss, back after
    140 s. During the reconnect: `MapResponse JSON parse failed near:
    RegionI…`.
  - Boot 146, uptime 26,467 s: Wi-Fi lost (reason 200, beacon timeout),
    back after 4 s; Tailnet back after 30 s.
  - No microSD; console level ERROR. The WARN lines that name a reconnect
    cause were therefore never generated, and the RAM ring only kept console
    output.
- 3.0.7-beta.5 (`ed6c224`, MicroLink `bdf2843`, firmware.bin
  `5100a073…5ecd`) adds:
  - a sdlog memory sink, so the RAM ring keeps WARN at any console level;
  - MicroLink loss and attempt-failure reasons;
  - Tailnet events with the cause;
  - `/api/operations.tailnet_reconnects`;
  - a detailed MapResponse parse report.

  Offline validation: 105/105.
- Not yet installed. Board A no longer has 3.0.5 in ota_1, so installing an
  image there needs the owner's go-ahead.
