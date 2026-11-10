/* Top bar and sub-section bars that do not fit show that more sections exist
 * (3.0.14). Actual SPA, Chromium:
 * - at 1100 px wide the top bar overflows: a right arrow and fade appear, no
 *   left arrow; the arrow scrolls the row; at the end the right arrow goes and
 *   the left one appears;
 * - opening a page whose tab is out of view scrolls it into view;
 * - at 1600 px everything fits: no arrow, no fade;
 * - at 800 px (menu drawer) no arrow is shown. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();

async function open(browser, width) {
  const context = await browser.newContext({ viewport: { width, height: 800 }, locale: 'en-US' });
  await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
    if (url.pathname === '/api/auth/status')
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ password_set: true, auth_enabled: true, auth_required: true, authenticated: true }) });
    return route.fulfill({ contentType: 'application/json', body: '{}' });
  });
  await page.goto('http://esp32.test/#status');
  await page.waitForTimeout(400);
  const state = () => page.evaluate(() => {
    const row = document.getElementById('navTabs');
    const l = document.querySelector('.nav .scroll-more-left'), r = document.querySelector('.nav .scroll-more-right');
    return { overflow: row.scrollWidth > row.clientWidth, left: !!(l && l.classList.contains('show')), right: !!(r && r.classList.contains('show')),
             fadeR: row.classList.contains('more-right'), scroll: row.scrollLeft, max: row.scrollWidth - row.clientWidth };
  });
  return { context, page, errors, state };
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    let { context, page, errors, state } = await open(browser, 1100);
    let s = await state();
    if (s.overflow) {
      assert.ok(s.right && s.fadeR && !s.left, 'right arrow and fade, no left arrow at the start');
      await page.click('.nav .scroll-more-right button');
      await page.waitForTimeout(700);
      s = await state();
      assert.ok(s.scroll > 0 && s.left, 'the arrow scrolls and the left arrow appears');
      await page.evaluate(() => { const r = document.getElementById('navTabs'); r.scrollLeft = r.scrollWidth; });
      await page.waitForTimeout(200);
      s = await state();
      assert.ok(!s.right && s.left, 'at the end only the left arrow remains');
      await page.evaluate(() => { document.getElementById('navTabs').scrollLeft = 0; location.hash = '#tools'; });
      await page.waitForTimeout(500);
      const visible = await page.evaluate(() => {
        const row = document.getElementById('navTabs'), a = row.querySelector('[data-page="tools"]');
        const r = a.getBoundingClientRect(), b = row.getBoundingClientRect();
        return r.left >= b.left - 1 && r.right <= b.right + 1;
      });
      assert.ok(visible, 'the active tab is scrolled into view');
    }
    assert.deepEqual(errors, []);
    await context.close();

    ({ context, page, errors, state } = await open(browser, 1600));
    s = await state();
    if (!s.overflow) assert.ok(!s.left && !s.right && !s.fadeR, 'no arrow when everything fits');
    await context.close();

    ({ context, page, errors, state } = await open(browser, 800));
    s = await state();
    assert.ok(!s.left && !s.right, 'no arrow in the menu drawer');
    assert.deepEqual(errors, []);
    await context.close();
    console.log('PASS: overflowing tab rows show arrows and fades, scroll on click, reveal the active tab; none when everything fits or in the drawer');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
