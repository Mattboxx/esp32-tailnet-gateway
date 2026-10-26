# ESP Web Tools 10.4.0 (vendored)

Unmodified `dist/web` bundle of [esp-web-tools](https://github.com/esphome/esp-web-tools)
10.4.0 from the npm registry (tarball integrity sha512 verified against the
registry on 2026-10-23; tarball SHA-256
`f18da75335d2f0dca044c4bb052848c0696e7b03cc23d61d8530dd6eba0a9008`).
Licence: Apache-2.0, see `LICENSE.txt`. Served from this site so the page
needs no third-party CDN (Content-Security-Policy `script-src 'self'`).

Verbatim dependency licenses and copyright headers accompany the bundle in
[DEPENDENCY-LICENSES.txt](DEPENDENCY-LICENSES.txt). Exact package versions,
tarball integrity and notice hashes are recorded in
[dependency-license-provenance.json](dependency-license-provenance.json).
They were collected from the runtime dependency closure of the pinned release
lockfile (source commit `fab2ba48253d19fd29a15af57bec771d34978b62`). Conservative
inclusion does not claim every dependency survives browser tree-shaking.

The dependency closure retains these licenses:

| Package | Licence |
|---|---|
| esptool-js 0.6.0 | Apache-2.0 |
| @material/web 2.4.1 | Apache-2.0 |
| improv-wifi-serial-sdk 2.8.0 | Apache-2.0 |
| lit 3.3.3, lit-html 3.3.0, lit-element 4.2.0, @lit/reactive-element 2.1.0 | BSD-3-Clause |
| @lit-labs/ssr-dom-shim 1.2.0 | BSD-3-Clause; upstream monorepo LICENSE plus package copyright headers |
| pako 2.2.0 | MIT AND Zlib |
| tslib 2.8.1 | 0BSD; Microsoft copyright notice retained |
| atob-lite 2.0.0 | MIT |
| @types/trusted-types 2.0.7 | MIT; declaration dependency retained conservatively |

Reproduce the notice collection with `python tools/refresh_web_license_notices.py`.
It verifies every tracked installer JavaScript file against the original npm
tarball and each dependency tarball against the locked integrity. Windows
checkout newline conversion is distinguished from changes to the Git payload.

Update only by replacing the whole folder with another verified release and
changing `EWT_VERSION` in `tools/build_site.py`.
