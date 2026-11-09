/* Settings search (3.0.14). Actual SPA with ui_fixture.cjs data, Chromium:
 * - nothing is built at page load (no palette, no index) until it opens;
 * - opens with the magnifier, Ctrl+K and "/" (not while typing in a field);
 * - finds a card by title (MagicDNS) and Enter opens its page and section
 *   and highlights it; finds options with a typo (pasword), in Italian
 *   (aggiornamento) and with accents (wí-fi); the first field of the result
 *   gets the focus;
 * - arrow keys move the selection (wrapping); Esc closes and returns focus;
 * - unknown words show the empty message and no result;
 * - hidden cards are not offered;
 * - in simple mode an advanced option is tagged and opening it switches to
 *   advanced mode;
 * - in Chinese, German and Italian it finds options in that language;
 * - no script errors; the phone layout keeps the palette inside the screen. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { install } = require('./ui_fixture.cjs');

async function open(browser, opts = {}) {
  const width = opts.width || 1280;
  const context = await browser.newContext({ viewport: { width, height: 860 }, locale: 'en-US', hasTouch: width < 768, isMobile: width < 768 });
  await context.addInitScript(o => { try { localStorage.setItem('ui-advanced', o.a ? '1' : '0'); if (o.l) localStorage.setItem('ui-lang', o.l); } catch (e) {} },
    { a: opts.advanced !== false, l: opts.lang || '' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await install(page, {});
  await page.goto('http://esp32.test/#status');
  await page.waitForTimeout(800);
  return { context, page, errors };
}
const results = page => page.$$eval('.search-item', els => els.map(e => ({ title: e.querySelector('.search-title').firstChild.textContent,
  path: e.querySelector('.search-path').textContent, adv: !!e.querySelector('.search-tag') })));
async function type(page, text) { await page.fill('#search-input', text); await page.waitForTimeout(60); return results(page); }

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    {
      const f = await open(browser);
      assert.equal(await f.page.evaluate(() => !!document.querySelector('.search-pal') || window.s_search_items !== undefined), false, 'nothing built at load');
      await f.page.click('#searchBtn');
      assert.equal(await f.page.evaluate(() => document.activeElement.id), 'search-input');
      assert.ok(await f.page.evaluate(() => window.s_search_items > 100), 'index built on open');
      assert.match(await f.page.textContent('.search-empty'), /Type a setting/);

      let r = await type(f.page, 'magicdns');
      assert.equal(r[0].title, 'Tailnet names (MagicDNS)', JSON.stringify(r.slice(0, 3)));
      assert.match(r[0].path, /^Tailscale › /);
      await f.page.keyboard.press('Enter');
      await f.page.waitForTimeout(400);
      assert.equal(await f.page.evaluate(() => location.hash), '#tailscale/options');
      assert.ok(await f.page.evaluate(() => document.getElementById('tsn-card').classList.contains('search-hit')));
      assert.ok(await f.page.isHidden('.search-pal'));
      assert.equal(await f.page.evaluate(() => document.activeElement.id), 'tsn-enabled', 'first field of the result focused');

      await f.page.keyboard.press('Control+k');
      r = await type(f.page, 'pasword');
      assert.ok(r.length && r.some(x => /password/i.test(x.title)), 'typo: ' + JSON.stringify(r.slice(0, 3)));
      r = await type(f.page, 'aggiornamento');
      assert.ok(r.some(x => /update|firmware/i.test(x.title + ' ' + x.path)), 'Italian synonym: ' + JSON.stringify(r.slice(0, 3)));
      r = await type(f.page, 'Wí-Fí');
      assert.ok(r.some(x => /wi-?fi/i.test(x.title)), 'accents: ' + JSON.stringify(r.slice(0, 3)));
      r = await type(f.page, 'zzqqxx');
      assert.equal(r.length, 0);
      assert.match(await f.page.textContent('.search-empty'), /Nothing found/);
      r = await type(f.page, 'wake');
      assert.ok(r.length >= 2);
      await f.page.keyboard.press('ArrowDown');
      assert.equal(await f.page.$eval('.search-item.active', e => e.id), 'search-opt-1');
      await f.page.keyboard.press('ArrowUp'); await f.page.keyboard.press('ArrowUp');
      assert.equal(await f.page.$eval('.search-item.active', e => e.id), 'search-opt-' + (r.length - 1), 'wraps around');
      await f.page.keyboard.press('Escape');
      assert.ok(await f.page.isHidden('.search-pal'));
      assert.equal(await f.page.evaluate(() => document.activeElement.id), 'tsn-enabled', 'Esc returns focus to the opener');

      /* "/" opens, but not while typing in a field. */
      await f.page.keyboard.press('/');
      assert.ok(await f.page.isVisible('.search-pal'));
      await f.page.keyboard.press('Escape');
      await f.page.evaluate(() => { const i = document.createElement('input'); i.id = 'probe'; document.body.appendChild(i); i.focus(); });
      await f.page.keyboard.press('/');
      assert.ok(await f.page.isHidden('.search-pal'), '"/" typed into a field');
      assert.equal(await f.page.inputValue('#probe'), '/');

      /* Hidden cards are not offered. */
      await f.page.evaluate(() => { document.getElementById('trend-card').hidden = true; });
      await f.page.click('#searchBtn');
      r = await type(f.page, 'turn on trends');
      assert.ok(!r.some(x => x.title === 'Turn on trends'), JSON.stringify(r));
      await f.page.keyboard.press('Escape');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }
    {
      /* Simple mode: advanced options are tagged; opening one shows advanced settings. */
      const f = await open(browser, { advanced: false });
      await f.page.click('#searchBtn');
      const r = await type(f.page, 'ethernet uplink');
      const i = r.findIndex(x => /Ethernet uplink/.test(x.title));
      assert.ok(i >= 0 && r[i].adv, JSON.stringify(r));
      await f.page.click('#search-opt-' + i);
      await f.page.waitForTimeout(400);
      assert.equal(await f.page.evaluate(() => document.body.classList.contains('ui-simple')), false, 'advanced shown');
      assert.match(await f.page.evaluate(() => location.hash), /^#network/);
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }
    {
      /* Phone: the palette fits the screen, the input does not trigger zoom. */
      const f = await open(browser, { width: 375 });
      await f.page.click('#searchBtn');
      await type(f.page, 'password');
      const box = await f.page.$eval('.search-box', e => { const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, vw: innerWidth }; });
      assert.ok(box.l >= 0 && box.r <= box.vw, JSON.stringify(box));
      assert.equal(await f.page.$eval('#search-input', e => getComputedStyle(e).fontSize), '16px');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }
    for (const [lang, word, expect] of [['zh', '密码', /密码/], ['de', 'Passwort', /Passwort/i], ['it', 'aggiornamento', /aggiorn|firmware/i]]) {
      /* Translated interface: the search reads the page in that language;
       * Chinese words need no spaces. */
      const f = await open(browser, { lang });
      await f.page.waitForFunction(l => document.documentElement.lang.startsWith(l), lang);
      await f.page.click('#searchBtn');
      const r = await type(f.page, word);
      assert.ok(r.some(x => expect.test(x.title + ' ' + x.path)), lang + ': ' + JSON.stringify(r.slice(0, 3)));
      assert.notEqual(await f.page.getAttribute('#search-input', 'placeholder'), 'Search settings', lang + ' placeholder translated');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }
    console.log('settings search: OK');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
