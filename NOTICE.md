# Third-party notices

This project (ESP32 Tailnet Gateway — Mattboxx Edition, formerly ESP32 Homelab
Gateway; repository `esp32-tailnet-gateway`, formerly
`esp32-tailscale-gateway-NAS-recovery`, forked from
`esp32-tailscale-subnet-router`) is licensed under the
[MIT License](LICENSE), Copyright (c) 2026 Csontikka.

Original firmware repository:
https://github.com/Csontikka/esp32-tailscale-subnet-router.

It incorporates the following third-party components, each under its own
license:

## MicroLink: actual dependency and fork chain

- **Dependency used by this project:** https://github.com/Mattboxx/microlink,
  branch `mattboxx`, pinned by the `external/microlink` gitlink. The audited
  revision is `fa3153b6892d00d0c9a9c42f11c8f1a89c6ea910`; the gitlink, not a
  moving branch name, selects the code built into a release.
- **Immediate upstream:** https://github.com/Csontikka/microlink.
- **Original project:** https://github.com/CamM2325/microlink, by
  **Cameron Malone**. Fork lineage: CamM2325 → Csontikka → Mattboxx.
- **License:** MIT
- **Original copyright:** Copyright (c) 2025-2026 Cameron Malone, as preserved
  in `external/microlink/LICENSE`. Mattboxx is not the original MicroLink author.
- **Use:** Tailscale-compatible `ts2021` control-plane + userspace
  WireGuard data-plane stack. Attached as a git submodule under
  `external/microlink`.

## wireguard_lwip

- **Repository:** https://github.com/smartalock/wireguard-lwip
- **License:** BSD-3-Clause
- **Copyright:** Copyright (c) 2021 Daniel Hope (www.floorsense.nz).
- **Use:** Userspace WireGuard implementation for the lwIP TCP/IP stack.
  Vendored inside microlink at
  `external/microlink/components/microlink/components/wireguard_lwip`.
  See that directory's `LICENSE` for the full text and copyright.

The vendored X25519 source identifies **Mike Hamburg / Cryptography Research,
Inc.**, with Copyright (c) 2015-2016 Cryptography Research, Inc. Its MIT notice
is retained in `external/microlink/x25519-license.txt`. Preserve that notice
as well as MicroLink's license; the protocol's name does not replace the
implementation's license.

## ESP-IDF

- **Repository:** https://github.com/espressif/esp-idf
- **Audited SDK:** ESP-IDF 5.5.3, selected by the pinned PlatformIO environment.
- **License:** Apache-2.0 for the SDK generally; bundled components and
  compiler runtime libraries carry their own notices and exceptions.
- **Use:** Espressif's RTOS, WiFi/networking stack, and build system.

In particular, the distribution also includes lwIP (BSD notices, including
the mDNS authors Verisure Innovation AB), FreeRTOS (MIT), cJSON (MIT),
mbedTLS (Apache-2.0 option), ESP-MQTT (Apache-2.0), FatFs (its upstream
redistribution notice), wpa_supplicant (BSD-3-Clause, with its full terms in
the SDK component's `README`), and newlib/GCC/libstdc++ runtime notices. The GCC
Runtime Library Exception is not a reason to relicense this application as
GPL. Use the notices from the exact SDK/toolchain used for the image.

`main/lwip_mdns/mdns.c` preserves its original BSD source notice and identifies
the local modification. The firmware notice generator additionally carries
source-header notices from the configured build sources into binary packages.
The local `components/dhcpserver/dhcpserver.c` and `dhcpserver.h` differ from
the SDK originals and carry explicit modification notices without replacing
Espressif's original Apache-2.0 copyright headers. The options header is kept
as shipped by the SDK.

An expanded notice supplement for the already published 3.0.2 image is kept
at [licenses/firmware-v3.0.2-notices.txt](licenses/firmware-v3.0.2-notices.txt).
It is a legal-material supplement, not a replacement firmware image or a claim
that historical download packages have already been republished.

## Managed and other build components

Additional ESP-IDF managed components pulled at build time keep their
original licenses as declared in their respective `idf_component.yml` /
`LICENSE` files under `managed_components/`.

## Website browser installer (separate from the firmware)

ESP Web Tools 10.4.0 is vendored under
`website/assets/esp-web-tools/10.4.0/` (Apache-2.0). Its bundled dependencies
include esptool-js, Material Web and Improv Wi-Fi Serial SDK (Apache-2.0), Lit
packages (BSD-3-Clause), tslib (0BSD), and pako/zlib notices where bundled.
See that directory's `THIRD-PARTY-NOTICES.md` and `DEPENDENCY-LICENSES.txt`
for package provenance and verbatim license texts. These website dependencies
are not relabeled MIT or described as code embedded in the ESP32 image.

## Desktop flashing tool (separate from the firmware)

Easy Install includes an unmodified esptool Windows executable as a separate
program. The audited executable reports esptool 5.3.1; esptool is GPL-2.0-or-later,
not MIT. Its license accompanies the tool as `ESPTOOL-LICENSE.txt`.
Redistributing its executable also requires the applicable corresponding-source
arrangement; a license copy alone is insufficient. See
[Flashing-tool redistribution](docs/FLASHING-TOOL-LICENSES.md). A standalone tool
aggregated with the firmware does not by itself relicense the firmware GPL.

## Mattboxx edition, branding and optional support

The edition's name, custom artwork, additional features and documentation do
not replace the original authorship above. The root MIT notice is preserved
unchanged; third-party files retain their own terms. Brand assets use the
repository MIT license as documented in `assets/brand/BRAND.md`.

Optional https://ko-fi.com/mattboxx tips support the **Mattboxx Edition**,
not Csontikka or Cameron Malone. Separately labeled upstream support links
support their stated recipients. Tips do not purchase features or imply
upstream endorsement. These notices do not add a donation, citation, approval
or endorsement requirement to the applicable licenses.

---

## Trademarks

Names and marks belong to their respective owners and describe compatibility.
This project is an independent, community-built client and is **not**
affiliated with, endorsed by, or sponsored by Tailscale Inc. or the
Headscale project or Espressif. No trademark rights are granted by this notice.
