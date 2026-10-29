# Validation records

MQTT power-return work for firmware 3.0.5 has its own evidence under
`build/notification-ui/`. Preserve the qualified 3.0.4 image and separate actual
host/broker/HA/power-cycle outcomes; no new device result follows from unit tests.

The 3.0.4 ntfy wording increment has its own evidence under
`build/notification-ui/`; the published 3.0.3 image and its qualification
remain unchanged. Inspect that private checkpoint before device operations.

Detailed execution summaries, device captures, remaining test cases, resource
measurements and maintainer handovers are stored locally under ignored
`build/private-device/` and `build/validation-*/` directories. They are not
firmware downloads or public release notes. Preserve their original outcomes;
do not overwrite a failed run to make a later corrective rerun appear cleaner.

Public automated workflow logs are available in GitHub Actions. The supported
hardware and operational boundaries are documented in [Hardware](HARDWARE.md),
[Tailnet authorization](TAILNET-AUTHORIZATION.md) and the release instructions.

Maintainers follow [Quality policy](QUALITY-GATE.md), [Testing](TESTING.md),
the full [feature matrix](FEATURE-IMPLEMENTATION-MATRIX.md) and
[architecture decisions](ARCHITECTURE-DECISIONS.md). A source check, simulated
packet path, browser fixture and physical-device experiment are distinct kinds
of evidence and must never be presented as interchangeable.
