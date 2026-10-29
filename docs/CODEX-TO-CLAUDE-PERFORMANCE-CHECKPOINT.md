# Codex to Claude — performance continuation

Updated 2026-10-29. This is local experimental work, not a published release.
Read this before the older notification/release handovers.

## Current ownership and Git

- Root branch: `perf/gateway-profile-20261029`; starting HEAD
  `c3234d9f058eb4de4fecac6d489abfc78688f057`. Uncommitted changes are intentional;
  inspect current HEAD/status instead of resetting to that starting point.
- MicroLink branch: `perf/owned-rx-pbuf-20261029`, local HEAD
  `c2acf70b4478c339ba4549d776148dc5a1bdf571`; based on published `fa3153b`.
  The first semantic commit is `9c0c34e`; two follow-ups preserve inherited
  line endings. Review the **combined** `fa3153b..HEAD` diff: 24 added/9 removed
  lines in `ml_wg_mgr.c`, not a deliberate whole-file refactor.
- No push, flash or publication. Source parent gitlink is still an uncommitted
  change. Do not publish a parent whose nested commit is unavailable remotely.
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

## Changes to preserve

`CMakeLists.txt` identifies the **unbuilt/uninstalled** prototype as
`3.0.7-dev.1`; stable 3.0.6 remains on the test device. New tools/tests above,
`test_gateway_benchmark.py`, `test_wg_rx_owned.py`, `test_wg_rx_sdk.py`, and their
`validate_all.py` registrations are local. Roadmap/next-steps/matrix/validation
documents are modified. The Linux runner now normalizes the Bash here-string
to LF; Windows CRLF otherwise broke its commands.

## Active/blocking work and exact next action

**Next: review/commit the root, build one exact experimental image and record
its source/config/binary/ELF hashes. No image has been built yet.**

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

After build success, record source/gitlink/config/binary/ELF hashes,
review exact current OTA geometry and recovery, then request fresh explicit
authorization for that candidate before any install. Hardware speed gains,
concurrent-feature load resilience, forced DERP, real remote/wired comparisons,
NVS/OTA and an uninterrupted 500 MB candidate test remain pending.

## Evidence and operational safety

Private session folder is pointed to by
`build/notification-ui/performance-active-path.txt`. It contains original state,
paired-run reports/samples, host-test logs, scan triage and Linux wrapper logs.
Linux container logs are under ignored `build/linux-validation-*`.
The earlier completed 500 MB test is a separate private pointer and used two
segments after a host interruption; never relabel it uninterrupted qualification.

No benchmark/server/rule remains active after the six-run campaign. Before new
experiments check processes and device settings again. If interrupted mid-test,
use the benchmark's STOP file/recovery procedure and exact saved rule identity;
never overwrite a stale whole table. Update this checkpoint after every material
operation; detailed step journal and exact live paths belong in the private
`build/notification-ui/PERFORMANCE-CHECKPOINT.md`.
