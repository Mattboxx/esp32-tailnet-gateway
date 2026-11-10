# Validation records

Health & Resources layout (post-3.0.15): 104 Chromium scenarios passed on
the generated Web UI with synthetic APIs, including 390 px placement,
independent saves and the per-device pause indicator. The settings-search
regression passed, including opening the collapsed guard controls. All language tables
pass `python tools/i18n_extract.py --check 100`. Hardware verification pending.

2026-10-29: [Performance/load exploration](PERFORMANCE-EXPLORATION-ROADMAP.md)
is active. Twelve harness host tests, actual RX ownership tests, real SDK pbuf
lifetime tests and existing authorization/SDK-forwarding targeted checks pass
on Windows. Six real 32 MB transfers passed hashes and preserved original
rule/lease/log settings, with no ESP reboot; INFO/WARN differences did not
justify a default change. The owning-pbuf RX prototype is not hardware-qualified.
Linux runner fixes and current sanitizer/build results are tracked in the
[performance checkpoint](CODEX-TO-CLAUDE-PERFORMANCE-CHECKPOINT.md); do not infer
their completion. Broader concurrent-load, remote/direct/DERP and uninterrupted
500 MB candidate gates remain pending. RAM tradeoffs require measured reserves.

The 3.0.6 update-transfer fix has separate actual-handler regression and
private transport evidence in `build/notification-ui/`. It does not replace
the released 3.0.5 qualification or imply a new physical install.

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
