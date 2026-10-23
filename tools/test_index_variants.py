"""Embedded web page variants produced by the actual main/gen_index_html_gz.py.

The WiFi image embeds the UI translations; the experimental W5500 image is
built with --english-only to fit its 1920 KiB app partition. Runs the real
generator both ways and checks the page, the translation bundle and the
generated C array. Host only.
"""
from pathlib import Path
import gzip
import json
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'main/gen_index_html_gz.py'
PAGE = ROOT / 'main/index.html'


def run(*args):
    subprocess.run([sys.executable, str(GEN), *args], check=True, cwd=ROOT)


def c_array(path):
    data = path.read_text(encoding='utf-8')
    assert 'index_html_gz_start[]' in data and 'index_html_gz_len' in data
    return gzip.decompress(bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', data)))


with tempfile.TemporaryDirectory(prefix='index-variants-') as d:
    d = Path(d)
    run('--html', str(PAGE), str(d / 'full.html'))
    run('--english-only', '--html', str(PAGE), str(d / 'en.html'))
    run(str(PAGE), str(d / 'full.c'))
    run('--english-only', str(PAGE), str(d / 'en.c'))
    full = (d / 'full.html').read_bytes()
    en = (d / 'en.html').read_bytes()
    assert c_array(d / 'full.c') == full and c_array(d / 'en.c') == en, 'C arrays differ from the pages'

    m = re.search(rb'window\.I18N_DATA=(\{.*?\});</script>', full, re.S)
    assert m, 'translations missing from the WiFi page'
    bundle = json.loads(m.group(1))
    languages = json.loads((ROOT / 'main/i18n/languages.json').read_text(encoding='utf-8'))
    assert set(bundle['langs']) == set(languages) and all(len(row) == len(bundle['h']) for row in bundle['tr'].values())
    assert b'I18N_DATA=' not in en and b'id="i18n-data"' not in en, 'translations left in the English-only page'
    # Same UI otherwise: the English page is the full page minus the bundle.
    assert full.replace(m.group(0), b'').replace(b'<script id="i18n-data">', b'').replace(b'\n</head>', b'</head>') \
        .replace(b'\n', b'') == en.replace(b'\n', b''), 'English-only page differs beyond the translation bundle'
    for marker in (b'id="vendor-sjcl"', b'fb-done-open', b'window.I18N_DATA||null'):
        assert marker in en, marker
    full_gz, en_gz = len(gzip.compress(full, 9, mtime=0)), len(gzip.compress(en, 9, mtime=0))
    assert en_gz < full_gz - 30000, (full_gz, en_gz)
print(f'PASS: actual page generator: WiFi page with {len(languages)} translations, English-only page without the bundle and otherwise identical, '
      f'C arrays decode to the pages; English-only saves {full_gz - en_gz} gzip bytes (host)')
