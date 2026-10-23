# ESP32 Homelab Gateway — Mattboxx Edition

**Development source: `0.1.38-Mattboxx-1.14-dev.1`. Not a published release.**

The product now emphasizes selective Tailnet service access, independent
Wake-on-LAN and local diagnostics. NAS recovery remains a use case, not a
requirement. Repository URL, app identity, updater repository and original
credits/licenses are unchanged.

## Changes

- Explain each LAN → Tailnet rule's saved path, allowed sources, observed
  runtime state and next troubleshooting step.
- Distinguish a local mapping being installed from a service actually being
  tested. This panel is passive: no hidden probes, new sockets or poller.
- Start new UI rules disabled. Keep failed reads, unknown status and unsaved
  drafts distinct. Preserve fields on a failed read and require a successful
  reload before saving. Only configuration is saved/backed up, not diagnostics.
- Keep the old WoL address book active if saving its replacement fails.
  Preserve its record layout, reject malformed targets/fields and explicitly
  distinguish sending a magic packet from confirming a device has started.
- Correct the Ethernet support wording and separate shared upstream features
  from fork additions. Document current policy-compatibility limitations.

## Availability

The current public stable remains **0.1.38-Mattboxx-1.13**. No new stable,
beta tag or download asset is published by this work. This candidate has not
been installed on the physical reference board; do not confuse a local build
with a released, hardware-validated image. The existing stable binary and
flashing ZIP are not replaced or relabeled.

Smart Recovery with service-readiness verification, active health monitoring,
profiles, commissioning templates and Ethernet remain roadmap items, not
features supplied by this development increment. See the
[roadmap and release gates](../ROADMAP.md), [source audit](../archive/PRODUCT-AUDIT.md) and
[selective service guide](../SERVICE-GATEWAY.md).
