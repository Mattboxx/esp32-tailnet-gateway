# ESP32 Tailscale Gateway 0.1.33-Mattboxx-1.12-dev.1 — stable

October 20, 2026. The existing `v0.1.33-Mattboxx-1.12-dev.1` GitHub release was
marked stable/latest at the maintainer's request, without changing its tag,
commit, five assets, sizes or SHA-256 digests. No renamed/rebuilt firmware or
new tag was published, and no board flash or settings change was performed.
The internal dev.1 suffix stays. Stable 1.11 remains available for rollback.
This is not a new upstream rebase or a claim that every possible bug is fixed;
newer upstream alignment is deferred to the subsequent release.

## Original credits

Based on [Csontikka's ESP32 router](https://github.com/Csontikka/esp32-tailscale-subnet-router)
and [microlink](https://github.com/Csontikka/microlink), originally by Cameron
Malone. Original contributors, notices, licenses and upstream donation links
are retained. Optional [Mattboxx support](https://ko-fi.com/mattboxx) supports
the custom edition; all features remain free. No upstream endorsement is implied.

## Included fixes and improvements

- Published upstream v0.1.32/v0.1.33 corrections: lower WireGuard logging
  overhead; exact manual default-route handling for exit-node DNS/NAT;
  missing DERP queue cleanup guard; interruptible coordination shutdown wait.
- Optional live and persistent WiFi modem sleep. OFF remains this fork's
  low-latency default. Driver/save failures are reported and rollback is
  checked; configured and runtime policy are distinguished.
- WiFi and manual exit-mode visibility in Web UI, MQTT/Home Assistant, ntfy
  info and configuration backups.
- Optional one-click Ko-fi window/tab initiated only by the user. No embedded
  checkout, background third-party widget or device-page referrer.
- All existing Mattboxx controls retained: both forwarding systems,
  source restrictions and MagicDNS, named WoL, MQTT/HA, ntfy, optional AP,
  route/exit/4via6 controls, configurable UI port and authentication/timeouts,
  diagnostics, read-only SNMP and opt-in stable/beta/manual/automatic updates.
- Prepared local documentation/tooling improvements (not a new firmware):
  clearer NAS recovery onboarding and limitations, corrected source-build
  directory and download links, correctly attributed upstream board reports,
  version-correct flashing instructions and a reminder to redact logs.

No usage reporting, external crash/log uploads, forced update polling or
public speed-test service is reintroduced. Integrations and the VPN still
contact their configured services when enabled or explicitly requested.

## Validation and limits

The October 13 [beta record](RELEASE-1.12-dev.1.md) documents OTA, settings
preservation, controlled restarts, live WiFi policy tests and bounded
HTTPS ntfy info/reply checks on the reference ESP32-S3. These are historical
tests of the beta, not a new 24–48-hour stable-image soak.

The board was initially unreachable, then became accessible through the
owner's tailnet. Fresh authenticated checks observed the expected beta build,
251,771 seconds of uptime, connected WiFi/Tailscale/MQTT and an active ntfy
worker. A bounded 180-second check completed 32 samples without an observed
reboot, uplink/tunnel loss or integration disconnect; minimum internal free
heap was 16,891 B. Fifteen protected GET endpoints rejected anonymous access
and loaded after login. SNMP stayed OFF. Observed uptime is not a claim of
continuous monitoring for that whole period. No new flash, reboot, live
WoL/NAS recovery, physical Ethernet or HA frontend test is claimed.

Twenty-nine offline browser scenarios and existing C/feature-preservation
regressions passed, including 38 TCP/UDP cases against the pinned SDK's real
IPv4/NAPT/pbuf path. Pattern checks reported zero findings across 1,417
historical blobs and current project/submodule checks; that is not proof of
absence of every bug or secret. Local attempts to rebuild a renamed stable
image failed on relative output paths in the Windows toolchain. That approach
was abandoned in favor of the requested existing-release promotion; no failed
build was uploaded. Stable is a release channel, not security certification.

## Install or update

Target: **ESP32-S3 N16R8, 8 MB octal PSRAM**, existing 4 MB partition layout.

- `firmware.bin`: Web UI OTA update; preserves settings. Never upload the
  merged factory image to the Web UI updater.
- `ESP32-S3-router-0.1.33-Mattboxx-1.12-dev.1-windows.zip`: bundled esptool and guided
  `UPDATE_KEEP_SETTINGS.bat`; no build toolchain needed.
- `firmware-factory.bin` / `CLEAN_INSTALL_ERASE_ALL.bat`: fresh installation,
  explicitly erases configuration after confirmation. Factory NVS is blank.
- `FIRMWARE-LICENSES.txt` and `RELEASE-SHA256SUMS.txt`: original notices and
  artifact checksums.

The current updater rejects development-form tags classified as stable.
This existing dev.1 release therefore requires manual download/Web UI OTA;
it is not a newly eligible automatic update. If the identical build is already
installed, no reflash is needed. This limitation is disclosed in the public
release notes. All five existing assets were verified unchanged after promotion.

Unchanged OTA SHA-256:

`4e899a6965f929dc825201a679522d60f959d1a6744279a8dc8b8645a199023c`

The local Web UI uses HTTP: trusted LAN or encrypted tailnet only, not public
Internet exposure. SNMPv1/v2c is optional and unencrypted. WoL requires target
support and standby power; it cannot hard-reset a frozen NAS or recover files.
See [NAS checklist](../NAS-RECOVERY.md) and [security model](../../SECURITY.md).
