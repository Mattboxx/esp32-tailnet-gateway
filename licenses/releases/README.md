# Legal companions of the ten newest releases

GitHub release pages carry the legal materials of every public release. For
the ten newest releases (v2.0.2 to v3.0.2) four of the small companion files
are kept here instead of as release assets, because 2.x firmware already in
the field reads the list of the ten newest releases into a 256 KiB buffer and
extra assets made that list too large for it. The files are byte-for-byte the
ones published on 2026-10-26; their SHA-256 values are in each folder's
`LICENSE-SHA256SUMS.txt` and in
[distribution-remediation.json](../distribution-remediation.json).

| File | Where |
|---|---|
| `FIRMWARE-LICENSES-ADDENDUM.txt` — expanded firmware copyright and license companion | `<tag>/` here; also inside that release's `FIRMWARE-LICENSES.txt` in the `…-WITH-NOTICES.zip` (v2.1.0 has no ZIP) |
| `license-provenance.json` — source revision, MicroLink gitlink, SDK and image hashes | `<tag>/` here |
| `LICENSE-SHA256SUMS.txt` — checksums of the legal downloads | `<tag>/` here |
| `FLASHING-TOOL-LICENSES.txt` — esptool 5.3.1 desktop-tool notices (identical for every release) | [one shared copy](FLASHING-TOOL-LICENSES.txt); also inside every `…-WITH-NOTICES.zip` |

Still attached to each of these releases: the original assets (unchanged),
the `…-WITH-NOTICES.zip` Easy Install archive with complete notices, and
`esptool-5.3.1-CORRESPONDING-SOURCE.tar.gz`, the source of the bundled
esptool executable. Older releases keep all their legal assets on the release
page.
