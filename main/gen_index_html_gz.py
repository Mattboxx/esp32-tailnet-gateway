#!/usr/bin/env python3
"""Build helper: turn main/index.html into the gzip C array embedded in the
firmware. Invoked from main/CMakeLists.txt.

Steps (all deterministic, standard library only):
1. Conservative minification, segment-aware: HTML comments and blank or
   indentation-only whitespace in markup, comments in <style>, and
   comment-only lines in <script>. Code, strings and <pre>/<textarea>
   content are never rewritten. The browser suite runs against this output
   (`--html`) so a minifier mistake fails the tests, not the device.
2. UI translations from main/i18n/*.json are injected as one compact
   bundle (English text is the key and the fallback).
3. The vendored SJCL library is injected for encrypted backups over HTTP.
4. gzip -9 with mtime 0, emitted as a C array.

Why a script and not CMake natively? CMake cannot gzip a single member
stream, and Python ships with the PlatformIO/ESP-IDF toolchain.

Usage:
    gen_index_html_gz.py <input.html> <output.c>
    gen_index_html_gz.py --html <input.html> <output.html>   # for tests
"""
import gzip
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


def i18n_bundle(folder):
    """{"langs":{code:{"name":..}}, "h":[hash...], "tr":{code:[...]}}.

    Keys are FNV-1a hashes of the English text instead of the text itself:
    the English already ships in the page, so repeating it would only cost
    flash. A colliding hash is rejected at build time."""
    folder = Path(folder)
    meta_path = folder / 'languages.json'
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    tables = {}
    for code in meta:
        path = folder / (code + '.json')
        if path.exists():
            tables[code] = json.loads(path.read_text(encoding='utf-8'))
    patterns = {code: sorted([k, v] for k, v in table.items() if '{}' in k and v) for code, table in tables.items()}
    tables = {code: {k: v for k, v in table.items() if '{}' not in k} for code, table in tables.items()}
    source = sorted({k for t in tables.values() for k, v in t.items() if v and v != k})
    hashes = [fnv1a(s) for s in source]
    if len(set(hashes)) != len(hashes):
        raise SystemExit('i18n: hash collision between two English strings; rephrase one')
    index = {s: i for i, s in enumerate(source)}
    tr = {}
    for code, table in tables.items():
        row = [''] * len(source)
        for k, v in table.items():
            if k in index and v and v != k:
                row[index[k]] = v
        tr[code] = row
    return {'langs': meta, 'h': hashes, 'tr': tr, 'p': patterns}


def build_html(src):
    src = Path(src)
    text = minify(src.read_text(encoding='utf-8'))
    head_close = '</head>'
    bundle = i18n_bundle(src.parent / 'i18n')
    if bundle:
        data = json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        text = text.replace(head_close, '<script id="i18n-data">window.I18N_DATA=' + data + ';</script>\n' + head_close, 1)
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
    return raw


def main() -> int:
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == '--html':
        Path(args[2]).write_bytes(build_html(args[1]))
        return 0
    if len(args) != 2:
        print('usage: gen_index_html_gz.py [--html] <input.html> <output>', file=sys.stderr)
        return 2
    src, dst = Path(args[0]), Path(args[1])
    original = src.stat().st_size
    raw = build_html(src)

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    gz_bytes = buf.getvalue()

    out = io.StringIO()
    out.write('/* GENERATED — see main/gen_index_html_gz.py. Do not edit by hand. */\n')
    out.write('#include <stddef.h>\n')
    out.write('const char index_html_gz_start[] = {')
    for i, b in enumerate(gz_bytes):
        if i % 16 == 0:
            out.write('\n    ')
        out.write('0x%02x,' % b)
    out.write('\n};\n')
    out.write('const size_t index_html_gz_len = sizeof(index_html_gz_start);\n')
    dst.write_text(out.getvalue(), encoding='utf-8')
    print('gen_index_html_gz: source=%d  built=%d  gz=%d' % (original, len(raw), len(gz_bytes)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
