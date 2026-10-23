# ESP32 Tailscale Gateway 0.1.28-Mattboxx-1.6

Stable community release, October 2, 2026. Target: ESP32-S3 N16R8 with 8MB
octal PSRAM, using the existing 4MB partition layout. Not a universal binary
for all ESP32 variants. The embedded firmware version is exactly
`0.1.28-Mattboxx-1.6` (no development suffix).

## Original credits and upstream base

Based on [Csontikka/esp32-tailscale-subnet-router v0.1.28](https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.28),
plus the subsequent `e3e2e50` HTTP-registration/favicon fix. Includes the
earlier v0.1.20–v0.1.27 improvements and the upstream microlink revision shared
by v0.1.27/v0.1.28. Full original credit belongs to Csontikka, microlink's
authors and contributors; gszigethy contributed the upstream SNMP agent.
Original MIT licensing is retained. See the integration records for deliberate
adaptations rather than claiming every upstream implementation is unchanged.

## What you get

- Tailscale/Headscale subnet routing and an IoT WiFi gateway on one board.
- Independent LAN → Tailnet TCP/UDP forwarding to peer IPv4/MagicDNS names,
  source-subnet restrictions, live counters and per-rule enable controls.
  Existing uplink → AP-client port forwarding stays separate.
- Configurable AP policy: always available or standby while uplink is online.
- Named WOL devices, MQTT monitoring/commands, Home Assistant discovery and
  optional ntfy alerts/commands, including replay-protected WOL and info.
- 4via6 support, exit-node advertising, configurable web port, optional web
  password/session timeout, CPU/per-core monitoring and encrypted backups.
- Optional read-only SNMP monitoring, off by default, with standard MIBs for
  interfaces, CPU, memory, task count and temperature. No Ethernet board is
  required. New SNMP/socket diagnostics are exposed through MQTT/HA and info.

## Fixed since 1.5 / early 1.6 candidates

- Automation requests wait for authentication, and login reloads the active
  page rather than Status alone. A WOL read failure cannot discard MQTT data.
- Unknown configuration is Loading/Unavailable, not falsely Disabled. Settings
  cannot be saved before their first successful read. Transient reads have a
  bounded timeout/retry; authentication failures and writes are not retried.
- Pinned PlatformIO 6.13.0 / ESP-IDF 5.5.3 with 26 socket slots. A build guard
  rejects stale lower SDK settings. This fixes the observed ntfy connection
  failures caused by the older binary's 10-socket configuration.
- Every HTTP handler checks registration; 88 slots cover all 64 endpoints
  with headroom. A local/embedded favicon removes needless 404 log noise.
- SNMP and the dashboard share one temperature-sensor owner. ACL hooks install
  first, and SNMP traffic-hook changes run in the TCP/IP thread.
- SNMP's worker alone closes its socket; disable cannot recycle a descriptor
  during receive/send. Replies hold the configuration mutex. Unsupported
  versions, invalid integer widths and OID overflow are rejected.
- CI also runs on the actual default Main branch, including codec sanitizers
  and tracked/history/submodule sensitive-pattern checks.

## Privacy removals stay removed

No anonymous telemetry sender, external crash/log uploader, automatic release
polling/downloading, Cloudflare speed-test request or hard-coded public DNS
fallback is restored. Optional user-enabled MQTT/ntfy traffic and normal VPN,
DNS and time synchronization remain. Device logs remain local unless the user
explicitly enables an integration that sends diagnostic context.

SNMPv1/v2c is unencrypted and can reveal interface addresses and operator-entered
contact/location. Keep it off when unused, select a private community and
restrict UDP 161 with the firewall. The community/contact/location are not
added to MQTT state or ntfy info. The web UI remains HTTP-only: trusted LAN or
encrypted tailnet access, never public Internet exposure.

## Validation actually performed

- ESP32-S3 release compilation on the pinned IDF 5.5.3 SDK. Data/BSS: 74,132 B;
  application partition usage: 1,664,324 B / 1,966,080 B.
- Host C regression binaries: DHCP bounds, MQTT values/indexes, CPU arithmetic
  and rollover, route composition/deduplication, client-version and long-cookie
  exact token matching.
- Seven Python integration guards, three scanner tests and eight browser
  scenarios rendering the actual SPA with synthetic APIs, including SNMP.
- Actual SNMP codec/PDU functions: 50,000 malformed/mutated inputs, bounded
  responses, v1/v2c, community checks, SET/version/integer/OID rejection.
- Manual authenticated OTA and successful boot of the exact release image.
  Existing WiFi, VPN identity, saved WOL targets and integration settings stayed
  present. Session authentication was required again after this update.
- Actual device SNMP: 82-object walks over v1 and v2c; wrong/empty communities
  and SET rejected; malformed, truncated and oversized UDP inputs survived;
  three disable/enable cycles. Restored OFF with all descriptive strings and
  the existing community unchanged after the authorized temporary test.
- All 15 selected protected GET endpoints rejected unauthenticated access and
  loaded after login; favicon returned its SVG. Compiled diagnostics reported
  26 sockets and 24 active TCP slots.
- MQTT connected, status queued, and ntfy test notifications accepted by the
  configured server. Automation displayed the correct enabled/reachable state.
- On October 2 the board reported 31,130 seconds of uptime (over 8.6 hours)
  on this image. A further bounded smoke test completed nine repeated status
  samples without reboot, uplink/tunnel loss or MQTT disconnect. Internal heap
  minimum during those samples: 30,443 B. This is not a long-term soak guarantee.
- Parent tracked files/artifacts/reachable Git history and microlink source
  sensitive-pattern scans: zero findings. Pattern scans are not proof that no
  private data or vulnerabilities exist.
- Package: tested application SHA matches; factory NVS region is all 0xFF;
  merged application matches byte-for-byte; ZIP CRC/payload hashes and embedded
  credential-pattern checks passed. Packaged Windows checksum verifier passed.
  Espressif's standalone esptool download hash matched its official release.

## Coverage limits

The original upstream hardware results are not presented as tests of this fork.
This release was not destructively factory-flashed onto the configured device.
Fresh installation scripts and the merged image were validated offline.
The earlier 1.5 routing/WOL checks are not claimed as a repeat on IDF 5.5.3.
Complete HA entity/control end-to-end tests, AP-client DHCP/ACL traffic, forced
WiFi roaming, all TCP/UDP/MagicDNS forwarding combinations, 4via6, exit-node
bulk/IPv6 scenarios and multi-day stress remain outside this validation.
Stable names the community release channel, not a security certification or
claim that every possible scenario has been tested.

## Download and flash

- `firmware.bin`: authenticated web OTA; preserves configuration.
- `firmware-factory.bin`: fresh-board merged image at offset `0x0`; not for web
  OTA and not a settings-preserving image.
- `ESP32-S3-router-0.1.28-Mattboxx-1.6-windows.zip`: firmware, bootloader,
  partitions, Espressif esptool v5.3.1, license, README, checksum verifier and
  two guided batch files. UPDATE_KEEP_SETTINGS.bat preserves NVS; the separate
  CLEAN_INSTALL_ERASE_ALL.bat requires explicit YES before erasing everything.
- `RELEASE-SHA256SUMS.txt`: hashes of the three downloadable assets.

Application SHA-256:
`89bb518f91ad65695dcf2379fdd25b52d76718cd54e032aff7d461aa512ed390`.
The published application is the identical image tested on the board, not a
post-test rebuild. Prior release assets, including 0.1.19/1.5, stay unchanged.
