# 0.1.38-Mattboxx-1.14-dev.8 — ESP32 Tailnet Gateway (development candidate)

**Channel:** pre-release, local candidate. Not published. Stable remains 1.13.

Everything listed for [dev.6](RELEASE-1.14-dev.6.md) is included. This page
lists what changed since then and what was actually tested on this image.

## What changes for users since dev.6

- **Truthful recovery after a control-plane interruption:** when the
  complete policy is not yet available the gateway requests a fresh peer map
  and retries a missing initial network map instead of reporting a usable
  connection. Until the policy arrives, the Web UI shows "policy pending" and
  traffic stays refused (fail closed).
- **Clearer refusals:** the Service Gateway diagnosis now says when a request
  was refused because its source is not allowed by the rule.
- **SNMP starts reliably:** the SNMP worker no longer fails to start when
  internal RAM is fragmented (its stack now lives in PSRAM).

## Upgrade notes

- From 1.13: upload `firmware.bin` in System → Firmware, or use the Windows
  package. Settings, app identity and updater identity are unchanged.
- The previous image stays in the other slot; a failed boot returns to it.

## What was tested on this exact image

Image SHA-256 `b70ff745fb0328be8f98b9ec7fe9b1ce1468501d082bf083ebdf336c08e1361f`,
on one ESP32-S3 N16R8 (home WiFi, hosted Tailscale, one tailnet PC):

- Web UI upgrade from 1.13 into the free slot; 1.13 kept in the other slot;
  saved configuration preserved.
- Service Gateway: TCP 20/20 and UDP 20/20 through a LAN client, refusal when
  OFF and for a source outside the rule, expiry, persistence across a reboot,
  profile apply/rollback and Service watch.
- SNMP v1/v2c: full 109-object walks, tailnet queries, refusal of wrong
  community, SET and malformed packets, repeated OFF/ON.
- Offline: the full host campaign (Windows, Linux with sanitizers) and
  browser tests in four languages.

## Not yet tested (blocked or pending)

Two independent tailnet identities (policy matrix over direct and DERP), a
deliberate control-stream interruption, Wi-Fi access point fallback after the
uplink disappears, power loss during a settings write or an update, ntfy on a
real service, W5500 hardware. See [DEV8-VALIDATION.md](DEV8-VALIDATION.md) for
the current evidence. Do not treat this candidate as stable.

## Build note

PlatformIO links the component libraries in a varying order, so two builds
of the same source differ in layout and hash (same symbols, different code
placement). Only the image above was tested; the local package contains
exactly that file.
