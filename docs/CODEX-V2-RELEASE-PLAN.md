# Handoff to Codex — Firmware v2.0.0 preparation (Claude, 2026-10-23)

**State: FIRMWARE NOT READY — REMAINING BLOCKERS** (list at the end). Everything
below is local; nothing was pushed, released, renamed or deployed.

## 1. Where everything is

| Item | Location |
|---|---|
| Firmware branch | `mattboxx` in this repo; latest local commit = `git log -1` (this file is in it). MicroLink `fa3153b` (unchanged, clean). |
| Site + README work | separate worktree `../esp32-tailnet-site-v2`, branch `site-v2`, based on public Main `a85681a`, commit `b965dcd` (site done; **README v2 not yet written**) |
| Candidate snapshot | `build/development-2.0.0-rc.1/target/{esp32-s3,esp32-s3-eth}/` (ignored) |
| Candidate packages | `build/release-v2.0.0-rc.1/` (ignored): `easy-install/`, EASY INSTALL zip, `assets/`, `web-installer/` |
| Private evidence | `build/private-device/install-2.0.0-rc.1/` (OTA switch log, 75-min serial), `qualify-2.0.0-rc.1-*.json/.jsonl`, backups `backup-20261023-before-dev10/` — never commit or upload |
| Owner file | `docs/COMMUNITY-POSTS.md` untracked — never stage/publish |

## 2. What changed (commits on `mattboxx` after Codex's dev.9 checkpoint)

- `92ff5d8` adopts Codex dev.9 (esp-mqtt PSRAM-stack adapter, MQTT manager PSRAM
  stack, coalesced `ts_connect` with PSRAM stack and retry) + **task reaper**
  (ADR-028): SDK self-delete of WithCaps tasks allocates an internal stack at exit
  and `abort()`s on failure; all such exits now go through a boot-time reaper.
- `de341c3`, `3e6e41e`: **First-Boot Setup** (ADR-029, `docs/FIRST-BOOT-SETUP.md`):
  open AP only on a truly unconfigured device, captive DNS + probe redirects,
  BOOT-button / console-code pairing, X25519 + AES-256-GCM sealed requests, AP
  isolation, atomic power-loss-ordered save; one-prompt qualification tool.
- `cc6c0cb`: **v2 identity**: `PROJECT_VER 2.0.0-rc.1`; updater accepts
  `2.x[-rc.N]` tags and orders every 2.x above every legacy `0.1.x-Mattboxx-A.B`;
  System > About shows product, edition, build commit, upstream base
  (Csontikka v0.1.38 `42ec1081c5ab`; git fork point v0.1.19 `a1c4d86`), MicroLink
  commit; wizard text/roles per owner spec (`ESP32-Tailnet-Setup-XXXX`,
  "Welcome to ESP32 Tailnet Gateway", show/hide, six roles, no secrets in
  summary); wizard English-only (saves 5.4 KB; owner authorised); AP default
  password warning.
- Last commit: Easy Install scripts/templates (`tools/easy_install/`),
  `tools/package_v2.py` (fixed CRLF checksum bug), `tools/test_easy_install.py`,
  this handoff.

## 3. Candidate 2.0.0-rc.1 (exact, ADR-026: never substitute a rebuild)

| File | SHA-256 |
|---|---|
| WiFi `firmware.bin` (1,905,632 B, commit `cc6c0cbfcb29`, clean) | `d879529206c92660b12b8cbb3e0343b2d9b6c707c183144cefe0e1266938cd16` |
| WiFi ELF | `cab46952d25888ea8362668c81a81690cfa68bf3e8e151b73874f98d7d500f4f` |
| Ethernet `firmware-eth.bin` (compile only, experimental) | `ffd54463e8092a288c3f436279fafb0db684ebff1c09d493084f083d5bf1728e` |
| WiFi factory | `834837ffcb6d833ef2833a506809ecaa4d1f383e8105ceb179af5e81b6ed01a9` |
| EASY INSTALL zip (rc.1) | `ba0c3a759bafeb44a67debefd0cc9e9c108464410ac1f75539f0c04f00bfa66c` |

Flash: WiFi 96.9 % (≈60 KB free), Ethernet 99.7 % (≈5.6 KB free — next feature will overflow it).

## 4. Results

| Gate | Result |
|---|---|
| Windows offline (build, browser, first-boot UI 14 runs, crypto) | 69/70 PASS; only `sensitive-history` FAIL (see blocker B1) |
| Linux ASan/UBSan | 63/64 PASS; same `sensitive-history` |
| Guarded OTA 1.13 (ota_1) → 2.0.0-rc.1 (ota_0) | **PASS**, 63 s, 8 setting groups unchanged, stable ota_1 untouched (digest verified before) — also proves an upgraded device does NOT enter first-boot |
| Identity on hardware | **PASS**: version, slot ota_0, setup inactive, no setup SSID; internal free 24.7 KB, lifetime min 19.8 KB, largest 7.7 KB, reaper reaped 1, fallbacks 0 |
| MQTT activation from OFF after reboot, lab MQTT/WoL/Wi-Fi reconnect, 30-min observation | **RUNNING** at handoff in the owner's terminal (`qualify_candidate_device.py`); read `build/private-device/qualify-2.0.0-rc.1-*.json` (`passed` per phase) and the serial log summary |
| First-boot flow on real hardware | NOT TESTED (owner's board is configured; needs a spare/erased board) |
| Two independent tailnet identities, recovery AP outage, power loss during OTA/NVS, W5500, real HA/ntfy | BLOCKED / NOT TESTED (unchanged from dev.8 gate) |

## 5. Remaining blockers before v2.0.0 stable

- **B1 history scan:** commit `de341c3` contains two *synthetic* `tskey-auth-…`
  test strings (removed later); the CI `Sensitive Data Check` scans full history
  and will fail on push. Owner must choose: rewrite the unpushed local commits
  (e.g. interactive-free `git filter-repo --replace-text` on a backup branch) or
  add an exact reviewed-blob exemption. Do not push until decided.
- **B2** finish/inspect the running qualification; fix anything that fails.
- **B3** first-boot on a spare ESP32-S3 (open AP, captive popup on Android/iOS/
  Windows, BOOT pairing, wizard, restart) — record per platform, no claims otherwise.
- **B4** remaining dev.8 gates (two identities, recovery-AP outage, power loss).
- **B5** README v2 in `site-v2` (base: published README; titles per rule:
  "ESP32 Tailnet Gateway — Mattboxx Edition", version only as "Firmware v2.0.0").
- **B6** final build `PROJECT_VER 2.0.0`, install via guarded path, requalify
  applicable gates on that exact image, then `package_v2.py` (non-prerelease).
- **B7** bridge release (below).

## 6. OTA migration (must be followed in order)

Old updaters (1.10–1.13) parse only `X.Y.Z-Mattboxx-A.B` tags, query only the
old repository name and do not follow redirects; the image version must equal
the tag. Therefore:
1. Build a **bridge**: same 2.0.0 source with `PROJECT_VER "0.1.38-Mattboxx-1.99"`,
   qualify it, publish as stable release `v0.1.38-Mattboxx-1.99` with
   `firmware.bin` (+ digest) **under the current name**, before renaming.
2. Publish `v2.0.0` (assets from `package_v2.py`: `firmware.bin`,
   `firmware-eth.bin` keep their names). Bridge devices update to it.
3. Keep a migration window; then rename to `Mattboxx/esp32-tailnet-gateway`
   (same repository, never a new one). Devices still ≤1.13 after the rename
   must update by hand (Web UI upload or Easy Install update) — documented on
   the site (Updating page).

## 7. Publication steps for Codex (after owner authorisation)

1. Resolve B1, then review `git diff fork/Main...mattboxx` and `site-v2`;
   run `python tools/check_sensitive_data.py --history` (root) and the nested scan.
2. Integrate `site-v2` into Main by function (do not overwrite published files
   with older `mattboxx` copies): site, `tools/build_site.py`, tests, vendored
   ESP Web Tools 10.4.0 (Apache-2.0, integrity-verified).
3. Push `mattboxx` + MicroLink gitlink; publish bridge, then v2.0.0 release with
   title "ESP32 Tailnet Gateway — Mattboxx Edition v2.0.0".
4. Copy `build/release-v2.0.0/web-installer/*` to `website/firmware/2.0.0/`,
   set `NEXT_PUBLISHED = True` in `tools/build_site.py`, run
   `python tools/build_site.py --check`, `python tools/test_site_flasher.py --browser`,
   `node tools/test_site_browser.cjs`, deploy Pages.
5. After the rename: `RENAMED = True`, rebuild/deploy, update repo metadata,
   verify old and new URLs, downloads, checksums, browser installer and OTA.
