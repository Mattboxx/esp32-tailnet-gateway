# Desktop flashing-tool redistribution

The firmware's root MIT license does not relicense separately bundled tools.
Easy Install for Windows contains **esptool**, a standalone GPL-2.0-or-later
program. macOS/Linux scripts ask users to install esptool themselves. The
website's **esptool-js** is a different Apache-2.0 implementation.

## Audited Windows executable

The 3.0.2 Easy Install executable reports **5.3.1** and has SHA-256:
`a939e28fe2fbb53e65e46f0246a4d71b9fd6c052ef0e046182df4a4fe8bec946`.
It matches the executable inside Espressif's
[official v5.3.1 Windows archive](https://github.com/espressif/esptool/releases/tag/v5.3.1),
whose SHA-256 is
`2b4a73c45db27426685896f64ce3e557f63a64f43cc100cb65c0cc3486af96d3`.
This establishes binary provenance, not a complete corresponding-source audit.

The [upstream license](https://github.com/espressif/esptool/blob/v5.3.1/LICENSE)
is included beside the program as `ESPTOOL-LICENSE.txt`. Keep it unchanged.
The [upstream source](https://github.com/espressif/esptool/tree/v5.3.1) and build
scripts identify the starting point for a corresponding-source arrangement.

## GPL executable distribution is a separate acceptance item

GPLv2 section 3 requires an applicable source-distribution arrangement for
object-code distribution. Depending on the circumstances, this can involve
accompanying complete corresponding source, equivalent source access for a
download, or an applicable valid written offer. A copy of the GPL alone does
not establish that obligation has been met. A generic repository link also
does not prove completeness or applicability of an arrangement.

The audited Easy Install archives contain the executable and license, but do
not themselves include a complete esptool/PyInstaller/Python dependency source
bundle or an identified publisher-specific source offer. Verify the relevant
sources, build scripts and dependencies and the chosen arrangement before
claiming this item closed. The audit does **not** manufacture a written offer
or commit the owner to a new legal promise. Existing license alternatives
remain available; no upstream approval is invented.

As separate aggregated programs, esptool and this firmware retain their own
terms; distributing them together does not by itself make the firmware GPL.
This conclusion is limited to the separate-tool arrangement, not permission
to copy GPL implementation code into the firmware under MIT.

Keep this document with future desktop packages. It is a disclosure of the
verification boundary, not a substitute for the required source arrangement.
