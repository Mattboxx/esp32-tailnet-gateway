# ESP32 Tailscale Gateway 0.1.31-Mattboxx-1.10-dev.11

Beta hotfix, October 11, 2026. Supersedes dev.10; stable 1.8 remains unchanged.
Enable the beta channel to discover this compatible newer custom build.

## Original credits

Based on [Csontikka's router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
through v0.1.31 and [microlink](https://github.com/Csontikka/microlink).
Original authors' credits, contributions and MIT licensing remain intact.

## Reported crash and correction

The exact dev.10 debug image resolves the repeating addresses in the supplied
trace to `ts_input_hook` (SNMP traffic accounting) and `wg_input_hook` (network
input wrapper). Their periodic installers independently saved the currently
installed callback as the original. With both installed, they could save each
other and recurse indefinitely, exhausting the stack and provoking a panic or
watchdog restart. This is not an ntfy login or server-configuration failure.

Remove the redundant transparent WireGuard input wrapper. Tailnet listener
policy still runs in the IPv4-core wrapper before SDK input. SNMP remains the
tunnel input-wrapper owner and retains RX/TX counters. Physical STA/AP ACL,
TTL and MTU hooks are unchanged and are installed once before SNMP starts.

All earlier custom features remain: separate LAN-to-Tailnet and AP forwarding,
MQTT/Home Assistant, ntfy, named WOL targets, AP policy, Web UI port/password/
session settings, opt-in GitHub stable/beta/manual/automatic updates, route and
exit controls, Ethernet support, diagnostics and read-only SNMP.

## Verification

- The same actual-C combined-installer regression fails against published
  dev.10 before invoking the recursive chain, and passes after this correction.
- 4,000 alternating network/SNMP refreshes, both installation orders, tunnel
  reconnect/address reuse and 20 disable/enable cycles preserve the original
  chain and exact-once traffic counting. CI also runs the test with ASan/UBSan.
- Feature-preservation, SNMP codec, ntfy, forwarding configuration/packet-path,
  routing, update and 16 actual-SPA browser scenarios pass locally. The real
  pinned lwIP/NAPT suite includes 38 cases and 40,000 mutations.
- The exact linked Ethernet and raw-IP input callers still enter the policy
  wrapper; its stack budgets remain unchanged.
- The exact ESP32-S3 image was installed on the reference board by authenticated
  OTA in 37 seconds. Eight saved-setting groups were unchanged, compared only
  in memory. SNMP v1/v2c identity, both 82-object walks and three live
  disable/enable cycles passed.

- Thirty real HTTP replies over the board's Tailnet IP completed in 64 seconds
  while the SNMP-enabled soak was still running. Connectivity became available
  after the host joined the matching tailnet; requests traversed the actual tunnel.
- Twelve real Tailnet SNMP v1/v2c identity replies succeeded across repeated
  installer ticks, followed by both full LAN walks and live disable/enable checks.

- SNMP remained enabled for 604 seconds across 117 live queries without an
  observed reboot or WiFi/Tailscale loss. It was restored OFF with community,
  name, contact and location unchanged.
- A concurrent 302-second ntfy HTTPS soak completed three `info` commands and
  verified replies at the configured broker, with MQTT connected and no reboot.
  Minimum sampled remaining ntfy stack: 5,824 B; internal heap: 13,703 B.
  These samples do not measure all transient peaks. The original command
  availability setting was restored; private notification bodies were not
  displayed or saved.
- GitHub's regression/credential-history workflow and C/C++/Python CodeQL
  completed successfully for the firmware-source commit. Pattern checks on
  source/history and packaged images reported no findings; they are not an
  exhaustive guarantee that no sensitive data can exist.

## Assets and updating

Use `firmware.bin` for **System → Firmware update**, or **Install latest update**
with the beta channel enabled. The Windows ZIP includes esptool and its license,
hashes and `UPDATE_KEEP_SETTINGS.bat`. Settings are preserved by these updates.
`firmware-factory.bin` / `CLEAN_INSTALL_ERASE_ALL.bat` are only for a fresh install
and erase saved settings after confirmation.

OTA SHA-256:

`41ebc98f3637496ac6f2461f4e188b9ba9e8655d91afe85d3a87cf48aa101868`

Targets ESP32-S3 N16R8 with 8MB octal PSRAM and the existing 4MB partition layout.
Application use: 1,696,344 / 1,966,080 B; static RAM: 76,900 B.

## Limits

This fixes the identified crash, not a promise that no other bug exists.
The combined callback regression uses actual C functions with synthetic
interfaces; the reference board is additionally exercised with real inbound
Tailnet traffic and enabled SNMP. These checks do not establish reliability
for every network, packet shape or operating duration.
Physical Ethernet hardware, arbitrary remote forwarding services, full exit-node
Internet traversal and a separate Home Assistant frontend were not tested here.
Keep SNMP OFF unless needed and restrict the HTTP UI to a trusted LAN/tailnet.
