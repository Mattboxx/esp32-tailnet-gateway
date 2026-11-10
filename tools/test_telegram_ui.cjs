/* Telegram card: remote command options (3.0.12). Actual SPA, synthetic
 * /api/notify, Chromium. Loads the saved options and status, keeps the
 * dependent fields in step with their switches, refuses a poll interval out
 * of 5-300 s without saving, and saves every option under telegram.commands
 * together with the existing Telegram fields (token write-only). */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();

const notify = {
  events: 'problems', waiting: 0, dropped: 0, connectivity_grace_seconds: 120, pending_connectivity: 0, worker_running: false,
  telegram: { enabled: true, chat: '42', has_token: true, events: 'problems', notify_startup: false, notify_poweron: false, sent: 3, failed: 0, last_error: '',
    commands: { enabled: true, only_when_tailscale_down: false, allow_direct_mac: false, info_enabled: true, info_include_details: false,
      poll_interval_seconds: 20, running: true, received: 4, errors: 1, other_chats_skipped: 2, last_error: '' } },
  email: { enabled: false, host: '', port: 465, security: 'tls', user: '', has_password: false, from: '', to: '', events: 'problems', sent: 0, failed: 0, last_error: '' },
};

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'en-US' });
    await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
    const page = await context.newPage();
    const errors = []; const posts = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('http://esp32.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
      if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
      const json = b => route.fulfill({ contentType: 'application/json', body: JSON.stringify(b) });
      if (url.pathname === '/api/auth/status') return json({ password_set: true, auth_enabled: true, auth_required: true, authenticated: true });
      if (url.pathname === '/api/notify') {
        if (route.request().method() === 'POST') { posts.push(route.request().postDataJSON()); return json({ ok: true }); }
        return json(notify);
      }
      return json({});
    });
    await page.goto('http://esp32.test/#automation/notifications');
    await page.waitForFunction(() => document.getElementById('nt-tg-cmd').value === 'basic');
    const v = await page.evaluate(() => ({
      cmd: document.getElementById('nt-tg-cmd').value, down: document.getElementById('nt-tg-cmd-down').checked,
      info: document.getElementById('nt-tg-cmd-info').checked, details: document.getElementById('nt-tg-cmd-details').checked,
      mac: document.getElementById('nt-tg-cmd-mac').checked, poll: document.getElementById('nt-tg-cmd-poll').value,
      status: document.getElementById('nt-tg-status').textContent }));
    assert.deepEqual([v.cmd, v.down, v.info, v.details, v.mac, v.poll], ['basic', false, true, false, false, '20']);
    assert.match(v.status, /commands on: 4 run, 1 refused, 2 from other chats ignored/);

    /* invalid interval: not saved */
    await page.fill('#nt-tg-cmd-poll', '3');
    await page.click('#nt-tg-save');
    await page.waitForTimeout(200);
    assert.equal(posts.length, 0);
    assert.match(await page.textContent('#nt-tg-note'), /Poll interval: use 5 to 300/);

    /* valid change: every option sent under telegram.commands */
    await page.fill('#nt-tg-cmd-poll', '30');
    await page.selectOption('#nt-tg-cmd','recovery');
    await page.check('#nt-tg-cmd-mac', { force: true });
    await page.check('#nt-tg-cmd-down', { force: true });
    await page.click('#nt-tg-save');
    await page.waitForFunction(() => true);
    await page.waitForTimeout(400);
    assert.equal(posts.length, 1);
    const t = posts[0].telegram;
    assert.deepEqual(t.commands, { enabled: true, allow_recovery: true, only_when_tailscale_down: true, allow_direct_mac: true, info_enabled: true,
                                   info_include_details: false, poll_interval_seconds: 30 });
    assert.equal(t.chat, '42'); assert.equal(t.token, '');

    /* dependent field follows its switch */
    await page.uncheck('#nt-tg-cmd-info', { force: true });
    const dependent = await page.evaluate(() => document.getElementById('nt-tg-cmd-details-setting').getAttribute('data-feature-state') ||
      document.getElementById('nt-tg-cmd-details-setting').className);
    assert.match(String(dependent), /disabled|feature-disabled|inactive/);
    assert.deepEqual(errors, []);
    await context.close();
    console.log('PASS: Telegram remote command options load with their status, invalid interval refused, every option saved under telegram.commands, dependent fields follow');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
