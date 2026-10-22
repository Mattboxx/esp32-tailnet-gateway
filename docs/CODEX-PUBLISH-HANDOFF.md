# Codex publish handoff — ESP32 Tailnet Gateway, Mattboxx Edition

Main document for the agent that continues this project. Keep it current.
Last updated: 2026-10-22 (Claude Code session). **No push, release, rename,
Pages activation or announcement has been performed.** All work is in local
commits.

Status words used below: **COMPLETED**, **PARTIAL**, **BLOCKED**,
**NOT STARTED**; test results: **PASS**, **FAIL**, **BLOCKED**,
**NOT TESTED**. Implemented code is never reported as tested unless a test ran.

Release verdict: **NOT READY FOR RELEASE** (see section D and
[QUALITY-GATE.md](QUALITY-GATE.md)). Handoff state: complete.

---

## A. General state

| Item | Value |
|---|---|
| Working directory | `C:\Users\mattb\Documents\PlatformIO\Projects\esp32-tailscale-subnet-router` |
| Branch | `mattboxx` (default remote branch on the fork is `Main`; local `main` tracks upstream) |
| HEAD | see `git log -1`; at the time of writing the latest commits are the handoff/checkpoint commits after `0470c8e` |
| Working tree | clean except the owner's untracked `docs/COMMUNITY-POSTS.md` — **never commit it** |
| Remotes | `fork` = `https://github.com/Mattboxx/esp32-tailscale-gateway.git` (GitHub redirects to the current repo `Mattboxx/esp32-tailscale-gateway-NAS-recovery`); `origin` = upstream `Csontikka/esp32-tailscale-subnet-router` |
| Local vs fork | ~105 local commits ahead of the last fetched `fork/mattboxx` (fetch first; refs may be stale) |
| Submodule | `external/microlink` @ `2e2e96c` on local branch `mattboxx`, 3 commits ahead of fetched `fork/mattboxx` (`Mattboxx/microlink`). Push the submodule **before** the parent so the gitlink resolves |
| Firmware version | `0.1.38-Mattboxx-1.14-dev.6` (`PROJECT_VER` in `CMakeLists.txt`) |
| App identity | `esp32_tsr` (unchanged; NVS and updater identity unchanged) |
| Board | ESP32-S3 QFN56 rev 0.2, 16 MB flash, 8 MB PSRAM, USB-Serial/JTAG on **COM3**. LAN address and tailnet name: private file `build/private-device/LOCAL-ENV.md` (git-ignored) |
| Installed image | **ota_0 = candidate `aaf166ed…` (active)**, written with ESP-IDF `otatool.py write_ota_partition`, otadata selects ota_0 (seq 29) |
| Stable rollback | **ota_1 = stable 0.1.38-Mattboxx-1.13, untouched.** Switch back: `otatool.py --port COM3 switch_ota_partition --name ota_1` (needs `IDF_PATH` and `PYTHONPATH=<idf>/components/partition_table`) |
| Private backup | `build/private-device/backup-20261022/` (two verified full-flash reads, per-slot images, `SHA256SUMS`, `RESTORE.md`). Git-ignored. **Contains secrets: never upload, attach or log** |
| Private logs | `build/private-device/*.log` (serial captures; contain identifiers). Git-ignored |
| Candidate records | `build/development-0.1.38-Mattboxx-1.14-dev.6/candidate-final/` (bin, elf, SHA256SUMS) |
| Local package | `build/release-0.1.38-Mattboxx-1.14-dev.6/` (pre-release, WiFi) |

Admin password: the agent must not type it on a non-local host. Authenticated
tests need the owner to sign in once in the app's built-in browser pane; the
session can then be used from that pane (same-origin `fetch`). Never store the
password, cookies or tokens in files, scripts, commits or logs.

---

## B. Work completed

| Area | Status | Notes |
|---|---|---|
| 42-feature roadmap code | PARTIAL | Most features implemented; validation states per feature in [FEATURE-IMPLEMENTATION-MATRIX.md](FEATURE-IMPLEMENTATION-MATRIX.md) (many remain "In sviluppo" pending hardware/real-client evidence) |
| Hardware fixes | COMPLETED | Policy gate blocked the tunnel at stream start (`microlink 2e2e96c`, root `49b8441`); login/logout lacked cross-site screening (`9b541ba`); AP fallback after 60 s (ADR-023) |
| OTA rename bridge | COMPLETED (code+host tests) | Updater tries new repo name, falls back to old only on 404 (`5b797f8`) |
| Variant-safe updates | COMPLETED (code+host tests) | WiFi updates only from `firmware.bin`, Ethernet only from `firmware-eth.bin` (`865d474`) |
| Web UI design system | COMPLETED | Default button size, 44 px touch targets, 16 px inputs on phones, wrapping headers (`4da9410`) |
| Service Gateway rule UI | COMPLETED | Table rows on desktop, cards on phones, editor on demand (`4da9410`) |
| Beginner flow | COMPLETED | Goal launcher (6 goals), IoT WiFi guide, simple/advanced mode, at-a-glance strip (`1711739`) |
| Translations | COMPLETED | EN/IT/ES/ZH built in; FR/DE drafts kept in `main/i18n/disabled/` by owner decision (`fc8121e`); see [I18N.md](I18N.md) |
| Page minification | COMPLETED | Build-time, segment-aware; browser tests run on the built page |
| Rebrand (name, README, docs) | COMPLETED | ESP32 Tailnet Gateway; README in the 20-section order (`69de720`) |
| Logo black/green | PARTIAL | New sources from `tools/brand_svg.py` (`0470c8e`): tile/transparent/light/mono/compact marks, lockups, banner, social preview, PNG exports. **Not yet applied** to: Web UI mark/favicon and accent colour, website CSS and hero, the 8 diagrams (still teal), `assets/brand/BRAND.md` palette text |
| Website | COMPLETED (teal palette) | 16 pages, search, 404, redirects, sitemap, robots, canonical, OG, JSON-LD; checks in CI and `validate_all` (`e3d4600`). Needs the black/green palette |
| GitHub files and Actions | COMPLETED (not run on GitHub) | `ci.yml` (both builds, read-only), `pages.yml` (manual only), CodeQL, sensitive scan, templates, CoC, SUPPORT, release.yml |
| Packaging | COMPLETED | `tools/package_release.py --variant wifi|eth`, manifest, Linux/macOS steps; WiFi pre-release package built |
| Launch drafts | COMPLETED (drafts) | `docs/launch/ANNOUNCEMENTS.md` — not posted |

---

## C. Remaining work (priority order)

1. **Authenticated hardware campaign** — BLOCKED on owner sign-in.
   *Missing:* Service Gateway TCP and UDP end-to-end through a LAN client;
   source refusal with a second address; rule create/edit/save/delete;
   expiry; Service watch alerts; profiles preview/apply/rollback; settings
   after reboot; session/CSRF with a real session.
   *Lab plan (no third-party targets):* the PC is both LAN client
   (192.168.1.x) and Tailnet service: run a TCP echo and a UDP echo bound to
   the PC's tailnet IP, add a rule `ESP:18830 → <PC tailnet IP>:<port>`,
   source `/32` of the PC, connect from the PC to `<device LAN IP>:18830`,
   confirm the echo and the rule counters; then change the source to another
   `/32` and confirm refusal. If Windows Firewall blocks the echo port on the
   tailnet interface, record BLOCKED — do not change host security settings.
   *Files:* `docs/HARDWARE-CAMPAIGN.md`, results into
   `docs/VALIDATION-STATUS.md`. *Done when:* echo traffic observed through the
   board with counters, refusal observed, results recorded.
2. **OTA and rollback on hardware** — NOT TESTED. **Do not write ota_1 (stable
   1.13) for a simple test.** Safe path: `switch_ota_partition --name ota_1`
   (boots 1.13), sign in to 1.13, upload the candidate `firmware.bin` via
   1.13's Web UI — it writes ota_0 — reboot into the candidate: this proves the
   real 1.13 → 1.14 upgrade with settings kept, and 1.13 stays in ota_1.
   Rollback evidence: bootloader returns to ota_1 if the new image does not
   confirm (needs a deliberately failing test image; optional). *Done when:*
   upgrade from 1.13 recorded with settings intact.
3. **RAM and stability** — PARTIAL. Observed internal free heap 7.8–13 KB
   (120 s capture; minimum during TLS handshakes), DERP task stack ≥ 5.3 KB,
   no panic. *Missing:* ≥ 1 h soak with largest-free-block and allocation-
   failure tracking, behaviour under Service Gateway traffic and parallel
   TLS (MQTT broker reachable), watchdog/reset counters. Tools:
   `tools/observe_candidate.py` (needs a session),
   serial capture script pattern in this document's history (reset + log;
   heap lines `heap_internal_free=` every ~10 s). *Done when:* soak report
   with min heap, largest block and zero unexpected resets.
4. **Integrations** — BLOCKED/NOT TESTED. MQTT broker unreachable from the
   lab; ntfy/SNMP have no lab server. Option: temporary local broker
   (e.g. Mosquitto) and a local ntfy, clearly labelled "local lab". SNMP can
   be queried from the PC (`snmpget` / Python) once enabled. *Done when:* each
   integration has PASS (lab) or explicit BLOCKED.
5. **Black/green identity rollout** — PARTIAL. Apply to:
   `main/index.html` (`.brand-mark` inline SVG, favicon data URI, `--accent`
   tokens → green `#1FC97A`, `.btn-primary` text dark `#04130B`),
   `website/assets/site.css` (accent tokens: dark `#1FC97A`, light `#0B7A4B`;
   neutrals tinted), `website/pages/00-home.html` hero SVG, the 8 diagrams in
   `assets/diagrams/` (teal `#2DD4BF` → green palette from
   `tools/brand_svg.py`), `assets/brand/BRAND.md`. Rebuild and re-run
   `test_automation_ui.cjs`, `test_ui_layout.cjs`, `build_site.py --check`,
   `test_site_browser.cjs`. Rendering check at 16/32/180/512 px.
   *Done when:* no `#2DD4BF`/`#3b82f6` remains in shipped assets and all
   browser checks pass.
6. **Secret-scan scope** — PARTIAL. `.github/sensitive-patterns.yml`
   currently excludes `website/**` and `assets/diagrams/**` from the RFC1918
   rule only (other rules still scan them). Owner asked for narrower
   exclusions: replace with explicit `allow` entries for the synthetic
   example addresses (192.168.1.0/24 examples used in docs: `.1`, `.20`,
   `.30`, `.50`, `192.168.1.0/24`, `192.168.4.0/24`, `192.168.50.42`) and
   remove the directory excludes. Re-run `python tools/check_sensitive_data.py --history`.
7. **Linux sanitizers** — BLOCKED here (no WSL distro/Docker). CI job
   `sensitive-check.yml` already runs `validate_all.py --sanitizers` on
   ubuntu; it will run on the first push. Locally:
   `python tools/validate_all.py --sanitizers --browser` on Linux with
   `libcjson-dev` and the pinned esp-lwip checkout.
8. **AP fallback live test** — NOT TESTED; reversible procedure: temporarily
   change the saved SSID to a non-existent one via the UI (keep the original
   in a password manager — never in files), wait 60 s, confirm the recovery
   AP appears, restore the SSID, confirm the AP disappears.
9. **W5500 Ethernet** — BLOCKED (no module). Do not publish the Ethernet
   package as tested; `package_release.py --variant eth` only after hardware.
10. **Final freeze** — after 1–9: rebuild both variants, re-run the full
    campaign, package, record hashes (section E).

Aesthetic items still open: item 5; a final visual review of the wizard panel
on phones; native-speaker review of it/es/zh wording; Lighthouse on the
deployed site.

---

## D. Test results (real)

| Area | Result | Evidence |
|---|---|---|
| Offline campaign (`validate_all.py --browser`) | PASS 57/58 + rerun | 58th was the sensitive-scan scope (fixed, rerun 0 findings). Log: `build/validation-20261022-204617-583805/` |
| Browser scenarios (built page) | PASS 73 | `tools/test_automation_ui.cjs` |
| UI layout | PASS | `tools/test_ui_layout.cjs`: 8 sections × 20 runs (320–1920 px, simple/advanced, it/es/zh) |
| Website | PASS | `build_site.py --check`, `test_site_browser.cjs` 16 pages × 9 viewports |
| i18n coverage | PASS | it 94.0 %, es 94.5 %, zh 95.1 % (rest are technical terms) |
| WiFi build | PASS | `aaf166ed…` 1,875,760 B (95.4 % of the 1,966,080 B app slot) |
| Ethernet build | PASS (compile only) | `975e4d61…` 1,930,912 B (98.2 %) |
| Boot / WiFi / tailnet join on ESP32 | PASS | 6 flashes, all booted |
| Direct WireGuard path | PASS | `tailscale ping` 10–15 ms via LAN endpoint |
| Web UI over tailnet | PASS | HTTP 200 |
| Unauthenticated API refusal | PASS | 401 on status/restart/ethernet/service-watch/export/capabilities |
| Cross-site login/logout | PASS | 403 for `Origin` and `Sec-Fetch-Site: cross-site` |
| Translations served by the board | PASS | login screen EN/IT/ZH, desktop and phone |
| Service Gateway TCP/UDP through the board | BLOCKED | needs session (section C.1) |
| Source authorization with two clients | BLOCKED | same |
| Expiry, Service watch, profiles, rule CRUD | BLOCKED | same (host tests PASS) |
| NVS persistence after reboot | NOT TESTED on hardware | host tests PASS |
| OTA via Web UI/updater, rollback | NOT TESTED on hardware | host tests PASS; flashing used otatool |
| Reboot / heap / stack | PASS (short) | 120 s: no panic, heap 7.8–13.0 KB, DERP stack ≥ 5,300 B |
| Long soak / load | NOT TESTED | |
| MQTT / Home Assistant | BLOCKED | broker unreachable (client errors every ~20 s, routing unaffected) |
| ntfy / SNMP | NOT TESTED | no lab server |
| AP fallback (60 s) | NOT TESTED on hardware | host test PASS |
| Linux ASan/UBSan | BLOCKED | no Linux here |
| W5500 | BLOCKED | no hardware |
| Two-client policy matrix (F01–F07) | NOT TESTED | roadmap release blocker |

---

## E. Binaries

| Image | Commit (firmware sources) | SHA-256 | Size | Flash use | Status |
|---|---|---|---|---|---|
| WiFi `firmware.bin` | `865d474` (unchanged through `0470c8e`) | `aaf166eddaef76444f37d0a80cde7973707406e4f955e5ca1ca59d77674fd172` | 1,875,760 | 95.4 % | **Installed and smoke-tested** on COM3 board |
| WiFi ELF | same | `40783d9e7d1a563afc5c3dc0ba92b5b5f02842b55e3fb5add9d725892ca6a581` | | | `build/development-…/candidate-final/` |
| WiFi factory | same | `4adb8ffff7ef3bcb99c32744a4539cfe492045c73251cb0601c24973cc4f2329` | 2,006,832 | | packaged, not flashed (would erase NVS) |
| Windows ZIP | same | `8f922030f9dbb260e75befc8f5977f68a699aac2d49a170f2f8f3134848f8ab9` | 16,712,198 | | `build/release-0.1.38-Mattboxx-1.14-dev.6/` |
| Ethernet `firmware.bin` | `865d474` | `975e4d61add87edff50e55bfdf7503e8d3fbf25fe7d099992c21771ce95cc331` | 1,930,912 | 98.2 % | compiled only; build dir `%TEMP%/mattboxx-esp32-build-0114/esp32-s3-eth` |

**These are not final.** Item C.5 changes `main/index.html` (mark, favicon,
accent), so both images must be rebuilt, re-flashed, re-tested and
re-packaged. Never relabel these hashes as the release.

Build: `$env:PLATFORMIO_BUILD_DIR=Join-Path $env:TEMP 'mattboxx-esp32-build-0114'; platformio run -e esp32-s3` (and `-e esp32-s3-eth`).
Package: `cd tools; python package_release.py --version <ver> [--prerelease] --variant wifi --tested-image <bin> --tested-sha256 <sha> --esptool ../build/release-0.1.38-Mattboxx-1.13/esptool.exe --esptool-license ../build/release-0.1.38-Mattboxx-1.13/ESPTOOL-LICENSE.txt --build-dir <envdir>`.

---

## F. GitHub and migration

- Current repository: `Mattboxx/esp32-tailscale-gateway-NAS-recovery`
  (fork of `Csontikka/esp32-tailscale-subnet-router`). Proposed final name:
  `Mattboxx/esp32-tailnet-gateway`. Not renamed.
- Rebrand in the repo: COMPLETED in README/docs/UI/site, links already use the
  new name where they are only meaningful after the rename (badges, website
  URL). Release artefacts and the in-firmware release link use the old name,
  which keeps redirecting after the rename.
- GitHub Pages: NOT STARTED remotely; workflow `pages.yml` is manual-only.
- Workflows: present, never run on GitHub. First push will run CI, CodeQL and
  the sensitive scan (including Linux sanitizers).
- OTA compatibility: 1.13 and older call the releases API of the **old**
  name with redirects disabled and need HTTP 200, and accept downloads only
  from the old path → after a rename they **cannot update by themselves**.
  The new firmware handles both names. Details and the bridge plan:
  [MIGRATION-RENAME.md](MIGRATION-RENAME.md).
- Safe order of remote operations (each needs the owner's explicit OK):
  1. Fetch; review the diff against `fork/mattboxx` and `fork/Main`.
  2. Push `external/microlink` branch `mattboxx`, then the parent branch.
  3. Let CI run; fix anything red (sanitizers run there for the first time).
  4. Publish the **bridge** release (1.14 stable, or a pre-release first)
     under the current name with `firmware.bin` + digest; 1.13 devices with
     the updater enabled will see it.
  5. Migration window (suggested ≥ 4 weeks); announce.
  6. Rename to `esp32-tailnet-gateway`; never recreate the old name.
  7. Enable Pages (Source: GitHub Actions), run `pages.yml`, set
     description/topics/homepage/social preview.
  8. Verify from a bridge device that "Check for updates" reaches the new name.
- Open risks: devices on 1.13 that miss the window need one manual update;
  Ethernet image headroom 35 KB; un-run CI; authenticated hardware evidence
  missing.

---

## Security warnings

- Never commit or upload `build/private-device/**`, NVS dumps, flash backups,
  serial logs, session cookies, the admin password or Tailscale keys.
- `docs/COMMUNITY-POSTS.md` is the owner's untracked file — leave it.
- Do not change host firewall/security settings to make a test pass.
- Do not weaken authentication, the policy gate or tests to get PASS.
- Physical flash/OTA authorization covered only the COM3 board and the agreed
  campaign; do not write ota_1 (stable) for a test.

## Checklist before push and release

- [ ] Section C items 1–6 done or explicitly accepted as BLOCKED by the owner
- [ ] Final rebuild of both variants from a committed tree; hashes recorded
- [ ] Final image installed and smoke-tested on the board; upgrade from 1.13 tested
- [ ] `python tools/validate_all.py --build --browser` PASS; sensitive history scan 0 findings
- [ ] `package_release.py` PASS for the tested image; release notes match tested scope
- [ ] Submodule pushed before parent; CI green after push
- [ ] Owner's explicit authorization for: push, release, rename, Pages, announcements

---

## START HERE — NEXT ACTIONS FOR CODEX

1. `git status`, `git log --oneline -5`, `git -C external/microlink status`;
   confirm HEAD contains this file and the tree is clean (except
   `docs/COMMUNITY-POSTS.md`). `git fetch fork origin` (read-only).
2. Read [QUALITY-GATE.md](QUALITY-GATE.md) and section C above.
3. Ask the owner to sign in once in the built-in browser pane at
   the device's LAN address (see `build/private-device/LOCAL-ENV.md`); run section C.1 (Service Gateway lab) and record
   results.
4. Run C.2 (1.13 → candidate upgrade via switch_ota_partition, stable kept)
   and C.3 (≥ 1 h soak with heap/largest-block tracking).
5. Finish C.5 (black/green rollout to UI, site, diagrams, BRAND.md); re-run
   browser and layout tests.
6. C.6 narrow the secret-scan allowlist; C.4 integrations with local lab
   servers if acceptable.
7. Rebuild WiFi and Ethernet, flash WiFi to ota_0, smoke-test, package,
   record hashes here and in VALIDATION-STATUS.md.
8. Re-read [MIGRATION-RENAME.md](MIGRATION-RENAME.md); decide bridge release
   version (1.14 stable vs pre-release) with the owner.
9. Prepare the coordinated publication request (section F order).
10. Ask the owner for final authorization before any public operation.
