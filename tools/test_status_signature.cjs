/* Status page signature (3.0.14). Actual SPA with ui_fixture.cjs data, Chromium:
 * - wide screens: the summary is one signal line; the travelling light runs
 *   only while uplink and tailnet are both up, never with the tailnet down;
 * - the Client WiFi node appears only while the access point runs, with SSID
 *   and client count, and the grid gains a fifth column; on a phone it stays
 *   two columns with RAM spanning the last row;
 * - the header rate stays hidden after one reading and shows the averaged
 *   uplink rate after a second one; counters that go backwards are ignored;
 * - sparklines appear on the summary only while trends are on;
 * - a changed value gets a short highlight, the first fill does not;
 * - the top-bar chip counts the hidden sections;
 * - reduced motion stops every loop and hides the travelling light;
 * - state-coloured cards use the corner bar, not a left border. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { install, data } = require('./ui_fixture.cjs');

function status(mut) {
  const s = JSON.parse(JSON.stringify(data['/api/status']));
  if (mut) mut(s);
  return s;
}

async function open(browser, opts) {
  const context = await browser.newContext({ viewport: { width: opts.width || 1440, height: 900 }, locale: 'en-US',
    reducedMotion: opts.reduced ? 'reduce' : 'no-preference' });
  await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await install(page, opts.overrides || {});
  const live = { body: opts.status || status() };
  await page.route('http://esp32.test/api/status', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(live.body) }));
  await page.goto('http://esp32.test/#status');
  await page.waitForTimeout(900);
  return { context, page, errors, live };
}

async function refresh(page) {
  await page.click('#refreshBtn');
  await page.waitForTimeout(500);
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    /* Line, light, AP node, sparks, rate, tick. */
    {
      const f = await open(browser, { status: status(s => { s.ap.enabled = false; }) });
      const st = () => f.page.evaluate(() => {
        const g = document.getElementById('status-glance'), ap = document.getElementById('glance-ap');
        const flow = g.querySelector('.glance-flow');
        return { flowing: g.classList.contains('flowing'), flowShown: getComputedStyle(flow).display !== 'none',
                 line: getComputedStyle(g.querySelector('.glance-line')).display !== 'none',
                 hasAp: g.classList.contains('has-ap'), apHidden: ap.hidden, apText: ap.querySelector('strong').textContent,
                 cols: getComputedStyle(g).gridTemplateColumns.split(' ').length,
                 sparks: Array.from(g.querySelectorAll('.glance-spark')).map(x => x.parentElement.id).sort(),
                 rateHidden: document.getElementById('status-rate').hidden, rate: document.getElementById('status-rate').textContent,
                 runner: getComputedStyle(g.querySelector('.glance-runner')).animationName };
      });
      let s = await st();
      assert.equal(s.line, true, 'signal line shown on wide screens');
      assert.equal(s.flowing, true); assert.equal(s.flowShown, true); assert.equal(s.runner, 'orbTravel');
      assert.equal(s.hasAp, false); assert.equal(s.apHidden, true); assert.equal(s.cols, 4);
      assert.deepEqual(s.sparks, ['glance-memory', 'glance-peers', 'glance-uplink'], 'trends on: sparks on the summary');
      assert.equal(s.rateHidden, true, 'one reading: no rate yet');

      /* AP on + second reading with more bytes + tailnet down. */
      const prev = await f.page.evaluate(() => window.s_rate_prev);
      assert.ok(prev && typeof prev.i === 'number');
      f.live.body = status(x => {
        x.ap.enabled = true; x.ap.clients = 2;
        x.sta.bytes_in = prev.i + 1250000; x.sta.bytes_out = prev.o + 125000;
        x.tailscale.connected = false;
      });
      await f.page.evaluate(() => { window.s_rate_prev.t = Date.now() - 10000; });
      await refresh(f.page);
      s = await st();
      assert.equal(s.hasAp, true); assert.equal(s.apHidden, false); assert.equal(s.cols, 5);
      assert.equal(s.apText, 'Tailnet-Gateway · 2 clients');
      assert.equal(s.flowing, false, 'tailnet down: no travelling light'); assert.equal(s.flowShown, false);
      assert.equal(s.rateHidden, false);
      const m = s.rate.match(/^↓(\d+(?:\.\d)?) (kbit|Mbit)\/s↑(\d+(?:\.\d)?) kbit\/s$/);
      assert.ok(m, s.rate);
      const down = +m[1] * (m[2] === 'Mbit' ? 1000 : 1), up = +m[3];
      assert.ok(down > 800 && down <= 1000 && up > 80 && up <= 100, s.rate);  /* 10 Mbit and 1 Mbit over 10–12.5 s */
      const ticked = await f.page.evaluate(() => document.querySelector('#glance-tailnet strong').classList.contains('val-tick'));
      assert.equal(ticked, true, 'changed value is highlighted');

      /* Counters going backwards (restart) keep the shown rate, no negative value. */
      f.live.body = status(x => { x.sta.bytes_in = 10; x.sta.bytes_out = 10; });
      await f.page.evaluate(() => { window.s_rate_prev.t -= 10000; });
      await refresh(f.page);
      s = await st();
      assert.doesNotMatch(s.rate, /-/);

      /* Corner bar instead of a left stripe. */
      const card = await f.page.evaluate(() => {
        const c = document.getElementById('card-uplink'), b = getComputedStyle(c, '::before');
        return { left: getComputedStyle(c).borderLeftWidth, w: b.width, h: b.height };
      });
      assert.equal(card.left, '1px'); assert.equal(card.w, '56px'); assert.equal(card.h, '3px');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }

    /* Trends off: no sparks; first fill does not highlight. */
    {
      const f = await open(browser, { overrides: { '/api/history': { config: { events: true, metrics: false, snapshots: true }, points: [] } } });
      const r = await f.page.evaluate(() => ({ sparks: document.querySelectorAll('#status-glance .glance-spark').length,
        ticks: document.querySelectorAll('#page-status .val-tick').length }));
      assert.equal(r.sparks, 0, 'trends off: no sparks');
      assert.equal(r.ticks, 0, 'first fill is not highlighted');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }

    /* Phone: two columns, RAM spans the last row, no line. */
    {
      const f = await open(browser, { width: 390, status: status(s => { s.ap.enabled = true; }) });
      const r = await f.page.evaluate(() => {
        const g = document.getElementById('status-glance');
        return { cols: getComputedStyle(g).gridTemplateColumns.split(' ').length, line: getComputedStyle(g.querySelector('.glance-line')).display,
                 span: getComputedStyle(document.getElementById('glance-memory')).gridColumnStart };
      });
      assert.equal(r.cols, 2); assert.equal(r.line, 'none'); assert.equal(r.span, '1');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }

    /* Top bar chip counts hidden sections. */
    {
      const f = await open(browser, { width: 1100 });
      const r = await f.page.evaluate(() => {
        const row = document.getElementById('navTabs'), b = document.querySelector('.nav .scroll-more-right button');
        const box = row.getBoundingClientRect();
        const hidden = Array.from(row.children).filter(c => c.offsetParent !== null && c.getBoundingClientRect().right > box.right - 40).length;
        return { text: b.textContent, aria: b.getAttribute('aria-label'), hidden, hint: b.parentElement.classList.contains('hint') };
      });
      assert.ok(r.hidden > 0);
      assert.equal(r.text, '+' + r.hidden + ' ›');
      assert.equal(r.aria, r.hidden + ' more sections on the right');
      assert.equal(r.hint, true);
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }

    /* Reduced motion: loops stopped, light hidden. */
    {
      const f = await open(browser, { reduced: true });
      const r = await f.page.evaluate(() => ({
        flow: getComputedStyle(document.querySelector('#status-glance .glance-flow')).display,
        dot: getComputedStyle(document.querySelector('#overall-badge .badge-dot')).animationName,
        card: getComputedStyle(document.getElementById('card-uplink')).animationName }));
      assert.equal(r.flow, 'none'); assert.equal(r.dot, 'none'); assert.equal(r.card, 'none');
      assert.deepEqual(f.errors, []);
      await f.context.close();
    }
    console.log('status signature: OK');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
