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

Validation results and the exact tested OTA hash are recorded before release.
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
