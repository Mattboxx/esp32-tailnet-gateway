"""Offline presentation-only checks; never builds or accesses firmware/hardware."""
from pathlib import Path
import re
import build_site

root = Path(__file__).resolve().parents[1]
site = root/'build/site'
if not site.exists():
    build_site.build(site)

assert build_site.REPO_URL.endswith('/esp32-tailscale-gateway-NAS-recovery')
assert build_site.SITE_URL.endswith('/esp32-tailscale-gateway-NAS-recovery/')
assert build_site.STABLE_TAG == 'v0.1.38-Mattboxx-1.13'
assert len(list((root/'website/pages').glob('*.html'))) == 16
for file in site.rglob('*.html'):
    text = file.read_text(encoding='utf-8')
    assert 'https://github.com/Mattboxx/esp32-tailnet-gateway' not in text, file
    assert 'https://mattboxx.github.io/esp32-tailnet-gateway/' not in text, file
    assert not re.search(r'releases/download/[^\s"<>]*1\.14', text), file
    if 'name="robots" content="noindex"' not in text:
        assert 'aria-label="Firmware availability"' in text, file
        assert build_site.STABLE_TAG in text, file
        assert '1.14 preview' in text, file
readme = (root/'README.md').read_text(encoding='utf-8')
for target in re.findall(r'(?:\]\(|src=")([^\s"\)]+)',readme):
    if target.startswith(('https:', 'http:', 'mailto:', '#', '../../releases')):
        continue
    assert (root/target.split('#')[0]).exists(), target
for name in ('firmware.bin','firmware-factory.bin','RELEASE-SHA256SUMS.txt',
             'ESP32-S3-router-0.1.38-Mattboxx-1.13-windows.zip'):
    assert name in (site/'downloads/index.html').read_text(encoding='utf-8'), name
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
print('PASS: 16-page current-path preview, real stable assets, README links, manual-only workflow and output guards')
