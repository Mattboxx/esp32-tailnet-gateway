# Firmware v2.0.0 — owner acceptance and remaining evidence

On 2026-10-23 the owner explicitly authorized publishing the bridge, firmware,
website and rebranding, accepting the missing hardware tests. The owner also
selected **immediate rename after bridge publication**, with no migration
window, accepting manual updates for legacy devices that miss the bridge.

This is release-risk acceptance, **not fabricated test success**. The following
remain NOT TESTED / accepted by the owner: a spare-device first boot across
Android/iOS/Windows, independent Tailnet identities/direct+DERP policy matrix,
prolonged recovery-AP outage and interrupted power during OTA/NVS writes.
Ethernet stays experimental and not hardware-qualified, with existing UI
languages retained while the image fits. No full official-client policy parity,
Secure Boot/signing, encrypted storage or fully out-of-band recovery is claimed.

Actual rc.1 results: identity, three runtime MQTT activations, lab integrations
and a 30-minute observation PASS. Observation: 60 samples, zero request errors,
monotonic uptime, control/authority 60/60, internal free minimum 22,215 B,
lifetime minimum 21,083 B, largest internal block minimum 12,800 B, sockets
maximum 10, reaper pending/fallback maximum zero. The separate 75-minute serial
collector is still running and must not be interrupted or mistaken for a
completed result. These are rc.1 results, not results for unbuilt final images.

The integrated clean source/presentation campaign passed 71 checks on Windows,
including browser/first-boot crypto/UI fixtures and the clean reachable-history
scan. Two published-site layout sweeps each passed 23 pages × 9 viewports with
synthetic firmware, before and after simulated rename. Those are not real
device flashing or first-boot captive-portal tests. No existing test expectation
or scanner exemption was weakened to manufacture a PASS.

Before distributing each final image: build the actual intended version from
a committed source, record exact BIN/ELF hashes, respect the protected stable
slot and perform the available exact-image qualification. Package that exact
saved image (ADR-026), not a rebuild or renamed rc.1. Publish bridge assets under
the existing repository first. Only then perform the owner-authorized immediate
rename and verify real public URLs/downloads/OTA and Pages.

Final-image build/install/qualification, package hashes and publication results
must be recorded separately when actually completed. This acceptance does not
declare the complete 42-item hardware roadmap finished.
