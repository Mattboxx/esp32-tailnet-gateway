"""Offline presentation-only checks; never builds or accesses firmware/hardware."""
from pathlib import Path
import os
import re
import build_site

root = Path(__file__).resolve().parents[1]
site = Path(os.environ.get('SITE_PRESENTATION_DIR', str(root/'build/site')))
if not site.exists():
    build_site.build(site)

assert build_site.REPO_URL.endswith('/'+build_site.REPO_SLUG)
assert build_site.SITE_URL.endswith('/'+build_site.REPO_SLUG+'/')
assert build_site.STABLE_TAG == 'v0.1.38-Mattboxx-1.13'
assert len(list((root/'website/pages').glob('*.html'))) == 25
for file in site.rglob('*.html'):
    text = file.read_text(encoding='utf-8')
    if (file.parent == site and re.fullmatch(r'google[0-9a-f]+\.html', file.name)
            and text.strip() == 'google-site-verification: ' + file.name):
        continue  # Ownership proof is an exact plain-text file, not a site page.
    if not build_site.RENAMED:
        assert 'https://github.com/Mattboxx/esp32-tailnet-gateway' not in text, file
        assert 'https://mattboxx.github.io/esp32-tailnet-gateway/' not in text, file
    if not build_site.NEXT_PUBLISHED:
        assert not re.search(r'releases/download/[^\s"<>]*(?:1\.14|v2\.)', text), file
        assert 'esp-web-install-button' not in text, file
    if 'name="robots" content="noindex"' not in text:
        assert 'rel="canonical" href="'+build_site.SITE_URL in text, file
        if build_site.NEXT_PUBLISHED:
            assert 'aria-label="Firmware availability"' not in text, file
            assert f'Firmware v{build_site.NEXT_VERSION} is in preparation' not in text, file
        else:
            assert 'aria-label="Firmware availability"' in text, file
            assert build_site.STABLE_TAG in text, file
            assert f'Firmware v{build_site.NEXT_VERSION} is in preparation' in text, file
readme = (root/'README.md').read_text(encoding='utf-8')
for target in re.findall(r'(?:\]\(|src=")([^\s"\)]+)',readme):
    if target.startswith(('https:', 'http:', 'mailto:', '#', '../../releases')):
        continue
    assert (root/target.split('#')[0]).exists(), target
assets = ('firmware.bin','firmware-eth.bin','EASY-INSTALL-Windows-macOS-Linux.zip') if build_site.NEXT_PUBLISHED else (
    'firmware.bin','firmware-factory.bin','RELEASE-SHA256SUMS.txt','ESP32-S3-router-0.1.38-Mattboxx-1.13-windows.zip')
for name in assets:
    assert name in (site/'downloads/index.html').read_text(encoding='utf-8'), name
installer = (site/'install-firmware/index.html').read_text(encoding='utf-8')
assert ('<esp-web-install-button manifest=' in installer) == build_site.NEXT_PUBLISHED
if build_site.NEXT_PUBLISHED:
    changes = (site/'changelog/index.html').read_text(encoding='utf-8')
    assert f'[{build_site.NEXT_VERSION}]' in changes and 'dev.8' not in changes
    assert re.search(r'<h3>(Added|Fixed|Improved|Changed)</h3>', changes), 'changelog sections missing'
workflow=(root/'.github/workflows/pages.yml').read_text(encoding='utf-8')
assert '  workflow_dispatch:' in workflow and '  push:' not in workflow
assert 'submodules:' not in workflow  # Site build cannot publish dependency work.
for unsafe in (root,root/'build',root/'website',root.parent):
    try:
        build_site.build(unsafe)
    except ValueError:
        pass
    else:
        raise AssertionError('Unsafe output directory accepted')
print('PASS: 25-page presentation matches release/rename state; manifest gated, correct assets/canonical paths, README links and manual workflow')
