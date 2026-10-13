# ESP32 Tailscale Gateway 0.1.31-Mattboxx-1.10 — stable

Stable release, October 13, 2026. Replaces stable 1.8 and the older 1.10 betas.
Beta enrollment is **not required**. All saved settings are retained by OTA
and the keep-settings Windows update script.

## Original credits

Based on [Csontikka's ESP32 router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink), including upstream
v0.1.30/v0.1.31. Original authors, contributors and component licenses retain
full credit. This is the Mattboxx custom edition, not a new VPN implementation.

## What's included

- Tailnet-to-LAN/AP subnet routing, route controls and exit-node features.
- Independent **LAN → Tailnet TCP/UDP forwarding**, with source CIDR rules,
  live counters and IP/MagicDNS destinations; existing AP-side forwarding
  stays separate. Configurable Web UI port prevents listener conflicts.
- Optional WiFi gateway/AP, with automatic AP-off on uplink connection and
  an explicit disabled state; Ethernet support remains hardware-dependent.
- Named, saved Wake-on-LAN targets and ntfy `info` reporting.
- MQTT/Home Assistant discovery, monitoring and device controls; ntfy HTTPS
  notifications and commands, including operation while Tailscale is online.
- Optional Web UI password and idle timeout, graphical feature switches,
  diagnostics/reset history, CPU/temperature metrics and read-only SNMP.
- Fork-only opt-in GitHub update checks, manual latest download/install,
  automatic installation/window and optional beta enrollment. The install
  button stays unavailable when no compatible newer version exists.

## Corrections and improvements

- Fix **Registering stuck indefinitely** after task allocation failure: reserve
  worker stacks largest first, delay TLS/cache work until all workers exist,
  clean up incomplete startup and bound memory retries. Display startup errors.
- Fix runtime AP-worker creation failures: one reserved 8KB worker coalesces
  changes, retries mode errors and suppresses recovery during intentional restart.
- Fix missing Tailnet replies through stale/asymmetric direct paths: actual
  relay-delivered requests select relay replies immediately, retaining working
  direct paths for empty keepalives and preserving existing sessions.
- Fix concurrent logins with timeout OFF: use true activity-based LRU instead
  of identical infinite expiry values. The four-session limit is unchanged.
- Retain the SNMP/Tailnet callback-recursion fix that prevented stack exhaustion
  and watchdog/panic resets in dev.10. Preserve forwarding policy and counters.
- Prefer PSRAM for JSON, previous-boot logs and ordinary larger buffers. Keep
  DMA/stacks internal and their original sizes. Initialize JSON hooks once.
- Treat a zero STUN baseline as unknown; show a previous-boot log as such,
  rather than treating every ordinary restart as proof of a crash.
- Retain the 1.10 ntfy transport/streaming, forwarding validation/transaction,
  IPv4 packet handling, Web UI port protection and upstream integration fixes.
  No external log upload is introduced; logs/settings are not bundled in assets.

## Verification and limits

The stable build promotes the fully tested dev.18 runtime. Its validation
record includes two software restarts with real Tailnet HTTP, eight additional
logins with active-session retention, three ntfy `info` replies during a
302-second HTTPS soak, twelve real Tailnet SNMP replies, both 82-object walks,
three SNMP disable/enable cycles and a 301-second enabled soak. SNMP was restored
OFF, AP stayed OFF and saved settings were unchanged. See the detailed
[candidate validation record](RELEASE-1.10-dev.18.md).

Actual-C regressions, 21 SPA browser scenarios, exact linked packet-path checks,
GitHub regression/history checks and CodeQL passed. Pattern scans found no
sensitive data in checked source/history/dependency contents or packaged images;
these checks are not a guarantee that every possible issue has been found.

Stable is a release-channel designation, not a promise of universal or unlimited
uptime. Physical Ethernet hardware, arbitrary remote services, full exit-node
Internet throughput and the Home Assistant frontend were not revalidated here.
The Windows bundle is verified structurally; these board updates used OTA,
not the Windows serial script. Old reset-history entries are intentionally kept.

## Download and flash

Use `firmware.bin` in **System → Firmware update**, or **Check for updates →
Install latest update**. Beta enrollment can remain OFF for stable 1.10.
The Windows ZIP includes esptool, its license, hashes and
`UPDATE_KEEP_SETTINGS.bat`: unzip it and double-click that script to update.
`firmware-factory.bin` / `CLEAN_INSTALL_ERASE_ALL.bat` are for fresh installation
and erase settings only after confirmation. Factory NVS is blank, never a
copy of the reference board's private configuration.

Targets ESP32-S3 N16R8 with 8MB octal PSRAM and the existing 4MB partition layout.
Application use: 1,698,572 / 1,966,080 B; static RAM: 85,548 B.

OTA SHA-256:

`fbaacd9fc160df75a78d88b2baead436151771fc70909050c471232259d48eea`

The exact stable image was flashed by authenticated OTA in 32 seconds. Eight
saved-setting groups were unchanged. Two software restarts restored
WiFi/Tailscale/MQTT and actual authenticated Tailnet HTTP in 48/47 seconds,
with the same identity/settings and AP OFF. Eight additional logins retained
two active no-timeout sessions, then test sessions were logged out.

The rebuilt stable image has a different linked layout from the candidate;
it is not claimed to be byte-identical. The exact stable ELF retained the
verified packet-policy entry points and stack budgets. Its SNMP v1/v2c checks,
twelve Tailnet replies, both 82-object walks and three live disable/enable
cycles passed. A 65-second enabled soak completed twelve queries without an
observed reboot, with zero LAN retransmissions and one bounded Tailnet UDP
retry. SNMP was restored OFF without changing its other settings.

An exact-version ntfy check received the stable build's `info` reply during a
64-second HTTPS test with no observed restart. Minimum observed ntfy stack
headroom was 4,636 B and internal free heap was 17,071 B. The original command
reply policy was restored. These are bounded tests, not a long-term guarantee.
