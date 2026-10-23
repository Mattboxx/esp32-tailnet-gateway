# Release quality policy

Release artifacts must identify their source, version, dependency revision and
SHA-256 checksums. Package the exact saved image; never substitute a rebuild
or rename an older candidate as a stable image (ADR-026).

Before distribution, maintainers review applicable source, API, browser,
authorization, persistence, update, resource and device checks. Keep execution
logs, device information, acceptance decisions and incomplete-test ledgers in
ignored local records, not in public release notes. Never invent a result.

Public notes explain actual functionality, installation, supported hardware,
security boundaries and operational limitations. Experimental hardware must
remain explicitly labelled. Preserve original authorship, licenses, settings,
previous recovery images and historical releases.

See [Testing](TESTING.md), [Architecture decisions](ARCHITECTURE-DECISIONS.md),
[Hardware](HARDWARE.md), [Security](../SECURITY.md) and [Updates](UPDATES.md).
