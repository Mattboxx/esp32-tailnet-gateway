# Release notice supplements

`firmware-v3.0.2-notices.txt` supplies expanded legal materials for the 3.0.2
application (`fcc6011bab4b2f1aa38d5fb49564f0cef3163378`, SHA-256
`fdb763c1db0d3c2320c26280792894b20f7595190e03ec1b036652756ba585e0`).
It was generated from its saved ESP-IDF 5.5.3 component/source metadata and
GCC 14.2.0 toolchain, including original source-header and runtime notices.
The root `NOTICE.md` was updated for the audit; legal-only source annotations
post-date the image. No application instructions or firmware bytes changed.
The adjacent `firmware-v3.0.2-provenance.json` records the image, ELF and notice
hashes. The local browser-installer copy and its notice checksum are updated;
the four binary parts and installation manifest are unchanged.

This supplement does not assert every conservatively listed source survives
linker garbage collection, or that older download archives have already been
replaced. Keep it with copies of the corresponding binary distribution.
It is not a substitute for the independent GPL source-distribution obligations
of the desktop esptool executable. See
[Flashing-tool licenses](../docs/FLASHING-TOOL-LICENSES.md) and
[Audit findings](../docs/LICENSE-AUDIT.md).

Future packages generate notices directly from their own exact build metadata;
do not reuse this version's supplement as proof for an unrelated image or SDK.

## Desktop-tool source and distribution repairs

`esptool-5.3.1-source-index.json` pins the upstream source archives supplied
with the public esptool corresponding-source download. The module verification
record identifies the 617 checked Python modules. This does not relicense
esptool, Windows components, or the firmware under a common license.
See [desktop-tool redistribution](../docs/FLASHING-TOOL-LICENSES.md) for the
source download, reproduction command and the packaging `--tool-sources` input.

`tibs-0.5.7/` holds the Maturin-generated `tibs/__init__.py` wrapper of the
frozen executable (absent from the tibs sdist), with its license and provenance.

`releases/` holds four small legal companions of the ten newest releases that
are kept in the repository instead of as release assets; see
[releases/README.md](releases/README.md).

`distribution-remediation.json` records the additive legal-material assets
published with historical releases. Original images and ZIPs retain their
identities/checksums; `WITH-NOTICES.zip` downloads add legal documentation.
