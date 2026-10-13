/* Run with Node.js and Playwright. Uses the actual SPA with synthetic APIs;
 * never reads device credentials or changes a running board. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const html = fs.readFileSync(path.join(__dirname, '../main/index.html'), 'utf8');
const mqtt = { enabled: true, connected: true, uri: 'mqtts://broker.example',
  base_topic: 'fixture/router', interval_seconds: 30, broker_watchdog_timeout_seconds: 300,
  broker_watchdog_wol_mac: '02:00:00:00:00:01' };
const ntfy = { enabled: true, server: 'https://notify.example', topic: 'fixture',
  info_enabled: true, commands_enabled: true, last_publish_ok: true };
const updates = { enabled: false, auto_install: false, beta_channel: false,
  install_hour: -1, busy: false, checked: false, update_available: false,
  status: 'Periodic checks disabled', latest_version: '' };

async function fixture(browser, options = {}) {
  const context = await browser.newContext({ viewport: options.viewport || { width: 1280, height: 800 } });
  const page = await context.newPage();
  const calls = [];
  const errors = [];
  const externalRequests = [];
  page.on('request', request => {
    if (!request.url().startsWith('http://esp32.test/')) externalRequests.push(request.url());
  });
  const state = { authenticated: options.authenticated !== false, ...options };
  page.on('pageerror', error => errors.push(error.message));
  await page.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    calls.push(url.pathname);
    let body = {};
    let status = 200;
    if (url.pathname === '/api/auth/status') {
      body = { password_set: true, auth_enabled: true, auth_required: true,
        authenticated: state.authenticated, session_timeout_s: 0 };
    } else if (url.pathname === '/api/mqtt') {
      if (state.mqttDelay) await new Promise(resolve => setTimeout(resolve, state.mqttDelay));
      if (state.mqttFailures) { state.mqttFailures--; status = 503; }
      body = state.mqttBody || mqtt;
    } else if (url.pathname === '/api/ntfy') {
      if (state.ntfyFailures) { state.ntfyFailures--; status = 503; }
      body = state.ntfyBody || ntfy;
    } else if (url.pathname === '/api/snmp') {
      if (state.snmpFailures) { state.snmpFailures--; status = 503; }
      body = state.snmpBody || { enabled: false, running: false, community: 'fixture' };
    } else if (url.pathname === '/api/system') {
      if (route.request().method() === 'POST') {
        state.savedSystem = route.request().postDataJSON();
        state.systemBody = {...(state.systemBody || {}), ...state.savedSystem,
          wifi_power_save_known: true, wifi_power_save_active: state.savedSystem.wifi_power_save};
        body = {ok: !state.systemSaveFails};
      } else {
        if (state.systemFailures) { state.systemFailures--; status = 503; }
        body = state.systemBody || { web_auth_enabled: true, session_timeout_s: 0,
          wifi_power_save: false, wifi_power_save_active: false, wifi_power_save_known: true };
      }
    } else if (url.pathname === '/api/system/updates') {
      if (route.request().method() === 'POST') {
        state.savedUpdates = route.request().postDataJSON();
        state.updatesBody = { ...updates, ...state.savedUpdates };
      }
      if (state.updatesFailures) { state.updatesFailures--; status = 503; }
      body = state.updatesBody || updates;
    } else if (url.pathname === '/api/system/updates/install' || url.pathname === '/api/system/updates/check') {
      state.updatesBody = { ...(state.updatesBody || updates), busy: true, status: 'Checking GitHub releases' };
      body = { ok: true }; status = 202;
    } else if (url.pathname === '/api/tailscale') {
      body = { settings: state.tailscaleSettings || {}, runtime: state.tailscaleRuntime || {}, peers: [] };
    } else if (url.pathname === '/api/status') {
      body = state.statusBody || {};
    } else if (url.pathname === '/api/wol') {
      if (state.wolFails) return route.abort('failed');
      if (state.wolDelay) await new Promise(resolve => setTimeout(resolve, state.wolDelay));
      body = { devices: [{ name: 'Fixture NAS', mac: mqtt.broker_watchdog_wol_mac, port: 9 }] };
    }
    if (state.rejectProtected && ['/api/mqtt', '/api/ntfy'].includes(url.pathname)) status = 401;
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('http://esp32.test/#' + (options.page || 'automation'));
  return { context, page, calls, errors, state, externalRequests };
}

async function loaded(page) {
  await page.waitForFunction(() => document.getElementById('mqtt-badge').textContent === 'Connected'
    && document.getElementById('ntfy-badge').textContent === 'Enabled · reachable');
  assert.equal(await page.locator('#mqtt-enabled').isChecked(), true);
  assert.equal(await page.locator('#ntfy-enabled').isChecked(), true);
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  let count = 0;
  try {
    // A single deliberate click opens the provider directly. Simulate a
    // popup blocker/nullable noopener result: no duplicate window, no payment.
    let tip = await fixture(browser, {page: 'system'});
    await tip.page.evaluate(() => {window.tipCalls = []; window.open = (...args) => {window.tipCalls.push(args); return null;};});
    assert.deepEqual(tip.externalRequests, []);
    assert.equal(await tip.page.locator('#mod-support-fallback').isVisible(), false);
    await tip.page.locator('#nav-support-link').click();
    const tipCalls = await tip.page.evaluate(() => window.tipCalls);
    assert.equal(tipCalls.length, 1);
    assert.equal(tipCalls[0][0], 'https://ko-fi.com/mattboxx');
    assert.match(tipCalls[0][2], /popup=yes.*noopener,noreferrer/);
    assert.equal(await tip.page.locator('#mod-support-fallback').isVisible(), true);
    assert.deepEqual(tip.errors, []); await tip.context.close(); count++;
    // Saved WiFi policy, driver state and failed reads must stay distinct.
    let wifi = await fixture(browser, {page: 'system'});
    await wifi.page.waitForFunction(() => !document.getElementById('sys-wifi-ps').disabled);
    assert.equal(await wifi.page.locator('#sys-wifi-ps').isChecked(), false);
    await wifi.page.locator('#sys-wifi-ps').locator('..').click();
    await wifi.page.locator('#sys-device-name-save').click();
    await wifi.page.waitForFunction(() => document.getElementById('sys-wifi-ps-state').textContent === 'Configured: ON · Runtime: ON');
    assert.equal(wifi.state.savedSystem.wifi_power_save, true);
    wifi.state.systemFailures = 1;
    await wifi.page.locator('#sys-reload').click();
    await wifi.page.waitForFunction(() => document.getElementById('sys-wifi-ps-state').textContent.includes('unavailable'));
    assert.equal(await wifi.page.locator('#sys-wifi-ps').isChecked(), true);
    assert.equal(await wifi.page.locator('#sys-wifi-ps').isDisabled(), true);
    await wifi.page.locator('#sys-reload').click();
    await wifi.page.waitForFunction(() => !document.getElementById('sys-wifi-ps').disabled);
    assert.equal(await wifi.page.locator('#sys-wifi-ps').isChecked(), true);
    assert.deepEqual(wifi.errors, []); await wifi.context.close(); count++;
    wifi = await fixture(browser, {page: 'tailscale', tailscaleSettings: {
      manual_exit_advertisement: true, advertise_exit_node: false, exit_server_active: true}});
    await wifi.page.waitForFunction(() => document.getElementById('ts-manual-exit-state').textContent.includes('manual default route'));
    assert.equal(await wifi.page.locator('#ts-advertise-exit').isChecked(), false);
    assert.deepEqual(wifi.errors, []); await wifi.context.close(); count++;
    // Optional support must be visible, responsive and fully local until a
    // deliberate click. Never visit a payment checkout or send a test tip.
    for (const width of [1280, 1000, 800, 390, 320]) {
      const f = await fixture(browser, { page: 'system', viewport: { width, height: 800 } });
      await f.page.waitForFunction(() => !document.getElementById('sys-updates-check').disabled);
      for (const id of ['nav-support-link', 'mod-support-link']) {
        const link = f.page.locator('#' + id);
        assert.equal(await link.getAttribute('href'), 'https://ko-fi.com/mattboxx');
        assert.equal(await link.getAttribute('target'), '_blank');
        assert.equal(await link.getAttribute('rel'), 'noopener noreferrer');
        assert.equal(await link.getAttribute('referrerpolicy'), 'no-referrer');
        assert.match(await link.getAttribute('aria-label'), /Mattboxx.*new tab/);
        await link.scrollIntoViewIfNeeded();
        const box = await link.boundingBox();
        assert(box && box.x >= 0 && box.x + box.width <= width && box.height >= 40);
        await link.focus();
        assert.equal(await link.evaluate(el => el === document.activeElement), true);
      }
      assert.equal(await f.page.locator('#mod-support').evaluate(el => getComputedStyle(el).position), 'static');
      assert.match(await f.page.locator('#mod-support').textContent(), /Always optional.*stay free/s);
      assert.equal(await f.page.locator('a[href="https://www.buymeacoffee.com/csontikka"]').count(), 1);
      assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(f.externalRequests, []);
      assert.deepEqual(f.errors, []);
      if (process.env.TEST_SUPPORT_SCREENSHOTS && [1280, 390].includes(width)) {
        const folder = process.env.TEST_SUPPORT_SCREENSHOTS;
        fs.mkdirSync(folder, { recursive: true });
        await f.page.locator('#mod-support').screenshot({ path: path.join(folder, `support-footer-${width}.png`) });
        await f.page.evaluate(() => scrollTo(0, 0));
        await f.page.screenshot({ path: path.join(folder, `support-nav-${width}.png`), clip: { x: 0, y: 0, width, height: 90 } });
      }
      await f.context.close(); count++;
    }
    // Deep link while logged out: no protected requests until login. A WOL
    // transport failure must not block MQTT or ntfy configuration rendering.
    let f = await fixture(browser, { authenticated: false, wolFails: true });
    await f.page.locator('#authLogin').waitFor({ state: 'visible' });
    assert.equal(f.calls.includes('/api/mqtt'), false);
    assert.equal(f.calls.includes('/api/ntfy'), false);
    f.state.authenticated = true;
    await f.page.evaluate(() => { window.loginPasswordRequest = () => Promise.resolve({ ok: true }); });
    await f.page.locator('#login-pw').fill('synthetic-password');
    await f.page.locator('#loginSubmitBtn').click();
    await loaded(f.page);
    assert.equal(f.calls.filter(url => url === '/api/wol').length, 1);
    assert.equal(await f.page.locator('#mqtt-watchdog-target').inputValue(), mqtt.broker_watchdog_wol_mac);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // Expired authentication opens login immediately and is never retried.
    f = await fixture(browser);
    await loaded(f.page);
    const beforeExpiry = f.calls.filter(url => url === '/api/mqtt').length;
    f.state.rejectProtected = true;
    await f.page.evaluate(() => window.loadMqtt());
    await f.page.locator('#authLogin').waitFor({ state: 'visible' });
    assert.equal(f.calls.filter(url => url === '/api/mqtt').length, beforeExpiry + 1);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // A stalled transport is aborted by the real eight-second deadline,
    // then the retry reads and renders fresh settings.
    f = await fixture(browser);
    await loaded(f.page);
    await f.page.evaluate(async () => {
      const originalFetch = window.fetch;
      let stalled = false;
      window.fetch = (url, options) => {
        if (url === '/api/mqtt' && !stalled) {
          stalled = true;
          return new Promise((resolve, reject) => options.signal.addEventListener('abort',
            () => reject(new DOMException('Request aborted', 'AbortError')), { once: true }));
        }
        return originalFetch(url, options);
      };
      await window.loadMqtt();
    });
    await loaded(f.page);
    assert.equal(await f.page.locator('#mqtt-card').getAttribute('aria-busy'), 'false');
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // Restore an authenticated deep link, retry an HTTP failure, and update
    // target labels when the independent WOL response arrives later.
    f = await fixture(browser, { mqttFailures: 1, ntfyFailures: 1, wolDelay: 700 });
    await loaded(f.page);
    await f.page.waitForFunction(() => document.getElementById('mqtt-watchdog-target').selectedOptions[0].textContent.includes('Fixture NAS'));
    assert.equal(f.calls.filter(url => url === '/api/mqtt').length, 2);
    assert.equal(f.calls.filter(url => url === '/api/ntfy').length, 2);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // Unknown state stays neutral and cannot be saved as disabled. Invalid
    // JSON shapes likewise cannot be mistaken for a disabled integration.
    f = await fixture(browser, { mqttFailures: 2, ntfyBody: {} });
    await f.page.waitForFunction(() => ['mqtt', 'ntfy'].every(key => document.getElementById(key + '-badge').textContent === 'Unavailable'));
    for (const key of ['mqtt', 'ntfy']) {
      assert.equal(await f.page.locator('#' + key + '-enabled').isDisabled(), true);
      assert.equal(await f.page.locator('#' + key + '-save').isDisabled(), true);
      assert.equal(await f.page.locator('#' + key + '-card').getAttribute('data-feature-state'), 'unknown');
    }
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // Failed refresh retains the last known enabled state; recovery uses the
    // fresh server value, including a legitimately disabled integration.
    f = await fixture(browser);
    await loaded(f.page);
    f.state.mqttFailures = 2; f.state.ntfyFailures = 2;
    await f.page.locator('#automation-reload').click();
    await f.page.waitForFunction(() => ['mqtt', 'ntfy'].every(key => document.getElementById(key + '-badge').textContent === 'Unavailable'));
    for (const key of ['mqtt', 'ntfy']) {
      assert.equal(await f.page.locator('#' + key + '-enabled').isChecked(), true);
      assert.equal(await f.page.locator('#' + key + '-card').getAttribute('data-feature-state'), 'enabled');
    }
    f.state.mqttBody = { ...mqtt, enabled: false };
    f.state.ntfyBody = { ...ntfy, enabled: false };
    await f.page.locator('#automation-reload').click();
    await f.page.waitForFunction(() => ['mqtt', 'ntfy'].every(key => document.getElementById(key + '-badge').textContent === 'Disabled'));
    assert.equal(await f.page.locator('#mqtt-enabled').isChecked(), false);
    assert.equal(await f.page.locator('#ntfy-enabled').isChecked(), false);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // Repeated reloads share one in-flight request and fields cannot change
    // while the response that will replace them is pending.
    f = await fixture(browser);
    await loaded(f.page);
    const before = f.calls.filter(url => url === '/api/mqtt').length;
    f.state.mqttDelay = 400;
    await f.page.evaluate(() => { window.loadMqtt(); window.loadMqtt(); window.loadMqtt(); });
    assert.equal(await f.page.locator('#mqtt-enabled').isDisabled(), true);
    await f.page.waitForFunction(() => document.getElementById('mqtt-card').getAttribute('aria-busy') === 'false');
    assert.equal(f.calls.filter(url => url === '/api/mqtt').length, before + 1);
    assert.equal(await f.page.locator('#mqtt-enabled').isDisabled(), false);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;

    // New upstream SNMP settings use the same honest unknown-state model:
    // no failed read may turn a running listener into an unchecked switch.
    f = await fixture(browser, { page: 'system', snmpBody: { enabled: true, running: true, community: 'fixture' } });
    await f.page.waitForFunction(() => document.getElementById('sys-snmp-badge').textContent === 'Running');
    assert.equal(await f.page.locator('#sys-snmp-en').isChecked(), true);
    f.state.snmpFailures = 2;
    await f.page.locator('#sys-snmp-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-snmp-badge').textContent === 'Unavailable');
    assert.equal(await f.page.locator('#sys-snmp-en').isChecked(), true);
    f.state.snmpBody = { enabled: false, running: false, community: 'fixture' };
    await f.page.locator('#sys-snmp-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-snmp-badge').textContent === 'Disabled');
    assert.equal(await f.page.locator('#sys-snmp-card').getAttribute('data-feature-state'), 'disabled');
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;
    // An unlimited idle timer must not imply that password protection is off.
    f = await fixture(browser, { page: 'system' });
    await f.page.waitForFunction(() => document.getElementById('sys-auth-to-badge').textContent === 'Password required · no idle timeout');
    assert.equal(await f.page.locator('#sys-web-auth-enabled').isChecked(), true);
    f.state.systemBody = { web_auth_enabled: false, session_timeout_s: 1800 };
    await f.page.locator('#sys-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-auth-to-badge').textContent === 'Password gate off');
    assert.equal(await f.page.locator('#sys-web-auth-enabled').isChecked(), false);
    f.state.systemBody = { web_auth_enabled: true, session_timeout_s: 3600 };
    await f.page.locator('#sys-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-auth-to-badge').textContent === 'Idle timeout: 1 h');
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;
    // Saved exit-node policy and the running DNS listener are distinct.
    // A custom Web UI port of 41180 must allow the advertised alternate 41181.
    f = await fixture(browser, { page: 'tailscale', tailscaleSettings: {
      enabled: true, advertise_exit_node: true, exit_server_active: true,
      exit_dns_running: true, peerapi_port: 41181 } });
    await f.page.waitForFunction(() => document.getElementById('ts-exit-dns-status').textContent.includes('DNS running on port 41181'));
    assert.equal(await f.page.locator('#ts-advertise-exit').isChecked(), true);
    f.state.tailscaleSettings.exit_dns_running = false;
    await f.page.locator('#ts-reload').click();
    await f.page.waitForFunction(() => document.getElementById('ts-exit-dns-status').textContent.includes('DNS unavailable'));
    f.state.tailscaleSettings.exit_server_active = false;
    await f.page.locator('#ts-reload').click();
    await f.page.waitForFunction(() => document.getElementById('ts-exit-dns-status').textContent.includes('after restart'));
    assert.equal(await f.page.locator('#ts-advertise-exit').isChecked(), true);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;
    // Manual GitHub installs remain usable while periodic checks are OFF;
    // channel changes must be saved and writes are never retried silently.
    f = await fixture(browser, { page: 'system' });
    await f.page.waitForFunction(() => !document.getElementById('sys-updates-install').disabled);
    assert.equal(await f.page.locator('#sys-updates-enabled').isChecked(), false);
    assert.equal(await f.page.locator('#sys-updates-auto').isDisabled(), true);
    assert.equal(await f.page.locator('#sys-updates-policy').getAttribute('data-feature-state'), 'disabled');
    await f.page.locator('#sys-updates-beta').locator('..').click();
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    await f.page.locator('#sys-updates-save').click();
    await f.page.waitForFunction(() => !document.getElementById('sys-updates-install').disabled);
    assert.deepEqual(f.state.savedUpdates, {enabled: false, auto_install: false, beta_channel: true, install_hour: -1});
    f.page.on('dialog', dialog => dialog.accept());
    await f.page.locator('#sys-updates-install').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Working…');
    assert.equal(f.calls.filter(url => url === '/api/system/updates/install').length, 1);
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    f.state.updatesBody.busy = false; f.state.updatesBody.status = 'Rejected: SHA-256 mismatch';
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-updates-status').textContent.includes('SHA-256 mismatch'));
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), false);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;

    // A successful check with no candidate disables installation, not checks.
    // Refresh/polling must preserve this until a newer candidate is found.
    f = await fixture(browser, { page: 'system' });
    await f.page.waitForFunction(() => !document.getElementById('sys-updates-check').disabled);
    await f.page.locator('#sys-updates-check').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Working…');
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    assert.equal(await f.page.locator('#sys-updates-check').isDisabled(), true);
    f.state.updatesBody = {...updates, checked: true, status: 'No newer compatible release'};
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-updates-status').textContent === 'No newer compatible release');
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    assert.equal(await f.page.locator('#sys-updates-check').isDisabled(), false);
    assert.match(await f.page.locator('#sys-updates-install').getAttribute('title'), /No newer compatible release/);
    await f.page.evaluate(() => document.getElementById('sys-updates-install').click());
    assert.equal(f.calls.filter(url => url === '/api/system/updates/install').length, 0);
    await f.page.locator('#sys-updates-reload').click();
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    await f.page.locator('#sys-updates-check').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Working…');
    f.state.updatesBody = {...updates, checked: true, update_available: true,
      latest_version: '0.1.31-Mattboxx-1.11', status: 'Newer compatible release available'};
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Update available');
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), false);
    assert.equal(await f.page.locator('#sys-updates-check').isDisabled(), false);
    f.state.updatesBody = {...updates, checked: true, status: 'No newer compatible release'};
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-updates-status').textContent === 'No newer compatible release');
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;

    // Missing or non-boolean availability fields must not unlock installation.
    for (const invalid of [{checked: undefined}, {update_available: 'false'}]) {
      f = await fixture(browser, {page: 'system', updatesBody: {...updates, ...invalid}});
      await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Unavailable');
      assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
      assert.equal(await f.page.locator('#sys-updates-check').isDisabled(), true);
      f.state.updatesBody = {...updates, checked: true, status: 'No newer compatible release'};
      await f.page.locator('#sys-updates-reload').click();
      await f.page.waitForFunction(() => document.getElementById('sys-updates-status').textContent === 'No newer compatible release');
      assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
      assert.equal(await f.page.locator('#sys-updates-check').isDisabled(), false);
      assert.deepEqual(f.errors, []); await f.context.close(); count++;
    }

    f = await fixture(browser, { page: 'system' });
    await f.page.waitForFunction(() => !document.getElementById('sys-updates-install').disabled);
    f.page.on('dialog', dialog => dialog.accept());
    await f.page.locator('#sys-updates-enabled').locator('..').click();
    await f.page.locator('#sys-updates-auto').locator('..').click();
    await f.page.locator('#sys-updates-hour').selectOption('4');
    await f.page.locator('#sys-updates-save').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Automatic install');
    assert.deepEqual(f.state.savedUpdates, {enabled: true, auto_install: true, beta_channel: false, install_hour: 4});
    await f.page.locator('#sys-updates-enabled').locator('..').click();
    assert.equal(await f.page.locator('#sys-updates-auto').isChecked(), false);
    assert.equal(await f.page.locator('#sys-updates-auto').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Failed status reads retain visible policy, disable writes and do not
    // report an enabled automatic installer as OFF. Invalid links stay hidden.
    f = await fixture(browser, { page: 'system', updatesBody: {...updates,
      enabled: true, auto_install: true, beta_channel: true, install_hour: 3,
      release_url: 'javascript:alert(1)'} });
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Automatic install');
    assert.equal(await f.page.locator('#sys-updates-release').isVisible(), false);
    f.state.updatesFailures = 2;
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Unavailable');
    assert.equal(await f.page.locator('#sys-updates-auto').isChecked(), true);
    assert.equal(await f.page.locator('#sys-updates-install').isDisabled(), true);
    await f.page.locator('#sys-updates-reload').click();
    await f.page.waitForFunction(() => document.getElementById('sys-ota-badge').textContent === 'Automatic install');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // A failed task allocation is not an endlessly registering node. Check
    // both independently rendered Tailnet badges and recovery to Connected.
    for (const retrying of [false, true]) {
      const runtime = {enabled: true, connected: false, startup_error: 'ESP_ERR_NO_MEM', startup_retrying: retrying};
      const expected = retrying ? 'Retrying startup' : 'Startup failed';
      f = await fixture(browser, {page: 'tailscale', tailscaleSettings: {enabled: true}, tailscaleRuntime: runtime});
      await f.page.waitForFunction(text => document.getElementById('ts-page-badge').textContent === text, expected);
      assert.equal(await f.page.locator('#ts-page-badge').getAttribute('title'), 'ESP_ERR_NO_MEM');
      assert.deepEqual(f.errors, []); await f.context.close(); count++;
      f = await fixture(browser, {page: 'status', statusBody: {tailscale: runtime}});
      await f.page.waitForFunction(text => document.getElementById('ts-badge').textContent === text, expected);
      assert.deepEqual(f.errors, []); await f.context.close(); count++;
    }
    f = await fixture(browser, {page: 'tailscale', tailscaleSettings: {enabled: true}, tailscaleRuntime: {connected: true, startup_error: 'ESP_ERR_NO_MEM'}});
    await f.page.waitForFunction(() => document.getElementById('ts-page-badge').textContent.includes('Connected'));
    assert.equal(await f.page.locator('#ts-page-badge').getAttribute('title'), '');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    console.log(`PASS: ${count} browser scenarios (local-only responsive support, automation, SNMP/session labels, startup error/retry/recovery, exit DNS and GitHub updates)`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
