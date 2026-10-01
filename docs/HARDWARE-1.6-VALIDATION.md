# Mattboxx 1.6 development hardware validation

Date: October 1, 2026. Target: ESP32-S3 with PSRAM.
No user credentials, broker addresses, topic names, MACs or tailnet topology
are included in this record.

## Confirmed on dev.1

- Installed version: `0.1.27-Mattboxx-1.6-dev.1`.
- Login directly into Automation populates both integrations correctly.
- Five consecutive refreshes preserve MQTT Connected and ntfy Enabled, with
  checked switches, editable settings, and no loading errors.
- Full-page reload restores the authenticated Automation page correctly.
- Logout, reload, and login again restore both states correctly.
- MQTT Publish now returns Status queued. Broker delivery and Home Assistant
  entity behavior have not been independently observed.
- JavaScript console: no errors or warnings during these tests.
- Saved WOL targets and Home Assistant discovery settings remain present.

## Socket allocation correction in dev.2

The ntfy test failed, and the live device log showed:

```text
esp-tls: Failed to create socket (family 2 socktype 1 protocol 0)
HTTP_CLIENT: Connection failed, sock < 0
ntfy: publish failed: ESP_ERR_HTTP_CONNECT HTTP 0
```

The generated configuration and compiled header for the dev.1 image both
contained `CONFIG_LWIP_MAX_SOCKETS=10`, while the tracked defaults specify 16.
Defaults do not overwrite an existing generated SDK configuration. This left
too few descriptors for concurrent HTTP, microlink, MQTT, DNS and ntfy usage.

Dev.2 sets the active ESP32-S3 SDK configuration to 16 and adds a compilation
guard that rejects lower socket limits. `/api/system/diag` includes the compiled
socket and active-TCP limits, making future build drift observable.

The deployed command policy only polls ntfy while Tailscale is offline.
An info command while the tunnel is connected is therefore not a valid test
of that configured policy. This setting was not changed during validation.

## Confirmed on dev.2

- Manual web OTA completed; the board restarted into
  `0.1.27-Mattboxx-1.6-dev.2` (build tag `V26.1001.2214`).
- MQTT connected after restart, and Publish now returned Status queued.
- Two ntfy tests succeeded. Reload displayed Enabled · reachable, and the
  second test explicitly returned ntfy test sent. This confirms server
  acceptance, not delivery to a particular phone or subscription.
- Automation refresh and a full-page reload restored both enabled switches,
  MQTT Connected and ntfy Enabled · reachable without loading errors.
- No saved integration settings were changed or erased; the existing session
  and saved WOL target remained present. Browser console checks were clean.
- Compiled SDK header: socket limit 16; application image: 1,614,432 bytes.
  SHA-256: `26c24a2cdacca2993f06781c2981f71fcf532bdac0d3a8d15db622027f7f5a31`.

This is a development candidate, not a stable release promotion or a complete
test of Home Assistant, remote-command delivery, routing, WiFi roaming or
long-term uptime. No GitHub assets were replaced by this validation step.
