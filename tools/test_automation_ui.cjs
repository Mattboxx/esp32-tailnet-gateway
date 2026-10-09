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

async function fixture(browser, options = {}) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const calls = [];
  const errors = [];
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
      body = state.systemBody || { web_auth_enabled: true, session_timeout_s: 0 };
    } else if (url.pathname === '/api/tailscale') {
      body = { settings: state.tailscaleSettings || {}, runtime: {}, peers: [] };
    } else if (url.pathname === '/api/wol') {
      if (state.wolFails) return route.abort('failed');
      if (state.wolDelay) await new Promise(resolve => setTimeout(resolve, state.wolDelay));
      body = { devices: [{ name: 'Fixture NAS', mac: mqtt.broker_watchdog_wol_mac, port: 9 }] };
    }
    if (state.rejectProtected && ['/api/mqtt', '/api/ntfy'].includes(url.pathname)) status = 401;
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('http://esp32.test/#' + (options.page || 'automation'));
  return { context, page, calls, errors, state };
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
    console.log(`PASS: ${count} browser scenarios (auth deep links, WOL isolation, retries, unknown state, reload recovery, coalescing, SNMP, session labels and exit-node DNS)`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
