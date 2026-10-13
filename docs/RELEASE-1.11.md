# ESP32 Tailscale Gateway 0.1.31-Mattboxx-1.11 — stable

October 13, 2026. Replaces the withdrawn 1.10 release with the same verified
runtime and an optional support button for the Mattboxx edition. Beta enrollment
is not required. The version number is new so installed 1.10 devices can update.

## Original credits

This is a community fork of
[Csontikka's ESP32 router](https://github.com/Csontikka/esp32-tailscale-subnet-router),
using [microlink](https://github.com/Csontikka/microlink), originally by Cameron
Malone, and their contributors. Original copyrights, licenses and credits are
preserved. The donation link does not imply endorsement by the original authors.

## What's new

- A small, theme-matched **Support mod** button in the top bar; compact **Ko-fi**
  label on smaller screens. A quiet footer invites an optional small tip.
- Support goes to [Mattboxx on Ko-fi](https://ko-fi.com/mattboxx). Csontikka's
  original support links remain available and clearly attributed separately.
- No popups, payment widgets, remotely loaded UI assets or background Ko-fi
  requests. The plain link opens only on a deliberate click, in a new tab,
  without the device-page referrer. All features remain free.
- Matching README buttons and a GitHub funding entry. Binary downloads carry
  the original firmware/component copyright and license notices, also included
  in the Windows ZIP.

## Everything retained

Upstream v0.1.30/v0.1.31 and every Mattboxx feature remain: independent LAN →
Tailnet TCP/UDP forwarding and AP-side forwarding, source CIDR controls,
MagicDNS, configurable Web UI port, optional AP/automatic AP-off, WOL saved
targets, MQTT/Home Assistant discovery and controls, ntfy HTTPS commands/info,
route and exit-node controls, hardware-dependent Ethernet, optional password
and timeout, diagnostics/metrics, read-only SNMP, and opt-in GitHub stable/beta,
manual and automatic updates.

Retains the fixes for startup stuck on Registering, AP worker allocation,
stale direct-path replies, SNMP callback recursion and concurrent no-timeout
logins. No VPN/networking runtime logic or saved-settings format changes in
this release. See [the complete runtime correction and validation record](RELEASE-1.10.md).

## Verification and limitations

Twenty-six browser regression scenarios passed, including support links at
1280/1000/800/390/320px, keyboard focus, no horizontal overflow, retained
upstream support, zero third-party requests before clicking and the existing
automation/update controls. The support UI was visually checked on desktop
and mobile. Feature-preservation tests confirm existing UI controls, HTTP
endpoints, Home Assistant entities and MQTT commands are retained.

Hardware verification and exact asset hashes are recorded below before release.
The existing ESP32-S3 N16R8 / 8MB octal PSRAM target and 4MB partition layout
are unchanged. Physical Ethernet, arbitrary remote services, full exit-node
throughput and the Home Assistant frontend are not newly revalidated here.
The Windows bundle is verified structurally; live board testing uses OTA,
not the Windows serial script. Stable does not guarantee unlimited uptime.

## Download and flash

- `firmware.bin`: upload through **System → Firmware update**, or use
  **Check for updates → Install latest update**. Beta enrollment can stay OFF.
- Windows ZIP: unzip and double-click `UPDATE_KEEP_SETTINGS.bat`; includes
  esptool, its license, component notices and verified hashes.
- `firmware-factory.bin` / `CLEAN_INSTALL_ERASE_ALL.bat`: fresh installation;
  erase saved settings only after confirmation. Factory NVS is blank, not a
  dump of the reference board.
- `FIRMWARE-LICENSES.txt`: original licenses/notices accompanying the firmware.

Optional tips never unlock features or replace the original authors' credit.
