# ESP32 Tailscale Gateway 0.1.31-Mattboxx-1.10-dev.10

**Known crash: superseded by dev.11.** A reported watchdog/panic trace resolves
to recursive SNMP/Tailnet input wrappers. Earlier short tests did not cover
their alternating installers together. Do not use this candidate with SNMP;
upgrade to the fixed candidate. The previous test results below are historical,
not evidence that this build is reliable under that combination.

Beta development candidate, October 10, 2026. The stable 1.8 release is not
replaced. Enable the beta channel to discover this candidate from an older
compatible custom build, or download it explicitly. An already installed
identical/newer version correctly reports no available update.

## Original credits

Based on [Csontikka's router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
through v0.1.31 and [microlink](https://github.com/Csontikka/microlink).
Credit and MIT licensing remain with their authors and contributors, including
the original routing/SNMP contributions. Mattboxx additions remain independent
from the upstream AP-side forwarding and original manual route settings.

## Improvements included

- Upstream v0.1.30/v0.1.31 integration while retaining the custom features.
- Reliable Automation loading, explicit unavailable/loading states and the
  original dark theme with graphical enable switches.
- ntfy stack, bounded command streaming, atomic settings/cursors and failure
  reporting fixes. No local log excerpts in outgoing alerts.
- Correct routing on CGNAT uplinks, lifecycle-safe interface discovery and
  synchronized route snapshots.
- Independent LAN-to-Tailnet forwarding with installed-state/source-policy
  enforcement, safe fragmented/split-header handling and bounded reassembly.
- Transactional AP/Tailnet saves and toggles, consistent joint installation,
  and validation/compaction of legacy saved records.
- Protect both the running and next-boot Web UI ports from forwarding conflicts.
  Validate admin-port requests before conversion and retain settings on failure.
- Opt-in GitHub checks, manual latest-version download/install, scheduled
  automatic installation and explicit stable/beta channel selection.
- Preserve MQTT/Home Assistant, saved named WOL targets, AP policy, password and
  session controls, exit advertising/server DNS, 4via6, diagnostics and SNMP.

See [the detailed changelog](../../CHANGELOG.md) and
[update behavior](../UPDATES.md). No new account credentials, telemetry or external
crash upload are added. Optional enabled integrations still use their configured
services, and explicitly requested update checks contact GitHub.

## Verified on the reference board

The exact ESP32-S3 WiFi image below was installed by authenticated web OTA.
The board restarted into the expected version in approximately 40 seconds.
Eight saved-setting groups were compared entirely in memory before/after;
they were unchanged. No credential/configuration dump was written to Git.

- Fifteen protected read endpoints rejected anonymous requests and loaded
  successfully after login. The local favicon was served correctly.
- WiFi, Tailscale and MQTT reconnected; the ntfy HTTPS test was accepted.
- A 303-second ntfy command soak completed three `info` commands/replies with
  no observed reboot, connection loss or command error. Replies were verified
  at the configured broker without displaying or saving their private bodies.
  All saved WOL names and forwarding/web/update sections were present.
- Minimum sampled remaining ntfy stack: 5,976 B. Minimum sampled internal heap:
  17,963 B. These samples do not measure every transient allocation peak.
- Twenty synthetic route-diagnostic requests completed. These are diagnostics,
  not proof of end-to-end forwarded traffic.
- SNMP v1/v2c identity, both 82-object walks and live enable/disable behavior
  passed. The agent was restored OFF with its original descriptive settings.

## Software and artifact checks

The pinned ESP-IDF 5.5.3 build uses 31 sockets and the existing 4MB partition
layout. Flash/application use is 1,697,024 / 1,966,080 B; static RAM is 76,908 B.
The ntfy worker's exact linked frame is 496 B; the complete private reassembler
frame is 144 B. Ethernet/raw-IP callers enter the linked policy wrapper.

Regression suites cover the existing custom features, ntfy, SNMP, route and
interface hooks, NVS saves, eight concurrent forwarding/admin operations,
HTTP port validation, update selection/download failure handling and packaging.
The real pinned lwIP/NAPT path passes 38 cases, including 40,000 mutations.
CI uses ASan/UBSan for the applicable C suites. Actual-SPA browser tests pass
16 scenarios. Credential-pattern checks on content/history/artifacts and the
current microlink checkout report no findings; these are not exhaustive proof
that no sensitive data or bug can exist.

OTA `firmware.bin` SHA-256:

`017835e2200f2073379c46c056a498ae869da9fca205a19d6c65397f61bbd35e`

After publication, all four GitHub asset digests were compared with the local
package. An anonymous OTA download was byte-identical to the flashed image.
The real C updater selector accepted the actual published catalog from an
older development version with beta enabled, excluded it in stable-only mode,
and did not offer an identical installed version. A real-board GitHub check
also completed successfully without changing the saved update preferences.

## Download and flash

Use `firmware.bin` for **System → Firmware update**. It preserves settings.
The Windows ZIP includes esptool, its license, verified hashes and
`UPDATE_KEEP_SETTINGS.bat`; double-click it with the USB data cable connected.
`firmware-factory.bin` and `CLEAN_INSTALL_ERASE_ALL.bat` are for a fresh install
only. The latter requires confirmation and erases all device settings.

This image targets ESP32-S3 N16R8/8MB octal PSRAM, not every ESP32 variant,
board-specific Ethernet wiring or partition layout.

## Coverage limits

This remains a beta candidate, not a guarantee of universal stability or a
security certification. Ethernet hardware, arbitrary remote forwarding
services, full exit-node Internet traversal and a separate Home Assistant
frontend were not exercised in this board session. Fragment/reassembly and
configuration-race checks use real C/SDK implementations with synthetic
interfaces/adapters; they do not replace those end-to-end hardware tests.
Keep SNMP OFF unless needed and use the HTTP UI only on a trusted LAN/tailnet.

Older stable assets remain available for an explicit rollback; automatic
updates never deliberately downgrade to them.
