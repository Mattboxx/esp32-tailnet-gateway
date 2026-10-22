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
    } else if (url.pathname === '/api/operations') {
      if(route.request().method()==='POST') {
        state.savedOperation=route.request().postDataJSON();body={ok:true};
      } else {if(state.operationsDelay) await new Promise(resolve=>setTimeout(resolve,state.operationsDelay));
        if(state.operationsFailures){state.operationsFailures--;status=503;}
        body=state.operationsBody || {devices:[],events:[],monitoring:false,guard:false,remote_commands:false,
        recovery_state:'idle',sockets_used:12,socket_limit:31,internal_min:14000,internal_largest:12000,
        minimum_internal:16384,minimum_largest:8192,socket_reserve:4,interval_s:60,control_connected:true};}
    } else if (url.pathname === '/api/capabilities') {
      if(state.capabilityFailures){state.capabilityFailures--;status=503;}
      body=state.capabilityBody || {schema:2,features:[{id:'smart-recovery',compiled:true,hardware_supported:true,configured:true,active:false,verified:false,experimental:true,evidence:'Fixture: no hardware qualification'}]};
    } else if (url.pathname === '/api/health') {
      if(state.healthFailures){state.healthFailures--;status=503;}
      body=state.healthBody || {enabled:false,notify:false,interval_s:60,failure_threshold:3,gateway_port:0,dns_name:'',internet_ip:'',internet_port:0,tailnet_target:'',tailnet_port:0,checks:[]};
    } else if (url.pathname === '/api/service-leases') {
      body=state.leasesBody || [];
    } else if (url.pathname === '/api/mqtt') {
      if (state.mqttDelay) await new Promise(resolve => setTimeout(resolve, state.mqttDelay));
      if (state.mqttFailures) { state.mqttFailures--; status = 503; }
      body = state.mqttBody || mqtt;
    } else if (url.pathname === '/api/ntfy') {
      if (state.ntfyFailures) { state.ntfyFailures--; status = 503; }
      if (route.request().method() === 'POST') { state.savedNtfy = route.request().postDataJSON(); state.ntfyBody = {...(state.ntfyBody || ntfy), ...state.savedNtfy}; body = {ok: true}; }
      else body = state.ntfyBody || ntfy;
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
    } else if (url.pathname === '/api/profiles') {
      const profiles=[{id:'gateway',title:'Gateway',summary:'Fixture gateway',enables:['service_expiry_notifications']},
        {id:'monitoring',title:'Monitoring',summary:'Fixture monitoring',enables:['device_monitoring','health_monitor']},
        {id:'advanced',title:'Advanced',summary:'Fixture advanced',enables:[]}];
      state.profileActive=state.profileActive||'none';state.profileToken=state.profileToken||101;
      if(route.request().method()==='POST'){
        const input=route.request().postDataJSON();(state.profilePosts=state.profilePosts||[]).push(input);
        if(input.action==='apply'&&state.profileConflict){state.profileConflict=0;state.profileToken++;status=409;body={ok:false,error:'settings changed since the preview; preview again',rolled_back:false,partial:false,left_changed:[]};}
        else if(input.action==='apply'&&input.token===state.profileToken){state.profileActive=input.profile;state.profileRollback=true;state.profileToken++;body={ok:true,applied:true,rolled_back:false,changed:['device_monitoring','health_monitor'],kept:[]};}
        else if(input.action==='rollback'&&state.profileRollback){state.profileActive='none';state.profileRollback=false;state.profileToken++;body={ok:true,applied:false,rolled_back:true,changed:['device_monitoring'],kept:['health_monitor']};}
        else {status=input.action==='rollback'?404:409;body={ok:false,error:'rejected'};}
      } else {
        const preview=url.searchParams.get('preview');
        body={schema:1,active:state.profileActive,rollback_available:!!state.profileRollback,rollback_to:'none',rollback_restores:[],profiles};
        if(preview)body.preview={profile:preview,token:state.profileToken,disables_anything:false,changes_network_exposure:false,
          changes:preview==='monitoring'?[{setting:'device_monitoring',current:false,proposed:true,change:'enable'},{setting:'health_monitor',current:true,proposed:true,change:'unchanged'}]:[],
          manual_steps:['Fixture manual step']};
      }
    } else if (url.pathname === '/api/tailscale') {
      if (route.request().method() === 'POST') { state.savedTailscale = route.request().postDataJSON(); body = {ok: true}; }
      else body = { settings: state.tailscaleSettings || {}, runtime: state.tailscaleRuntime || {}, peers: [] };
    } else if (url.pathname === '/api/status') {
      body = state.statusBody || {};
    } else if (url.pathname === '/api/tailnet-forward/import') {
      const input=route.request().postDataJSON();
      if(state.importDelay)await new Promise(resolve=>setTimeout(resolve,state.importDelay));
      const rules=input.rules.map(r=>({...r,enabled:false}));
      body=state.importBody || {ok:true,applied:input.action==='apply',format:'homelab-service-rules/v1',rules,
        expected_guard:'0000000000000001-0000000000000002',previous_count:1,previous_enabled:1};
      if(input.action==='apply'){
        state.savedImport=input;
        if(state.importConflict){status=409;body={ok:false,error:'Saved table changed'};}
        else state.forwardBody={rules:rules.map(r=>({...r,installed:false})),max:8};
      }
    } else if (url.pathname === '/api/tailnet-forward/export') {
      body={format:'homelab-service-rules/v1',rules:(state.forwardBody||{rules:[]}).rules};
    } else if (url.pathname === '/api/tailnet-forward/check') {
      const input=route.request().postDataJSON();(state.checkPosts=state.checkPosts||[]).push(input);
      if(state.checkStatus){status=state.checkStatus;body={ok:false,error:'another check is running'};}
      else {status=202;body={ok:true,state:'pending'};
        const rule=(state.forwardBody.rules||[]).find(r=>r.index===input.index&&r.rule_token===input.rule_token);
        if(rule)rule.destination_check={state:'reachable',summary:'This gateway completed a TCP handshake with the Tailnet destination',next_step:'Enable the rule, then connect from an allowed LAN client',checked_ip:'100.64.0.9',latency_ms:42,age_s:0};}
    } else if (url.pathname === '/api/tailnet-forward') {
      if (state.forwardFailures) { state.forwardFailures--; status = 503; }
      if (route.request().method() === 'POST') {
        state.savedForward = route.request().postDataJSON();
        body = {ok: true};
      } else {
        body = state.forwardBody || {rules: [], max: 8, uplink_ip: '192.0.2.20', observation: 'passive_snapshot'};
      }
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
    // Selective service gateway: installed mapping != verified service.
    const forwardRule = {name: 'Synthetic broker', enabled: true, installed: true,
      protocol: 'tcp', listen_port: 18830, destination_port: 1883,
      tailnet_destination: '100.64.0.2', allowed_source_subnet: '192.0.2.42/32',
      accepted_packets: 5, blocked_packets: 2, error: '', diagnostic: {
        code: 'mapping_installed', summary: 'Mapping installed; service not tested',
        next_step: 'Connect from an allowed LAN client.', service_status: 'not_tested', data_plane_status: 'not_verified'}};
    const forwardBody = {max: 8, rules: [forwardRule], uplink_ip: '192.0.2.20', observation: 'passive_snapshot'};
    f = await fixture(browser, {page: 'network', forwardBody});
    await f.page.waitForFunction(() => document.getElementById('tf-context').textContent.startsWith('Saved configuration'));
    assert.equal(await f.page.locator('.tf-runtime-badge').textContent(), forwardRule.diagnostic.summary);
    await f.page.locator('.tf-diagnostic summary').click();
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /192\.0\.2\.20:18830 → 100\.64\.0\.2:1883/);
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /not proof of service replies/);
    assert.deepEqual(f.externalRequests, []);
    await f.page.locator('.tf-name').fill('Draft name');
    assert.equal(await f.page.locator('.tf-runtime-badge').textContent(), 'Unsaved');
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /Save and reload/);
    f.state.forwardFailures = 1; await f.page.locator('#tf-reload').click();
    await f.page.waitForFunction(() => document.getElementById('tf-badge').textContent === 'Unavailable');
    assert.equal(await f.page.locator('.tf-name').inputValue(), 'Draft name');
    assert.equal(await f.page.locator('#tf-save').isDisabled(), true);
    assert.equal(await f.page.locator('#tf-add').isDisabled(), true);
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /not evidence/);
    await f.page.locator('#tf-reload').click();
    await f.page.waitForFunction(() => document.getElementById('tf-context').textContent.startsWith('Saved configuration'));
    await f.page.locator('#tf-add').click();
    assert.equal(await f.page.locator('.tf-enabled').nth(1).isChecked(), false);
    assert.equal(await f.page.locator('.tf-name').nth(0).inputValue(), forwardRule.name);
    await f.page.locator('.tf-name').nth(1).fill('New service');
    await f.page.locator('.tf-listen').nth(1).fill('2222.5');
    await f.page.locator('.tf-dest').nth(1).fill('100.64.0.3');
    await f.page.locator('.tf-dport').nth(1).fill('22');
    await f.page.locator('.tf-cidr').nth(1).fill('192.0.2.42/32');
    await f.page.locator('#tf-save').click();
    assert.equal(f.state.savedForward, undefined);
    await f.page.locator('.tf-listen').nth(1).fill('2222');
    await f.page.locator('#tf-save').click();
    await f.page.waitForFunction(() => document.getElementById('tf-context').textContent.startsWith('Saved configuration'));
    assert.equal(f.state.savedForward.rules[1].enabled, false);
    assert.deepEqual(Object.keys(f.state.savedForward.rules[0]).sort(),
      ['name','enabled','protocol','listen_port','tailnet_destination','destination_port','allowed_source_subnet'].sort());
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Malformed status must not wipe the saved/draft rule table or enable Save.
    f = await fixture(browser, {page: 'network', forwardBody: {rules: {}, max: 8}});
    await f.page.waitForFunction(() => document.getElementById('tf-badge').textContent === 'Unavailable');
    assert.equal(await f.page.locator('#tf-save').isDisabled(), true);
    assert.equal(await f.page.locator('#tf-add').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Remote fields are text, not HTML, and /0 exposure is explicit on mobile.
    f = await fixture(browser, {page: 'network', viewport: {width: 390, height: 844}, forwardBody: {
      ...forwardBody, rules: [{...forwardRule, name: '<img src=x onerror="window.tfInjected=1">',
        allowed_source_subnet: '0.0.0.0/0', diagnostic: {...forwardRule.diagnostic,
          next_step: '<img src=x onerror="window.tfInjected=1">'}}]}});
    await f.page.waitForFunction(() => document.getElementById('tf-context').textContent.startsWith('Saved configuration'));
    await f.page.locator('.tf-diagnostic summary').click();
    assert.equal(await f.page.locator('#tf-list img').count(), 0);
    assert.equal(await f.page.evaluate(() => window.tfInjected), undefined);
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /Broad exposure/);
    const bounds = await f.page.locator('#tf-list').boundingBox();
    assert.ok(bounds.width > 200 && bounds.x + bounds.width <= 391);
    if (process.env.GATEWAY_SCREENSHOT === '1') {
      await f.page.locator('.tf-row').screenshot({path: path.join(__dirname, '../build/gateway-diagnostics-mobile.png')});
    }
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Template drafts are OFF and require actual destination/source parameters.
    f=await fixture(browser,{page:'network'});
    await f.page.waitForFunction(()=>!document.getElementById('tf-add').disabled);
    await f.page.locator('#tf-template').selectOption('home-assistant');await f.page.locator('#tf-add').click();
    assert.equal(await f.page.locator('.tf-enabled').isChecked(),false);
    assert.equal(await f.page.locator('.tf-listen').inputValue(),'18123');
    assert.equal(await f.page.locator('.tf-dport').inputValue(),'8123');
    assert.equal(await f.page.locator('.tf-dest').inputValue(),'');assert.equal(await f.page.locator('.tf-cidr').inputValue(),'');
    assert.equal(f.state.savedForward,undefined);assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Import preview cannot save; apply needs explicit confirmation, stays OFF,
    // excludes concurrent editor writes, and never retries a stale-table conflict.
    const importFile={name:'fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({format:'homelab-service-rules/v1',rules:[{name:'Remote SSH',enabled:true,protocol:'tcp',listen_port:2222,tailnet_destination:'100.64.0.2',destination_port:22,allowed_source_subnet:'192.0.2.42/32'}]}))};
    for(const conflict of [false,true]){
      f=await fixture(browser,{page:'network',importConflict:conflict,importDelay:100});
      await f.page.waitForFunction(()=>!document.getElementById('tf-add').disabled);
      await f.page.getByText('Back up or import saved service rules',{exact:true}).click();
      await f.page.locator('#tf-import-file').setInputFiles(importFile);
      await f.page.waitForFunction(()=>!document.getElementById('tf-import-confirm').disabled);
      assert.match(await f.page.locator('#tf-import-preview').textContent(),/DISABLED/);
      assert.equal(f.state.savedImport,undefined);assert.equal(await f.page.locator('#tf-import-apply').isDisabled(),true);
      await f.page.locator('#tf-import-confirm').check();await f.page.locator('#tf-import-apply').click();
      assert.equal(await f.page.locator('#tf-add').isDisabled(),true);assert.equal(await f.page.locator('#tf-import-file').isDisabled(),true);
      await f.page.waitForFunction(()=>document.getElementById('tf-import-preview').textContent.includes('Imported saved')||document.getElementById('tf-import-preview').textContent.includes('no automatic retry'));
      assert.equal(f.state.savedImport.confirm_replace,true);assert.equal(f.state.savedImport.rules[0].enabled,false);
      assert.equal(f.calls.filter(p=>p==='/api/tailnet-forward/import').length,2);
      if(conflict){assert.equal(await f.page.locator('#tf-save').isDisabled(),true);assert.equal(await f.page.locator('#tf-import-apply').isDisabled(),true);}
      else assert.equal(await f.page.locator('.tf-enabled').isChecked(),false);
      assert.deepEqual(f.errors,[]);await f.context.close();count++;
    }
    // Operational UI uses text nodes and MAC-bound submissions, never proof-of-boot labels.
    f=await fixture(browser,{page:'operations'});
    await f.page.waitForFunction(()=>document.getElementById('ops-settings-save').disabled===false);
    assert.match(await f.page.locator('#ops-summary').textContent(),/sockets 12\/31/);
    await f.page.locator('#ops-settings-save').click();
    await f.page.waitForFunction(()=>document.getElementById('ops-refresh').disabled===false);
    assert.equal(f.state.savedOperation.action,'settings');
    assert.equal(f.state.savedOperation.remote_commands,false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'operations',operationsBody:{devices:{},events:[],monitoring:false,guard:false}});
    await f.page.waitForFunction(()=>document.getElementById('ops-summary').textContent.includes('Incomplete'));
    assert.equal(await f.page.locator('#ops-settings-save').isDisabled(),true);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'operations',operationsBody:{devices:[{index:0,mac:'02:00:00:00:00:01',name:'Fixture',target:'192.0.2.1',monitor:false,notify:false,host_port:22,service_port:0,timeout_s:60,interval_s:60,max_checks:10,kind:0,scope:0,state:'idle'}],events:[],monitoring:false,guard:false,remote_commands:false,recovery_state:'idle',packet_sent:false,minimum_internal:16384,minimum_largest:8192,socket_reserve:4,interval_s:60}});
    await f.page.waitForFunction(()=>!document.getElementById('ops-settings-save').disabled);
    assert.match(await f.page.locator('#ops-job').textContent(),/partial send may have occurred/);
    await f.page.locator('#ops-devices input[type=text]').fill('draft.example');
    f.state.operationsFailures=1;await f.page.locator('#ops-refresh').click();
    await f.page.waitForFunction(()=>document.getElementById('ops-summary').textContent.includes('stale'));
    assert.equal(await f.page.locator('#ops-devices input[type=text]').inputValue(),'draft.example');
    for(const button of await f.page.locator('#ops-devices button').all()) assert.equal(await button.isDisabled(),true);
    assert.equal(await f.page.locator('#ops-cancel').isDisabled(),true);
    await f.page.locator('#ops-refresh').click();await f.page.waitForFunction(()=>!document.getElementById('ops-settings-save').disabled);
    for(const button of await f.page.locator('#ops-devices button').all()) assert.equal(await button.isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'operations'});
    await f.page.waitForFunction(()=>!document.getElementById('health-save').disabled);
    await f.page.locator('label:has(#health-enabled)').click();assert.equal(await f.page.locator('#health-enabled').isChecked(),true);await f.page.locator('#health-dns').fill('operator.example');
    await f.page.locator('#health-save').click();await f.page.waitForFunction(()=>!document.getElementById('ops-refresh').disabled);
    assert.equal(f.state.savedOperation.action,'health');assert.equal(f.state.savedOperation.enabled,true);
    assert.equal(f.state.savedOperation.dns_name,'operator.example');
    f.state.healthFailures=1;await f.page.locator('#ops-refresh').click();
    await f.page.waitForFunction(()=>document.getElementById('health-status').textContent.includes('unavailable'));
    assert.equal(await f.page.locator('#health-save').isDisabled(),true);
    assert.equal(await f.page.locator('#ops-settings-save').isDisabled(),false); // Independent read failure.
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Profiles: token-bound preview, conflict re-preview, apply, rollback.
    f=await fixture(browser,{page:'system'});
    await f.page.waitForFunction(()=>document.getElementById('profile-select').options.length===3&&!document.getElementById('profile-preview').disabled);
    assert.equal(await f.page.locator('#profile-apply').isDisabled(),true);
    await f.page.locator('#profile-select').selectOption('monitoring');await f.page.locator('#profile-preview').click();
    await f.page.waitForFunction(()=>document.getElementById('profile-changes').children.length===2&&!document.getElementById('profile-apply').disabled);
    assert.match(await f.page.locator('#profile-changes').textContent(),/off → on.*already on \(unchanged\)/);
    assert.equal(await f.page.locator('#profile-steps-title').isHidden(),false);
    await f.page.locator('#profile-select').selectOption('gateway');assert.equal(await f.page.locator('#profile-apply').isDisabled(),true);
    await f.page.locator('#profile-select').selectOption('monitoring');await f.page.locator('#profile-preview').click();
    await f.page.waitForFunction(()=>!document.getElementById('profile-apply').disabled);
    f.state.profileConflict=1;await f.page.locator('#profile-apply').click();
    await f.page.waitForFunction(()=>document.getElementById('profile-status').textContent.includes('preview again'));
    assert.equal(await f.page.locator('#profile-apply').isDisabled(),true); // stale preview cannot be reused
    await f.page.locator('#profile-preview').click();await f.page.waitForFunction(()=>!document.getElementById('profile-apply').disabled);
    await f.page.locator('#profile-apply').click();
    await f.page.waitForFunction(()=>document.getElementById('profile-status').textContent.includes('Applied'));
    assert.match(await f.page.locator('#profile-status').textContent(),/Active: Monitoring/);
    const applied=f.state.profilePosts.filter(x=>x.action==='apply');assert.equal(applied.length,2);
    assert.deepEqual(Object.keys(applied[1]).sort(),['action','profile','token']);assert.equal(applied[1].token,102);
    f.page.once('dialog',d=>d.accept());await f.page.locator('#profile-rollback').click();
    await f.page.waitForFunction(()=>document.getElementById('profile-status').textContent.includes('Rolled back'));
    assert.match(await f.page.locator('#profile-status').textContent(),/Left as you changed them: Health Monitor worker/);
    assert.equal(await f.page.locator('#profile-rollback').isDisabled(),true);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Guided setup: exposure confirmation, snapshot, focus, diff and restore.
    f=await fixture(browser,{page:'status',tailscaleSettings:{hostname:'fixture',advertise_routes:'',auth_key:'never-sent'}});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===12);
    assert.equal(await f.page.locator('#wizard-panel').isHidden(),true);
    await f.page.locator('#wizard-list button',{hasText:'Subnet router'}).click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden&&!document.getElementById('wizard-checks').textContent.includes('checking'));
    assert.match(await f.page.locator('#wizard-checks').textContent(),/✗ Connected to the Tailscale/);
    assert.equal(await f.page.locator('#wizard-start').isDisabled(),true); // exposure needs explicit confirmation
    await f.page.locator('#wizard-exposure').check();assert.equal(await f.page.locator('#wizard-start').isDisabled(),false);
    await f.page.locator('#wizard-start').click();
    await f.page.waitForFunction(()=>document.getElementById('page-tailscale').classList.contains('active')&&document.querySelector('.wizard-focus #ts-routes, #ts-routes.wizard-focus'));
    await f.page.locator('#wizard-verify').click();
    await f.page.waitForFunction(()=>document.getElementById('wizard-result').textContent.includes('No saved setting changed'));
    assert.equal(await f.page.locator('#wizard-restore').isHidden(),true);
    f.state.tailscaleSettings={hostname:'fixture',advertise_routes:'192.168.1.0/24',auth_key:'never-sent'};
    await f.page.locator('#wizard-verify').click();
    await f.page.waitForFunction(()=>document.getElementById('wizard-result').textContent.includes('advertise_routes'));
    assert.doesNotMatch(await f.page.locator('#wizard-result').textContent(),/never-sent/);
    f.page.once('dialog',d=>d.accept());await f.page.locator('#wizard-restore').click();
    await f.page.waitForFunction(()=>document.getElementById('wizard-result').textContent.includes('restored'));
    assert.deepEqual(f.state.savedTailscale,{settings:{hostname:'fixture',advertise_routes:''}}); // snapshot, no secret
    await f.page.locator('#wizard-close').click();assert.equal(await f.page.locator('#wizard-panel').isHidden(),true);
    assert.equal(await f.page.locator('.wizard-focus').count(),0);
    assert.deepEqual(f.errors,[]);assert.deepEqual(f.externalRequests,[]);await f.context.close();count++;
    // MQTT badge reports bounded backoff and incomplete settings honestly.
    f=await fixture(browser,{mqttBody:{...mqtt,connected:false,status:{configured:true,connecting:false,retry_level:2,retry_in_seconds:17,discovery_pending:false,discovery_entities:0}}});
    await f.page.waitForFunction(()=>document.getElementById('mqtt-badge').textContent==='Retry in 17 s');
    await f.context.close();count++;
    f=await fixture(browser,{mqttBody:{...mqtt,connected:false,status:{configured:false,connecting:false,retry_level:0,retry_in_seconds:0,discovery_pending:false,discovery_entities:0}}});
    await f.page.waitForFunction(()=>document.getElementById('mqtt-badge').textContent==='Incomplete settings');
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Capability manifest gates controls (advisory) and guide buttons.
    f=await fixture(browser,{capabilityBody:{schema:2,features:[
      {id:'smart-recovery',compiled:true,hardware_supported:true,configured:true,active:false,verified:false,experimental:true,evidence:'Fixture'},
      {id:'mqtt',compiled:false,hardware_supported:null,configured:false,active:false,verified:false,experimental:false,evidence:'Fixture: not compiled'},
      {id:'ntfy',compiled:true,hardware_supported:true,configured:true,active:null,verified:false,experimental:false,evidence:'Fixture'}]}});
    await f.page.waitForFunction(()=>document.getElementById('mqtt-card').classList.contains('capability-unavailable'));
    assert.match(await f.page.locator('#mqtt-card .capability-note').textContent(),/Not available in this firmware — Fixture: not compiled/);
    assert.equal(await f.page.locator('#mqtt-card .card-body').evaluate(e=>e.inert),true);
    assert.equal(await f.page.locator('#ntfy-card').evaluate(e=>e.classList.contains('capability-unavailable')),false);
    assert.equal(await f.page.locator('#wizard-list button',{hasText:/^MQTT$/}).isDisabled(),true);
    assert.equal(await f.page.locator('#wizard-list button',{hasText:'ntfy'}).isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Service Gateway: test a saved (still disabled) rule's Tailnet destination.
    const tfRule=()=>({index:0,rule_token:77,name:'NAS',enabled:false,installed:false,protocol:'tcp',listen_port:15000,tailnet_destination:'100.64.0.9',
      destination_port:5000,allowed_source_subnet:'192.168.1.20/32',accepted_packets:0,blocked_packets:0,error:'',diagnostic:{code:'disabled',summary:'Rule disabled',next_step:'Enable it'},
      activity:{last_accepted_age_s:null,last_rejected_age_s:12,service_reply_age_s:null}});
    f=await fixture(browser,{page:'network',forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.querySelector('.tf-test')&&!document.querySelector('.tf-test').disabled);
    assert.equal(await f.page.locator('.tf-check-state').textContent(),'Not tested');
    assert.match(await f.page.locator('.tf-activity').textContent(),/Last accepted: never this boot · last rejected: 12 s ago · reply from the Tailnet service: none seen/);
    await f.page.locator('.tf-test').click();
    await f.page.waitForFunction(()=>document.querySelector('.tf-check-state')&&document.querySelector('.tf-check-state').textContent==='Reachable from gateway (42 ms)',null,{timeout:10000});
    assert.deepEqual(f.state.checkPosts,[{index:0,rule_token:77}]);
    assert.match(await f.page.locator('.tf-check-next').textContent(),/connect from an allowed LAN client/);
    await f.page.locator('.tf-name').fill('NAS edited');
    assert.equal(await f.page.locator('.tf-test').isDisabled(),true); // tests the saved rule only
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'network',checkStatus:429,forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.querySelector('.tf-test')&&!document.querySelector('.tf-test').disabled);
    await f.page.locator('.tf-test').click();
    await f.page.waitForFunction(()=>document.querySelector('.tf-check-state').textContent.includes('Test not started: another check is running'));
    assert.equal(await f.page.locator('.tf-test').isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Primary guide runs one destination test inline from "Check result".
    f=await fixture(browser,{page:'status',forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===12);
    await f.page.locator('#sg-home-guide').click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-checks').textContent.includes('checking'));
    assert.match(await f.page.locator('#wizard-checks').textContent(),/✓ A free service rule slot/);
    await f.page.locator('#wizard-exposure').check();await f.page.locator('#wizard-start').click();
    await f.page.waitForFunction(()=>document.getElementById('page-network').classList.contains('active'));
    await f.page.locator('#wizard-verify').click();
    await f.page.waitForFunction(()=>document.getElementById('wizard-result').textContent.includes('Destination test for “NAS”'),null,{timeout:10000});
    assert.deepEqual(f.state.checkPosts,[{index:0,rule_token:77}]);
    assert.match(await f.page.locator('#wizard-result').textContent(),/1 with a reachable destination test/);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'status'});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===12);
    const first=f.page.locator('#wizard-list button').first();
    assert.equal(await first.textContent(),'Publish a Tailnet service to the LAN');
    assert.equal(await first.evaluate(e=>e.classList.contains('btn-primary')),true);
    await f.page.waitForFunction(()=>document.getElementById('sg-home-summary').textContent.startsWith('No service rules yet'));
    assert.equal(await f.page.locator('#sg-home-badge').textContent(),'0 / 8');
    await f.page.locator('#sg-home-guide').click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden&&document.getElementById('wizard-title').textContent==='Publish a Tailnet service to the LAN');
    assert.equal(await f.page.locator('#wizard-exposure-row').isHidden(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Templates: risk hint, first free listen port per protocol, UDP template.
    f=await fixture(browser,{page:'network'});
    await f.page.waitForFunction(()=>!document.getElementById('tf-add').disabled);
    await f.page.locator('#tf-template').selectOption('mqtt');
    assert.match(await f.page.locator('#tf-template-hint').textContent(),/Unencrypted/);
    await f.page.locator('#tf-template').selectOption('ssh');await f.page.locator('#tf-add').click();await f.page.locator('#tf-add').click();
    assert.deepEqual(await f.page.locator('.tf-listen').evaluateAll(e=>e.map(x=>x.value)),['2222','2223']);
    await f.page.locator('#tf-template').selectOption('syslog');await f.page.locator('#tf-add').click();
    assert.equal(await f.page.locator('.tf-proto').nth(2).inputValue(),'udp');assert.equal(await f.page.locator('.tf-listen').nth(2).inputValue(),'15514');
    assert.equal(await f.page.locator('.tf-enabled:checked').count(),0);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Home card lists open temporary access with the soonest closure.
    f=await fixture(browser,{page:'status',forwardBody:{rules:[{index:0,rule_token:5,name:'NAS',enabled:true,installed:true,protocol:'tcp',listen_port:15001,tailnet_destination:'100.64.0.9',destination_port:5001,allowed_source_subnet:'192.168.1.20/32',accepted_packets:3,blocked_packets:0,error:''}],max:8},
      leasesBody:[{index:0,rule_token:5,temporary:true,effective_enabled:true,remaining_s:840,status:'active'},{index:1,rule_token:6,temporary:true,effective_enabled:false,remaining_s:0,status:'expired'}]});
    await f.page.waitForFunction(()=>document.getElementById('sg-home-summary').textContent.includes('temporary'));
    assert.match(await f.page.locator('#sg-home-summary').textContent(),/1 rule\(s\) · 1 enabled · 1 installed .* 1 temporary rule\(s\) open; the next closes in 14 min\./);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // ntfy system events are opt-in and saved with the rest of the card.
    f=await fixture(browser,{});await loaded(f.page);
    assert.equal(await f.page.locator('#ntfy-system-events').isChecked(),false);
    await f.page.locator('label:has(#ntfy-system-events)').click();
    await f.page.waitForFunction(()=>!document.getElementById('ntfy-save').disabled);
    await f.page.locator('#ntfy-save').click();
    for(let i=0;i<50&&!f.state.savedNtfy;i++)await f.page.waitForTimeout(100);
    assert.equal(f.state.savedNtfy.system_events,true);assert.equal(f.state.savedNtfy.tailscale_alerts,false); // other switches unchanged
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    console.log(`PASS: ${count} browser scenarios (synthetic APIs, including operational/health settings, profiles, guided setup, MQTT backoff, Service Gateway destination tests and malformed/stale-state refusal)`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
