"""Collect translatable English UI strings from main/index.html.

The Web UI translates whole text nodes and the placeholder/title/aria-label
attributes whose English text exactly matches a dictionary key, plus
confirm() messages. This tool lists those candidates so translators work on
the same set the runtime can actually replace:

    python tools/i18n_extract.py                # write main/i18n/source.json
    python tools/i18n_extract.py --coverage     # per-language coverage report
    python tools/i18n_extract.py --check 95     # fail below 95 % in any language

Coverage is reported honestly: strings assembled at run time from several
pieces (counters, addresses, dynamic sentences) cannot be matched and stay
English; they are not counted as translated.
"""
import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'main/index.html'
I18N = ROOT / 'main/i18n'
SKIP_TAGS = {'style', 'svg', 'code', 'pre', 'script', 'textarea'}


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        for key, value in attrs:
            if key in ('placeholder', 'title', 'aria-label') and value and _wordy(value):
                self.found.append(value.strip())

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        text = ' '.join(data.split())
        if not self.skip and _wordy(text):
            self.found.append(text)


def _wordy(text):
    text = text.strip()
    return bool(re.search(r'[A-Za-z]{2}', text)) and not re.fullmatch(r'[\w.:/-]+\.(?:json|bin|html)|https?://\S+|[\d./:]+', text)


_CODEY = re.compile(r'[<>{}=$\\`]|;(?! )|^\s|\s$|\b(?:function|var|return|document|querySelector)\b|^[#.\[]|^[a-z0-9_-]+$|^/api/')


def _js_strings(source):
    out = set()
    for script in re.findall(r'<script\b[^>]*>(.*?)</script>', source, re.S):
        for quote in ("'", '"'):
            pattern = quote + r'((?:[^' + quote + r'\\\n]|\\.){2,400})' + quote
            for m in re.finditer(pattern, script):
                text = m.group(1).replace("\\'", "'").replace('\\"', '"')
                if '<' in text or '>' in text:
                    # HTML built in script: its text segments and attributes become text nodes too.
                    for seg in re.findall(r'>([^<>]+)<', text) + re.findall(r'(?:placeholder|title|aria-label)="([^"]+)"', text):
                        seg = ' '.join(seg.split())
                        if _wordy(seg) and re.search(r'[A-Za-z]{3}', seg) and not re.search(r'[{};=$`\\]', seg):
                            out.add(seg)
                    continue
                if '\\' in text or _CODEY.search(text) or not re.search(r'[A-Za-z]{3}', text):
                    continue
                if not re.match(r'[A-Z0-9✓✗?(“"]', text):
                    continue
                if ' ' not in text and not re.fullmatch(r'[A-Z][a-z]+(?:-[a-z]+)?', text):
                    continue
                out.add(text)
    return out


def extract():
    source = SRC.read_text(encoding='utf-8')
    body = source[source.index('<body'):]
    markup = re.sub(r'<script\b.*?</script>', '', body, flags=re.S)
    parser = _Markup()
    parser.feed(markup)
    strings = {x for x in set(parser.found) | _js_strings(source)
               # partial pieces of run-time sentences and time-zone labels are not matchable/translatable
               if not x.endswith(('(', '"', '“', ' ·', ' —', ',')) and not x.startswith('UTC')}
    title = re.search(r'<title>(.*?)</title>', source)
    if title:
        strings.add(title.group(1).strip())
    return sorted(strings)


def coverage(strings):
    meta = json.loads((I18N / 'languages.json').read_text(encoding='utf-8'))
    report = {}
    for code in meta:
        path = I18N / (code + '.json')
        table = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        done = sum(1 for s in strings if table.get(s))
        report[code] = (done, len(strings))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--coverage', action='store_true')
    parser.add_argument('--check', type=float)
    args = parser.parse_args()
    strings = extract()
    if not args.coverage and args.check is None:
        I18N.mkdir(exist_ok=True)
        (I18N / 'source.json').write_text(json.dumps(strings, ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
        print(f'{len(strings)} strings, {sum(map(len, strings))} characters -> main/i18n/source.json')
        return 0
    failed = False
    for code, (done, total) in coverage(strings).items():
        pct = 100.0 * done / total if total else 0.0
        print(f'{code}: {done}/{total} strings ({pct:.1f} %)')
        if args.check is not None and pct < args.check:
            failed = True
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
