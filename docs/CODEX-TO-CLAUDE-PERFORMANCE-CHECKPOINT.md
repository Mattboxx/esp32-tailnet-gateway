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
