# Desktop flashing-tool redistribution

The firmware's root MIT license does not relicense separately bundled tools.
Easy Install for Windows contains **esptool**, a standalone GPL-2.0-or-later
program. macOS/Linux scripts ask users to install esptool themselves. The
website's **esptool-js** is a different Apache-2.0 implementation.

## Audited executable and supplied source

All 24 inspected public ZIPs contain the same unmodified Espressif esptool
**5.3.1** Windows executable, SHA-256
`a939e28fe2fbb53e65e46f0246a4d71b9fd6c052ef0e046182df4a4fe8bec946`.
It matches the executable inside the [official Windows archive](https://github.com/espressif/esptool/releases/tag/v5.3.1),
archive SHA-256 `2b4a73c45db27426685896f64ce3e557f63a64f43cc100cb65c0cc3486af96d3`.
The original [GPL license](https://github.com/espressif/esptool/blob/v5.3.1/LICENSE)
remains alongside the program as `ESPTOOL-LICENSE.txt`.

The release download pages additionally supply
`esptool-5.3.1-CORRESPONDING-SOURCE.tar.gz`, SHA-256
`c407d13fd84a0d8019ea9d5634412918fd9dbeaf999d0289841425aa8dafa018`.
[Download with firmware 3.0.2](https://github.com/Mattboxx/esp32-tailnet-gateway/releases/download/v3.0.2/esptool-5.3.1-CORRESPONDING-SOURCE.tar.gz).
This supplies source access beside the executable download, rather than
creating a written source offer or a new approval requirement. The
`WITH-NOTICES.zip` packages contain full firmware/tool notices and the exact
source URL/hash; original archives and their published checksums are preserved.

## Contents and evidence

The source companion includes 104 checksum-locked archives: esptool source
and CI/build scripts; Python 3.13.14 and its identified native-library sources;
PyInstaller 6.11.1; actual Python dependencies; bitarray 3.8.2 and tibs 0.5.7;
the Cargo.lock crate sources and identified Rust standard-library revision;
legacy GPL stub 1.11.1 and MIT/Apache stub 1.0.0, including their submodules.
Original license texts and source notices are preserved inside those archives
and collected into `FLASHING-TOOL-LICENSES.txt`.

Read-only inspection and compilation without importing the application matched
**617** frozen Python modules to the supplied source. The bitarray/tibs native
extensions matched the corresponding official wheels byte for byte. The
bundled Python DLL matched the official Python 3.13.14 runtime. These are
source-correspondence checks, not a claim of byte-identical rebuilding or a
certification of every upstream right. Microsoft OS/runtime components retain
their own terms; this collection neither relicenses them nor claims ownership.

A supplemental comparison against the official source distributions (sdists)
alone matched 616 of those modules with no mismatch. The remaining one is the
99-byte `tibs/__init__.py` wrapper that Maturin generates during the tibs
build, so it is absent from the tibs sdist; the original wheel-generated file,
its MIT license and its provenance are in [licenses/tibs-0.5.7](../licenses/tibs-0.5.7/).
It supplements, without replacing, the Rust source and build inputs in the
source download.
No private code-signing keys are supplied or required for an unsigned build.

Reproducible source inputs and checks:

- [Pinned source index](../licenses/esptool-5.3.1-source-index.json).
- [Module/source correspondence](../licenses/esptool-5.3.1-verified-modules.json).
- `python tools/build_flashing_tool_sources.py --index licenses/esptool-5.3.1-source-index.json --cache build/tool-source-cache --verification licenses/esptool-5.3.1-verified-modules.json --out build/esptool-5.3.1-CORRESPONDING-SOURCE.tar.gz --notice-out build/FLASHING-TOOL-LICENSES.txt --fetch`

## Future packaging

Pass `--tool-sources <the verified source companion>` to `package_v2.py` or
`package_release.py`. Packaging verifies the executable's hash against the
source index and validates the source archive checksums. It emits the source
asset with the release and places its exact download URL/hash inside Easy
Install. Publish that source asset with the binary; a license copy or generic
repository link alone does not replace source access. A different executable
requires a corresponding newly reviewed source bundle, not this one's label.

As separate aggregated programs, esptool and the firmware retain their own
terms. Bundling them does not by itself make the firmware GPL; this does not
permit copying GPL implementation code into MIT firmware. Preserve notices
when redistributing copies. No donation, citation or upstream approval
condition is added by this document.
