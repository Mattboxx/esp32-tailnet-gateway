# 1.5 review and validation record

The tested development candidate is promoted unchanged to the project's
stable 1.5 release channel on 2026-09-08. This is not a hardware or security
certification. Existing 1.4 assets remain unchanged. No new VPN implementation,
telemetry, external log collection or credential export was added.

## Fixes and additions

| Area | Finding | Change |
| --- | --- | --- |
| MQTT commands | Unknown switch payloads became OFF; an empty forwarding index selected rule zero. | Explicit ON/OFF, true/false, 1/0 parsing and bounded decimal indexes. Embedded NULs, incomplete messages and empty payloads are rejected. |
| MQTT lifecycle | Commands could allocate repeated restart tasks; reconnect destroyed a VPN handle still used by other tasks. | Manager-owned, coalesced operations. Tailscale reinitialization uses a full device restart, clearly named in HA. Identical switch values do not reboot or rewrite settings. Failed saves do not trigger reconnects. |
| Tailscale settings | microlink retained auth-key/hostname pointers that web saves could free. | Immutable boot-lifetime copies, and delayed publication of the handle until start succeeds. Changes take effect after restart. |
| Settings validation | Overlong routes could be silently truncated; out-of-range numeric settings were mirrored into runtime. | Reject route text over 400 bytes and invalid peer/DERP/threshold values before writes. Reserve buffer space for 4via6 and exit-node routes. Reject truncated/invalid source CIDR prefixes. |
| CPU diagnostics | Sampling depended on dashboard polling and used wrap-sensitive accumulated counters. | Two-second background sampling, per-core modular deltas and shared snapshots. HA receives three CPU sensors; ntfy info includes total/core values; dashboard tooltip shows cores. Missing/stale samples are not presented as a measured zero. |
| ntfy | Trailing newline or spaces prevented an otherwise correct info/WOL command from matching. | Trim edges, preserve internal WOL-name spaces, and bound command length. |
| DHCP | Lease allocations were dereferenced without checking failure; receive copied only two pbuf segments and accepted malformed request shapes. | Check allocations, copy the full chain, bound requests to 1500 bytes, validate Ethernet BOOTP header/cookie/options before modifying leases. |
| Repository checks | The previous workflow scanned only the tip and printed matched secret values. | Shared local/CI scanner, full reachable-history credential checks, redacted diagnostics and no filenames interpolated into shell code. |

## Upstream advisory triage

The build's project description identifies the actual framework as ESP-IDF
5.3.1. Another installed SDK is not evidence of what was compiled.

- [GHSA-3j8v-xgrq-5vg8](https://github.com/espressif/esp-idf/security/advisories/GHSA-3j8v-xgrq-5vg8): the SDK contains the affected WebSocket subprotocol parser, but this build has WebSocket support disabled and registers no WebSocket handlers. Keep that configuration; enabling it requires a patched SDK.
- [GHSA-g764-gwc3-75m5](https://github.com/espressif/esp-idf/security/advisories/GHSA-g764-gwc3-75m5): this firmware uses its own linked DHCP component. Its option parser already checked PAD/END, lengths and per-option fields. This review additionally hardens the receive and allocation paths; it does not claim the entire SDK is patched.

These are targeted checks, not an exhaustive CVE inventory. A newer SDK still
requires a separate compatibility and on-board regression pass.

## Reproducible local checks

```sh
gcc -std=c11 -Wall -Wextra -Werror tools/test_control_validation.c -o control-tests
./control-tests
python -m unittest discover -s tools -p test_sensitive_scanner.py
python tools/check_sensitive_data.py --history
pio run -e esp32-s3
```

The C tests cover accepted/rejected MQTT payloads, indexes, CPU arithmetic and
rollover, and valid/truncated/malformed DHCP requests. Python tests use synthetic
credentials to check detection without embedding real secrets. The scanner
checks source heuristics at the tip and high-confidence credential patterns in
history; it cannot reliably identify every SSID, human name or password.

## Validation scope and outstanding hardware checks

Local validation on 2026-09-07 passed: ESP32-S3 compilation, C regression
tests, three scanner unit tests, JavaScript syntax and 331 unique HTML IDs.
The application uses 1,609,895 bytes of the 1,966,080-byte application partition.
The gateway history scan checked 879 blobs with no credential-pattern matches.
A separate microlink history scan checked 330 blobs: nine matches were manually
triaged as all-`x` placeholder keys in upstream examples, not actual credentials.
These counts describe the local fetched history, not every remote GitHub object.
The final tip scan covered 152 paths and 16 existing artifact payloads without
findings. The separate development ZIP passed CRC and ten SHA-256 manifest
checks; no credential patterns were found in its eleven payloads. esptool
validated the application image and its `0.1.19-Mattboxx-1.5-dev` version.

- Boot and serial logs, idle/load CPU behavior and long-uptime rollover.
- AP DHCP discover/renew/release from real clients, including chained receives.
- MQTT/HA discovery, no-op and malformed controls, controlled restarts and WOL.
- ntfy info/WOL with trailing newlines and private-detail behavior.
- Login/settings persistence, LAN-to-Tailnet TCP/UDP forwarding with AP off,
  source-CIDR rejection, and exit-node routing/IPv6 behavior.

## Live checks after the user's flash

On 2026-09-07 the user flashed the candidate through the web interface. The
authenticated LAN API confirmed `0.1.19-Mattboxx-1.5-dev`. No serial port was
available; these observations come from live APIs, network traffic and the
device's buffered HTTP logs, not a serial boot capture.

- CPU samples changed between observations and included both cores. At the
  end of the functional tests, uptime was 21,284 seconds with no intervening
  restart, CPU load was 3%, temperature was approximately 49.9 C, and internal
  free memory was 41,227 bytes. These are snapshots, not a long-term leak test.
- With the AP disabled, a LAN client sent unique TCP and UDP payloads through
  temporary forwarding rules to an echo service bound to a different peer's
  Tailscale interface. Both replies matched. The echo service accepted only
  the ESP32's Tailscale source address.
- A nonmatching allowed-source CIDR blocked both protocols and increased the
  blocked counters without reaching the echo service. Disabled rules did not
  forward traffic. An attempted web-port conflict returned HTTP 409 and left
  the previous rules intact. Original forwarding rules were restored and the
  temporary echo listeners were closed.
- The ntfy test notification was independently retrieved from the configured
  server. With the offline-only command restriction temporarily disabled, an
  `info` command with a trailing newline produced a server-observed reply
  containing CPU diagnostics and the saved WOL device name. Command errors
  remained zero. The original offline-only restriction was restored.
- A saved-device WOL request succeeded. A LAN UDP receiver independently
  received all three exact 102-byte magic packets from the ESP32, matching
  the configured target MAC. Actual waking of a sleeping target was not
  observed; delivery is not proof that its BIOS/NIC accepts WOL.
- MQTT remained connected and its publish endpoint returned success. Broker
  receipt, Home Assistant discovery/state updates and incoming MQTT controls
  still need independent verification.
- Final buffered logs contained none of the checked panic, heap-corruption,
  stack-canary, assertion, CPU-sampler-start or MQTT-save failure markers.
  This is not proof that every possible error or vulnerability is absent.

Real-client AP DHCP, MQTT/HA controls, settings persistence across reboot,
serial boot diagnostics, exit-node/IPv6 behavior and long-uptime rollover
remain unverified on hardware. Original AP and ntfy policies were preserved.
No credentials, topic names, MAC addresses or private network addresses are
included in this report. The subsequent stable 1.5 release uses the same
application and factory images, with updated package instructions and release
notes. No additional flash or hardware validation is implied by promotion.
