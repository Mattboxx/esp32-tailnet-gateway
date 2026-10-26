# License, copyright and attribution audit

Completed: **2026-10-26** (review started 2026-10-25). Base reviewed:
`bfbc50879f183839dacb5455a5042794b1c9f066`; actual dependency:
`fa3153b6892d00d0c9a9c42f11c8f1a89c6ea910`. Current public stable version:
**3.0.2**, source `fcc6011bab4b2f1aa38d5fb49564f0cef3163378`.

This is an evidence-based technical redistribution review, not an absolute
legal opinion or a certification of ownership, trademarks or all historical
source provenance. No firmware logic, protocols, configuration, brand images,
product name or donation destinations were changed. No device was flashed.

## Files and distributions examined

- Root `LICENSE`, `NOTICE.md`, `CITATION.cff`, `.gitmodules`, README credits,
  funding links, SECURITY scope, brand license guidance and website
  About/versioning/installer notices. Historical planning and release prose
  was retained as archival context, not silently rewritten as current evidence.
- Actual MicroLink gitlink, its `LICENSE`, `x25519-license.txt`, vendored
  wireguard_lwip license/source notices and GitHub fork-parent records.
- Saved 3.0.2 build description, configured component/source lists, ELF/map
  provenance, ESP-IDF 5.5.3 license files and GCC 14.2.0 runtime notices.
- `package_release.py`, `package_v2.py`, `package_bridge.py`, Easy Install
  templates, versioned browser installer materials and actual public archives.
- All **25 public releases** listed at audit time: downloaded and inspected
  **24 ZIPs and 14 standalone firmware notice files** (38 assets). Binary
  contents were not republished or relabeled. These checks cover legal-member
  presence and available notices, not a complete per-symbol reconstruction of
  every historical SDK image.
- ESP Web Tools 10.4.0 npm tarball, exact installer JS Git payloads, pinned
  upstream lockfile and integrity-verified runtime dependency tarballs.

## Verified findings and corrections

### Original MIT license: intact

The root license is unchanged from Csontikka's original full MIT text and
Copyright (c) 2026 Csontikka. Its Git blob is
`2694857e74627637b7f58da11e8f0556a74f7498`, matching the upstream license API.
No copyright was replaced and no invented Mattboxx copyright was added.

### Fork attribution and citation metadata: corrected

`NOTICE.md`, README and website credits previously pointed only to
Csontikka/microlink although `.gitmodules` uses Mattboxx/microlink. They now
distinguish actual dependency from immediate upstream and original author:

CamM2325/microlink (**Cameron Malone**) → Csontikka/microlink → Mattboxx/microlink.

MicroLink's original MIT notice is preserved (Git blob
`befb8e069a54c2745e6e0851c745b56f4333c4b9`, matching the original project's
license). Daniel Hope's BSD-3-Clause wireguard_lwip and the MIT X25519 notice
for Cryptography Research, Inc. / source author Mike Hamburg are identified
separately. Neither Tailscale nor WireGuard is attributed to Mattboxx.

`CITATION.cff` had stale version 2.0.2 / date 2026-10-23. It now identifies
3.0.2 / 2026-10-25, the actual dependency and separate upstream references.
Citation is explicitly optional, not an added condition on MIT use.

### Firmware binary notices: expanded

The previous collector copied recognized license files below configured
components but omitted legal notices present only in compiled source headers
and compiler runtimes outside those component paths. The actual 3.0.2 notice
asset lacked **Verisure Innovation AB's mDNS BSD notice**, newlib aggregate
copyrights and the GCC Runtime Library Exception text despite these components
being present in the saved build/source/map evidence. The wpa_supplicant
`COPYING` file delegates its full BSD conditions to `README`; that referenced
legal text was also absent from the old filename-based collection and is now
explicitly included, with a missing-file regression guard.

The collector now retains leading copyright/license comments from configured
sources (deduplicating only identical blocks), `COPYRIGHT` files and exact
newlib/GCC/libstdc++ runtime license/exception files. Missing original-source
metadata or runtime notices fails with an actionable error instead of silently
generating an incomplete bundle. It uses relative labels, not developer paths.
The root source URL now uses the renamed repository.

An expanded [3.0.2 notice supplement](../licenses/firmware-v3.0.2-notices.txt)
is prepared without replacing the qualified image. Future packages obtain
their notices from their own build metadata. This is conservative collection,
not a claim that every configured source is present in the final executable.

Two modified local Apache-2.0 DHCP files retained Espressif copyright headers
but lacked a clear top-of-file modification statement. Comment-only notices
were added to `dhcpserver.c` and `dhcpserver.h`; code/declarations are unchanged.
`dhcpserver_options.h` matched the SDK and was not changed. No Apache license
text or original copyright header was rewritten.

### Browser installer dependencies: full texts added

The website previously listed dependency license names but supplied only the
main Apache-2.0 text. Installer JS is verified byte-for-byte in Git against the
original npm tarball; checkout-only newline conversion is distinguished from
code changes. No vendored JS was modified.

The checked-in `DEPENDENCY-LICENSES.txt` now carries verbatim notices for the
**12-package locked dependency closure**, including Lit's BSD-3-Clause,
atob-lite MIT, tslib 0BSD and pako's MIT/Zlib terms. Package copyright headers
are retained too. The ssr-dom-shim package omitted a standalone license file;
its pinned upstream monorepo BSD text is supplied with its original package
copyright headers. JSON provenance records versions, integrity and text hashes.

This conservative closure also contains a type declaration dependency; it is
not represented as executable firmware or guaranteed browser-linked code.

### Brand, independence and optional donations: preserved

README, NOTICE and website clearly describe an independent community edition,
not an official/endorsed Tailscale, Headscale or Espressif product. New legal
text does not grant trademark rights. The brand guide's recommendations are
clarified as visual guidance, not extra conditions on MIT rights.

Ko-fi remains directed to **Mattboxx Edition development**, separately from
upstream support links. No donation, new attribution display or upstream
approval requirement was imposed. This audit does not address taxation or
independently establish title to every artwork or trademark.

## Distribution remediation (2026-10-26)

The original inspection found eleven old ZIPs without firmware notices and
incomplete newer notices. The follow-up prepared matching companions for all
**25 public releases**, based on each source tag, its actual MicroLink gitlink
and the SDK version parsed from the image descriptor. The earliest six
releases identify **ESP-IDF 5.3.1**; the others identify **5.5.3**. SDK/component
source notices and runtime profiles were collected for those versions rather
than reusing a modern notice file as proof of the older image's dependencies.
The runtime profile follows the SDK/toolchain generation; a historical exact
compiler/link-map reconstruction is not asserted.

The release pages now provide version-specific firmware notices, provenance,
legal-download checksums and the source companion for the separately bundled
esptool. For the ten newest releases (v2.0.2–v3.0.2) the firmware addendum,
desktop-tool notices, provenance and checksum files were moved after
publication from release assets to [licenses/releases](../licenses/releases/)
in this repository, byte for byte: 2.x firmware in the field reads the ten
newest releases into a 256 KiB buffer and the extra assets had grown that list
to 263 KiB (about 202 KiB afterwards). The addendum and tool notices also stay
inside each release's `WITH-NOTICES.zip`; the ZIP and the esptool source
download stay attached to every release. **24 additional `WITH-NOTICES.zip` archives** include the expanded
firmware and desktop-tool notices and exact source download/hash. Original
ZIPs, binary images, release tags and their checksums are retained unchanged.
The current README/download button points at the new 3.0.2 legal-material ZIP.
The browser installer still serves the same four binary parts and manifest;
only its notice text/checksum is expanded.

The esptool source arrangement is no longer merely a generic upstream link:
a same-place source download supplies 104 pinned upstream source archives,
build scripts and original legal material, including the **GPL legacy flasher
stub** that the initial frozen-table inspection had not established. Source
correspondence was checked for 617 Python modules, both native dependency
wheels and the Python DLL. Details and scope are in
[Flashing-tool redistribution](FLASHING-TOOL-LICENSES.md). No written source
offer was invented and no private signing key was distributed.

Publication evidence is recorded in
[distribution-remediation.json](../licenses/distribution-remediation.json).
It identifies the additive assets and their hashes. Original asset IDs, sizes
and digests were compared before/after the repairs. The initial eleven
missing-notice archives are retained for historical integrity; users receive
complete materials from the documented corrected downloads and companions.

## Remaining verification boundaries

No new specific notice/source omission is established within this inspected
set after the documented repairs. This is not an absolute legal-compliance
opinion. Historical per-symbol provenance, exact old compiler flags, all
opaque vendor-object ownership, artwork/title and trademark clearance were
not independently certified. SDK notice inventories deliberately include
unlinked/disabled material. Microsoft runtime components retain their own
terms. The desktop executable was not rebuilt byte for byte; the supplied
source and build materials do not claim private signing keys or a new owner
source-offer commitment. Future executable/dependency changes require a new
review; these results do not automatically cover them.

## License-obligation checklist

| License / material | Evidence and handling | Status |
|---|---|---|
| MIT: original firmware, MicroLink, X25519, other MIT components | Original text/copyright retained; fork relationships corrected; binary generator carries notices | Preserved; matching distribution companions supplied |
| BSD-3-Clause: wireguard_lwip, lwIP/mDNS, Lit | Full terms/copyright/disclaimer preserved or supplemented; no implied endorsement | Corrected notices and binary companions supplied |
| Apache-2.0: SDK, local DHCP copies, website tools | License/NOTICE collection and source modification markers; no relicensing | Reviewed for the identified components |
| GCC runtime / libstdc++ and newlib | Actual toolchain license and exception texts included; not mislabeled root MIT | Version-specific supplements supplied |
| GPL-2.0-or-later: separate esptool executable | License present, official current binary hash verified | Pinned source access supplied; scope documented |
| Branding / tips | Independent edition and recipient distinction; no added MIT restrictions | Preserved, no absolute trademark/title opinion |

## Validation records

Targeted offline checks cover immutable original MIT text, dependency/author
metadata, citation version, legal comment parsing, missing-runtime refusal,
dependency notice presence, donation links and known supplement omissions.
Packaging tests exercise actual collection with synthetic SDK/toolchain
fixtures; actual 3.0.2 metadata was also processed. Site build/link/SEO checks
cover the added legal links. No firmware build, flash or hardware test is
needed for comment/document/packaging-only changes.

Detailed downloads, hashes, parsed archive tables and command outputs are
kept in ignored `build/license-audit/`. The owner authorized the additive distribution repair. This review does not
replace the verification boundaries above or authorize unrelated releases.

Executed offline results (2026-10-26):

| Check | Actual result |
|---|---|
| `python tools/test_license_compliance.py` | PASS, 8 cases |
| `python tools/test_release_packaging.py` | PASS, 8 cases |
| `python tools/test_v2_packaging.py` | PASS, 6 cases |
| `python tools/test_license_remediation.py` | PASS, 8 cases: nested/flat ZIPs, checksums, unchanged payloads, wrong source/executable, tampered source, malformed image metadata |
| `python tools/test_easy_install.py` | PASS, POSIX shell with stub esptool; no device access |
| `python tools/build_site.py --check` | PASS, 25 pages + 404 and 8 redirects; links/SEO/accessibility structure |
| `python tools/test_site_seo.py` / `test_site_presentation.py` | PASS |
| CFF against the official 1.2.0 JSON Schema | PASS (schema and validator stored in ignored audit output) |
| Two modified DHCP files, original versus current C token streams | PASS, identical non-comment tokens |
| Saved 3.0.2 metadata and runtime notice collection; exact BIN/ELF hashes | PASS; provenance beside the supplement |
| Actual corrected archives | PASS, 24 ZIPs retain every original image/executable/script byte; original ZIPs untouched |
| Desktop-source correspondence | PASS, 617 Python modules; official native-extension wheels and Python DLL; source archive internal checksums |
| Main tracked/untracked content, artifacts and reachable history scan | PASS, no findings |
| MicroLink history scan | Scanner reports 9 existing example-key placeholders, manually classified as all-X examples; scanner was not relaxed and history was not rewritten |

The site checks above are static/offline checks, not a new browser or firmware
qualification campaign. No network/device state or application behavior changed.

## Primary terms and next maintainer action

The review uses the actual copies shipped in the dependencies, supplemented by
the original [MIT terms](https://opensource.org/license/mit),
[BSD-3-Clause terms](https://opensource.org/license/bsd-3-clause),
[Apache-2.0 terms](https://www.apache.org/licenses/LICENSE-2.0),
[esptool 5.3.1 GPL license](https://github.com/espressif/esptool/blob/v5.3.1/LICENSE)
and the copied GCC runtime exception. A license-family label alone does not
replace any component's original copyright, notice or license text.

The owner authorized publication of these scoped corrections. Preserve all
original artifacts and tags when integrating later firmware work. Future
packages must carry the corresponding notices and, when bundling esptool,
the validated source companion. Do not substitute an independently rebuilt
image or merge archived/private history for a legal-material update.
