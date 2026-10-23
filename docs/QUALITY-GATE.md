# Quality gate — dev.8 installed candidate (2026-10-23, Claude final handoff)

> **Current:** this section and [DEV8-VALIDATION.md](DEV8-VALIDATION.md)
> supersede the older rows further below. Installed image dev.8 WiFi
> `b70ff745fb0328be8f98b9ec7fe9b1ce1468501d082bf083ebdf336c08e1361f` on ota_0,
> stable 1.13 on ota_1. Handoff for Codex:
> [CODEX-PUBLISH-HANDOFF.md](CODEX-PUBLISH-HANDOFF.md) (LATEST block).

| Gate | Result on dev.8 | Evidence / residual risk |
|---|---|---|
| Windows offline campaign (build, browser, site, i18n, scans) | PASS 64/64 | `build/validation-20261023-060645-818351/` |
| Linux ASan/UBSan campaign | PASS 60/60 | `build/linux-validation-20261023-061207/` |
| Guarded 1.13 → dev.8 OTA, stable slot kept | PASS (Codex) | DEV8-VALIDATION |
| Service Gateway TCP/UDP, refusal, expiry, reboot persistence, watch | PASS, one client | DEV8-VALIDATION; not identity-based |
| SNMP v1/v2c 109 objects, malformed, cycles | PASS (Codex) | DEV8-VALIDATION |
| One-hour passive serial + API observation | PASS as observation | 3600.27 s, 0 panic/WDT/reboot/errors, control 120/120; no stream closure occurred |
| MQTT / HA Discovery / strict commands / broker outage | PASS, local lab broker | 74 configs, 0 invalid, reconnect 3.2 s, tailnet up meanwhile, exact restore; not a real HA instance |
| Wake-on-LAN | PASS, HTTP and MQTT | synthetic MAC to the bench PC only; list restored exactly |
| Wi-Fi reconnect / DERP + control stream loss in session | PASS, 2/2 cycles | authority back in 16.1 s and 13.4 s, no reboot, MQTT back; short drop on one AP, one client; forced-DERP data path and long outages NOT TESTED |
| Internal RAM headroom | RISK | lifetime min 8043 B, largest block 3456 B, unchanged through all reconnects; runtime MQTT enable from OFF needs ~6.5 KB contiguous: NOT TESTED; `ts_connect` respawn fails silently (harmless today) |
| Two independent Tailnet identities, direct + DERP | BLOCKED | needs an owner-provided lab node/identity (HARDWARE-CAMPAIGN §9) |
| Recovery AP with Wi-Fi absent | NOT TESTED on hardware | host scheduler tests PASS; needs a controlled uplink outage |
| Power loss during OTA / NVS write | NOT TESTED | rollback enabled and OTA writes the inactive slot; physical test needs a planned USB power cut |
| W5500 Ethernet | BLOCKED | no hardware; compile only, never package |
| Bit-reproducible build | NO (ADR-026) | package exact tested image only |

**Verdict: NOT READY FOR RELEASE. Handoff state: HANDOFF READY FOR CODEX.**

## Verdict: NOT READY — BLOCKERS REMAIN

Latest takeover evidence and remaining gates are in
[TAKEOVER-VALIDATION.md](TAKEOVER-VALIDATION.md). Echo, source refusal, expiry
and profile rollback now have scoped physical results; Linux is available.
The older blocked rows below are historical and do not supersede that ledger.

Dev.7 builds and passes offline validation but is not installed. Dev.6 has
scoped authenticated hardware results and a confirmed multi-minute control-map
recovery disruption. The correction needs physical verification; essential
two-client/OTA/recovery/resource gates remain. Nothing was pushed or published.

## Firmware

| Check | Status | Evidence / reason |
|---|---|---|
| WiFi build | PASS, dev.7 | Binary `32485125…`; app 1,878,592 B / 95.6%; not installed |
| Ethernet build | PASS, compile only | Binary `f3ce7b92…`; app 1,933,008 B / 98.3%; no W5500 qualification |
| Offline campaign | PASS | Final Windows 63 checks (75 browser scenarios), Linux ASan/UBSan 60; both target builds separately PASS, same firmware inputs |
| Browser / layout / i18n | PASS | 75 synthetic scenarios; complete layout/site checks |
| Boot, WiFi, tailnet join, direct path | PASS (hardware) | ping 10–15 ms, tailnet HTTP 200, 5 flash iterations |
| Web security without a session | PASS (hardware) | 401 on protected APIs, 403 cross-site login/logout |
| Reboot, heap, stack | PASS (hardware, short) | 120 s: no panic, heap 7.8–13 KB, DERP stack ≥ 5.3 KB |
| **Service Gateway TCP/UDP end-to-end via a LAN client** | **PASS, installed dev.6** | Forced WiFi ingress: TCP 20/20, UDP 20/20; same-client source denial 0/3 each; not two identities |
| **Expiry / profile rollback** | **PASS, scoped dev.6** | 120 s TCP lease closed; UDP positive control; Monitoring apply/rollback restored OFF |
| **Service watch / NVS reboot persistence** | **PENDING** | Watch includes existing owner targets; no unapproved probes; reboot not yet performed |
| **OTA / rollback on hardware** | **PENDING** | Never overwrite stable ota_1 for a test; dev.7 needs exact install authority |
| SNMP operational tree | PASS, dev.6 | 27 OIDs, v1/v2c forced LAN plus 12 Tailnet replies; restored OFF unchanged |
| MQTT/HA, ntfy, WoL/recovery on hardware | PENDING | Controlled lab/fault/independent recovery target gates remain |
| AP fallback after 60 s | BLOCKED | requires removing the saved WiFi |
| Two real clients, direct + DERP policy matrix | PENDING | release blocker from the roadmap (F01–F07) |
| Linux ASan/UBSan | PASS, offline only | Isolated Docker: 58/58 after two fixture corrections; no sanitizer suppression |
| W5500 Ethernet | BLOCKED | no hardware; Ethernet package not produced |
| Soak / resources | COMPLETED collection, dev.6; availability finding | 3600.22 s serial, no observed panic/WDT/reset; 30/30 later API samples; serial heap min 7019 B, API lifetime min 5435 B, largest min 4864 B; five-minute authority interruption means no availability PASS |

## Repository

| Check | Status |
|---|---|
| History, fork link, Csontikka credits, licences, NOTICE | PASS (preserved; no rewrite) |
| microlink submodule | PASS — local commits on `mattboxx` need the parent gitlink pushed together |
| README (20-section order), guides, changelog, release notes | PASS |
| CI (build both variants, read-only), Pages (manual), CodeQL, sensitive scan | PASS (not yet run on GitHub) |
| Credential/history scan | PASS (0 findings) |

## Brand

| Check | Status |
|---|---|
| Original mark, lockups, mono variants, avatar, favicon, banner, social preview | PASS — black/green only, generated by `tools/brand_svg.py`, applied to UI, site, diagrams and README; visually reviewed |
| Web UI identity and design system | PASS (desktop and phone screenshots reviewed) |
| Authentic screenshots | PARTIAL — login screens from the real board; other screens need a signed-in session |

## Website

| Check | Status |
|---|---|
| 16 pages, nav, search, breadcrumbs, 404, redirects, sitemap, robots, canonical, OG, JSON-LD | PASS (`build_site.py --check`) |
| Responsive 320–1920 px, touch targets, no console errors | PASS (`test_site_browser.cjs`) |
| Lighthouse | PENDING — run on the deployed site |

## Release

| Check | Status |
|---|---|
| Pre-release package (WiFi) | PASS — `build/release-0.1.38-Mattboxx-1.14-dev.6/`, ZIP `8f922030…` |
| Checksums, manifest, blank NVS, exact tested image | PASS |
| OTA rename bridge | PASS (host tests) / PENDING (live GitHub) |
| Backup and rollback path | PASS — private full-flash backup + previous slot; documented |

## To reach READY

1. Finish current captures and remove only disposable lab rules; keep the owner
   rule, original integration settings and stable ota_1 intact.
2. With exact new-image authority and verified recovery, install dev.7 safely
   and qualify its real reconnect behavior, reboot persistence, OTA and recovery.
3. Complete controlled optional-service/fault and resource/long-soak checks.
4. Complete the two-independent-client direct/DERP authorization matrix, or
   retain NOT READY. Single-client and host fixtures do not satisfy that gate.

## Operations awaiting authorization (one coordinated request)

1. Push `mattboxx` and the microlink commits (parent gitlink included).
2. Publish the **bridge** release under the current repository name.
3. After the migration window, rename to `Mattboxx/esp32-tailnet-gateway`.
4. Enable GitHub Pages and run the manual Pages workflow; set description,
   topics, homepage and the social preview.
5. Post the announcements in `docs/launch/`.
