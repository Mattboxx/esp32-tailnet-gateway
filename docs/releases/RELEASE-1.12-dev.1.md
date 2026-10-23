# ESP32 Tailscale Gateway 0.1.33-Mattboxx-1.12-dev.1 — beta

October 13, 2026. Integrates the published upstream v0.1.32/v0.1.33 changes
without replacing this fork's networking or automation implementation.
Stable 1.11 remains available and unchanged. Enable beta updates to receive
this candidate; it has not completed a 24–48-hour soak or been promoted stable.

## Original credits

Based on [Csontikka's ESP32 router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink), originally by Cameron
Malone. Original authors, contributors, copyright notices, licenses and
donation links are retained. Upstream fixes are credited to their authors;
they are not presented as newly invented Mattboxx features.

## Corrections from upstream v0.1.32

- Move packet-by-packet WireGuard TX/RX logging to DEBUG and the periodic
  snapshot to INFO, so a normal WARN console no longer stalls the packet task
  for those dumps. Keep the fork's redacted snapshot fields. Upstream reports
  a substantial throughput benefit; no equivalent throughput measurement is
  claimed for this board. INFO console logging can still cost performance.
- Treat an exact, whitespace-trimmed manual `0.0.0.0/0` route as requesting
  exit-node DNS and NAT. Keep boot-frozen listener/NAT lifecycle and preserve
  the user's manual routes and subnet-SNAT preference. Reject configurations
  that simultaneously request a manual exit offer and use another exit node;
  legacy conflicting settings remain stored and require correction, not silent
  rewriting. Changes to exit mode still require a restart.
- Guard the absent DERP TX queue during failed-initialization cleanup, avoiding
  an assertion when memory allocation fails.
- Wake coordination immediately on shutdown while waiting for DERP, instead
  of remaining in the 15-second connection wait past the stop deadline.

## WiFi policy from upstream v0.1.33

- Add the **WiFi power save (modem sleep)** graphical switch on System.
  Save and apply live, and retain the choice at boot.
- **OFF remains this fork's default**, including upgrades: low-latency WiFi
  was already enabled in the Mattboxx edition. Unlike upstream, this update
  does not silently enable modem sleep on an existing installation.
- Driver/save failures are reported, saved policy and actual runtime state
  are separate, and failed NVS persistence attempts restore the previous
  driver policy. A failed UI read cannot masquerade as OFF.
- Add Home Assistant/MQTT WiFi power-save control/runtime status and explicit
  configured/manual exit-mode indicators. ntfy `info` includes both policies.
  Configuration backup/restore preserves the WiFi setting.

## Faster optional support

One deliberate click on **Support mod** opens the real HTTPS Ko-fi page in a
dedicated desktop payment window, or a normal tab on mobile. No intermediate
confirmation, automatic popup, remote widget, embedded card form, background
Ko-fi request or device-page referrer. A quiet normal-tab fallback handles
popup blockers without automatically opening duplicate windows.

Ko-fi allows guest contributions; payment methods and bank confirmations depend
on the creator's configured PayPal/Stripe account and the supporter's device.
The firmware does not collect card details or claim a payment was successful.
No test payment is made. All features remain free and upstream support stays
separate from [the Mattboxx mod](https://ko-fi.com/mattboxx).

## Features preserved

Both forwarding systems, source restrictions/MagicDNS, configurable Web UI
port, optional AP and automatic AP-off, named WOL targets, MQTT/HA, ntfy,
route/exit/4via6 controls, hardware-dependent Ethernet, password/timeout
settings, local diagnostics/CPU/temperature, read-only SNMP and opt-in
stable/beta/manual/automatic GitHub updates are retained. No external log
upload, forced update polling or public speed-test service is reintroduced.

## Verification and limits

The exact ESP32-S3 image was installed via authenticated Tailnet OTA, booting
in 229 seconds. The upload response was unavailable, so the image was not
repeated; the new version and eight unchanged saved-setting groups were
verified afterwards.

On the reference board, strict boolean input, live driver/saved policy changes,
and persistence through two controlled software restarts passed. Actual
authenticated Tailnet HTTP, WiFi and MQTT recovered after each restart; other
saved settings were unchanged. The original WiFi policy was restored OFF.

Twenty-nine browser scenarios passed, including WiFi saved/runtime/unknown
states, legacy manual exit-mode labeling, popup-blocker handling with no
duplicate payment window, responsive support and all previous automation
controls. Actual-C regressions cover the WiFi driver/NVS rollback paths,
exact default-route matching, missing DERP queue cleanup and all connection/
shutdown wait-bit combinations. Existing lifecycle, AP recovery, relay reply,
session and SNMP-hook regressions pass, as do feature-preservation checks for
all existing UI/HTTP/MQTT/HA controls. Exact linked ntfy stack budgets pass.

GitHub regression/history scanning and CodeQL passed for the runtime changes.
Packaging checks the exact tested image, blank factory NVS, ZIP CRC, hashes
and credential patterns. The Windows serial script is not physically exercised;
board updates and persistence checks use OTA.

The live served UI was byte-checked against the tested embedded page. Fifteen
protected GET endpoints rejected anonymous access and all loaded after login.
A bounded 60-second smoke test completed eleven integration samples with no
observed reboot, uplink/tunnel loss or MQTT disconnect; minimum internal free
heap was 16,815 B. SNMP remained OFF. The live Tailscale API rejected a manual
default-route/selected-exit conflict with HTTP 400 before changing saved
settings. WiFi power save was confirmed OFF after the tests.

The ntfy HTTPS notification/info soak completed three commands and three
exact-version replies over 306 seconds without an observed reset or
WiFi/Tailscale/MQTT disconnection. Replies included the new WiFi and manual
exit-mode policy fields. Minimum observed ntfy stack headroom was 4,612 B;
internal free heap was 16,815 B. Original command-availability policy was
restored. Historical reset-log entries were not erased.

Physical Ethernet, arbitrary remote services, the Home Assistant frontend,
every provider's checkout and Internet exit-node throughput are not fully
revalidated here. In particular, an end-to-end donation is not simulated.
Pattern checks and bounded tests do not guarantee absence of all possible bugs.

## Assets

- `firmware.bin`: authenticated Web UI OTA, or latest compatible update with
  beta enrollment enabled. Settings are preserved.
- Windows ZIP: esptool, license notices, checksums and
  `UPDATE_KEEP_SETTINGS.bat` for a guided update without erasing settings.
- `firmware-factory.bin` and `CLEAN_INSTALL_ERASE_ALL.bat`: fresh installation;
  erase settings only after explicit confirmation. Factory NVS is blank.
- `FIRMWARE-LICENSES.txt`: original firmware/component license notices.

ESP32-S3 N16R8 with 8MB octal PSRAM and the existing 4MB partition layout.

Application use: 1,702,780 / 1,966,080 B; static RAM: 85,652 B.

Exact OTA SHA-256:

`4e899a6965f929dc825201a679522d60f959d1a6744279a8dc8b8645a199023c`

The release checksum file also covers the factory image, Windows ZIP and
firmware/component license notices.
