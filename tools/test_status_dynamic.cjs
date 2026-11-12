/* Status page follows what is switched on (3.0.8): actual SPA, synthetic
 * /api/status and /api/capabilities, Chromium.
 * - live tiles only for features that are on, each with what it is doing;
 *   features that are off are listed once as "Available";
 * - suggestions come from the state, most urgent first, at most three:
 *   Tailnet down > weak Wi-Fi / MQTT down > tips; problems cannot be hidden,
 *   a hidden tip stays hidden after a reload;
 * - a healthy gateway with nothing set up gets one "put it to use" tip; a
 *   gateway with routes, notifications and monitoring gets none;
 * - goals already configured move to the end, marked "Configured";
 * - a tile whose state changes is highlighted on the next refresh;
 * - Italian labels. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();

const cap = (id, configured, active) => ({ id, compiled: true, hardware_supported: true, configured, active, experimental: false, verified: false, evidence: '' });
const IDS = ['lan-tailnet-forwarding', 'subnet-routing', 'exit-node', 'ap-gateway', 'dns-relay', 'tailnet-names', 'wol', 'event-history', 'trends',
  'settings-copies', 'health', 'service-watch', 'ntfy', 'telegram', 'email', 'mqtt', 'home-assistant', 'snmp'];
function caps(on) { return { schema: 2, features: IDS.map(id => on[id] ? cap(id, true, on[id] === 'down' ? false : on[id] === 'idle' ? null : true) : cap(id, false, id === 'ap-gateway' || id === 'dns-relay' ? false : null)) }; }
function status({ connected = true, rssi = -55, enabled = true } = {}) {
  return { version: '3.0.8', uptime_s: 100, mem_internal_free: 41000, mem_internal_total: 300000,
    sta: { connected: true, ssid: 'Home', rssi, ip: '192.168.1.2' }, ap: { enabled: false },
    tailscale: { enabled, connected, peers_online: connected ? 3 : 0, peers_total: 4, authority_ready: true, startup_error: connected ? '' : 'control-plane TCP connect failed' } };
}

async function open(browser, scene, opts = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: opts.lang ? 'it-IT' : 'en-US' });
  await context.addInitScript(([l, hidden]) => { try {
    if (l) localStorage.setItem('ui-lang', l);
    if (hidden) localStorage.setItem('st-tips-hidden', hidden);
  } catch (e) {} }, [opts.lang || '', opts.hidden || '']);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
    const json = b => route.fulfill({ contentType: 'application/json', body: JSON.stringify(b) });
    if (url.pathname === '/api/auth/status') return json({ password_set: true, auth_enabled: true, auth_required: true, authenticated: true, session_timeout_s: 0 });
    if (url.pathname === '/api/status') return json(scene.status);
    if (url.pathname === '/api/capabilities') return json(scene.caps);
    return json({});
  });
  await page.goto('http://esp32.test/#status');
  await page.waitForFunction(() => document.querySelector('#st-features a, #st-features p'));
  await page.waitForTimeout(300);
  return { page, context, errors };
}
const read = page => page.evaluate(() => ({
  tips: [...document.querySelectorAll('#st-next [data-tip]')].map(e => e.getAttribute('data-tip')),
  tipsText: document.getElementById('st-next').textContent, nextHidden: document.getElementById('st-next-card').hidden,
  tiles: [...document.querySelectorAll('#st-features a[data-feature]')].map(a => [a.getAttribute('data-feature'), a.className.trim(), a.querySelector('span').textContent]),
  avail: document.getElementById('st-available').textContent,
  goals: [...document.querySelectorAll('#goal-grid .goal-tile')].map(b => [b.querySelector('strong').textContent, b.classList.contains('done')]),
  count: document.getElementById('st-features-count').textContent }));

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    /* Problems first: Tailnet down, weak Wi-Fi, MQTT down; tips cut at three. */
    let s = { status: status({ connected: false, rssi: -80 }), caps: caps({ mqtt: 'down', wol: 'idle', 'subnet-routing': 1 }) };
    let { page, context, errors } = await open(browser, s);
    let r = await read(page);
    assert.deepEqual(errors, []);
    assert.deepEqual(r.tips, ['tailnet-down', 'weak-wifi', 'mqtt-down']);
    assert.match(r.tipsText, /control-plane TCP connect failed/);
    assert.match(r.tipsText, /Weak Wi-Fi signal \(-80 dBm\)/);
    assert.ok(!/Hide/.test(r.tipsText), 'problems cannot be hidden');
    assert.deepEqual(r.tiles.map(x => x[0]), ['subnet-routing', 'wol', 'mqtt']);
    assert.deepEqual(r.tiles[2], ['mqtt', 'warn', 'Not connected to the broker']);
    assert.match(r.tiles[0][2], /Waiting for the Tailnet/);
    assert.match(r.avail, /Available:.*Service Gateway.*Health Monitor/);
    assert.match(r.avail, /Gateway Wi-Fi/);   /* the access point is off: offered, its card hidden */
    assert.ok(!/DNS relay/.test(r.avail));
    assert.equal(await page.evaluate(() => document.getElementById('card-ap').hidden), true);
    assert.equal(r.count, '3 of 17 on');   /* 17 known here: no DDNS in this build's manifest */
    const last = r.goals[r.goals.length - 1];
    assert.deepEqual(last, ['Wake or recover a NAS or PC', true]);
    assert.ok(r.goals.some(g => g[0] === 'Reach this network from anywhere' && g[1]));
    assert.ok(r.goals.findIndex(g => g[1]) > r.goals.findIndex(g => g[0] === 'Connect a LAN device to a Tailnet service'));
    /* MQTT comes back: the tile changes and flashes; the MQTT problem disappears. */
    s.caps = caps({ mqtt: 1, wol: 'idle', 'subnet-routing': 1 }); s.status = status({ connected: true });
    await page.evaluate(() => { fetchStatus(); });
    await page.waitForTimeout(200);
    await page.evaluate(() => statusExtras.refresh());
    await page.waitForFunction(() => document.querySelector('#st-features a[data-feature="mqtt"].changed'));
    r = await read(page);
    assert.deepEqual(r.tiles.find(x => x[0] === 'mqtt').slice(2), ['Connected to the broker']);
    assert.deepEqual(r.tips, ['watch-devices']);   /* WoL without monitoring; MQTT counts as a notifier */
    /* Hide the tip: gone, and still gone after a reload. */
    await page.locator('#st-next [data-tip="watch-devices"] [data-hide]').click();
    r = await read(page);
    assert.equal(r.nextHidden, true);
    const hidden = await page.evaluate(() => localStorage.getItem('st-tips-hidden'));
    await context.close();
    ({ page, context } = await open(browser, s, { hidden }));
    r = await read(page);
    assert.equal(r.nextHidden, true, 'hidden tip stays hidden');
    await context.close();

    /* Healthy, nothing set up: one tip to put the Tailnet to use. */
    ({ page, context } = await open(browser, { status: status(), caps: caps({}) }));
    r = await read(page);
    assert.deepEqual(r.tips, ['first-use']);
    assert.match(r.tipsText, /Choose a goal/);
    assert.equal(r.tiles.length, 0);
    await context.close();

    /* Well set up: no suggestions at all. */
    ({ page, context } = await open(browser, { status: status(), caps: caps({ 'subnet-routing': 1, wol: 'idle', health: 1, ntfy: 1, 'event-history': 1 }) }));
    r = await read(page);
    assert.equal(r.nextHidden, true);
    assert.deepEqual(r.tips, []);
    await context.close();

    /* Italian. */
    ({ page, context } = await open(browser, { status: status({ connected: false }), caps: caps({ mqtt: 'down' }) }, { lang: 'it' }));
    r = await read(page);
    assert.match(r.tipsText, /Il Tailnet non è connesso/);
    assert.match(r.tipsText, /Broker MQTT non raggiungibile/);
    assert.equal(r.tiles[0][2], 'Non connesso al broker');
    assert.match(r.avail, /Disponibili:/);
    await context.close();
    s = { status: status(), caps: caps({ 'ap-gateway': 1 }) };
    s.status.sta = { connected: false };
    s.status.lan_connected = true;
    s.status.uplink = { type: 'ethernet', connected: true, ip: '192.0.2.10', prefix: 24, bytes_in: 1000, bytes_out: 2000 };
    ({ page, context, errors } = await open(browser, s));
    assert.equal(await page.locator('#uplink-ssid').textContent(), 'Ethernet');
    assert.equal(await page.locator('#uplink-ip').textContent(), '192.0.2.10/24');
    assert.equal(await page.locator('#uplink-status-badge').textContent(), 'Connected');
    assert.equal(await page.locator('#uplink-channel').isVisible(), false);
    const result = await page.evaluate(async () => {
      const sim = { sta: { connected: false }, ap: { enabled: true }, lan_connected: false, local_connected: true,
        uplink: { type: 'cellular', connected: true, ip: '198.51.100.10', rssi: -85 } };
      applyStatus(sim);
      const fetch = window.wzStatus;
      window.wzStatus = async () => sim;
      try {
        return { internet: await WZ_UPLINK.fn(), lan: await WZ_LAN.fn(), local: await WZ_LOCAL.fn() };
      } finally { window.wzStatus = fetch; }
    });
    assert.deepEqual(result, { internet: true, lan: 'Connect a local Ethernet or WiFi LAN first', local: true });
    assert.equal(await page.locator('#uplink-ssid').textContent(), 'Cellular');
    assert.equal(await page.locator('#uplink-rssi').textContent(), '-85 dBm');
    assert.deepEqual(errors, []);
    await context.close();
    console.log('PASS: Status follows what is on: live tiles, available list, state-based suggestions (order, cap, ' +
                'no-hide for problems, persistent hide), configured goals last, change highlight, Italian');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
