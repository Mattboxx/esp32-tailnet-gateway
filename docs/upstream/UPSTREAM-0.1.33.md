# Published upstream v0.1.32/v0.1.33 alignment

October 13, 2026. Mattboxx candidate `0.1.33-Mattboxx-1.12-dev.1`.
Stable `0.1.31-Mattboxx-1.11` remains available; this is not a stable promotion.

Source comparison is limited to the published tags:

- v0.1.32: `4030ee4b4b4f08d621be0dcb91be206607163e86`.
- v0.1.33: `ace09b31e322c2dc5e8823862b66802494360860`.
- Dependency changes from `17a8c9c0b9f6d7871fd1430f800383c87b99caa2`
  through `2c796e3b14872b94fb2c54102affaacb1cc4a77b`, ported onto the
  existing custom microlink branch at `102e2a65dda7d335fc560964826b70fcfa483e10`.

Original credit remains with Csontikka/router, Cameron Malone and
Csontikka/microlink and their contributors. Copyright/license notices and
upstream support links are preserved. No later unreleased upstream commits
are included.

| Published change | Integration in the Mattboxx fork |
|---|---|
| Per-packet WG logs become DEBUG; snapshot becomes INFO | Ported. Keep redacted peer indexes/endpoint-presence fields instead of restoring peer names/IPs. WARN no longer emits these dumps. INFO can still be expensive on UART. |
| Manual `0.0.0.0/0` enables exit DNS/NAT | Exact trimmed route matching; frozen boot mode, configured/active/manual status separation, web/API/ntfy/MQTT/HA visibility. Preserve manual routes and SNAT preference. Reject server/client conflicts without rewriting manual NVS routes. |
| Stop interrupts the coordination DERP wait | Port the shutdown event into the wait mask and stop branch. Keep the fork's existing startup barrier and partial-start rollback. |
| Partial initialization cannot drain a null DERP queue | Port the queue guard, with actual-C missing/nonempty queue regression. |
| WiFi power-save setting, live and at boot | Port/adapt to the graphical-switch UI. OFF remains the existing fork default, unlike upstream ON. Add transactional driver/save error handling, actual runtime status, backup/restore, MQTT/HA control and ntfy info. |
| UI/docs/throughput descriptions | Adapt to the fork without overwriting custom UI/controls. Attribute upstream throughput measurements; do not claim equivalent measurements on this board. Version follows the new upstream base and custom beta channel. |

No unchanged upstream sections are copied wholesale: optional AP, both
forwarding paths, routing/exit/4via6, Ethernet variants, WOL, ntfy, MQTT/HA,
auth/timeout, diagnostics, SNMP, remote updates and the local-only support
integration remain. Removed external telemetry/log uploads, hard-coded public
DNS and public speed tests are not restored.

The independently requested donation shortcut opens Ko-fi only after a user
click, in a separate HTTPS window/tab rather than an embedded payment widget.
It does not collect payment data, report payment success or change financial
account settings. See [candidate validation and limitations](../releases/RELEASE-1.12-dev.1.md).
