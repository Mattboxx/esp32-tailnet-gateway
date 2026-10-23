"""Presentation-only crawlability, image sitemap and ownership-file checks.

No search-engine submission, device access or firmware build is performed.
Run after build_site.py --check. Actual indexing is observable only in the
owner's Search Console; a passing local check never means Google indexed it.
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import build_site


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.images = []
        self.schemas = []
        self._json = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('name') or attrs.get('property')] = attrs.get('content', '')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs['href']
        if tag == 'img':
            self.images.append(attrs)
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self._json = ''

    def handle_data(self, data):
        if self._json is not None:
            self._json += data

    def handle_endtag(self, tag):
        if tag == 'script' and self._json is not None:
            self.schemas.append(json.loads(self._json))
            self._json = None


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'build/site'
    pages = [build_site.Page(p) for p in sorted((root / 'website/pages').glob('*.html'))]
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9',
          'i': 'http://www.google.com/schemas/sitemap-image/1.1'}
    sitemap = ET.parse(out / 'sitemap.xml').getroot()
    entries = {entry.find('s:loc', ns).text: entry for entry in sitemap.findall('s:url', ns)}
    assert set(entries) == {build_site.SITE_URL + p.slug for p in pages}
    assert not sitemap.findall('.//s:lastmod', ns), 'Do not manufacture a lastmod from the deploy date'
    screenshot_count = 0
    for page in pages:
        parsed = Metadata()
        parsed.feed((out / page.slug / 'index.html').read_text(encoding='utf-8'))
        expected = build_site.SITE_URL + page.slug
        assert parsed.canonical == expected, page.slug
        assert parsed.meta['og:url'] == expected, page.slug
        assert 'noindex' not in parsed.meta['robots'], page.slug
        assert 'max-image-preview:large' in parsed.meta['robots'], page.slug
        assert parsed.schemas, page.slug
        if page.meta.get('search_title'):
            assert parsed.meta['og:title'] == page.meta['search_title']
        for image in entries[expected].findall('i:image/i:loc', ns):
            assert image.text.startswith(build_site.SITE_URL), image.text
            assert (out / image.text.removeprefix(build_site.SITE_URL)).is_file(), image.text
        for image in parsed.images:
            if 'screenshots/' not in image['src']:
                continue
            screenshot_count += 1
            assert image.get('alt') and int(image['width']) > 0 and int(image['height']) > 0
            # Chrome's screenshot API returns JPEG bytes: never serve them as PNG.
            target = (out / page.slug / image['src']).resolve()
            assert target.suffix == '.jpg' and target.read_bytes().startswith(b'\xff\xd8\xff')
            assert b'Exif\x00\x00' not in target.read_bytes(), 'Do not publish location/device EXIF'
    assert screenshot_count >= 4
    for file in (root / 'website/root').glob('google*.html'):
        expected = 'google-site-verification: ' + file.name
        assert (out / file.name).read_text(encoding='utf-8').strip() == expected
    assert (out / '404.html').read_text(encoding='utf-8').count('content="noindex"') == 1
    assert 'screenshots/' in (out / 'search-index.js').read_text(encoding='utf-8')
    assert 'mqtt-across-networks/' in (out / 'search-index.js').read_text(encoding='utf-8')
    print(f'PASS: {len(pages)} canonical/indexable pages, valid image sitemap, '
          f'{screenshot_count} real-UI image embeds, JSON-LD and Google verification file')


if __name__ == '__main__':
    main()
