# Upstream v0.1.28 integration — Mattboxx 1.6

Integration date: October 1, 2026. Router release: upstream `v0.1.28`
(`1e01759`), plus the following `e3e2e50` HTTP registration/favicon correction.
At verification time this is upstream's latest published release and current
main-branch tip. Microlink stays at the same upstream `7de6a936` used by both
router v0.1.27 and v0.1.28, merged with the fork's privacy and 4via6 hooks.
The preceding v0.1.20–v0.1.27 integration is documented separately.

Credit: Csontikka's router and microlink, their original authors/contributors,
and gszigethy's read-only SNMP contribution. Original MIT headers are retained.

## Integrated

- Optional BSD-socket SNMPv1/v2c GET/GETNEXT agent, disabled by default, with
  standard system/interfaces, host-resources and entity-sensor objects. No
  Ethernet hardware is required; a missing Ethernet interface reports down.
- Atomic single-blob NVS configuration, legacy-key migration, nonempty
  community validation, 255-byte string limits and PSRAM work/config buffers.
- WireGuard lookup by `wg` name, traffic hooks installed after router ACL
  wrappers, and hook installation/removal through the TCP/IP thread.
- One temperature-sensor owner shared by SNMP and the web UI. Monitoring still
  works with SNMP disabled. The fork's CPU sampler remains in UI/MQTT/ntfy.
- 26 socket descriptors, using official PlatformIO Espressif32 6.13.0 and
  ESP-IDF 5.5.3, pinned to eliminate the older cached SDK's 16-socket ceiling.
- Registration-error reporting for all 64 HTTP handlers, 88 handler slots,
  and an inline/local favicon. No automatic external image request is added.

## Additional hardening and preserved differences

- Only the SNMP worker closes its socket. Disable performs shutdown, with a
  bounded receive as fallback; it cannot recycle the descriptor while the
  worker still has a receive/send pending. Rapid changes remain serialized.
- The configuration mutex also covers reply encoding, avoiding simultaneous
  changes to community/name/contact/location strings during serialization.
- Reject unsupported protocol versions, empty/over-wide request integers and
  OID-arc overflow. A host harness exercises the actual codec/PDU C functions.
- The System card uses the fork's graphical switch and disabled styling,
  preserves known state on failed reads, and warns that SNMP is unencrypted.
- MQTT/HA and ntfy expose SNMP enabled/running state and socket budget only;
  no community/contact/location is added to their outgoing status.
- Bench-only forced-roam/reconnect endpoints remain excluded, so upstream's
  debug-BSSID validation change has no exposed counterpart in this build.
- No telemetry, external log/crash uploader, automatic firmware downloader,
  Cloudflare test, public DNS fallback or Ethernet wiring assumptions return.
- Restart-based application VPN reconfiguration remains deliberate: existing
  consumers retain the microlink handle. All custom gateway/automation/routing
  features and their existing privacy controls remain compiled and configured.

Release-specific evidence and limitations: [RELEASE-1.6.md](RELEASE-1.6.md).
