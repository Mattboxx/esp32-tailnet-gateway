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

## Remaining distribution issues: NOT closed

1. **Historical download notices:** eleven ZIPs, from
   `v0.1.19-Mattboxx` through the earlier `v0.1.31-Mattboxx-1.10-dev.11` series,
   have an esptool license but no firmware license/notice member. Their public
   release assets also lack standalone `FIRMWARE-LICENSES.txt`. Do not mistake
   the desktop tool's GPL license for firmware attribution. Each historical
   image needs a matching notice addendum/source-dependency review; the 3.0.2
   supplement is not proof of its exact old dependency versions.

   Affected archive release tags:
   `v0.1.19-Mattboxx`, `v0.1.19-Mattboxx-1.1`, `v0.1.19-Mattboxx-1.2`,
   `v0.1.19-Mattboxx-1.3`, `v0.1.19-Mattboxx-1.4`,
   `v0.1.19-Mattboxx-1.5`, `v0.1.28-Mattboxx-1.6`,
   `v0.1.29-Mattboxx-1.7`, `v0.1.29-Mattboxx-1.8`,
   `v0.1.31-Mattboxx-1.10-dev.10`, `v0.1.31-Mattboxx-1.10-dev.11`.
2. **Published 3.0.2 packages:** the expanded supplement and corrected future
   generator do not mean the already-published asset/ZIP/browser copy has been
   replaced. The local `website/firmware/3.0.2/FIRMWARE-LICENSES.txt` and its
   checksum are corrected, with all binary parts and the installer manifest
   unchanged; this needs a later authorized Pages deployment. Publish
   appropriate companion notices and update relevant package
   checksums/metadata without changing or rebuilding qualified firmware. No
   release assets or tags were mutated during this local audit.
3. **GPL esptool corresponding source:** the current executable reports 5.3.1
   and matches Espressif's official Windows executable by hash. All 24 inspected
   ZIPs include `ESPTOOL-LICENSE.txt`. They contain no source bundle; current
   instructions link the generic upstream repository but do not themselves
   demonstrate a complete applicable GPLv2 section 3 source arrangement.
   A frozen-tool table inspection additionally identifies Python 3.13 and an
   OpenSSL DLL, with three embedded notice files (Click and stub-flasher
   notices). Complete frozen dependency/source/license coverage remains
   unverified. See [Flashing-tool redistribution](FLASHING-TOOL-LICENSES.md).
   Do not call this resolved merely by adding another link or inventing a
   written offer on the owner's behalf.
4. **Scope boundaries:** a complete file-by-file provenance reconstruction of
   every historical binary, all opaque vendor objects and frozen desktop tool
   dependencies was not established. Original upstream source notices are
   preserved; no full legal-compliance guarantee follows from a successful scan.

## License-obligation checklist

| License / material | Evidence and handling | Status |
|---|---|---|
| MIT: original firmware, MicroLink, X25519, other MIT components | Original text/copyright retained; fork relationships corrected; binary generator carries notices | Source verified; historical binary repairs remain |
| BSD-3-Clause: wireguard_lwip, lwIP/mDNS, Lit | Full terms/copyright/disclaimer preserved or supplemented; no implied endorsement | Current legal material corrected; publication still required |
| Apache-2.0: SDK, local DHCP copies, website tools | License/NOTICE collection and source modification markers; no relicensing | Reviewed for the identified components |
| GCC runtime / libstdc++ and newlib | Actual toolchain license and exception texts included; not mislabeled root MIT | Supplement prepared |
| GPL-2.0-or-later: separate esptool executable | License present, official current binary hash verified | Corresponding-source/dependency closure OPEN |
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
kept in ignored `build/license-audit/`. New release publication still requires
explicit authority. This audit must not be presented as fully closed while
the distribution/source items above remain open.

Executed offline results (2026-10-26):

| Check | Actual result |
|---|---|
| `python tools/test_license_compliance.py` | PASS, 8 cases |
| `python tools/test_release_packaging.py` | PASS, 8 cases |
| `python tools/test_v2_packaging.py` | PASS, 6 cases |
| `python tools/test_easy_install.py` | PASS, POSIX shell with stub esptool; no device access |
| `python tools/build_site.py --check` | PASS, 25 pages + 404 and 8 redirects; links/SEO/accessibility structure |
| `python tools/test_site_seo.py` / `test_site_presentation.py` | PASS |
| CFF against the official 1.2.0 JSON Schema | PASS (schema and validator stored in ignored audit output) |
| Two modified DHCP files, original versus current C token streams | PASS, identical non-comment tokens |
| Saved 3.0.2 metadata and runtime notice collection; exact BIN/ELF hashes | PASS; provenance beside the supplement |
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

Changes are local until explicitly authorized for publication. Apply this
scoped audit commit to the current development/public-source branch only after
reviewing intervening changes. Do not replace qualified BIN files, rewrite
historical tags, or merge archived private history. After source/Pages approval,
publish the notice-only browser update and current companion notices; review
each of the eleven older archives against its own recorded dependencies.
Resolve the desktop-tool corresponding-source arrangement separately before
claiming full binary redistribution compliance. No new source offer, relicensing
or upstream approval requirement is created by this handoff.
