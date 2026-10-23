"""Browser installer (ESP Web Tools) in the site build, with synthetic firmware.

Builds the site as if NEXT_VERSION were published, using fixture files in a temp
folder (never real firmware), and checks: the manifest and parts are served
from the site itself, offsets come from partitions.csv, the installer asks
before erasing, and wrong offsets, checksums, a missing manifest or an
erase-by-default manifest stop the build. With --browser it also renders the
page in Chromium (Playwright via node) and fails on console/CSP errors.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import runpy
import subprocess
import sys
import tempfile

import build_site

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/site-flasher-test'
LAYOUT = build_site.flash_layout()
assert LAYOUT == {'bootloader': 0x0, 'partitions': 0x8000, 'otadata': 0x19000, 'ota_0': 0x20000}, LAYOUT


def fixture(folder: Path, *, offsets=None, erase=True, bad_sum=False):
    folder.mkdir(parents=True, exist_ok=True)
    names = {'bootloader': 'bootloader.bin', 'partitions': 'partitions.bin',
             'otadata': 'ota_data_initial.bin', 'ota_0': 'firmware.bin'}
    parts, sums = [], []
    for key, name in names.items():
        data = (key + ' synthetic fixture, not firmware\n').encode() * 8
        (folder / name).write_bytes(data)
        parts.append({'path': name, 'offset': (offsets or LAYOUT)[key]})
        digest = hashlib.sha256(data + (b'x' if bad_sum and key == 'ota_0' else b'')).hexdigest()
        sums.append(f'{digest}  {name}\n')
    (folder / 'SHA256SUMS.txt').write_text(''.join(sums), encoding='ascii')
    # Served next to the installer files and linked from the downloads page.
    (folder / 'FIRMWARE-LICENSES.txt').write_text('synthetic license notices fixture\n', encoding='ascii')
    manifest = {'name': 'ESP32 Tailnet Gateway', 'version': build_site.NEXT_VERSION, 'new_install_prompt_erase': erase,
                'new_install_improv_wait_time': 0, 'builds': [{'chipFamily': 'ESP32-S3', 'parts': parts}]}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


def build_with(fw: Path):
    build_site.NEXT_PUBLISHED = True
    build_site.FIRMWARE_DIR = fw
    return build_site.build(OUT)


def expect_failure(**kw):
    with tempfile.TemporaryDirectory() as d:
        fixture(Path(d) / build_site.NEXT_VERSION, **kw)
        try:
            build_with(Path(d))
        except (AssertionError, SystemExit):
            return
    raise AssertionError(f'build accepted a bad installer manifest: {kw}')


with tempfile.TemporaryDirectory() as d:
    fixture(Path(d) / build_site.NEXT_VERSION)
    build_with(Path(d))
page = (OUT / 'install-firmware/index.html').read_text(encoding='utf-8')
assert f'<esp-web-install-button manifest="../firmware/{build_site.NEXT_VERSION}/manifest.json">' in page
assert f'../assets/esp-web-tools/{build_site.EWT_VERSION}/install-button.js' in page and 'type="module"' in page
assert 'slot="unsupported"' in page and 'Easy Install' in page
assert (OUT / f'firmware/{build_site.NEXT_VERSION}/firmware.bin').exists() and (OUT / 'assets/esp-web-tools/10.4.0/LICENSE.txt').exists()
assert f'Firmware v{build_site.NEXT_VERSION} is in preparation' not in page and 'aria-label="Firmware availability"' not in page
downloads = (OUT / 'downloads/index.html').read_text(encoding='utf-8')
assert 'EASY-INSTALL-Windows-macOS-Linux.zip' in downloads and 'Install from browser' in downloads
assert 'Experimental, not hardware-qualified' in downloads
for kw in ({'offsets': dict(LAYOUT, ota_0=0x10000)}, {'erase': False}, {'bad_sum': True}):
    expect_failure(**kw)
with tempfile.TemporaryDirectory() as d:
    try:
        build_with(Path(d))
    except SystemExit:
        pass
    else:
        raise AssertionError('published build without a manifest')
print('PASS: installer published only with exact parts, partitions.csv offsets and an erase prompt; bad manifests stop the build')

# Pages runs the presentation validator on deployment. Exercise the actual
# validator in all migration stages: it must not reject a published/renamed
# site merely because its original checks were written for the preview.
saved = {key: getattr(build_site, key) for key in ('RENAMED', 'NEXT_PUBLISHED', 'REPO_SLUG', 'REPO_URL', 'SITE_URL', 'FIRMWARE_DIR')}
old_output = os.environ.get('SITE_PRESENTATION_DIR')
try:
    with tempfile.TemporaryDirectory() as d:
        fixture(Path(d) / build_site.NEXT_VERSION)
        for renamed, published in ((False, False), (False, True), (True, True)):
            build_site.RENAMED, build_site.NEXT_PUBLISHED = renamed, published
            build_site.REPO_SLUG = 'esp32-tailnet-gateway' if renamed else 'esp32-tailscale-gateway-NAS-recovery'
            build_site.REPO_URL = 'https://github.com/Mattboxx/' + build_site.REPO_SLUG
            build_site.SITE_URL = 'https://mattboxx.github.io/' + build_site.REPO_SLUG + '/'
            build_site.FIRMWARE_DIR = Path(d)
            pages = build_site.build(OUT)
            problems = build_site.check(OUT, pages)
            assert not problems, f'Site checks failed (renamed={renamed}, published={published}): '+ '; '.join(problems[:6])
            os.environ['SITE_PRESENTATION_DIR'] = str(OUT)
            runpy.run_path(str(ROOT / 'tools/test_site_presentation.py'))
            if published and '--layouts' in sys.argv:
                env = dict(os.environ, SITE_TEST_DIR=str(OUT))
                subprocess.run(['node', str(ROOT / 'tools/test_site_browser.cjs')], check=True, cwd=ROOT, env=env)
    print('PASS: actual Pages presentation gate accepts preview, release-before-rename and release-after-rename (synthetic firmware)')
finally:
    for key, value in saved.items():
        setattr(build_site, key, value)
    if old_output is None:
        os.environ.pop('SITE_PRESENTATION_DIR', None)
    else:
        os.environ['SITE_PRESENTATION_DIR'] = old_output

if '--browser' in sys.argv:
    with tempfile.TemporaryDirectory() as d:
        fixture(Path(d) / build_site.NEXT_VERSION)
        build_with(Path(d))
    script = r'''
const { chromium } = require('playwright'); const path = require('node:path'); const fs = require('node:fs');
const out = process.argv[1];
(async () => {
  const b = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  const p = await b.newPage(); const errors = [];
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); }); p.on('pageerror', e => errors.push(e.message));
  await p.route('https://site.test/**', r => { const u = new URL(r.request().url()); let f = path.join(out, decodeURIComponent(u.pathname));
    if (u.pathname.endsWith('/')) f = path.join(f, 'index.html');
    if (!fs.existsSync(f)) return r.fulfill({ status: 404, body: 'missing' });
    const type = f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : f.endsWith('.css') ? 'text/css' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
    r.fulfill({ body: fs.readFileSync(f), contentType: type }); });
  await p.goto('https://site.test/install-firmware/');
  await p.waitForFunction(() => customElements.get('esp-web-install-button'), null, { timeout: 15000 });
  const visible = await p.isVisible('#flasher button[slot="activate"]');
  const manifest = await p.evaluate(async () => (await fetch(document.querySelector('esp-web-install-button').getAttribute('manifest'))).json());
  if (!visible || manifest.version !== process.argv[2] || errors.length) { console.log('FAIL', visible, manifest.version, errors); process.exit(1); }
  console.log('PASS: ESP Web Tools renders the Connect & Install button in Chromium, manifest served same-origin, no console/CSP errors');
  await b.close();
})();
'''
    subprocess.run(['node', '-e', script, str(OUT), build_site.NEXT_VERSION], check=True, cwd=ROOT, env=os.environ.copy())
shutil.rmtree(OUT, ignore_errors=True)
