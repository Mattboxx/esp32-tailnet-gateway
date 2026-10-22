/* Layout audit of the real embedded Web UI with synthetic data, at phone,
 * tablet and desktop widths. Fails on page-level horizontal scrolling,
 * controls clipped by the viewport, small touch targets on touch widths,
 * tiny text and script errors. Optional first argument: screenshot folder.
 * Run: NODE_PATH=<playwright> node tools/test_ui_layout.cjs [shots] */
const { chromium } = require('playwright');
const path = require('node:path');
const { install } = require('./ui_fixture.cjs');

const all = [[320, 640], [360, 740], [390, 844], [430, 932], [768, 1024], [1024, 768], [1440, 900], [1920, 1080], [844, 390]];
// Advanced mode shows every section; simple mode is checked at a phone and a desktop width.
const runs = all.map(v => [...v, 'advanced', 'en-US']).concat([[390, 844, 'simple', 'en-US'], [1440, 900, 'simple', 'en-US']])
  // Every shipped translation at a narrow phone and a desktop width (longest words, CJK rendering).
  .concat(['it-IT', 'es-ES', 'zh-CN'].flatMap(l => [[320, 640, 'advanced', l], [390, 844, 'simple', l], [1440, 900, 'advanced', l]]));
const tabs = ['status', 'network', 'tailscale', 'firewall', 'tools', 'operations', 'automation', 'system'];
const shots = process.argv[2];
const only = process.env.UI_TABS ? process.env.UI_TABS.split(',') : tabs;

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  const failures = [];
  try {
    for (const [width, height, mode, locale] of runs) {
      const touch = width < 768;
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch, isMobile: touch, locale });
      if (mode === 'advanced') await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await install(page);
      await page.goto('http://esp32.test/#status');
      await page.waitForTimeout(600);
      const lang = await page.evaluate(() => document.documentElement.lang);
      if (lang !== (locale === 'zh-CN' ? 'zh-Hans' : locale.slice(0, 2))) failures.push(`${locale}: page language ${lang}`);
      for (const tab of only) {
        await page.evaluate(t => { location.hash = t; }, tab);
        await page.waitForTimeout(450);
        const where = `${width}x${height} ${mode} ${locale} #${tab}`;
        const r = await page.evaluate(({ touch }) => {
          const vw = window.innerWidth, out = { overflow: document.documentElement.scrollWidth - vw, clipped: [], small: [], tiny: [] };
          const visible = el => { const s = getComputedStyle(el); const b = el.getBoundingClientRect();
            return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[hidden]'); };
          const page = document.querySelector('.page.active') || document.body;
          const scroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
            const s = getComputedStyle(p); if (/(auto|scroll)/.test(s.overflowX)) return true; } return false; };
          page.querySelectorAll('button, a.btn, input, select, textarea, .switch, label.toggle').forEach(el => {
            if (!visible(el) || scroller(el)) return;
            const b = el.getBoundingClientRect();
            const name = (el.id || el.getAttribute('aria-label') || el.textContent || el.name || el.tagName).trim().slice(0, 28);
            if (b.right > vw + 1 || b.left < -1) out.clipped.push(name + '@' + Math.round(b.right));
            if (touch && b.height < 36 && el.type !== 'checkbox' && el.type !== 'radio' && el.type !== 'hidden') out.small.push(name + ':' + Math.round(b.height));
          });
          page.querySelectorAll('p, li, td, label, .form-hint, button').forEach(el => {
            if (!visible(el) || !el.textContent.trim()) return;
            const f = parseFloat(getComputedStyle(el).fontSize); if (f < 11) out.tiny.push(el.textContent.trim().slice(0, 20) + ':' + f);
          });
          return out;
        }, { touch });
        if (r.overflow > 0) failures.push(`${where}: page scrolls horizontally by ${r.overflow}px`);
        if (r.clipped.length) failures.push(`${where}: clipped ${[...new Set(r.clipped)].slice(0, 6).join(', ')}`);
        if (r.small.length) failures.push(`${where}: touch targets <36px ${[...new Set(r.small)].slice(0, 6).join(', ')}`);
        if (r.tiny.length) failures.push(`${where}: text <11px ${[...new Set(r.tiny)].slice(0, 4).join(', ')}`);
        if (shots) await page.screenshot({ path: path.join(shots, `ui-${locale}-${mode}-${width}x${height}-${tab}.png`), fullPage: true });
      }
      if (errors.length) failures.push(`${width}x${height}: script errors ${[...new Set(errors)].slice(0, 3).join(' | ')}`);
      await context.close();
    }
  } finally { await browser.close(); }
  if (failures.length) { console.log(failures.join('\n')); console.log('FAIL ' + failures.length); process.exit(1); }
  console.log(`PASS: Web UI ${only.length} sections x ${runs.length} viewport/mode runs: no page overflow or clipped controls, touch targets, readable text, no script errors`);
})();
