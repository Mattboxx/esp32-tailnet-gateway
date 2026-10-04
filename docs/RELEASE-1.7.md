# ESP32 Tailscale Gateway 0.1.29-Mattboxx-1.7

> Superseded by [1.8](RELEASE-1.8.md): a subsequently reproduced ntfy HTTPS
> command-reception stack overflow can cause repeated panic/reboots in 1.7.
> Upgrade if using ntfy commands. The original 1.7 images/checksums below are
> preserved; its short test notification/soak did not cover this command path.

Stable community release, October 4, 2026. For the ESP32-S3 N16R8 reference
board with 8MB octal PSRAM and the existing 4MB partition layout. Not a
universal image for all ESP32 variants or Ethernet board wiring.

## Original credits and upstream alignment

Based on [Csontikka's v0.1.29](https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/tag/v0.1.29),
commit `294af8880140ae78ec5b7153a22a6edfccc50732`, including all previously
integrated v0.1.20–v0.1.28 improvements. Credit remains with Csontikka,
microlink's authors and contributors, and gszigethy for the upstream routing
and SNMP contributions. Original MIT licensing is retained.

## Fixed in 1.7

- **CGNAT uplinks no longer impersonate WireGuard.** The tunnel is identified
  by its `wg` interface name, not its 100.64/10 address. This matters on LTE,
  Starlink and other CGNAT networks, especially at boot/reconnect before the
  tunnel has an address. Route hooks, exit supervision and selective NAPT
  share the corrected identification.
- **LAN bypass skips disconnected interfaces.** Both packet routing and the
  Tools explanation require UP and LINK_UP before selecting a physical
  interface's prefix. Stale IPs on disconnected interfaces cannot win that
  bypass lookup.
- **Peer-route generations are synchronized.** The supervisor builds a local
  table first. Publication, packet lookup and HTTP snapshots use a bounded
  cross-core critical section, so readers cannot mix old/new network/prefix
  entries. No allocation, logging, microlink calls or network I/O inside it.
- **Default-route changes run in the TCP/IP task.** The release SDK disables
  optional TCP/IP core locking; the old lock macros were therefore no-ops.
  A callback now performs the update in the correct context. Queue failure
  is logged and retried by the next supervisor cycle.
- **Web Session reports what is actually disabled.** An unlimited idle timer
  no longer shows a generic "Disabled" badge suggesting password protection
  is off. It distinguishes the password gate and idle timeout.

Checked HTTP handler registration, headroom (88 slots for 64 handlers) and
the anonymous/local favicon were already integrated in 1.6 and remain.
The SDK remains pinned to PlatformIO 6.13.0 / ESP-IDF 5.5.3, with 26 sockets
and 24 active TCP slots. Microlink's upstream gitlink did not change for 0.1.29.

## Your features stay intact

Independent LAN → Tailnet TCP/UDP forwarding and source restrictions; separate
AP-side forwarding; configurable AP policy; named WOL; MQTT/Home Assistant
monitoring and controls; optional ntfy alerts/info/WOL; 4via6; exit-node
advertising; web port/password/session controls; encrypted backups; CPU and
temperature monitoring; hardened optional read-only SNMP, OFF by default.
No Ethernet hardware or new wiring is required.

No telemetry, external crash/log uploader, automatic release polling/download,
Cloudflare speed test or hard-coded public DNS fallback is restored. Optional
user-enabled integrations, VPN, configured DNS and time synchronization still
produce their normal traffic. No personal settings/NVS are packaged.

## Validation and review

- ESP32-S3 release build passed: data/BSS 74,140 B; application partition usage
  1,664,612 B / 1,966,080 B.
- Actual route-hook/diagnostic C functions compiled in a host harness: CGNAT
  interface ordering, missing tunnel, UP/LINK_UP combinations, LAN prefixes,
  local versus forwarded exit traffic, accepted-route snapshots, all 256
  prefix-byte values and queued default-route updates/failures passed.
  Concurrent writer/reader stress passed 20,000 table publications without a
  mixed generation. CI also runs this harness with ASan/UBSan.
- Existing C regressions (DHCP/MQTT/CPU, route composition/version/auth cookie),
  eight upstream integration guards, three sensitive-scanner tests, 50,000
  malformed/mutated SNMP codec inputs, and nine actual-SPA synthetic-browser
  scenarios passed. The new UI case covers password/timeout labels.
- Authenticated OTA of the exact final image and successful boot into
  `0.1.29-Mattboxx-1.7`. Existing WiFi/VPN and integration configuration
  remained operational; SNMP stayed OFF and no community was changed.
- All 15 selected protected GET endpoints rejected anonymous access and
  loaded after login; the anonymous favicon returned its embedded SVG.
- A bounded 300-second hardware soak completed 58 status samples without
  reboot, WiFi/Tailscale loss or MQTT disconnect. Minimum sampled internal
  heap: 30,415 B. ntfy accepted the generic test notification; MQTT state was
  queued. Actual Automation UI showed Connected and Enabled · reachable.
- Twenty read-only route-diagnostic interface decisions were unchanged
  before/after OTA, using synthetic destinations and the board's existing
  configuration. No exit-node setting or network configuration was changed.
- Parent tracked content/artifacts/reachable history and microlink source
  sensitive-pattern scans: zero findings. CodeQL/sanitizer and privacy
  workflows on the default Main branch are release gates, not certification.
- Package verification passed: application bytes match the uploaded image,
  factory NVS area is all 0xFF, merged application is byte-identical, ZIP
  CRC/payload hashes and credential-pattern checks pass, and the Windows
  checksum verifier succeeds. Cached Espressif esptool archive digest and
  executable bytes still match the official v5.3.1 download verified in 1.6.
  No destructive factory flash was performed on the configured board.

## Coverage limits and security boundaries

The CGNAT carrier-uplink case is simulated in the actual-code host tests,
not a claim of testing a real LTE/Starlink uplink. Diagnostic route lookups
are not forwarded-traffic tests. No forced WiFi outage/roam, AP-client or
exit-node bulk traffic, all TCP/UDP/MagicDNS forwarding combinations, 4via6,
full HA control delivery or multi-day stress is claimed for this update.
SNMP's enabled-agent hardware tests belong to the earlier 1.6 validation;
this update does not re-enable it or change its community.

The UI remains HTTP-only; use a trusted LAN or encrypted tailnet and do not
expose it to the public Internet. SNMPv1/v2c is unencrypted and remains OFF
when unused. Pattern scans and CodeQL cannot guarantee no private data or
vulnerabilities exist. Stable is a community release channel, not certification.

## Download and flash

- `firmware.bin`: web OTA image; preserves settings. Upload through System.
- `firmware-factory.bin`: merged fresh-board image at `0x0`, not for web OTA
  and not a settings-preserving image.
- `ESP32-S3-router-0.1.29-Mattboxx-1.7-windows.zip`: images, official Espressif
  esptool v5.3.1, license, checksums and guided Windows batch files.
  `UPDATE_KEEP_SETTINGS.bat` preserves NVS; `CLEAN_INSTALL_ERASE_ALL.bat`
  requires explicit YES and destroys settings/identity. Use the update path
  unless you deliberately want a clean installation.
- `RELEASE-SHA256SUMS.txt`: SHA-256 checksums for the downloadable assets.

Application SHA-256:
`4067f45fca22cef741477784637a71dd443e7a4df103bffba5524763ec7be1b2`.
Older 0.1.19/1.5 and 0.1.28/1.6 releases are unchanged.
Full integration record: [UPSTREAM-0.1.29.md](UPSTREAM-0.1.29.md).
