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
