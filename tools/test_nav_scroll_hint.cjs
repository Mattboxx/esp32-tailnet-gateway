/* Top bar and sub-section bars that do not fit show that more sections exist
 * (3.0.14). Actual SPA, Chromium:
 * - at 1100 px wide the top bar overflows: a right arrow and fade appear, no
 *   left arrow; the arrow scrolls the row; at the end the right arrow goes and
 *   the left one appears;
 * - opening a page whose tab is out of view scrolls it into view;
 * - at 1600 px everything fits: no arrow, no fade;
 * - at 800 px (menu drawer) no arrow is shown. */
const assert = require('node:assert/strict');
const { chromium, webkit } = require('playwright');
const { install } = require('./ui_fixture.cjs');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();

async function checkDrawer(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 620 }, isMobile: true, hasTouch: true, locale: 'en-US' });
  try {
    const page = await context.newPage();
    await install(page);
    await page.goto('http://esp32.test/#automation/notifications');
    await page.locator('#page-automation.active .subpage[data-sub="notifications"]:not([hidden])').waitFor();
    const button = page.locator('#navHamBtn');
    const position = await button.boundingBox();
    const toggle = () => page.touchscreen.tap(position.x + position.width / 2, position.y + position.height / 2);
    const bottom = await page.evaluate(() => {
      window.scrollTo(0, document.scrollingElement.scrollHeight);
      return window.scrollY;
    });
    assert.ok(bottom > 150, 'fixture must exercise a scrolled page');
    await toggle();
    const drawer = page.locator('#navTabs.open');
    await drawer.waitFor();
    const navTop = await button.evaluate(el => el.closest('.nav').getBoundingClientRect().top);
    assert.ok(Math.abs(navTop) < 2, 'opening the drawer must keep the sticky toolbar on screen');
    assert.ok(Math.abs((await drawer.boundingBox()).y - 48) < 2, 'drawer starts below the toolbar');
    assert.equal(await page.evaluate(() => window.scrollY), bottom, 'opening preserves the page position');
    await page.evaluate(() => window.openSettingsSearch());
    await page.locator('#search-input').press('Escape');
    assert.ok(await drawer.isVisible(), 'closing search leaves the drawer open');
    assert.ok(await page.evaluate(() => document.documentElement.classList.contains('scroll-locked')));
    await toggle();
    assert.equal(await button.getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => window.scrollY), bottom, 'closing returns to the same page position');

    await toggle();
    await drawer.locator('[data-page="network"]').tap();
    await page.locator('#page-network.active').waitFor();
    assert.equal(await page.evaluate(() => window.scrollY), 0, 'a different page opens at its top');
    assert.equal(await button.getAttribute('aria-expanded'), 'false');

    await page.setViewportSize({ width: 390, height: 330 });
    await toggle();
    await drawer.evaluate(el => { el.scrollTop = el.scrollHeight; });
    assert.ok(await drawer.evaluate(el => el.scrollTop > 0), 'short viewports can scroll the menu itself');
    assert.equal(await page.evaluate(() => window.scrollY), 0);
    await page.setViewportSize({ width: 1200, height: 620 });
    await page.waitForFunction(() => !document.documentElement.classList.contains('scroll-locked'));
    assert.equal(await page.locator('.nav > #navTabs').count(), 1, 'desktop tabs return to the toolbar');
    assert.equal(await button.getAttribute('aria-expanded'), 'false');
    await page.evaluate(() => { location.hash = '#system/about'; });
    const about = page.locator('#page-system.active .subpage[data-sub="about"]:not([hidden])');
    await about.waitFor();
    assert.deepEqual(await about.locator('a[href$="/microlink"], a[href$="/esp32-tailscale-subnet-router"]').evaluateAll(links => links.map(link => link.getAttribute('href'))), [
      'https://github.com/Mattboxx/microlink',
      'https://github.com/Csontikka/esp32-tailscale-subnet-router',
      'https://github.com/CamM2325/microlink'
    ]);
    assert.equal(await about.locator('#about-base, #about-microlink').count(), 0);
  } finally {
    await context.close();
  }
}

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
    await checkDrawer(browser);
    console.log('PASS: overflowing tab rows show arrows and fades, scroll on click, reveal the active tab; none when everything fits or in the drawer');
  } finally {
    await browser.close();
  }
  if (process.env.TEST_MOBILE_WEBKIT === '1') {
    const safari = await webkit.launch();
    try { await checkDrawer(safari); } finally { await safari.close(); }
  }
  console.log('PASS: mobile drawer preserves the page position, switches at the top and resets on desktop resize');
})().catch(e => { console.error(e); process.exit(1); });
