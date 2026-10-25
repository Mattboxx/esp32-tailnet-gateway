#!/usr/bin/env python3
"""Build helper: turn main/index.html into the gzip C array embedded in the
firmware. Invoked from main/CMakeLists.txt.

Steps (all deterministic, standard library only):
1. Conservative minification, segment-aware: HTML comments and blank or
   indentation-only whitespace in markup, comments in <style>, and
   comment-only lines in <script>. Code, strings and <pre>/<textarea>
   content are never rewritten. The browser suite runs against this output
   (`--html`) so a minifier mistake fails the tests, not the device.
2. UI translations from main/i18n/*.json become one small script per
   language (i18n/<code>-<hash>.js, gzip, served from flash and cached by
   the browser); the page carries only the list of languages, so it loads
   the one language the visitor uses and stays small (English text is the
   key and the fallback).
3. The vendored SJCL library is injected for encrypted backups over HTTP.
4. gzip -9 with mtime 0, emitted as a C array.

Why a script and not CMake natively? CMake cannot gzip a single member
stream, and Python ships with the PlatformIO/ESP-IDF toolchain.

Usage:
    gen_index_html_gz.py <input.html> <output.c>
    gen_index_html_gz.py --html <input.html> <output.html>   # for tests; the
        language scripts are written next to it in i18n/
"""
import gzip
import hashlib
import io
import json
import re
import sys
from pathlib import Path

_PROTECTED = re.compile(r'(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<pre\b[^>]*>.*?</pre>|<textarea\b[^>]*>.*?</textarea>)',
                        re.S | re.I)


def _trim_lines(text):
    return '\n'.join(line.strip() for line in text.split('\n') if line.strip())


def _minify_script(block):
    open_tag, body, close = re.match(r'(<script\b[^>]*>)(.*)(</script>)$', block, re.S | re.I).groups()
    out, in_comment = [], False
    for raw in body.split('\n'):
        line = raw.strip()
        if in_comment:
            if '*/' in line:
                in_comment = False
                line = line.split('*/', 1)[1].strip()
            else:
                continue
        if line.startswith('/*'):
            if '*/' in line:
                line = line.split('*/', 1)[1].strip()
            else:
                in_comment = True
                continue
        if not line or line.startswith('//'):
            continue
        out.append(line)
    return open_tag + '\n' + '\n'.join(out) + '\n' + close


def _minify_style(block):
    block = re.sub(r'/\*.*?\*/', '', block, flags=re.S)
    return _trim_lines(block)


def minify(text):
    parts = _PROTECTED.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            part = re.sub(r'<!--(?!\[).*?-->', '', part, flags=re.S)
            out.append(_trim_lines(part))
        elif part[:7].lower() == '<script':
            out.append(_minify_script(part))
        elif part[:6].lower() == '<style':
            out.append(_minify_style(part))
        else:
            out.append(part)   # <pre>/<textarea>: whitespace is content
    return '\n'.join(p for p in out if p)


def fnv1a(text):
    """FNV-1a 32-bit over UTF-16 code units, identical to the UI runtime."""
    h = 0x811c9dc5
    raw = text.encode('utf-16-le')
    for i in range(0, len(raw), 2):
        h = ((h ^ (raw[i] | raw[i + 1] << 8)) * 0x01000193) & 0xffffffff
    return h


def i18n_packs(folder):
    """({code: {"name": ..}}, {code: {"h": [hash...], "tr": [...], "p": [...]}}).

    One pack per language with only the strings it translates. Keys are
    FNV-1a hashes of the English text instead of the text itself: the
    English already ships in the page. A colliding hash is rejected."""
    folder = Path(folder)
    meta_path = folder / 'languages.json'
    if not meta_path.exists():
        return None, {}
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    packs = {}
    for code in meta:
        path = folder / (code + '.json')
        if not path.exists():
            continue
        table = json.loads(path.read_text(encoding='utf-8'))
        patterns = sorted([k, v] for k, v in table.items() if '{}' in k and v)
        plain = sorted((k, v) for k, v in table.items() if '{}' not in k and v and v != k)
        hashes = [fnv1a(k) for k, _ in plain]
        if len(set(hashes)) != len(hashes):
            raise SystemExit(f'i18n: hash collision between two English strings ({code}); rephrase one')
        packs[code] = {'h': hashes, 'tr': [v for _, v in plain], 'p': patterns}
    return meta, packs


def build(src, english_only=False):
    """(page bytes, {asset name: bytes}) exactly as the firmware serves them."""
    src = Path(src)
    text = minify(src.read_text(encoding='utf-8'))
    meta, packs = (None, {}) if english_only else i18n_packs(src.parent / 'i18n')
    assets = {}
    if meta:
        langs = {}
        for code, info in meta.items():
            if code not in packs:
                continue
            body = ('I18N_LOADED(' + json.dumps(code) + ',' +
                    json.dumps(packs[code], ensure_ascii=False, separators=(',', ':')) + ');\n').encode('utf-8')
            name = f'{code}-{hashlib.sha256(body).hexdigest()[:10]}.js'   # new text, new name: no stale cache
            assets[name] = body
            langs[code] = {'name': info['name'], 'src': 'i18n/' + name}
        data = json.dumps(langs, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        # First thing in <head>: the language loader there needs the list.
        text = text.replace('<head>', '<head>\n<script id="i18n-data">window.I18N_LANGS=' + data + ';</script>', 1)
    raw = text.encode('utf-8')
    # Inject vendor SJCL so encrypted backups work over plain HTTP (WebCrypto
    # needs a secure context); the JS prefers crypto.subtle when present.
    sjcl_path = src.parent / 'vendor' / 'sjcl.min.js'
    if sjcl_path.exists():
        tag = b'<script id="vendor-sjcl">\n' + sjcl_path.read_bytes() + b'\n</script>\n'
        idx = raw.find(b'</head>')
        if idx >= 0:
            raw = raw[:idx] + tag + raw[idx:]
        else:
            print('gen_index_html_gz: WARNING - no </head>, SJCL not injected', file=sys.stderr)
    else:
        print('gen_index_html_gz: WARNING - vendor/sjcl.min.js missing, '
              'encrypted-backup will only work over HTTPS', file=sys.stderr)
    return raw, assets


def build_html(src, english_only=False):
    return build(src, english_only)[0]


def _gz(data):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def _c_bytes(out, name, data):
    out.write('static const unsigned char %s[] = {' % name)
    for i, b in enumerate(data):
        if i % 16 == 0:
            out.write('\n    ')
        out.write('0x%02x,' % b)
    out.write('\n};\n')


def main() -> int:
    args = sys.argv[1:]
    # --english-only: no translations (the UI then offers English only).
    english_only = bool(args) and args[0] == '--english-only'
    if english_only:
        args = args[1:]
    if len(args) == 3 and args[0] == '--html':
        page, assets = build(args[1], english_only)
        out = Path(args[2])
        out.write_bytes(page)
        if assets:
            folder = out.parent / 'i18n'
            folder.mkdir(exist_ok=True)
            for name, body in assets.items():
                (folder / name).write_bytes(body)
        return 0
    if len(args) != 2:
        print('usage: gen_index_html_gz.py [--english-only] [--html] <input.html> <output>', file=sys.stderr)
        return 2
    src, dst = Path(args[0]), Path(args[1])
    original = src.stat().st_size
    raw, assets = build(src, english_only)
    gz_bytes = _gz(raw)

    out = io.StringIO()
    out.write('/* GENERATED — see main/gen_index_html_gz.py. Do not edit by hand. */\n')
    out.write('#include <stddef.h>\n')
    out.write('typedef struct {const char *name; const unsigned char *data; size_t len;} i18n_asset_t;\n')
    out.write('const char index_html_gz_start[] = {')
    for i, b in enumerate(gz_bytes):
        if i % 16 == 0:
            out.write('\n    ')
        out.write('0x%02x,' % b)
    out.write('\n};\n')
    out.write('const size_t index_html_gz_len = sizeof(index_html_gz_start);\n')
    entries, lang_gz = [], 0
    for n, (name, body) in enumerate(sorted(assets.items())):
        data = _gz(body)
        lang_gz += len(data)
        _c_bytes(out, 'i18n_%d' % n, data)
        entries.append('{"%s", i18n_%d, sizeof i18n_%d}' % (name, n, n))
    out.write('const i18n_asset_t i18n_assets[%d] = {%s};\n' % (max(1, len(entries)), ', '.join(entries) or '{0}'))
    out.write('const size_t i18n_asset_count = %d;\n' % len(entries))
    dst.write_text(out.getvalue(), encoding='utf-8')
    print('gen_index_html_gz: source=%d  built=%d  gz=%d  languages=%d (%d gz bytes)' % (original, len(raw), len(gz_bytes), len(assets), lang_gz))
    return 0


if __name__ == '__main__':
    sys.exit(main())
