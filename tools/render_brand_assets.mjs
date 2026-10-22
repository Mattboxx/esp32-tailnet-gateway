// Render the editable SVG brand sources in assets/brand to the PNG exports
// used by GitHub (README banner, social preview, avatar) and the website.
// Usage: node tools/render_brand_assets.mjs   (needs the playwright package)
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const brand = join(root, 'assets/brand');
const out = join(brand, 'png');
mkdirSync(out, { recursive: true });

// [source svg, output png, width, height, padding fraction, background]
const jobs = [
  ['banner.svg', 'banner.png', 1280, 400, 0, null],
  ['social-preview.svg', 'social-preview.png', 1280, 640, 0, null],
  ['logo-mark.svg', 'avatar-512.png', 512, 512, 0, null],
  ['logo-mark.svg', 'icon-192.png', 192, 192, 0, null],
  ['logo-mark.svg', 'apple-touch-icon.png', 180, 180, 0, null],
  ['logo-mark.svg', 'favicon-32.png', 32, 32, 0, null],
  ['logo-horizontal-dark.svg', 'logo-horizontal-dark.png', 1120, 192, 0, '#0D1117'],
  ['logo-horizontal-light.svg', 'logo-horizontal-light.png', 1120, 192, 0, '#FFFFFF'],
  ['logo-compact.svg', 'logo-compact-400.png', 400, 400, 0, null],
];

const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
try {
  for (const [src, dst, width, height, , background] of jobs) {
    const svg = readFileSync(join(brand, src), 'utf8');
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const bg = background ? `background:${background};` : 'background:transparent;';
    await page.setContent(`<!doctype html><html><body style="margin:0;${bg}">` +
      `<div style="width:${width}px;height:${height}px">${svg.replace('<svg ', `<svg width="${width}" height="${height}" `)}</div></body></html>`);
    await page.screenshot({ path: join(out, dst), omitBackground: !background, clip: { x: 0, y: 0, width, height } });
    await page.close();
    console.log('rendered', dst);
  }
} finally {
  await browser.close();
}
