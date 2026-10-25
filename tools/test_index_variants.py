"""Embedded web page variants produced by the actual main/gen_index_html_gz.py.

The 3.x image embeds the page plus one script per UI language (loaded only
for the language in use); the 2.1 migration bridge is built with
--english-only to fit a 1920 KiB 2.x slot. Runs the real generator both ways
and checks the page, the language scripts and the generated C arrays. Host only.
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
sys.path.insert(0, str(ROOT / 'main'))
from gen_index_html_gz import fnv1a  # noqa: E402


def run(*args):
    subprocess.run([sys.executable, str(GEN), *args], check=True, cwd=ROOT)


def c_arrays(path):
    """{name: decompressed bytes} for the page ('/') and every language script."""
    text = path.read_text(encoding='utf-8')
    def data(block):
        return bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', block))
    page = re.search(r'index_html_gz_start\[\] = \{(.*?)\};', text, re.S)
    out = {'/': gzip.decompress(data(page.group(1)))}
    arrays = {m.group(1): data(m.group(2)) for m in re.finditer(r'static const unsigned char (i18n_\d+)\[\] = \{(.*?)\};', text, re.S)}
    table = re.search(r'i18n_assets\[(\d+)\] = \{(.*?)\};\nconst size_t i18n_asset_count = (\d+);', text, re.S)
    assert table, 'asset table missing'
    for name, var in re.findall(r'\{"([^"]+)", (i18n_\d+), sizeof i18n_\d+\}', table.group(2)):
        out[name] = gzip.decompress(arrays[var])
    assert int(table.group(3)) == len(out) - 1
    return out


with tempfile.TemporaryDirectory(prefix='index-variants-') as d:
    d = Path(d)
    (d / 'full').mkdir(); (d / 'en').mkdir()
    run('--html', str(PAGE), str(d / 'full/index.html'))
    run('--english-only', '--html', str(PAGE), str(d / 'en/index.html'))
    run(str(PAGE), str(d / 'full.c'))
    run('--english-only', str(PAGE), str(d / 'en.c'))
    full = (d / 'full/index.html').read_bytes()
    en = (d / 'en/index.html').read_bytes()
    scripts = {p.name: p.read_bytes() for p in (d / 'full/i18n').iterdir()}
    assert not (d / 'en/i18n').exists(), 'language scripts written for the English-only page'
    built = c_arrays(d / 'full.c')
    assert built.pop('/') == full and built == scripts, 'C arrays differ from the page and the language scripts'
    en_built = c_arrays(d / 'en.c')
    assert en_built == {'/': en}, 'English-only image carries language scripts'

    m = re.search(rb'<script id="i18n-data">window\.I18N_LANGS=(\{.*?\});</script>', full)
    assert m, 'language list missing from the page'
    langs = json.loads(m.group(1))
    languages = json.loads((ROOT / 'main/i18n/languages.json').read_text(encoding='utf-8'))
    assert set(langs) == set(languages), (set(langs), set(languages))
    for code, info in langs.items():
        name = info['src'].split('/')[-1]
        assert info['src'] == 'i18n/' + name and name.startswith(code + '-') and name in scripts
        body = scripts[name].decode('utf-8')
        assert body.startswith('I18N_LOADED(' + json.dumps(code) + ',') and body.rstrip().endswith(');')
        pack = json.loads(body[len('I18N_LOADED(' + json.dumps(code) + ','):body.rindex(');')])
        assert len(pack['h']) == len(pack['tr']) == len(set(pack['h'])) and all(pack['tr'])
        table = json.loads((ROOT / f'main/i18n/{code}.json').read_text(encoding='utf-8'))
        sample = next(k for k, v in table.items() if v and v != k and '{}' not in k)
        assert pack['tr'][pack['h'].index(fnv1a(sample))] == table[sample], code
    # The page itself no longer carries any translation.
    assert b'I18N_DATA' not in full and b'"tr":' not in full
    assert b'id="i18n-data"' not in en and b'I18N_LANGS=' not in en
    # Same UI otherwise: the English page is the full page minus the language list.
    assert full.replace(m.group(0), b'').replace(b'\n', b'') == en.replace(b'\n', b''), 'pages differ beyond the language list'
    for marker in (b'id="vendor-sjcl"', b'fb-done-open', b'window.I18N_FETCH'):
        assert marker in en, marker
    page_gz = len(gzip.compress(full, 9, mtime=0))
    assert page_gz < 170000, page_gz
print(f'PASS: actual page generator: page with {len(langs)} languages as separate scripts ({page_gz} gzip bytes), '
      f'English-only page without them and otherwise identical, C arrays decode to the page and scripts (host)')
