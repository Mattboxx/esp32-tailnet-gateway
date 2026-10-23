# Browser installer firmware (filled at release time)

ESP Web Tools downloads firmware with `fetch()`. GitHub release assets do
not send CORS headers, so the installer files are served by this site.

At release of v2.0.0, and only with the exact qualified files:

1. Create `website/firmware/2.0.0/` containing, byte for byte from the
   released Easy Install package (`firmware/web-installer/`):
   `bootloader.bin`, `partitions.bin`, `ota_data_initial.bin`, `firmware.bin`,
   `manifest.json`, `SHA256SUMS.txt`.
2. In `tools/build_site.py` set `NEXT_PUBLISHED = True` (and `RENAMED = True`
   only after the repository rename).
3. `python tools/build_site.py --check` refuses the build if a file is
   missing, a checksum differs, an offset differs from `partitions.csv`, or
   the manifest would erase without asking.
4. `python tools/test_site_flasher.py --browser` and
   `node tools/test_site_browser.cjs`, then deploy Pages.

Never place a development or release-candidate image here.
