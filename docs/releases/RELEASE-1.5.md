# ESP32 Tailscale Gateway 0.1.19-Mattboxx-1.5

Stable release: improved CPU diagnostics, safer MQTT controls, more robust
Tailscale configuration handling, ntfy commands and DHCP parsing.

Based on [Csontikka's original ESP32 router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink). This release contains
the Mattboxx edition's fixes and integrations; upstream credits are retained.

## Important version note

The exact application and factory images tested on the ESP32-S3 were promoted
without rebuilding. The dashboard therefore still reports
`0.1.19-Mattboxx-1.5-dev`. This is intentional: GitHub release/tag 1.5 contains
that same tested binary, not a different or older image. Devices already
running the tested candidate do not need to reflash for this promotion.

## Fixed and improved since 1.4

- **CPU monitoring:** independent two-second background sampling, correct
  total/per-core calculations and counter-rollover handling. CPU values are
  shared by the dashboard, ntfy info and three Home Assistant CPU sensors.
  Unavailable or stale samples are not reported as a measured zero.
- **MQTT command validation:** malformed switch payloads no longer silently
  turn features off; empty or invalid rule indexes cannot select rule zero.
  Embedded NULs, incomplete messages and empty payloads are rejected.
- **Restart/reconnect safety:** coalesced manager-owned requests prevent
  repeated restart tasks. Unchanged settings do not cause unnecessary writes
  or restarts, and failed saves do not trigger reconnects. MQTT operations
  that reinitialize Tailscale now explicitly restart the entire device.
- **Tailscale configuration lifetime:** boot-lifetime copies prevent saved
  credential/hostname changes from invalidating pointers retained by the
  running VPN. The active handle is published only after successful startup.
- **Input limits:** reject excessive route lists, invalid numeric Tailscale
  settings and truncated or invalid allowed-source CIDRs before applying them.
- **ntfy commands:** leading/trailing spaces and line endings are accepted,
  including `info` sent with a final newline. Command length is bounded and
  spaces inside saved WOL names are preserved.
- **DHCP hardening:** validate request headers, cookie and options before
  changing leases; copy complete packet chains; limit allocation sizes and
  handle lease-allocation failure safely.
- **Repository privacy checks:** scan reachable Git history and artifact
  credential patterns with redacted diagnostics. Add host regression tests
  for DHCP parsing, MQTT controls, CPU calculations and the secret scanner.

## Verified on the running ESP32-S3

- LAN-to-Tailnet TCP and UDP round trips with the ESP access point disabled.
- Source-CIDR restrictions, disabled forwarding rules, and HTTP 409 rejection
  of a forwarding rule conflicting with the web UI port.
- ntfy test notification and a server-observed `info` reply, including CPU
  diagnostics and the saved WOL device name.
- Three correct WOL magic packets independently received on the LAN.
- MQTT connected and its publish request accepted; independent broker/HA
  verification is still pending.
- Changing CPU readings and no reset during functional tests. No checked
  panic, heap-corruption, stack-canary or assertion markers in buffered logs.

Build and host regression tests passed. Source/history and release-payload
scans found no credential-pattern matches; these are heuristic checks, not a
guarantee that all possible sensitive data or vulnerabilities can be detected.

## Download and installation

- **Existing installation / web OTA:** upload `firmware.bin` through the
  authenticated firmware-update page. Do not upload the factory image as OTA.
- **Easy Windows USB update:** extract the Windows ZIP and double-click
  `UPDATE_KEEP_SETTINGS.bat`. It targets the existing 4 MB partition layout
  and preserves the settings partition. Close serial monitors first.
- **Fresh installation:** use `CLEAN_INSTALL_ERASE_ALL.bat` from the ZIP.
  It requires typing `YES` and erases all saved WiFi, VPN and other settings.
  `firmware-factory.bin` is the combined image for a fresh USB installation.
- The ZIP includes Espressif esptool 5.3.1, its license, instructions and
  checksums. The reference target is ESP32-S3 N16R8; other variants are not
  hardware-validated by this release.
- `SHA256SUMS.txt` verifies the standalone images and Windows ZIP.

## Known validation limits

This is a stable community release, not a formal security certification.
Real-client AP DHCP, Home Assistant discovery/state updates and incoming MQTT
controls, settings persistence across reboot, serial boot diagnostics,
exit-node/IPv6 behavior and long-uptime rollover still need hardware checks.
WOL packet delivery was verified; actual waking of a sleeping target was not.

The ntfy offline-only command option still suppresses commands while Tailscale
is connected. Disable that option if replies are wanted while it is online.
HTTP administration and physical flash/NVS access retain the existing trust
boundaries described in [SECURITY.md](https://github.com/Mattboxx/esp32-tailscale-gateway/blob/mattboxx/SECURITY.md).
No telemetry, external log collection or new VPN provider was added.

See the [detailed validation record](https://github.com/Mattboxx/esp32-tailscale-gateway/blob/mattboxx/docs/REVIEW-1.5.md)
for test evidence and limitations. Older release assets are unchanged.
