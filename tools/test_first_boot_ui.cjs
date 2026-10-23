/* First-boot setup wizard in the real embedded Web UI against a mock gateway
 * that implements the setup API with Node's own X25519/AES-256-GCM: full
 * flow (BOOT-button pairing, password, scan, Wi-Fi test, tailnet, features,
 * finish), setup-code pairing with a wrong code, "another device is pairing",
 * no secret in any request body, and layout at phone/tablet/desktop widths in
 * every shipped browser language, wizard English-only (no page overflow, clipped controls, tiny targets or script
 * errors). Synthetic data only; no device.
 * Run: NODE_PATH=<playwright> node tools/test_first_boot_ui.cjs [shots] */
const { chromium } = require('playwright');
const crypto = require('node:crypto');
const path = require('node:path');
const assert = require('node:assert/strict');
const { builtHtml } = require('./ui_build.cjs');

const html = builtHtml();
const PKCS8 = Buffer.from('302e020100300506032b656e04220420', 'hex');
const SPKI = Buffer.from('302a300506032b656e032100', 'hex');
const LABEL = Buffer.from('mattboxx-tailnet-gateway-setup-v1');
const SECRETS = { admin: 'Blue-Lantern-42-river', wifi: 'home-wifi-passphrase-9', key: 'synthetic-headscale-preauth-0123456789' };
const shots = process.argv[2];

function mockGateway(opts = {}) {
  const g = { sid: '', key: null, state: 'none', seq: 0, wifi: 'idle', polls: 0, bodies: [], finish: null, busy: !!opts.busy, codeFails: 0 };
  g.press = () => { if (g.state === 'pending') g.state = 'claimed'; };
  g.handle = async (route) => {
    const req = route.request(), url = new URL(req.url()), body = req.postData() || '';
    if (body) g.bodies.push(body);
    const send = (status, obj) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(obj) });
    const sidHeader = req.headers()['x-setup-session'] || '';
    switch (url.pathname) {
      case '/': return route.fulfill({ contentType: 'text/html', body: html });
      case '/api/auth/status': return send(200, { setup_mode: true, password_set: false, auth_enabled: true, auth_required: false, authenticated: false, device_name: 'Tailnet Gateway' });
      case '/api/setup/state': {
        const mine = sidHeader && sidHeader === g.sid;
        const out = { setup: true, setup_ssid: 'ESP32-Tailnet-Setup-1A2B', default_ap_ssid: 'ESP32-Tailnet-1A2B', version: 'synthetic',
          session: mine ? g.state : 'none', other_pairing: false, code_locked: false, finished: !!g.finish };
        if (mine && g.state === 'claimed') {
          if (g.wifi === 'testing' && ++g.polls >= 2) g.wifi = 'ok';
          out.wifi = { state: g.wifi };
          if (g.wifi === 'ok') Object.assign(out.wifi, { ip: '192.168.1.77', prefix: 24 });
        }
        return send(200, out);
      }
      case '/api/setup/begin': {
        if (g.busy) return send(409, { error: 'busy', detail: 'another device is pairing' });
        const { client_pub } = JSON.parse(body);
        assert.match(client_pub, /^[0-9a-f]{64}$/);
        const devPriv = crypto.randomBytes(32);
        const devKey = crypto.createPrivateKey({ key: Buffer.concat([PKCS8, devPriv]), format: 'der', type: 'pkcs8' });
        const devPub = crypto.createPublicKey(devKey).export({ format: 'der', type: 'spki' }).subarray(12);
        const cpub = Buffer.from(client_pub, 'hex');
        const shared = crypto.diffieHellman({ privateKey: devKey, publicKey: crypto.createPublicKey({ key: Buffer.concat([SPKI, cpub]), format: 'der', type: 'spki' }) });
        g.key = crypto.createHash('sha256').update(Buffer.concat([LABEL, shared, devPub, cpub])).digest();
        g.sid = crypto.randomBytes(16).toString('hex'); g.state = 'pending'; g.seq = 0;
        return send(200, { sid: g.sid, device_pub: devPub.toString('hex'), expires_s: 120, button: true });
      }
      case '/api/setup/claim': {
        const { sid, code } = JSON.parse(body);
        if (sid !== g.sid) return send(404, { error: 'session' });
        if (code !== '12345678') { g.codeFails++; return send(403, { error: 'bad_code', detail: String(5 - g.codeFails) }); }
        g.state = 'claimed'; return send(200, { claimed: true });
      }
      case '/api/setup/apply': {
        const m = JSON.parse(body);
        if (m.sid !== g.sid) return send(404, { error: 'session' });
        if (g.state !== 'claimed') return send(403, { error: 'not_paired' });
        if (!(m.seq > g.seq)) return send(409, { error: 'replay' });
        const aad = Buffer.concat([Buffer.from(m.sid, 'hex'), Buffer.from([m.seq >>> 24 & 255, m.seq >>> 16 & 255, m.seq >>> 8 & 255, m.seq & 255])]);
        const d = crypto.createDecipheriv('aes-256-gcm', g.key, Buffer.from(m.iv, 'hex'));
        d.setAAD(aad); d.setAuthTag(Buffer.from(m.tag, 'hex'));
        let cmd;
        try { cmd = JSON.parse(Buffer.concat([d.update(Buffer.from(m.ct, 'hex')), d.final()]).toString('utf8')); }
        catch (e) { return send(403, { error: 'seal' }); }
        g.seq = m.seq;
        if (cmd.action === 'wifi_test') { g.wifi = 'testing'; g.polls = 0; g.tested = cmd.wifi; return send(200, { wifi: 'testing' }); }
        if (cmd.action === 'finish') { g.finish = cmd; return send(200, { ok: true, restart_in_s: 3, tailnet: !!cmd.tailnet.auth_key }); }
        return send(400, { error: 'action' });
      }
      case '/api/network/scan': return send(200, { status: 'scanning' });
      case '/api/network/scan/result': return send(200, { status: 'ready', age_ms: 10, networks: [
        { ssid: 'HomeNetwork', rssi: -48, channel: 6, auth: 'WPA2_PSK' }, { ssid: 'HomeNetwork', rssi: -71, channel: 11, auth: 'WPA2_PSK' },
        { ssid: 'Neighbour-Guest-Network-With-A-Very-Long-Name', rssi: -83, channel: 1, auth: 'OPEN' }, { ssid: '', rssi: -60, channel: 3, auth: 'WPA2_PSK' }] });
      default: return send(403, { error: 'setup' });   /* everything else is closed during setup */
    }
  };
  return g;
}

async function layout(page, touch) {
  return page.evaluate((touch) => {
    const vw = window.innerWidth, out = { overflow: document.documentElement.scrollWidth - vw, clipped: [], small: [], tiny: [] };
    const card = document.querySelector('#firstBoot');
    card.querySelectorAll('button, input, select, summary').forEach(el => {
      const b = el.getBoundingClientRect(), s = getComputedStyle(el);
      if (!b.width || !b.height || s.visibility === 'hidden' || el.closest('[hidden]')) return;
      const name = (el.id || el.textContent || el.tagName).trim().slice(0, 24);
      if (b.right > vw + 1 || b.left < -1) out.clipped.push(name);
      if (touch && b.height < 36 && el.type !== 'checkbox' && el.type !== 'radio') out.small.push(name + ':' + Math.round(b.height));
    });
    card.querySelectorAll('p, li, label, .form-hint, button, small, dt, dd').forEach(el => {
      const b = el.getBoundingClientRect();
      if (!b.width || el.closest('[hidden]') || !el.textContent.trim()) return;
      const f = parseFloat(getComputedStyle(el).fontSize); if (f < 11 && !el.closest('.fb-steps')) out.tiny.push(el.textContent.trim().slice(0, 18) + ':' + f);
    });
    return out;
  }, touch);
}

async function flow(browser, [width, height, locale], failures, full) {
  const touch = width < 768;
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch, isMobile: touch, locale });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const g = mockGateway(); await page.route('http://esp32.test/**', g.handle);
  const where = `${width}x${height} ${locale}`;
  const check = async (step) => {
    const r = await layout(page, touch);
    if (r.overflow > 0) failures.push(`${where} step ${step}: page scrolls horizontally by ${r.overflow}px`);
    if (r.clipped.length) failures.push(`${where} step ${step}: clipped ${r.clipped.slice(0, 5).join(', ')}`);
    if (r.small.length) failures.push(`${where} step ${step}: touch targets <36px ${r.small.slice(0, 5).join(', ')}`);
    if (r.tiny.length) failures.push(`${where} step ${step}: text <11px ${r.tiny.slice(0, 4).join(', ')}`);
    if (shots) await page.screenshot({ path: path.join(shots, `first-boot-${locale}-${width}x${height}-step${step}.png`), fullPage: true });
  };
  try {
    await page.goto('http://esp32.test/');
    await page.waitForSelector('#firstBoot', { state: 'visible' });
    await page.waitForFunction(() => document.getElementById('fb-pair-status').textContent.includes('BOOT'));
    assert.equal(await page.isVisible('#authSetup'), false);
    /* English-only by owner decision (flash budget), in every browser language. */
    assert.equal((await page.textContent('#fb-title')).trim(), 'Welcome to ESP32 Tailnet Gateway');
    assert.equal(await page.getAttribute('#firstBoot', 'lang'), 'en');
    assert.equal(await page.isEnabled('#fb-next'), false);
    await check(0);
    g.press();
    await page.waitForSelector('#fb-pw', { state: 'visible' });
    await page.fill('#fb-pw', 'short'); await page.fill('#fb-pw2', 'short');
    assert.equal(await page.isEnabled('#fb-next'), false, 'weak password refused');
    await page.fill('#fb-pw', SECRETS.admin); await page.fill('#fb-pw2', SECRETS.admin + 'x');
    assert.equal(await page.isEnabled('#fb-next'), false, 'mismatch refused');
    await page.fill('#fb-pw2', SECRETS.admin);
    if (locale.startsWith('en')) assert.equal((await page.textContent('#fb-next')).trim(), 'Set password & continue');
    await page.check('#fb-show'); assert.equal(await page.getAttribute('#fb-pw', 'type'), 'text'); await page.uncheck('#fb-show');
    await check(1);
    await page.click('#fb-next');
    await page.waitForSelector('#fb-nets button');
    const names = await page.$$eval('#fb-nets button span', s => s.map(x => x.textContent));
    assert.deepEqual(names.filter(n => n === 'HomeNetwork').length, 1, 'duplicate SSIDs merged');
    assert.ok(!names.includes(''), 'hidden SSIDs omitted');
    await page.click('#fb-nets button:has-text("HomeNetwork")');
    assert.equal(await page.inputValue('#fb-ssid'), 'HomeNetwork');
    await page.fill('#fb-wpw', SECRETS.wifi);
    await page.click('#fb-test');
    await page.waitForFunction(() => /192\.168\.1\.77/.test(document.getElementById('fb-test-status').textContent), null, { timeout: 15000 });
    assert.deepEqual(g.tested, { ssid: 'HomeNetwork', password: SECRETS.wifi });
    await check(2);
    await page.click('#fb-next');
    await page.waitForSelector('#fb-key', { state: 'visible' });
    await page.fill('#fb-key', 'tskey');
    assert.equal(await page.isEnabled('#fb-next'), false, 'short key refused');
    await page.fill('#fb-key', SECRETS.key);
    await page.check('input[name="fb-ctl"][value="hs"]');
    assert.equal(await page.isEnabled('#fb-next'), false, 'Headscale needs a URL');
    await page.fill('#fb-server', 'https://headscale.example.com');
    await page.fill('#fb-host', 'Bad_Name');
    assert.equal(await page.isEnabled('#fb-next'), false, 'invalid hostname refused');
    await page.fill('#fb-host', 'home-gateway');
    await check(3);
    await page.click('#fb-next');
    await page.waitForSelector('#fb-apname', { state: 'visible' });
    assert.equal(await page.inputValue('#fb-apname'), 'ESP32-Tailnet-1A2B');
    const apPw = await page.inputValue('#fb-appw');
    assert.match(apPw, /^[A-Za-z0-9]{5}-[A-Za-z0-9]{5}-[A-Za-z0-9]{4}$/);
    await page.fill('#fb-appw', SECRETS.admin);
    assert.equal(await page.isEnabled('#fb-next'), false, 'AP password must differ from admin');
    await page.click('#fb-appw-gen');
    await page.check('#fb-roles input[value="subnet-router"]');
    assert.equal(await page.isChecked('#fb-share-lan'), true, 'Connect a network selects the subnet route');
    await page.check('#fb-roles input[value="wol"]');
    await page.check('#fb-roles input[value="advanced"]');
    await check(4);
    await page.click('#fb-next');
    await page.waitForSelector('#fb-summary dt');
    const summaryText = await page.textContent('#fb-summary');
    assert.ok(summaryText.includes('HomeNetwork'));
    for (const s of [...Object.values(SECRETS), await page.inputValue('#fb-appw')]) assert.ok(!summaryText.includes(s), 'secret in summary');
    await check(5);
    await page.click('#fb-next');
    await page.waitForSelector('#fb-done', { state: 'visible' });
    assert.ok(g.finish, 'finish sent');
    assert.equal(g.finish.admin_password, SECRETS.admin);
    assert.deepEqual(g.finish.wifi, { ssid: 'HomeNetwork', password: SECRETS.wifi });
    assert.deepEqual(g.finish.tailnet, { auth_key: SECRETS.key, login_server: 'https://headscale.example.com', hostname: 'home-gateway' });
    assert.equal(g.finish.share_lan, true); assert.equal(g.finish.exit_node, false); assert.equal(g.finish.ap_recovery_only, true);
    assert.equal(g.finish.ap_ssid, 'ESP32-Tailnet-1A2B');
    assert.deepEqual(g.finish.roles, ['subnet-router', 'wol', 'advanced']); assert.equal(g.finish.advanced_ui, true); assert.ok(g.finish.ap_password.length >= 8 && g.finish.ap_password !== SECRETS.admin);
    assert.ok((await page.textContent('#fb-done-open')).includes('http://192.168.1.77/'));
    assert.equal(await page.inputValue('#fb-pw'), '', 'secrets cleared from the form');
    for (const b of g.bodies) for (const s of [...Object.values(SECRETS), g.finish.ap_password])
      assert.ok(!b.includes(s), 'secret sent in clear');
    await check(5);
    if (errors.length) failures.push(`${where}: script errors ${[...new Set(errors)].slice(0, 3).join(' | ')}`);
    if (!full) return;
    // Setup-code pairing with one wrong code, on a fresh page.
    const p2 = await context.newPage(); const g2 = mockGateway(); await p2.route('http://esp32.test/**', g2.handle);
    await p2.goto('http://esp32.test/'); await p2.waitForSelector('#firstBoot', { state: 'visible' });
    await p2.waitForFunction(() => document.getElementById('fb-pair-status').textContent.includes('BOOT'));
    await p2.click('.fb-details summary'); await p2.fill('#fb-code', '1111 2222'); await p2.click('#fb-code-btn');
    await p2.waitForFunction(() => /Attempts left: 4/.test(document.getElementById('fb-error').textContent));
    await p2.fill('#fb-code', '1234 5678'); await p2.click('#fb-code-btn');
    await p2.waitForSelector('#fb-pw', { state: 'visible' });
    // Gateway restarted during pairing (real board: console opened): the page says
    // so instead of "expired", the code is refused cleanly, and Try again recovers.
    const p4 = await context.newPage(); const g4 = mockGateway(); await p4.route('http://esp32.test/**', g4.handle);
    await p4.goto('http://esp32.test/'); await p4.waitForFunction(() => document.getElementById('fb-pair-status').textContent.includes('BOOT'));
    g4.sid = 'restarted';
    await p4.waitForFunction(() => /pairing was reset/.test(document.getElementById('fb-pair-status').textContent));
    assert.ok(await p4.isVisible('#fb-retry'));
    await p4.click('#fb-retry'); await p4.waitForFunction(() => document.getElementById('fb-pair-status').textContent.includes('BOOT'));
    g4.press(); await p4.waitForSelector('#fb-pw', { state: 'visible' });
    // Another device already pairing: clear message and a retry button.
    const p3 = await context.newPage(); const g3 = mockGateway({ busy: true }); await p3.route('http://esp32.test/**', g3.handle);
    await p3.goto('http://esp32.test/'); await p3.waitForSelector('#fb-retry', { state: 'visible' });
    assert.ok((await p3.textContent('#fb-pair-status')).includes('Another device'));
    g3.busy = false; await p3.click('#fb-retry');
    await p3.waitForFunction(() => document.getElementById('fb-pair-status').textContent.includes('BOOT'));
  } catch (e) {
    failures.push(`${where}: ${process.env.FB_VERBOSE ? e.stack : e.message.split('\n').slice(0, 6).join(' ')}`);
  } finally { await context.close(); }
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  const failures = [];
  const runs = [[390, 844, 'en-US', true], [1440, 900, 'en-US', true]].concat(
    ['en-US', 'it-IT', 'es-ES', 'zh-CN'].flatMap(l => [[320, 640, l], [768, 1024, l], [1920, 1080, l]]))
    .filter(r => !process.env.FB_LOCALE || r[2] === process.env.FB_LOCALE);
  try {
    for (const r of runs) await flow(browser, r, failures, r[3]);
  } finally { await browser.close(); }
  if (failures.length) { console.log(failures.join('\n')); console.log('FAIL ' + failures.length); process.exit(1); }
  console.log(`PASS: first-boot wizard end to end (${runs.length} viewport/language runs): pairing by button and code, busy pairing, password/Wi-Fi/tailnet/AP validation, sealed requests with no secret in clear, layout`);
})();
