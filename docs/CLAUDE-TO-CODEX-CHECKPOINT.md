# Claude-to-Codex checkpoint — 2026-11-07

## Latest state (end of 2026-11-07)

- **3.0.7** is the published stable (Latest; site and browser installer deployed).
- **3.0.8** is built from `e4a6c6b`; image SHA-256 `1349e6a1…53c2` is archived
  under `build/development-3.0.8/`.
  - Offline validation: 125/125.
  - Board A runs it from ota_0, with 3.0.7 in ota_1.
  - The PIE checksum self-test passed on hardware: 365 vs 2,264 cycles.
  - It is being published as the next stable on owner instruction.
- **3.0.8 content:**
  - a Status page that follows what is switched on;
  - state-based suggestions;
  - the Diagnostics "Connection & security" section;
  - no dashboard flash before sign-in;
  - the PIE checksum.
- **Evaluated and not done:**
  - X25519 in assembly: about 32 ms per handshake every 2 min per peer; not worth the risk.
  - lwIP in IRAM: about 10 KB of internal RAM, below the floor.
  - Flash QIO: needs a new bootloader over USB.
  - 1 kHz tick.
- **Still open:**
  - observe a real server-side session close on the board (watcher job `watch-loss*`);
  - radio-dependent tests stay off while the board is away from the router.


Read AGENTS.md, then this file, then `docs/NEXT-STEPS-FOR-AGENT.md`. Private
device state, passwords and addresses stay under ignored `build/private-device/`
and `build/notification-ui/PERFORMANCE-STATE.json`; never copy them here.

## Where the work is

- Worktree `C:/Users/mattb/.codex/workspaces/tailnet-notification-ui-20261028`,
  branch `perf/crypto-fast-20261031`; MicroLink `external/microlink`, same
  branch name. Commit the nested repository first, then the gitlink.
- Owner priorities: speed and responsiveness first, then no packet loss, then
  correctness, then flash wear. The web UI must not get noticeably slower under
  load (p95 ≤ ×1.25 and ≤ 1.5 s). Assembly only where it measurably helps.

## Done since 3.0.7-beta.8 (published pre-release)

| Change | Where | Evidence |
|---|---|---|
| Server session close (END_STREAM/GOAWAY/RST_STREAM) no longer revokes the policy | `ml_coord.c` `poll_map_update` | `test_coord_session_end.py` (actual code, mutant rejected) |
| Per-stage reconnect timing | `ml_coord.c` `note_reconnected`; `/api/operations` `tailnet_reconnects.last_reconnect_*` | `test_coord_recovery.py` |
| Minimal exit-node DoH server (480 B, 1 socket) with latency tuning | `main/peer_dns.c` | `test_peer_dns.py`; board: warm median 30 ms, 20.6 ms after 95 s idle |
| DERP header split across TLS records no longer drops the relay; RecvPacket moved in place | `ml_derp.c` `poll_derp_read` | `test_derp_frame_read.py` (beta.11 source) |
| AP DNS relay accepts only the matching upstream answer; random upstream ID | `components/dns_relay/dns_relay.c` | `test_dns_relay_upstream.py` (beta.11 source) |
| STUN IPv6 parser bounded family read | `ml_stun.c` | `test_stun_parse.py` (beta.11 source) |

Measured and rejected (no gain, removed): zero-copy WireGuard RX, DCache
preload. Crypto is about 7 % of CPU; TCP/IP hooks cost 2–8k cycles per call.
Throughput is limited by lwIP plus the Wi-Fi driver and radio, not by the CPU
(about 50 % idle). No further assembly is justified by current data.

## Board position (owner, 2026-11-07)

Board A is no longer near the router. Do not run, or draw conclusions from,
tests that depend on the radio (transfers, bursts, latency or UI p95 under
load, Wi-Fi losses). PERF-09 for beta.10 was stopped after its 500 MB
download for that reason. PERF-09 ACCEPT, which the beta and stable
publication gates require, is blocked until the owner restores the position
or changes the gate.

## Open, in order

1. **PERF-09 for 3.0.7-beta.10**: stopped (board position). Once allowed again, analyse it
   with `build/private-device/perf09-beta10/perf09_analyse.py`. If every firmware
   criterion passes (expected 48/49; "back on 3.0.6" fails by design), package
   with `tools/package_v2.py --version 3.0.7-beta.10`, scan, push both branches
   fast-forward and publish a GitHub pre-release (`--prerelease --latest=false`).
   Draft notes: `build/release-v3.0.7-beta.9-staged/RELEASE-NOTES.md`.
2. **3.0.7-beta.11**: the three fixes above. Commit, fresh
   `PLATFORMIO_BUILD_DIR`, archive under `build/development-3.0.7-beta.11/`,
   record the install authorization (standing lab authority: board A,
   app-only OTA of the exact archived image with provenance PASS), install,
   then run the Tailnet-loss watcher.
3. **Disconnect fix on hardware**: still not observed. The fix is confirmed
   when the watcher records "Tailnet control connection lost ... (traffic
   continues with the last policy)" for a server-side close, with no
   "Tailnet connection lost" warning and a "Control session back N ms after
   the loss (...)" line. Read the stage timings to find what made the
   2026-11-05 reconnect take about two minutes. A loss caused by the whole
   Internet going down (as on the night of 2026-11-06) does not count.
4. **Stable 3.0.7**: the owner authorised publishing a new stable only when the
   disconnections are shown to be resolved. Build 3.0.7 from the qualified
   source, run the full PERF-09 on that exact image, then follow the stable
   release procedure (Latest release, site installer; `website/firmware/*.bin`
   needs `git add -f`).
5. Security review not yet done in depth: SNMP community comparison is not
   constant-time (v2c sends it in clear anyway); `remote_console` sends its
   password in clear when enabled (off by default, AP only), so document it.

## Rules that keep biting

- Write C test sources from files, not inline heredocs (escapes break).
- Always build in a fresh `PLATFORMIO_BUILD_DIR` after committing; otherwise
  provenance reports `-dirty`.
- PERF-09 refuses a second image under the same version: bump the version.
- Keep CRLF and mixed line endings as found (`ml_coord.c`, `peer_dns.c`,
  `ml_derp.c` are CRLF; `ml_wg_mgr.c` is mixed).
- Never run `*_device.py` by glob; the web password lives only in the
  owner-started lab runner environment.
