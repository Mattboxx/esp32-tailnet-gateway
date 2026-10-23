"""Build the static ESP32 Tailnet Gateway website (standard library only).

Sources live in website/: pages/*.html are body fragments with a small
front-matter comment; assets/ holds CSS/JS; brand images and diagrams are
copied from assets/. Output is a self-contained folder for GitHub Pages:

    python tools/build_site.py                  # -> build/site
    python tools/build_site.py --out _site      # CI / Pages artifact
    python tools/build_site.py --check          # build + link/SEO/a11y checks
    python -m http.server -d build/site 8000    # local preview

No analytics, no external fonts or scripts. English is the primary language;
pages declare `lang` so an Italian tree (website/pages/it/) can be added later
without changing URLs.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'website'
# Repository rename (MIGRATION-RENAME.md): flip RENAMED only after GitHub has
# renamed the repository, then rebuild and redeploy. Every URL derives from it.
RENAMED = True
REPO_SLUG = 'esp32-tailnet-gateway' if RENAMED else 'esp32-tailscale-gateway-NAS-recovery'
SITE_URL = f'https://mattboxx.github.io/{REPO_SLUG}/'
REPO_URL = f'https://github.com/Mattboxx/{REPO_SLUG}'
FUTURE_REPO_URL = 'https://github.com/Mattboxx/esp32-tailnet-gateway'
NAME = 'ESP32 Tailnet Gateway'
TAGLINE = 'One ESP32. Multiple Tailnet roles. Enable only what you need.'
DESCRIPTION = ('All-in-one ESP32-S3 Tailscale/Headscale gateway with selective '
               'LAN-to-Tailnet access, subnet routing, remote recovery and optional automation.')
STABLE_VERSION = '0.1.38-Mattboxx-1.13'
STABLE_TAG = 'v' + STABLE_VERSION
# Current firmware: keep NEXT_PUBLISHED False until the qualified release
# exists. When True, website/firmware/<NEXT_VERSION>/ must hold the exact
# released files (see website/firmware/README.md); the build verifies them.
NEXT_VERSION = '2.0.1'
NEXT_PUBLISHED = True
FIRMWARE_DIR = SRC / 'firmware'
EWT_VERSION = '10.4.0'   # ESP Web Tools bundle vendored in website/assets/esp-web-tools/

# Moved or alternative URLs -> current page (served as tiny redirect pages).
REDIRECTS = {
    'lan-to-tailnet/': 'service-gateway/',
    'docs/service-gateway/': 'service-gateway/',
    'install/': 'install-firmware/',
    'flash/': 'install-firmware/',
    'start/': 'first-boot/',
    'download/': 'downloads/',
    'recovery/': 'remote-recovery/',
    'integrations/': 'automation/',
}


def front_matter(text: str) -> tuple[dict, str]:
    match = re.match(r'\s*<!--(.*?)-->', text, re.S)
    assert match, 'page needs a front-matter comment'
    meta = {}
    for line in match.group(1).strip().splitlines():
        key, _, value = line.partition(':')
        meta[key.strip()] = value.strip()
    return meta, text[match.end():].strip()


class Page:
    def __init__(self, path: Path):
        self.meta, self.body = front_matter(path.read_text(encoding='utf-8'))
        self.slug = self.meta['slug']                  # '' for home, 'features/' ...
        self.title = self.meta['title']
        self.description = self.meta['description']
        self.nav = self.meta.get('nav', '')
        self.group = self.meta.get('group', '')       # sidebar group for docs pages
        self.order = int(self.meta.get('order', '99'))
        self.lang = self.meta.get('lang', 'en')
        self.schema = self.meta.get('schema', '')

    @property
    def depth(self) -> int:
        return self.slug.count('/')

    def rel(self, target: str) -> str:
        """Relative link from this page to another slug or asset path."""
        up = '../' * self.depth
        return (up + target) or './'


def inline_md(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', text)
    # Repository-relative links point at GitHub.
    text = re.sub(r'\[([^\]]+)\]\(([^)\s:]+)\)', lambda m: f'<a href="{REPO_URL}/blob/Main/{m.group(2).lstrip("./")}">{m.group(1)}</a>', text)
    return text


def changelog_html(limit_sections: int = 4) -> str:
    """Tiny Markdown subset for CHANGELOG.md: headings, lists, paragraphs."""
    lines = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').splitlines()
    out, para, items, sections = [], [], [], 0

    def flush():
        if para:
            out.append('<p>' + inline_md(' '.join(para)) + '</p>'); para.clear()
        if items:
            out.append('<ul>' + ''.join('<li>' + inline_md(i) + '</li>' for i in items) + '</ul>'); items.clear()
    for line in lines:
        # The public summary is the current release, not internal candidate notes.
        if line.startswith('## Development history'):
            break
        if line.startswith('## ['):
            flush()
            out.append('<h2>' + inline_md(line[3:]) + '</h2>')
            continue
        if line.startswith('### '):
            flush(); sections += 1
            if sections > limit_sections:
                break
            out.append('<h3>' + inline_md(line[4:]) + '</h3>')
        elif line.startswith('#'):
            flush()
        elif line.startswith('- '):
            if para:
                flush()
            items.append(line[2:].strip())
        elif line.startswith('  ') and items:
            items[-1] += ' ' + line.strip()
        elif not line.strip():
            flush()
        elif sections:
            para.append(line.strip())
    flush()
    return '\n'.join(out)


def flash_layout() -> dict[str, int]:
    """Offsets the installers write, from the real partition table. The
    ESP32-S3 second-stage bootloader is at 0x0 and the table at 0x8000."""
    layout = {'bootloader': 0x0, 'partitions': 0x8000}
    for line in (ROOT / 'partitions.csv').read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.split(',')]
        if len(cells) >= 4 and not cells[0].startswith('#') and cells[3]:
            layout[cells[0]] = int(cells[3], 0)
    return {'bootloader': layout['bootloader'], 'partitions': layout['partitions'],
            'otadata': layout['otadata'], 'ota_0': layout['ota_0']}


def firmware_manifest():
    path = FIRMWARE_DIR / NEXT_VERSION / 'manifest.json'
    if not path.exists():
        return None
    return f'firmware/{NEXT_VERSION}/manifest.json', json.loads(path.read_text(encoding='utf-8'))


def verify_firmware(out: Path) -> None:
    """Publish installer files only when they are complete and exact."""
    import hashlib
    found = firmware_manifest()
    if NEXT_PUBLISHED and not found:
        raise SystemExit(f'NEXT_PUBLISHED is set but website/firmware/{NEXT_VERSION}/manifest.json is missing')
    if not found:
        return
    folder = FIRMWARE_DIR / NEXT_VERSION
    manifest = found[1]
    assert manifest['version'] == NEXT_VERSION, 'manifest version differs from NEXT_VERSION'
    assert manifest.get('new_install_prompt_erase') is True, 'the installer must ask before erasing settings'
    sums = {}
    for line in (folder / 'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        digest, _, name = line.partition('  ')
        sums[name.strip()] = digest.strip()
    want = sorted(flash_layout().values())
    for build_entry in manifest['builds']:
        assert build_entry['chipFamily'] == 'ESP32-S3', 'ESP32-S3 only'
        offsets = sorted(part['offset'] for part in build_entry['parts'])
        assert offsets == want, f'installer offsets {offsets} differ from partitions.csv {want}'
        for part in build_entry['parts']:
            data = (folder / part['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == sums.get(part['path']), f'{part["path"]} checksum mismatch'
    shutil.copytree(folder, out / 'firmware' / NEXT_VERSION)


def flasher_html(page: Page) -> str:
    found = firmware_manifest()
    if not (NEXT_PUBLISHED and found):
        return (f'<div class="note"><p><strong>Firmware v{NEXT_VERSION} is not released yet.</strong> '
                'The browser installer turns on when the release is published, using exactly the released files. '
                f'Until then the stable download is <a href="{REPO_URL}/releases/tag/{STABLE_TAG}">Mattboxx 1.13</a>, '
                'installed with its own package; its first start differs from the new setup described here.</p></div>')
    manifest = page.rel(found[0])
    module = page.rel(f'assets/esp-web-tools/{EWT_VERSION}/install-button.js')
    easy = page.rel('easy-install/')
    return (f'<script type="module" src="{module}"></script>\n'
            '<div class="flasher" id="flasher">'
            f'<esp-web-install-button manifest="{manifest}">'
            '<button slot="activate" class="btn primary" type="button">Connect &amp; Install</button>'
            '<span slot="unsupported" class="note">This browser cannot talk to USB serial devices. Use desktop Chrome or Edge, '
            f'or the <a href="{easy}">Easy Install package</a>.</span>'
            '<span slot="not-allowed" class="note">The installer needs a secure (https) page.</span>'
            '</esp-web-install-button></div>')


def release_note(page: Page) -> str:
    if NEXT_PUBLISHED:
        return ''
    return ('<aside class="release-note" aria-label="Firmware availability">\n'
            f'  <strong>Firmware v{NEXT_VERSION} is in preparation.</strong>\n'
            f'  The available download remains <a href="{REPO_URL}/releases/tag/{STABLE_TAG}">Mattboxx 1.13</a>.\n'
            f'  <a href="{page.rel("downloads/")}#availability">Check which features are available today</a>.\n'
            '</aside>')


def jsonld(data) -> str:
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace('</', '<\\/') + '</script>'


def render(page: Page, pages: list[Page]) -> str:
    canonical = SITE_URL + page.slug
    full_title = page.meta.get('search_title') or (NAME if not page.slug else f'{page.title} — {NAME}')
    nav_pages = sorted([p for p in pages if p.nav], key=lambda p: p.order)
    nav = ''.join(
        f'<li><a href="{page.rel(p.slug)}"{" aria-current=\"page\"" if p is page else ""}>{html.escape(p.nav)}</a></li>'
        for p in nav_pages)
    body = page.body.replace('{{root}}', page.rel('')).replace('{{repo}}', REPO_URL)
    body = (body.replace('{{next_version}}', NEXT_VERSION).replace('{{stable_tag}}', STABLE_TAG)
                .replace('{{stable_version}}', STABLE_VERSION).replace('{{future_repo}}', FUTURE_REPO_URL))
    if '{{flasher}}' in body:
        body = body.replace('{{flasher}}', flasher_html(page))
    # <!-- if:v2 -->...<!-- endif --> shows once v2.0.0 is published,
    # <!-- if:stable -->...<!-- endif --> only while 1.13 is the stable download.
    keep, drop = ('v2', 'stable') if NEXT_PUBLISHED else ('stable', 'v2')
    body = re.sub(r'<!-- if:%s -->.*?<!-- endif -->' % drop, '', body, flags=re.S)
    body = re.sub(r'<!-- (?:if:%s|endif) -->' % keep, '', body)
    if '{{changelog}}' in body:
        body = body.replace('{{changelog}}', changelog_html())
    crumbs, sidebar, structured = '', '', []
    if page.slug:
        crumbs = (f'<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="{page.rel("")}">Home</a></li>'
                  f'<li aria-current="page">{html.escape(page.title)}</li></ol></nav>')
        structured.append({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE_URL},
            {'@type': 'ListItem', 'position': 2, 'name': page.title, 'item': canonical}]})
    if page.group:
        groups: dict[str, list[Page]] = {}
        for p in sorted(pages, key=lambda p: p.order):
            if p.group:
                groups.setdefault(p.group, []).append(p)
        sidebar = '<aside class="sidebar" aria-label="Documentation"><nav>' + ''.join(
            f'<p class="side-h">{html.escape(g)}</p><ul>' + ''.join(
                f'<li><a href="{page.rel(p.slug)}"{" aria-current=\"page\"" if p is page else ""}>{html.escape(p.title)}</a></li>'
                for p in ps) + '</ul>' for g, ps in groups.items()) + '</nav></aside>'
    if page.schema == 'home':
        structured.append({'@context': 'https://schema.org', '@type': 'SoftwareApplication', 'name': f'{NAME} — Mattboxx Edition',
                           'applicationCategory': 'NetworkingApplication', 'operatingSystem': 'ESP32-S3 firmware (ESP-IDF)',
                           'description': DESCRIPTION, 'url': SITE_URL, 'license': 'https://opensource.org/licenses/MIT',
                           'codeRepository': REPO_URL, 'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'}})
        structured.append({'@context': 'https://schema.org', '@type': 'WebSite', 'name': NAME, 'url': SITE_URL})
    if page.meta.get('image'):
        structured.append({'@context': 'https://schema.org', '@type': 'WebPage',
                           'name': page.title, 'url': canonical,
                           'primaryImageOfPage': SITE_URL + page.meta['image']})
    if page.schema == 'faq':
        qa = re.findall(r'<details[^>]*>\s*<summary>(.*?)</summary>(.*?)</details>', body, re.S)
        structured.append({'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': re.sub('<[^>]+>', '', q).strip(),
             'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', a)).strip()}}
            for q, a in qa]})
    layout = 'with-sidebar' if sidebar else 'plain'
    image = SITE_URL + 'assets/social-preview.png'
    return f'''<!doctype html>
<html lang="{page.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(page.description)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#0A0F0C">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(page.description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta property="og:image:alt" content="{NAME} — {TAGLINE}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{page.rel('assets/favicon.svg')}" type="image/svg+xml">
<link rel="icon" href="{page.rel('assets/favicon-32.png')}" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{page.rel('assets/apple-touch-icon.png')}">
<link rel="manifest" href="{page.rel('site.webmanifest')}">
<link rel="stylesheet" href="{page.rel('assets/site.css')}">
<script src="{page.rel('assets/theme.js')}"></script>
{''.join(jsonld(s) for s in structured)}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top">
  <div class="top-inner">
    <a class="brand" href="{page.rel('')}" aria-label="{NAME} home"><img src="{page.rel('assets/logo-mark.svg')}" alt="" width="32" height="32"><span>Tailnet Gateway</span></a>
    <nav id="site-nav" class="site-nav" aria-label="Main"><ul>{nav}</ul></nav>
    <div class="tools">
      <button class="search-open icon" type="button" aria-haspopup="dialog" aria-label="Search" title="Search (/)"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg></button>
      <button class="theme icon" type="button" aria-label="Toggle colour theme" title="Theme"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" class="fill"/></svg></button>
      <a class="gh" href="{REPO_URL}">GitHub</a>
      <button class="menu icon" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="Menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>
    </div>
  </div>
</header>
<div class="search-panel" role="dialog" aria-modal="true" aria-label="Search the site" hidden>
  <label for="search-input">Search</label>
  <input id="search-input" type="search" placeholder="e.g. Headscale, Wake-on-LAN, UDP" autocomplete="off">
  <ul id="search-results" aria-live="polite"></ul>
  <button class="search-close" type="button">Close</button>
</div>
<div class="layout {layout}">
{sidebar}
<main id="main" tabindex="-1">
{crumbs}
{release_note(page)}
{body}
</main>
</div>
<footer class="foot">
  <div class="foot-inner">
    <p><strong>{NAME} — Mattboxx Edition.</strong> {TAGLINE}</p>
    <p>Community firmware based on Csontikka's esp32-tailscale-subnet-router and microlink. Not an official Tailscale client; not affiliated with Tailscale Inc., the Headscale project or Espressif. Tailscale, Headscale, WireGuard and ESP32 are trademarks of their respective owners.</p>
    <p><a href="{REPO_URL}">Source</a> · <a href="{page.rel('security/')}">Security</a> · <a href="{page.rel('about/')}">About and credits</a> · MIT licence · No analytics or tracking.</p>
  </div>
</footer>
<script src="{page.rel('search-index.js')}" defer></script>
<script src="{page.rel('assets/site.js')}" defer></script>
</body>
</html>
'''


def redirect_page(target: str, depth: int) -> str:
    rel = '../' * depth + target
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Moved — {NAME}</title>'
            f'<link rel="canonical" href="{SITE_URL}{target}"><meta name="robots" content="noindex">'
            f'<meta http-equiv="refresh" content="0; url={rel}"></head>'
            f'<body><p>This page moved to <a href="{rel}">{SITE_URL}{target}</a>.</p></body></html>\n')


def text_of(fragment: str) -> str:
    fragment = re.sub(r'<(script|style|svg)\b.*?</\1>', ' ', fragment, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def build(out: Path) -> list[Page]:
    out = out.resolve()
    build_root = (ROOT / 'build').resolve()
    if out != (ROOT / '_site').resolve() and not (out.is_relative_to(build_root) and out != build_root):
        raise ValueError('Output must be _site or a subdirectory of build; refusing source/broad-directory removal')
    pages = [Page(p) for p in sorted((SRC / 'pages').glob('*.html'))]
    slugs = [p.slug for p in pages]
    assert len(slugs) == len(set(slugs)), 'duplicate slug'
    if out.exists():
        shutil.rmtree(out)
    (out / 'assets').mkdir(parents=True)
    for f in (SRC / 'assets').iterdir():
        if f.is_dir():
            shutil.copytree(f, out / 'assets' / f.name)
        else:
            shutil.copy2(f, out / 'assets' / f.name)
    verify_firmware(out)
    brand = ROOT / 'assets/brand'
    shutil.copy2(brand / 'logo-mark.svg', out / 'assets/logo-mark.svg')
    shutil.copy2(brand / 'logo-mark.svg', out / 'assets/favicon.svg')
    for name in ('favicon-32.png', 'apple-touch-icon.png', 'icon-192.png', 'avatar-512.png', 'social-preview.png'):
        shutil.copy2(brand / 'png' / name, out / 'assets' / name)
    shutil.copytree(ROOT / 'assets/diagrams', out / 'assets/diagrams')
    shutil.copy2(ROOT / 'docs/images/login-1.14-dev6.png', out / 'assets/login-1.14-dev6.png')
    shutil.copy2(ROOT / 'docs/images/status_v3.png', out / 'assets/status-stable.png')
    for page in pages:
        target = out / page.slug / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(page, pages), encoding='utf-8')
    not_found = Page.__new__(Page)
    not_found.meta = {}
    not_found.slug, not_found.title = '404/', 'Page not found'
    not_found.description = 'The requested page does not exist.'
    not_found.nav = not_found.group = not_found.schema = ''
    not_found.order, not_found.lang = 99, 'en'
    not_found.body = ('<h1>Page not found</h1><p>The page you asked for does not exist or has moved.</p>'
                      '<p><a href="{{root}}">Go to the home page</a> or use Search.</p>')
    # GitHub Pages serves /404.html for any missing path, so links must be absolute.
    html404 = render(not_found, pages).replace('href="../', f'href="{SITE_URL}').replace('src="../', f'src="{SITE_URL}')
    html404 = html404.replace('<meta name="robots" content="index, follow, max-image-preview:large">',
                              '<meta name="robots" content="noindex">')
    (out / '404.html').write_text(html404, encoding='utf-8')
    for old, new in REDIRECTS.items():
        assert new in slugs, new
        (out / old).mkdir(parents=True, exist_ok=True)
        (out / old / 'index.html').write_text(redirect_page(new, old.count('/')), encoding='utf-8')
    index = [{'t': p.title, 'u': p.slug, 'd': p.description, 'x': text_of(p.body)[:1600]} for p in pages]
    (out / 'search-index.js').write_text('window.SEARCH_INDEX=' + json.dumps(index, ensure_ascii=False) + ';\n', encoding='utf-8')
    # A deployment is not an edit to every page. Omit optional lastmod rather
    # than claiming that every document changed on each rebuild.
    def sitemap_entry(page: Page) -> str:
        sources = set(re.findall(r'<img\b[^>]*\bsrc="\{\{root\}\}([^"]+)"', page.body))
        images = ''.join('<image:image><image:loc>' + html.escape(SITE_URL + src) +
                         '</image:loc></image:image>' for src in sorted(sources))
        return f'  <url><loc>{SITE_URL}{page.slug}</loc>{images}</url>\n'
    (out / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' +
        ''.join(sitemap_entry(p) for p in pages) +
        '</urlset>\n', encoding='utf-8')
    (out / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n', encoding='utf-8')
    (out / 'site.webmanifest').write_text(json.dumps({
        'name': f'{NAME} — Mattboxx Edition', 'short_name': 'Tailnet Gateway', 'start_url': './', 'display': 'browser',
        'background_color': '#0A0F0C', 'theme_color': '#0A0F0C',
        'icons': [{'src': 'assets/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
                  {'src': 'assets/avatar-512.png', 'sizes': '512x512', 'type': 'image/png'}]}, indent=1), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    extra = SRC / 'root'   # verification files etc., copied verbatim
    if extra.is_dir():
        for f in extra.iterdir():
            if f.is_file():
                shutil.copy2(f, out / f.name)
    return pages


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.images, self.headings, self.ids, self.h1 = [], [], [], set(), 0
        self.title = self.desc = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'a' and 'href' in a:
            self.links.append(a['href'])
        if tag in ('link', 'script') and (a.get('href') or a.get('src')) and a.get('rel') not in ('canonical',):
            self.links.append(a.get('href') or a.get('src'))
        if tag == 'img':
            self.images.append(a)
            self.links.append(a.get('src', ''))
        if re.fullmatch(r'h[1-6]', tag):
            self.headings.append(int(tag[1]))
            self.h1 += tag == 'h1'
        if tag == 'title':
            self._in_title = True
        if tag == 'meta' and a.get('name') == 'description':
            self.desc = a.get('content')

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or '') + data

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False


def check(out: Path, pages: list[Page]) -> list[str]:
    problems, titles, descs = [], {}, {}
    for page in pages:
        file = out / page.slug / 'index.html'
        audit = Audit(); audit.feed(file.read_text(encoding='utf-8'))
        where = page.slug or 'home'
        if audit.h1 != 1:
            problems.append(f'{where}: expected exactly one h1, found {audit.h1}')
        levels = [h for h in audit.headings]
        for prev, cur in zip(levels, levels[1:]):
            if cur > prev + 1:
                problems.append(f'{where}: heading jumps h{prev} -> h{cur}'); break
        if not (30 <= len(page.description) <= 170):
            problems.append(f'{where}: description length {len(page.description)} outside 30-170')
        titles.setdefault(audit.title, []).append(where); descs.setdefault(audit.desc, []).append(where)
        for img in audit.images:
            if 'alt' not in img:
                problems.append(f'{where}: image without alt: {img.get("src")}')
        for link in audit.links:
            if not link or link.startswith(('http://', 'https://', 'mailto:', '#', 'data:')):
                continue
            path, _, frag = link.partition('#')
            target = (file.parent / path).resolve()
            if target.is_dir():
                target = target / 'index.html'
            if not target.exists():
                problems.append(f'{where}: broken link {link}')
        for link in audit.links:
            if link.startswith(REPO_URL + '/blob/Main/'):
                rel = link[len(REPO_URL + '/blob/Main/'):].split('#')[0]
                if not (ROOT / rel).exists():
                    problems.append(f'{where}: repository link to missing file {rel}')
    problems += [f'duplicate title {t!r}: {w}' for t, w in titles.items() if len(w) > 1]
    problems += [f'duplicate description: {w}' for d, w in descs.items() if len(w) > 1]
    sitemap = (out / 'sitemap.xml').read_text(encoding='utf-8')
    problems += [f'sitemap misses {p.slug}' for p in pages if f'<loc>{SITE_URL}{p.slug}</loc>' not in sitemap]
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/site')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    pages = build(out)
    print(f'built {len(pages)} pages + 404, {len(REDIRECTS)} redirects -> {out}')
    if args.check:
        problems = check(out, pages)
        for p in problems:
            print('FAIL', p)
        if problems:
            return 1
        print('PASS: links, single h1, heading order, unique titles/descriptions, image alt, sitemap')
    return 0


if __name__ == '__main__':
    sys.exit(main())
