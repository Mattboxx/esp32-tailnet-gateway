# ESP32 Tailscale Gateway 0.1.29-Mattboxx-1.8

Stable community hotfix, October 4, 2026. ESP32-S3 N16R8 reference board,
8MB octal PSRAM and the existing 4MB partition layout. Not a universal image
for every ESP32 variant or Ethernet pinout. **Recommended update for ntfy users.**

## Original credits

Based on [Csontikka/esp32-tailscale-subnet-router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
v0.1.29 and [Csontikka/microlink](https://github.com/Csontikka/microlink).
Credit remains with the original authors/contributors, including gszigethy's
routing/SNMP work. Original MIT licensing is retained. All Mattboxx features
and [the 1.7 upstream routing improvements](https://github.com/Mattboxx/esp32-tailscale-gateway/blob/Main/docs/RELEASE-1.7.md) remain intact.

## Why this hotfix exists

A real board running 1.7 repeatedly panicked in the `ntfy` task. Decoding
its backtrace against the exact release ELF identified
`vApplicationStackOverflowHook`, not a WiFi password or ntfy credential error.
GCC had inlined the reporting/polling paths into the worker, leaving its
4,240-byte frame resident during TLS on an 8,192-byte stack. The previous
short 1.7 smoke test sent a notification but did not cover this command path.

## Fixed

- Keep polling, `info`, command handling, publishing and alert construction
  in separate compiler frames. The worker's frame is now **496 bytes**.
- Move the 2,300-byte alert log buffer to the heap and free it before HTTPS.
  Allocation failure cleans up and returns an error, without a reboot.
- Reserve **12,288 bytes** for the ntfy worker and check task creation.
  `/api/ntfy` exposes `task_running` and `stack_min_free_bytes` for diagnosis.
- Synchronize ntfy status counters with their readers; alert retry decisions
  use that alert's result, not a racing web-test publication result.
- Propagate failed `info` publications to command errors instead of counting
  them as successful commands.
- Latch oversized command responses and reject them before parsing. No
  partially reconstructed HTTP stream is used to execute commands.
- Correct the panic popup: the pre-crash log card is in **Diagnostics**.

There is no settings migration/erase. MQTT/HA, named WOL, ntfy privacy options,
AP policy, separate LAN-to-Tailnet/AP forwarding, exit advertising, 4via6,
SNMP and authentication controls are preserved. No automatic telemetry,
external crash upload, release polling or public speed tests are restored.
Optional configured integrations still send their normal user-enabled traffic.

## Validation

- ESP32-S3 release build: data/BSS **74,156 B**; application partition usage
  **1,664,176 / 1,966,080 B**, using the pinned IDF 5.5.3 / 26-socket SDK.
- Exact final ELF frame check: worker 496 B, poll 960 B, info 1,136 B,
  command handler 320 B, publisher 672 B, alert builder 32 B. This check
  rejects the archived original 1.7 ELF's 4,240-byte worker frame.
- Actual C callback, command accounting and alert builder pass bounds,
  overflow-latch, publish-failure and allocation-failure/cleanup tests.
  CI runs these with ASan/UBSan. Existing C regressions, 20,000 concurrent
  route publications, 50,000 mutated/malformed SNMP inputs, eight integration
  guards, three scanner tests and nine synthetic actual-SPA scenarios pass.
- Authenticated OTA of the exact final image, preserving existing settings.
  A **605-second** actual-board HTTPS ntfy soak completed **five `info`
  commands/replies**, with network details enabled, zero command errors,
  no reboot or WiFi/Tailscale/MQTT disconnect. Replies were checked at the
  configured broker without printing/saving their private contents. Minimum
  remaining worker stack: **5,744 B**; minimum sampled internal heap:
  **21,851 B**. The SDK's lifetime internal-heap low-water mark reached
  **8,971 B** during transient allocations: sampled heap is not peak usage.
  The original offline-only command policy was restored afterwards.
- Restarted with ntfy already enabled and the original offline-only policy:
  a further **120 seconds** without a second reboot, minimum stack **7,932 B**,
  and WiFi/Tailscale/MQTT operational after boot. ntfy remains enabled and the
  saved user configuration/policy is preserved.
- All 15 selected protected endpoints rejected anonymous requests and worked
  after login. A separate **184-second / 36-sample** board smoke completed
  without restart or integration disconnect; sampled heap minimum 22,275 B.
  SNMP remained OFF. An earlier parallel web smoke lost its authentication
  session and was rerun; the ntfy soak and uptime did not reset.
- Configured ntfy topic, MQTT broker URI and WiFi SSID are absent from the
  application image (compared privately, without printing their values).
- Package checks passed: exact OTA image, byte-identical merged application,
  blank factory NVS, ZIP CRC/payload hashes, credential-pattern scans and the
  included Windows checksum verifier. The official esptool v5.3.1 executable
  is unchanged from the previously verified package. No destructive clean
  installation was performed on the user's configured board.
- GitHub CodeQL (C/C++ and Python) and privacy/sanitizer workflows passed on
  the firmware fix commit; zero open CodeQL alerts at review time. Parent
  reachable history and microlink tracked content scans found no patterns.

## Coverage limits

This is bounded regression testing, not multi-day stability or security
certification. No deliberate WiFi/Tailscale outage, physical WOL delivery,
complete HA-control/routing matrix or Ethernet hardware test is claimed.
The alert builder's error paths are tested with synthetic dependencies, not
by disconnecting the user's VPN. HTTP authentication sessions are limited to
four; a new login can evict an existing test/browser session.

ntfy messages/log tails can contain network details when enabled. Private
topics and access controls remain recommended. Web UI is HTTP-only: trusted
LAN/encrypted tailnet only. SNMPv1/v2c is unencrypted; leave it OFF when unused.
No private device configuration, NVS image, credentials or live message/log
payloads are included in the public source or release assets. Pattern scans
and CodeQL cannot guarantee the absence of every vulnerability or secret.

## Download and flash

- `firmware.bin`: web OTA image, **preserves settings**. Upload through System.
- `firmware-factory.bin`: merged fresh-board image at `0x0`; **not** for web
  OTA or settings-preserving updates.
- `ESP32-S3-router-0.1.29-Mattboxx-1.8-windows.zip`: images, official Espressif
  esptool v5.3.1, license, checksums and guided Windows batch files.
  Use `UPDATE_KEEP_SETTINGS.bat` (optional COM port argument).
  `CLEAN_INSTALL_ERASE_ALL.bat` requires YES and erases settings/identity.
- `RELEASE-SHA256SUMS.txt`: SHA-256 of downloadable assets.

Application SHA-256:
`ed90c9039dae6421633f3ac3821bd09b18d534086be801364f5aa23e2bd124c0`.
The older releases' binary assets are not replaced. [1.7](https://github.com/Mattboxx/esp32-tailscale-gateway/blob/Main/docs/RELEASE-1.7.md) now
has an explicit upgrade notice for the subsequently reproduced ntfy bug.
