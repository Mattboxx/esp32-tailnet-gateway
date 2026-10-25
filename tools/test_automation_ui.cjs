/* Run with Node.js and Playwright. Uses the actual SPA with synthetic APIs;
 * never reads device credentials or changes a running board. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();
const mqtt = { enabled: true, connected: true, uri: 'mqtts://broker.example',
  base_topic: 'fixture/router', interval_seconds: 30, broker_watchdog_timeout_seconds: 300,
  broker_watchdog_wol_mac: '02:00:00:00:00:01' };
const ntfy = { enabled: true, server: 'https://notify.example', topic: 'fixture',
  info_enabled: true, commands_enabled: true, last_publish_ok: true };
const updates = { enabled: false, auto_install: false, beta_channel: false,
  install_hour: -1, busy: false, checked: false, update_available: false,
  status: 'Periodic checks disabled', latest_version: '' };

async function fixture(browser, options = {}) {
  const context = await browser.newContext({ viewport: options.viewport || { width: 1280, height: 800 }, locale: options.locale || 'en-US' });
  // Expert flows below use advanced sections; simple mode has its own scenario.
  if (options.simpleMode !== true) await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
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
    if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
    calls.push(url.pathname);
    let body = {};
    let status = 200;
    if (url.pathname === '/api/auth/status') {
      body = { password_set: true, auth_enabled: !state.lockOff, auth_required: !state.lockOff,
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
        state.updatesBody = { ...(state.updatesBody || updates), ...state.savedUpdates };
      }
      if (state.updatesFailures) { state.updatesFailures--; status = 503; }
      body = state.updatesBody || updates;
    } else if (url.pathname === '/api/system/updates/install' || url.pathname === '/api/system/updates/check') {
      state.updatesBody = { ...(state.updatesBody || updates), busy: true, status: 'Checking GitHub releases' };
      body = { ok: true }; status = 202;
    } else if (url.pathname === '/api/ethernet') {
      if (route.request().method() === 'POST') { state.savedEthernet = route.request().postDataJSON(); body = {ok: true, restart_required: true}; }
      else body = state.ethernetBody || {config:{enabled:false,chip:'w5500',spi_host:2,spi_mhz:20,sclk:12,mosi:11,miso:13,cs:10,int:14,rst:9,static_ip:false,ip:'',netmask:'',gateway:'',dns:'',preference:'wifi_first'},
        status:{compiled:false,enabled_at_boot:false,driver_started:false,link_up:false,has_ip:false,selected_uplink:false,restart_required:false,link_changes:0,ip:'',netmask:'',gateway:'',error:''}};
    } else if (url.pathname === '/api/service-watch') {
      if (route.request().method() === 'POST') { const w = route.request().postDataJSON(); state.savedWatch = w;
        if (w.interval_s < 60) { status = 400; body = {ok: false, error: 'interval must be 60-86400 s'}; } else { state.watchBody = w; body = w; } }
      else body = state.watchBody || {enabled: false, notify: false, interval_s: 900};
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
    } else if (url.pathname === '/api/network' && state.networkBody) {
      body = state.networkBody;
    } else if (url.pathname === '/api/system/migration') {
      if (route.request().method() === 'POST') { state.savedMigration = route.request().postDataJSON();
        state.migrationBody = {...state.migrationBody, busy: true, state: 'downloading', progress: 40, target: 'v3.0.0'}; status = 202; body = {ok: true}; }
      else body = state.migrationBody || {layout: '3.x', needed: false};
    } else if (url.pathname === '/api/cellular') {
      if (route.request().method() === 'POST') { state.savedCellular = route.request().postDataJSON(); body = {ok: true, restart_required: true}; }
      else body = state.cellularBody || {};
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
    } else if (url.pathname === '/api/events') {
      const cfg = state.histConfig || {events: false, metrics: false, snapshots: false};
      body = {config: cfg, persist: true, storage: true, boot: 3, now: 1700000000, uptime: 600, events: cfg.events ? (state.histEvents || []) : []};
    } else if (url.pathname === '/api/history/config') {
      state.savedHistory = route.request().postDataJSON(); state.histConfig = {...(state.histConfig || {}), ...state.savedHistory}; body = {ok: true, persist: true};
    } else if (url.pathname === '/api/history') {
      const cfg = state.histConfig || {events: false, metrics: false, snapshots: false};
      body = {config: cfg, persist: true, storage: true, boot: 3, now: 1700000000, uptime: 600, range: url.searchParams.get('range'), step: 60,
        points: state.histPoints || []};
    } else if (url.pathname === '/api/system/snapshots') {
      if (route.request().method() === 'POST') { (state.snapPosts = state.snapPosts || []).push(route.request().postDataJSON()); body = {ok: true}; }
      else body = {available: true, before_update: false, restore_pending: false, slots: [
        {slot: 1, valid: true, seq: 4, t: 1700000000, reason: 'update', firmware: '3.0.0<b>x</b>'}, {slot: 2, valid: false, seq: 0, t: 0, reason: '', firmware: ''},
        {slot: 3, valid: false, seq: 0, t: 0, reason: '', firmware: ''}]};
    } else if (url.pathname === '/api/tailnet-names') {
      if (route.request().method() === 'POST') { state.savedNames = route.request().postDataJSON(); body = {ok: true}; }
      else body = {enabled: !!(state.savedNames && state.savedNames.enabled), lan: false, relay: true, lan_listening: false, peers: 5};
    } else if (url.pathname === '/api/notify') {
      if (route.request().method() === 'POST') { state.savedNotify = route.request().postDataJSON(); body = {ok: true}; }
      else body = {events: 'problems', waiting: 0, dropped: 0,
        telegram: {enabled: !!state.savedNotify, has_token: !!state.savedNotify, chat: state.savedNotify ? state.savedNotify.telegram.chat : '', sent: 0, failed: 1, last_error: 'Telegram answered 401: Unauthorized'},
        email: {enabled: false, host: '', port: 465, security: 'tls', user: '', has_password: false, from: '', to: '', sent: 0, failed: 0, last_error: ''}};
    } else if (url.pathname === '/api/notify/test') {
      state.notifyTest = route.request().postDataJSON(); body = {ok: true, queued: true};
    } else if (url.pathname === '/api/ddns') {
      if (route.request().method() === 'POST') { state.savedDdns = route.request().postDataJSON(); body = {ok: true}; }
      else body = {provider: 'off', name: '', zone: '', has_token: false, has_url: false, status: 'Not updated yet', public_ip: '203.0.113.7', updated_ip: '', updated_ago_s: -1, running: false};
    } else if (url.pathname === '/api/diag/speedtest') {
      if (route.request().method() === 'POST') { state.savedSpeed = route.request().postDataJSON(); state.speedPolls = 0; body = {ok: true}; }
      else { state.speedPolls = (state.speedPolls || 0) + 1;
        body = state.speedPolls < 2 ? {running: true, bytes: 1048576, elapsed_ms: 1000, kbps: 8389, first_byte_ms: 40, http: 200, result: ''}
                                    : {running: false, bytes: 12582912, elapsed_ms: 10000, kbps: 10066, first_byte_ms: 40, http: 200, result: 'time limit reached'}; }
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
    // Nothing of the dashboard is rendered behind the sign-in screen (iOS keyboard scroll).
    assert.equal(await f.page.evaluate(() => document.body.classList.contains('auth-open')
      && getComputedStyle(document.querySelector('.page-container')).visibility === 'hidden'
      && getComputedStyle(document.querySelector('.nav')).visibility === 'hidden'
      && getComputedStyle(document.body).overflow === 'hidden'), true);
    f.state.authenticated = true;
    await f.page.evaluate(() => { window.loginPasswordRequest = () => Promise.resolve({ ok: true }); });
    await f.page.locator('#login-pw').fill('synthetic-password');
    await f.page.locator('#loginSubmitBtn').click();
    await loaded(f.page);
    assert.equal(await f.page.evaluate(() => document.body.classList.contains('auth-open')), false);
    assert.equal(f.calls.filter(url => url === '/api/wol').length, 1);
    assert.equal(await f.page.locator('#mqtt-watchdog-target').inputValue(), mqtt.broker_watchdog_wol_mac);
    assert.deepEqual(f.errors, []);
    await f.context.close(); count++;
    // Status refresh: no read while the browser tab is hidden; a stale page
    // refreshes once on return, a fresh one does not.
    f = await fixture(browser, { page: 'status' });
    await f.page.waitForFunction(() => /^Last updated \d/.test(document.getElementById('status-updated').textContent));
    const statusReads = () => f.calls.filter(p => p === '/api/status').length;
    const setHidden = hidden => f.page.evaluate(h => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => h });
      document.dispatchEvent(new Event('visibilitychange'));
    }, hidden);
    let reads = statusReads();
    await setHidden(false); await f.page.waitForTimeout(300);
    assert.equal(statusReads(), reads, 'fresh page must not refresh on return');
    await f.page.evaluate(() => { s_status_fetched = 0; });
    await setHidden(true); await f.page.waitForTimeout(300);
    assert.equal(statusReads(), reads, 'hidden page must not read status');
    await setHidden(false);
    await f.page.waitForTimeout(300);
    assert.equal(statusReads(), reads + 1);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Cellular uplink card: secrets are write-only (placeholder only), an empty
    // field keeps them, enabling requires the data notice, status is readable.
    {
      const cellConfig = {enabled: false, mode: 'failover', roaming: false, data_ack: false, uart: 1, baud: 115200, tx: 17, rx: 18, rts: -1, cts: -1,
        pwrkey: -1, pwrkey_active_high: false, apn: 'internet.example', user: '', has_password: true, has_pin: true};
      f = await fixture(browser, { page: 'network', cellularBody: {config: cellConfig, status: {enabled_at_boot: true, task_running: true, state: 'connected',
        registration: 1, rssi_dbm: -77, model: 'FIXTURE-MODEM', operator: 'Example Mobile', ip: '10.64.1.2', has_ip: true, selected_uplink: false,
        restart_required: false, connects: 1, bytes_in: 2048, bytes_out: 1024, error: '', qualification: 'experimental'}} });
      await f.page.waitForFunction(() => document.getElementById('cell-badge').textContent === 'Connected');
      assert.match(await f.page.locator('#cell-status').textContent(), /Connected · Example Mobile · -77 dBm · IP 10\.64\.1\.2/);
      assert.equal(await f.page.locator('#cell-pin').inputValue(), '');
      assert.equal(await f.page.locator('#cell-pin').getAttribute('placeholder'), 'Saved — leave empty to keep');
      assert.equal(await f.page.locator('#cell-password').getAttribute('placeholder'), 'Saved — leave empty to keep');
      await f.page.locator('label:has(#cell-enabled)').click();
      await f.page.locator('#cell-save').click();
      await f.page.waitForFunction(() => document.getElementById('cell-status').textContent.includes('acknowledge the mobile data notice'));
      assert.equal(f.state.savedCellular, undefined);
      await f.page.locator('label:has(#cell-ack)').click();
      await f.page.locator('#cell-save').click();
      await f.page.waitForFunction(() => document.getElementById('cell-status').textContent.startsWith('Connected'));
      await f.page.waitForTimeout(300);
      assert.equal(f.state.savedCellular.enabled, true); assert.equal(f.state.savedCellular.data_ack, true);
      assert.equal('pin' in f.state.savedCellular, false); assert.equal('password' in f.state.savedCellular, false);
      await f.page.locator('#cell-pin').fill('1234'); await f.page.locator('#cell-save').click(); await f.page.waitForTimeout(300);
      assert.equal(f.state.savedCellular.pin, '1234');
      assert.deepEqual(f.errors, []); await f.context.close(); count++;
    }
    // Layout migration card: only on the 2.x table, explicit confirmation, progress.
    f = await fixture(browser, { page: 'system/maintenance' });
    await f.page.waitForFunction(() => document.getElementById('sys-updates-reload'));
    await f.page.waitForTimeout(500);
    assert.equal(await f.page.locator('#mig-card').isHidden(), true);
    await f.context.close(); count++;
    f = await fixture(browser, { page: 'system/maintenance', migrationBody: {layout: '2.x', bridge: true, needed: true, supported: true, busy: false,
      physical_flash: 16777216, state: 'idle', progress: 0, target: '', error: ''} });
    await f.page.waitForFunction(() => !document.getElementById('mig-card').hidden);
    assert.equal(await f.page.locator('#mig-start').isDisabled(), true);
    await f.page.locator('label:has(#mig-confirm)').click();
    assert.equal(await f.page.locator('#mig-start').isDisabled(), false);
    f.page.once('dialog', dialog => dialog.accept());
    await f.page.locator('#mig-start').click();
    await f.page.waitForFunction(() => document.getElementById('mig-status').textContent.includes('Downloading and checking 3.0'));
    assert.deepEqual(f.state.savedMigration, {confirm: 'MIGRATE'});
    assert.match(await f.page.locator('#mig-status').textContent(), /v3\.0\.0 · 40%/);
    assert.equal(await f.page.locator('#mig-progress-wrap').isHidden(), false);
    assert.equal(await f.page.locator('#mig-start').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { page: 'system/maintenance', migrationBody: {layout: '2.x', bridge: true, needed: true, supported: false, busy: false,
      physical_flash: 4194304, state: 'idle', progress: 0, target: '', error: ''} });
    await f.page.waitForFunction(() => document.getElementById('mig-status').textContent.includes('needs 8 MB'));
    assert.equal(await f.page.locator('#mig-confirm').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Tabs follow overview → connectivity → protection → services → tools → admin,
    // and every tab has an icon.
    f = await fixture(browser);
    await loaded(f.page);
    assert.deepEqual(await f.page.evaluate(() => [...document.querySelectorAll('#navTabs .nav-tab')].map(t => t.dataset.page)),
      ['status', 'network', 'tailscale', 'firewall', 'operations', 'automation', 'tools', 'system']);
    assert.equal(await f.page.locator('#navTabs .nav-tab:not(:has(svg))').count(), 0);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Phone menu: the same button opens and closes the drawer, which sits
    // below the bar so the button stays tappable; picking a tab closes it.
    f = await fixture(browser, { viewport: { width: 390, height: 844 } });
    await loaded(f.page);
    const ham = f.page.locator('#navHamBtn'), drawer = f.page.locator('#navTabs');
    await ham.click();
    assert.equal(await drawer.isVisible(), true);
    assert.equal(await ham.getAttribute('aria-expanded'), 'true');
    assert.equal(await ham.getAttribute('aria-label'), 'Close menu');
    assert.equal(await f.page.locator('#navHamClose').isVisible(), false);
    const hamBox = await ham.boundingBox(), drawerBox = await drawer.boundingBox();
    assert.ok(drawerBox.y >= hamBox.y + hamBox.height, 'drawer must not cover the menu button');
    await ham.click();
    assert.equal(await drawer.isVisible(), false);
    assert.equal(await ham.getAttribute('aria-expanded'), 'false');
    assert.equal(await ham.getAttribute('aria-label'), 'Open menu');
    assert.equal(await f.page.evaluate(() => document.body.style.overflow), '');
    await ham.click(); await ham.click(); await ham.click();
    assert.equal(await drawer.isVisible(), true);
    await f.page.locator('#navTabs .nav-tab[data-page="operations"]').click();
    assert.equal(await drawer.isVisible(), false);
    assert.equal(await f.page.evaluate(() => location.hash), '#operations');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;

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
    f = await fixture(browser, { page: 'system/logging', snmpBody: { enabled: true, running: true, community: 'fixture' } });
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
    f = await fixture(browser, { page: 'system/security' });
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
    f = await fixture(browser, { page: 'system/maintenance' });
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

    // Resource admission guard: when it pauses optional work the operations
    // page, the MQTT badge and a refused check say so instead of a bare code.
    f = await fixture(browser, { page: 'operations', operationsBody: {devices:[{index:0,mac:'02:00:00:00:00:01',name:'Fixture',target:'192.0.2.1',monitor:true,notify:true,host_port:22,service_port:0,timeout_s:60,interval_s:60,max_checks:10,kind:0,scope:0,state:'idle'}],
      events:[],monitoring:true,guard:true,guard_deferring:true,remote_commands:false,recovery_state:'idle',internal_free:17191,internal_min:15000,internal_largest:7000,sockets_used:12,socket_limit:31,
      minimum_internal:16384,minimum_largest:8192,socket_reserve:4,interval_s:60} });
    await f.page.waitForFunction(() => !document.getElementById('ops-settings-save').disabled);
    assert.equal(await f.page.locator('#ops-guard-warning').isHidden(), false);
    assert.match(await f.page.locator('#ops-summary').textContent(), /free internal 17191 B/);
    await f.page.route('http://esp32.test/api/operations', route => route.request().method() === 'POST'
      ? route.fulfill({ status: 429, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'This device was checked less than a minute ago; try again shortly' }) })
      : route.fallback());
    await f.page.locator('#ops-devices button', { hasText: 'Check now' }).click();
    await f.page.waitForFunction(() => document.body.textContent.includes('checked less than a minute ago'));
    assert.doesNotMatch(await f.page.locator('#ops-job').textContent(), /refresh before another action/);
    await f.page.waitForFunction(() => !document.getElementById('ops-settings-save').disabled);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { mqttBody: {...mqtt, connected: false, status: {configured: true, guard_deferring: true, retry_in_seconds: 266}} });
    await f.page.waitForFunction(() => document.getElementById('mqtt-badge').textContent === 'Paused by the resource guard');
    assert.match(await f.page.locator('#mqtt-badge').getAttribute('title'), /resource admission guard/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;

    // A successful check with no candidate disables installation, not checks.
    // Refresh/polling must preserve this until a newer candidate is found.
    f = await fixture(browser, { page: 'system/maintenance' });
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
      f = await fixture(browser, {page: 'system/maintenance', updatesBody: {...updates, ...invalid}});
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

    f = await fixture(browser, { page: 'system/maintenance' });
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
    f = await fixture(browser, { page: 'system/maintenance', updatesBody: {...updates,
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
    // A surviving control transport cannot imply complete current authority.
    f = await fixture(browser, {page: 'status', statusBody: {tailscale: {
      enabled:true,connected:true,authority_ready:false,register_user_id:1}}});
    await f.page.waitForFunction(() => document.getElementById('ts-badge').textContent === 'Policy pending');
    assert.match(await f.page.locator('#ts-badge').getAttribute('class'), /badge-warning/);
    assert.equal(await f.page.locator('#glance-tailnet strong').textContent(), 'Policy pending');
    assert.match(await f.page.locator('#ts-badge').getAttribute('title'), /data is blocked/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, {page:'tailscale', tailscaleSettings:{enabled:true},
      tailscaleRuntime:{connected:true,authority_ready:false,register_user_id:1}});
    await f.page.waitForFunction(() => document.getElementById('ts-page-badge').textContent === 'Policy pending');
    assert.match(await f.page.locator('#ts-page-badge').getAttribute('class'), /badge-warning/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Selective service gateway: installed mapping != verified service.
    const forwardRule = {name: 'Synthetic broker', enabled: true, installed: true,
      protocol: 'tcp', listen_port: 18830, destination_port: 1883,
      tailnet_destination: '100.64.0.2', allowed_source_subnet: '192.0.2.42/32',
      accepted_packets: 5, blocked_packets: 2, error: '', diagnostic: {
        code: 'mapping_installed', summary: 'Mapping installed; service not tested',
        next_step: 'Connect from an allowed LAN client.', service_status: 'not_tested', data_plane_status: 'not_verified'}};
    const forwardBody = {max: 8, rules: [forwardRule], uplink_ip: '192.0.2.20', observation: 'passive_snapshot'};
    f = await fixture(browser, {page: 'network/services', forwardBody});
    await f.page.waitForFunction(() => document.getElementById('tf-context').textContent.startsWith('Saved configuration'));
    assert.equal(await f.page.locator('.tf-runtime-badge').textContent(), forwardRule.diagnostic.summary);
    await f.page.locator('.tf-diagnostic summary').click();
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /192\.0\.2\.20:18830 → 100\.64\.0\.2:1883/);
    assert.match(await f.page.locator('.tf-diag-body').textContent(), /not proof of service replies/);
    assert.deepEqual(f.externalRequests, []);
    assert.equal(await f.page.locator('.tf-editor').first().isHidden(), true); // saved rules show a summary first
    assert.match(await f.page.locator('.tf-sum-route').first().textContent(), /192\.0\.2\.20:18830 → 100\.64\.0\.2:1883/);
    await f.page.locator('.tf-edit').first().click();
    assert.equal(await f.page.locator('.tf-edit').first().getAttribute('aria-expanded'), 'true');
    await f.page.locator('.tf-name').fill('Draft name');
    assert.equal(await f.page.locator('.tf-sum-name').first().textContent(), 'Draft name'); // summary follows the editor
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
    f = await fixture(browser, {page: 'network/services', forwardBody: {rules: {}, max: 8}});
    await f.page.waitForFunction(() => document.getElementById('tf-badge').textContent === 'Unavailable');
    assert.equal(await f.page.locator('#tf-save').isDisabled(), true);
    assert.equal(await f.page.locator('#tf-add').isDisabled(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Remote fields are text, not HTML, and /0 exposure is explicit on mobile.
    f = await fixture(browser, {page: 'network/services', viewport: {width: 390, height: 844}, forwardBody: {
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
    f=await fixture(browser,{page:'network/services'});
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
      f=await fixture(browser,{page:'network/services',importConflict:conflict,importDelay:100});
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
    // A running check is followed live: badges and the job line update without
    // a reload, unsaved edits stay, and polling stops when the job ends.
    const liveDevice={index:0,mac:'02:00:00:00:00:01',name:'Fixture',target:'',monitor:false,notify:false,host_port:22,service_port:0,timeout_s:60,interval_s:60,max_checks:10,kind:0,scope:0,state:'idle',latency_ms:0};
    const liveBody=(state,device)=>({devices:[{...liveDevice,...device}],events:[],monitoring:false,guard:false,remote_commands:false,recovery_state:state,device_index:0,packet_sent:false,
      host_verified:state==='reachable',service_verified:false,minimum_internal:16384,minimum_largest:8192,socket_reserve:4,interval_s:60});
    f=await fixture(browser,{page:'operations',operationsBody:liveBody('checking-service',{})});
    await f.page.waitForFunction(()=>!document.getElementById('ops-settings-save').disabled);
    const liveBadge=f.page.locator('#ops-devices .card-header .badge');
    assert.equal(await liveBadge.textContent(),'Checking the service…');
    assert.equal(await f.page.locator('#ops-cancel').isDisabled(),false);
    // Empty fields show an example; optional port 0 is an empty field.
    assert.equal(await f.page.locator('#ops-devices input[type=text]').getAttribute('placeholder'),'e.g. 192.168.1.20 or nas.lan');
    assert.equal(await f.page.locator('#ops-devices input[type=number]').nth(1).inputValue(),'');
    assert.equal(await f.page.locator('#ops-devices .form-hint').count(),8);
    assert.equal(await f.page.locator('#health-gateway-port').inputValue(),'');
    assert.equal(await f.page.locator('#health-dns').getAttribute('placeholder'),'e.g. example.com');
    await f.page.locator('#ops-devices input[type=text]').fill('draft.example');
    const pollsBefore=f.calls.filter(p=>p==="/api/operations").length;
    f.state.operationsBody=liveBody('reachable',{state:'reachable',latency_ms:12});
    await f.page.waitForFunction(()=>document.querySelector('#ops-devices .card-header .badge').textContent==='Reachable · 12 ms',null,{timeout:6000});
    assert.match(await liveBadge.getAttribute('class'),/badge-success/);
    assert.match(await f.page.locator('#ops-job').textContent(),/Recovery: reachable/);
    assert.equal(await f.page.locator('#ops-devices input[type=text]').inputValue(),'draft.example');
    assert.equal(await f.page.locator('#ops-cancel').isDisabled(),true);
    const pollsAfter=f.calls.filter(p=>p==="/api/operations").length;
    await f.page.waitForTimeout(2600);
    assert.equal(f.calls.filter(p=>p==='/api/operations').length,pollsAfter,'polling must stop once the job ends');
    assert.ok(pollsAfter>pollsBefore);
    // Saving connectivity checks sends 0 for an empty optional port.
    await f.page.locator('#health-save').click();await f.page.waitForFunction(()=>!document.getElementById('ops-refresh').disabled);
    assert.equal(f.state.savedOperation.gateway_port,0);
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
    // The selector shows the active profile; with none applied it says so.
    await f.page.waitForFunction(()=>document.getElementById('profile-select').options.length===4&&!document.getElementById('profile-select').disabled);
    assert.equal(await f.page.locator('#profile-select').inputValue(),'');
    assert.equal(await f.page.locator('#profile-preview').isDisabled(),true);
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
    assert.equal(await f.page.locator('#profile-select').inputValue(),'monitoring');
    const applied=f.state.profilePosts.filter(x=>x.action==='apply');assert.equal(applied.length,2);
    assert.deepEqual(Object.keys(applied[1]).sort(),['action','profile','token']);assert.equal(applied[1].token,102);
    f.page.once('dialog',d=>d.accept());await f.page.locator('#profile-rollback').click();
    await f.page.waitForFunction(()=>document.getElementById('profile-status').textContent.includes('Rolled back'));
    assert.match(await f.page.locator('#profile-status').textContent(),/Left as you changed them: Health Monitor worker/);
    assert.equal(await f.page.locator('#profile-select').inputValue(),'');
    assert.equal(await f.page.locator('#profile-rollback').isDisabled(),true);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Guided setup: exposure confirmation, snapshot, focus, diff and restore.
    f=await fixture(browser,{page:'status',tailscaleSettings:{hostname:'fixture',advertise_routes:'',auth_key:'never-sent'}});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===13);
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
      {id:'ntfy',compiled:true,hardware_supported:true,configured:true,active:null,verified:false,experimental:false,evidence:'Fixture'},
      {id:'snmp',compiled:false,hardware_supported:true,configured:false,active:false,verified:false,experimental:false,evidence:'Not included in this firmware.'}]}});
    await f.page.waitForFunction(()=>document.getElementById('mqtt-card').classList.contains('capability-unavailable'));
    assert.equal(await f.page.locator('#sys-snmp-card').evaluate(e=>e.hidden),true,'a module left out of the firmware disappears');
    assert.equal(await f.page.locator('#mqtt-card').evaluate(e=>e.hidden),false,'other not-compiled cards stay, greyed');
    assert.match(await f.page.locator('#mqtt-card .capability-note').textContent(),/Not available in this firmware — Fixture: not compiled/);
    assert.equal(await f.page.locator('#mqtt-card .card-body').evaluate(e=>e.inert),true);
    assert.equal(await f.page.locator('#ntfy-card').evaluate(e=>e.classList.contains('capability-unavailable')),false);
    assert.equal(await f.page.locator('#wizard-list button',{hasText:/^MQTT$/}).isDisabled(),true);
    assert.equal(await f.page.locator('#wizard-list button',{hasText:'ntfy'}).isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Service Gateway: test a saved (still disabled) rule's Tailnet destination.
    const tfRule=()=>({index:0,rule_token:77,name:'NAS',enabled:false,installed:false,protocol:'tcp',listen_port:15000,tailnet_destination:'100.64.0.9',
      destination_port:5000,allowed_source_subnet:'192.168.1.20/32',accepted_packets:0,blocked_packets:0,error:'',diagnostic:{code:'disabled',summary:'Rule disabled',next_step:'Enable it'},
      activity:{peer_path:'relay',last_accepted_age_s:null,last_rejected_age_s:12,service_reply_age_s:null}});
    f=await fixture(browser,{page:'network/services',forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.querySelector('.tf-test')&&!document.querySelector('.tf-test').disabled);
    assert.equal(await f.page.locator('.tf-check-state').textContent(),'Not tested');
    assert.match(await f.page.locator('.tf-activity').textContent(),/Last accepted: never this boot · last rejected: 12 s ago · reply from the Tailnet service: none seen · destination peer: relayed via DERP/);
    await f.page.locator('.tf-test').click();
    await f.page.waitForFunction(()=>document.querySelector('.tf-check-state')&&document.querySelector('.tf-check-state').textContent==='Reachable from gateway (42 ms)',null,{timeout:10000});
    assert.deepEqual(f.state.checkPosts,[{index:0,rule_token:77}]);
    assert.match(await f.page.locator('.tf-check-next').textContent(),/connect from an allowed LAN client/);
    await f.page.locator('.tf-edit').first().click();
    await f.page.locator('.tf-name').fill('NAS edited');
    assert.equal(await f.page.locator('.tf-test').isDisabled(),true); // tests the saved rule only
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'network/services',checkStatus:429,forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.querySelector('.tf-test')&&!document.querySelector('.tf-test').disabled);
    await f.page.locator('.tf-test').click();
    await f.page.waitForFunction(()=>document.querySelector('.tf-check-state').textContent.includes('Test not started: another check is running'));
    assert.equal(await f.page.locator('.tf-test').isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Primary guide runs one destination test inline from "Check result".
    // A saved but disabled rule does not bring the home card back.
    f=await fixture(browser,{page:'status',forwardBody:{rules:[tfRule()],max:8,uplink_ip:'192.0.2.20',observation:'passive_snapshot'}});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===13);
    await f.page.waitForFunction(()=>document.getElementById('sg-home-badge').textContent==='1 / 8');
    assert.equal(await f.page.locator('#sg-home-card').isHidden(),true);
    await f.page.locator('#goal-grid .goal-tile.primary').click();
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
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===13);
    const first=f.page.locator('#wizard-list button').first();
    assert.equal(await first.textContent(),'Publish a Tailnet service to the LAN');
    assert.match(await f.page.locator('#goal-grid .goal-tile.primary').textContent(),/Connect a LAN device to a Tailnet service/); // the killer feature leads the goal launcher
    await f.page.waitForFunction(()=>document.getElementById('sg-home-summary').textContent.startsWith('No service rules yet'));
    assert.equal(await f.page.locator('#sg-home-badge').textContent(),'0 / 8');
    // No rule, no temporary access and the role not chosen at setup: the home card stays out of the way.
    assert.equal(await f.page.locator('#sg-home-card').isHidden(),true);
    // The goal launcher sits after the live status cards and still offers the guide.
    assert.equal(await f.page.evaluate(()=>!!(document.getElementById('card-uplink').compareDocumentPosition(document.getElementById('wizard-card'))&Node.DOCUMENT_POSITION_FOLLOWING)),true);
    await f.page.locator('#goal-grid .goal-tile.primary').click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden&&document.getElementById('wizard-title').textContent==='Publish a Tailnet service to the LAN');
    assert.equal(await f.page.locator('#wizard-exposure-row').isHidden(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Role chosen in the first-boot wizard: recommended in the goal launcher only;
    // the home card still waits for an enabled rule.
    f=await fixture(browser,{page:'status',systemBody:{web_auth_enabled:true,session_timeout_s:0,wifi_power_save:false,wifi_power_save_active:false,wifi_power_save_known:true,setup_roles:'lan-tailnet'}});
    await f.page.waitForFunction(()=>document.getElementById('sg-home-summary').textContent.startsWith('No service rules yet'));
    assert.equal(await f.page.locator('#sg-home-card').isHidden(),true);
    // The chosen role is only recommended: no guide opens by itself at sign-in.
    await f.page.waitForFunction(()=>document.querySelector('#goal-grid .goal-tile.recommended'));
    assert.equal(await f.page.locator('#wizard-panel').isHidden(),true);
    // The exposure acknowledgement is asked once per browser, then remembered.
    await f.page.locator('#goal-grid .goal-tile.primary').click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden);
    assert.equal(await f.page.locator('#wizard-exposure').isChecked(),false);
    await f.page.locator('#wizard-exposure').check();
    await f.page.locator('#wizard-close').click();
    await f.page.locator('#goal-grid .goal-tile.primary').click();
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden&&!document.getElementById('wizard-checks').textContent.includes('checking'));
    assert.equal(await f.page.locator('#wizard-exposure').isChecked(),true);
    assert.equal(await f.page.locator('#wizard-start').isDisabled(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Templates: risk hint, first free listen port per protocol, UDP template.
    f=await fixture(browser,{page:'network/services'});
    await f.page.waitForFunction(()=>!document.getElementById('tf-add').disabled);
    await f.page.locator('#tf-template').selectOption('mqtt');
    assert.match(await f.page.locator('#tf-template-hint').textContent(),/Unencrypted/);
    await f.page.locator('#tf-template').selectOption('ssh');await f.page.locator('#tf-add').click();await f.page.locator('#tf-add').click();
    assert.deepEqual(await f.page.locator('.tf-listen').evaluateAll(e=>e.map(x=>x.value)),['2222','2223']);
    await f.page.locator('#tf-template').selectOption('syslog');await f.page.locator('#tf-add').click();
    assert.equal(await f.page.locator('.tf-proto').nth(2).inputValue(),'udp');assert.equal(await f.page.locator('.tf-listen').nth(2).inputValue(),'15514');
    assert.equal(await f.page.locator('.tf-enabled:checked').count(),0);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Status details: the board's own .local name, a recovery-only access point in standby,
    // internal RAM coloured by absolute headroom (normal ~20 KB is not an alarm).
    f=await fixture(browser,{page:'status',statusBody:{sta:{connected:true,ssid:'Home',lan_name:'esp32-tailnet-1a2b'},
      ap:{enabled:false,auto_off_when_connected:true,clients:0},mem_internal_free:20480,mem_internal_total:380000}});
    await f.page.waitForFunction(()=>document.getElementById('uplink-lan-name').textContent==='esp32-tailnet-1a2b.local');
    assert.equal(await f.page.locator('#uplink-lan-name').getAttribute('href'),'http://esp32-tailnet-1a2b.local/');
    assert.equal(await f.page.locator('#ap-runtime-status').textContent(),'Standby');
    assert.equal(await f.page.locator('#ap-clients-badge').textContent(),'Standby');
    assert.equal(await f.page.locator('#glance-memory .glance-label').textContent(),'Free internal RAM');
    assert.equal(await f.page.locator('#sys-mem-internal-bar').evaluate(e=>e.style.background),'var(--success)');
    // "Change" opens the hostname field, which previews the .local address it gives.
    f.state.networkBody={hostname:'',lan_name:'esp32-tailnet-1a2b',lan_name_default:'esp32-tailnet-1a2b',networks:[],sta_ttl_override:0};
    await f.page.locator('#uplink-lan-name-edit').click();
    await f.page.waitForFunction(()=>location.hash==='#network'&&document.activeElement&&document.activeElement.id==='net-hostname');
    const preview=f.page.locator('#net-hostname-preview');
    await f.page.waitForFunction(()=>document.getElementById('net-hostname-preview').textContent!=='');
    assert.equal(await preview.textContent(),'Address on your network: http://esp32-tailnet-1a2b.local/');
    assert.equal(await f.page.locator('#net-hostname').getAttribute('placeholder'),'esp32-tailnet-1a2b');
    await f.page.locator('#net-hostname').fill('NAS-Gateway');
    assert.equal(await preview.textContent(),'Address on your network after a restart: http://nas-gateway.local/');
    await f.page.locator('#net-hostname').fill('a'.repeat(33));
    assert.equal(await preview.textContent(),'Longer than 32 characters: the .local address stays esp32-tailnet-1a2b.local');
    await f.page.locator('#net-hostname').fill('bad_name');
    assert.equal(await preview.textContent(),'Address on your network: http://esp32-tailnet-1a2b.local/');
    assert.equal(await f.page.locator('#net-hostname-save').isDisabled(),true);
    // After a saved rename the active name stays until the restart.
    f.state.networkBody={...f.state.networkBody,hostname:'nas-gateway'};
    await f.page.evaluate(()=>loadNetwork());
    await f.page.waitForFunction(()=>document.getElementById('net-hostname').value==='nas-gateway');
    assert.equal(await preview.textContent(),'Address on your network after a restart: http://nas-gateway.local/');
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    f=await fixture(browser,{page:'status',statusBody:{sta:{connected:true},ap:{enabled:false,auto_off_when_connected:false},mem_internal_free:6144,mem_internal_total:380000}});
    await f.page.waitForFunction(()=>document.getElementById('ap-runtime-status').textContent==='Disabled');
    assert.equal(await f.page.locator('#uplink-lan-name').textContent(),'—');
    assert.equal(await f.page.locator('#sys-mem-internal-bar').evaluate(e=>e.style.background),'var(--danger)');
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Simple mode keeps a firewall summary instead of an empty page.
    f=await fixture(browser,{page:'firewall',simpleMode:true});
    await f.page.waitForFunction(()=>document.getElementById('fw-simple-text').textContent!=='Loading…');
    assert.equal(await f.page.locator('.fw-simple-summary').isVisible(),true);
    assert.equal(await f.page.locator('#fw-lists').isVisible(),false);
    await f.page.locator('#fw-show-advanced').click();
    assert.equal(await f.page.locator('.fw-simple-summary').isVisible(),false);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Home card lists open temporary access with the soonest closure.
    f=await fixture(browser,{page:'status',forwardBody:{rules:[{index:0,rule_token:5,name:'NAS',enabled:true,installed:true,protocol:'tcp',listen_port:15001,tailnet_destination:'100.64.0.9',destination_port:5001,allowed_source_subnet:'192.168.1.20/32',accepted_packets:3,blocked_packets:0,error:''}],max:8},
      leasesBody:[{index:0,rule_token:5,temporary:true,effective_enabled:true,remaining_s:840,status:'active'},{index:1,rule_token:6,temporary:true,effective_enabled:false,remaining_s:0,status:'expired'}]});
    await f.page.waitForFunction(()=>document.getElementById('sg-home-summary').textContent.includes('temporary'));
    assert.equal(await f.page.locator('#sg-home-card').isHidden(),false); // an enabled rule shows the card
    // ...after the live status cards, right above the goal launcher.
    assert.equal(await f.page.evaluate(()=>{const u=document.getElementById('card-uplink'),s=document.getElementById('sg-home-card'),w=document.getElementById('wizard-card');
      return !!(u.compareDocumentPosition(s)&Node.DOCUMENT_POSITION_FOLLOWING)&&s.nextElementSibling===w;}),true);
    assert.match(await f.page.locator('#sg-home-summary').textContent(),/1 rule\(s\) · 1 enabled · 1 installed .* 1 temporary rule\(s\) open; the next closes in 14 min\./);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // ntfy system events are opt-in and saved with the rest of the card.
    f=await fixture(browser,{});await loaded(f.page);
    await f.page.locator('.page-section.active .subnav-tab[data-sub="notifications"]').click();
    assert.equal(await f.page.locator('#ntfy-system-events').isChecked(),false);
    await f.page.locator('label:has(#ntfy-system-events)').click();
    await f.page.waitForFunction(()=>!document.getElementById('ntfy-save').disabled);
    await f.page.locator('#ntfy-save').click();
    for(let i=0;i<50&&!f.state.savedNtfy;i++)await f.page.waitForTimeout(100);
    assert.equal(f.state.savedNtfy.system_events,true);assert.equal(f.state.savedNtfy.tailscale_alerts,false); // other switches unchanged
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Ethernet: WiFi-only image reports not compiled; Ethernet build saves typed settings.
    f=await fixture(browser,{page:'network'});
    await f.page.waitForFunction(()=>document.getElementById('eth-status').textContent.includes('Not available in this firmware build'));
    assert.equal(await f.page.locator('#eth-badge').textContent(),'Not compiled');
    await f.context.close();count++;
    f=await fixture(browser,{page:'network',ethernetBody:{config:{enabled:false,chip:'w5500',spi_host:2,spi_mhz:20,sclk:12,mosi:11,miso:13,cs:10,int:14,rst:9,static_ip:false,ip:'',netmask:'',gateway:'',dns:'',preference:'wifi_first'},
      status:{compiled:true,enabled_at_boot:false,driver_started:false,link_up:false,has_ip:false,selected_uplink:false,restart_required:false,link_changes:0,ip:'',netmask:'',gateway:'',error:''}}});
    await f.page.waitForFunction(()=>document.getElementById('eth-status').textContent==='Off.');
    await f.page.locator('label:has(#eth-enabled)').click();await f.page.locator('#eth-pref').selectOption('ethernet_first');
    await f.page.locator('label:has(#eth-static)').click();await f.page.locator('#eth-ip').fill('192.168.1.60');await f.page.locator('#eth-mask').fill('255.255.255.0');await f.page.locator('#eth-gw').fill('192.168.1.1');
    await f.page.locator('#eth-save').click();
    for(let i=0;i<50&&!f.state.savedEthernet;i++)await f.page.waitForTimeout(100);
    assert.deepEqual(f.state.savedEthernet,{enabled:true,chip:'w5500',preference:'ethernet_first',spi_host:2,spi_mhz:20,sclk:12,mosi:11,miso:13,cs:10,int:14,rst:9,static_ip:true,ip:'192.168.1.60',netmask:'255.255.255.0',gateway:'192.168.1.1',dns:''});
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Service watch: off by default, saved with typed fields.
    f=await fixture(browser,{page:'network/services'});
    await f.page.waitForFunction(()=>document.getElementById('sw-status').textContent==='Off.');
    await f.page.locator('#sw-box summary').click();
    await f.page.locator('label:has(#sw-enabled)').click();await f.page.locator('#sw-interval').fill('300');
    await f.page.locator('#sw-save').click();
    await f.page.waitForFunction(()=>document.getElementById('sw-status').textContent==='Watching every 300 s.');
    assert.deepEqual(f.state.savedWatch,{enabled:true,notify:false,interval_s:300});
    await f.page.locator('#sw-interval').fill('30');await f.page.locator('#sw-save').click();
    assert.match(await f.page.locator('#sw-status').textContent(),/60–86400/);assert.equal(f.state.savedWatch.interval_s,300); /* refused client-side */
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Phone width: no page may scroll horizontally (375 px), guide panel fits.
    for(const page of ['status','network','tailscale','operations','automation','system']){
      f=await fixture(browser,{page,viewport:{width:375,height:812}});
      await f.page.waitForTimeout(400);
      const overflow=await f.page.evaluate(()=>{const w=document.documentElement.clientWidth;
        const wide=[...document.querySelectorAll('.page-section.active *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.right>w+1&&getComputedStyle(e).position!=='fixed';})
          .filter(e=>!e.closest('pre,code,.mono,table'));
        return {scroll:document.documentElement.scrollWidth-w,wide:wide.slice(0,3).map(e=>e.tagName+'#'+e.id+'.'+e.className)};});
      assert.ok(overflow.scroll<=1,`${page}: page scrolls horizontally by ${overflow.scroll}px: ${JSON.stringify(overflow.wide)}`);
      if(page==='status'){await f.page.locator('#wizard-list button').first().click();
        const box=await f.page.locator('#wizard-panel').boundingBox();assert.ok(box&&box.x>=0&&box.x+box.width<=375,'guide panel exceeds phone width');}
      assert.deepEqual(f.errors,[]);await f.context.close();count++;
    }
    // Every visible control on the main pages has an accessible name.
    for(const page of ['status','network','tailscale','firewall','operations','automation','system','tools']){
      f=await fixture(browser,{page});await f.page.waitForTimeout(300);
      const unnamed=await f.page.evaluate(()=>[...document.querySelectorAll('.page-section.active input,.page-section.active select,.page-section.active button,.page-section.active textarea')]
        .filter(e=>e.offsetParent!==null&&e.type!=='hidden').filter(e=>!((e.getAttribute('aria-label')||'').trim()
          ||(e.labels&&[...e.labels].map(l=>l.textContent).join('').trim())||(e.tagName==='BUTTON'&&e.textContent.trim())||e.getAttribute('title')))
        .map(e=>e.tagName+'#'+e.id));
      assert.deepEqual(unnamed,[],`${page}: controls without an accessible name`);
      await f.context.close();count++;
    }
    // Keyboard only: open the primary guide, confirm exposure, start, Escape returns focus.
    f=await fixture(browser,{page:'status'});
    await f.page.waitForFunction(()=>document.getElementById('wizard-list').children.length===13);
    await f.page.locator('#goal-grid .goal-tile.primary').focus();await f.page.keyboard.press('Enter');
    await f.page.waitForFunction(()=>!document.getElementById('wizard-panel').hidden&&document.activeElement.id==='wizard-close');
    await f.page.waitForFunction(()=>!document.getElementById('wizard-checks').textContent.includes('checking'));
    await f.page.locator('#wizard-exposure').focus();await f.page.keyboard.press('Space');
    assert.equal(await f.page.locator('#wizard-exposure').isChecked(),true);
    await f.page.keyboard.press('Tab');assert.equal(await f.page.evaluate(()=>document.activeElement.id),'wizard-start');
    await f.page.keyboard.press('Escape');
    await f.page.waitForFunction(()=>document.getElementById('wizard-panel').hidden&&document.activeElement.classList.contains('goal-tile'));
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Board without PSRAM: destination test and service watch are gated by the manifest.
    f=await fixture(browser,{page:'network/services',forwardBody:{rules:[{index:0,rule_token:77,name:'NAS',enabled:false,installed:false,protocol:'tcp',listen_port:15000,tailnet_destination:'100.64.0.9',destination_port:5000,allowed_source_subnet:'192.168.1.20/32',accepted_packets:0,blocked_packets:0,error:''}],max:8},
      capabilityBody:{schema:2,features:[{id:'smart-recovery',compiled:true,hardware_supported:false,configured:false,active:false,verified:false,experimental:true,evidence:'Fixture: no PSRAM'},
        {id:'destination-test',compiled:true,hardware_supported:false,configured:true,active:null,verified:false,experimental:true,evidence:'Fixture: no PSRAM'},
        {id:'service-watch',compiled:true,hardware_supported:false,configured:false,active:false,verified:false,experimental:true,evidence:'Fixture: no PSRAM'}]}});
    await f.page.waitForFunction(()=>document.getElementById('sw-box').classList.contains('capability-unavailable'));
    await f.page.waitForFunction(()=>document.querySelector('.tf-test')&&document.querySelector('.tf-test').disabled);
    assert.match(await f.page.locator('.tf-test').getAttribute('title'),/no PSRAM/);
    assert.deepEqual(f.errors,[]);await f.context.close();count++;
    // Goal launcher and simple mode: advanced sections hidden but reachable, never disabled.
    f = await fixture(browser, { page: 'status', simpleMode: true });
    await f.page.waitForFunction(() => document.querySelectorAll('#goal-grid .goal-tile').length === 7);
    assert.equal(await f.page.locator('body.ui-simple').count(), 1);
    await f.page.locator('#goal-grid .goal-tile', { hasText: 'Connect a LAN device' }).click();
    await f.page.waitForFunction(() => !document.getElementById('wizard-panel').hidden);
    assert.equal(await f.page.locator('#wizard-title').textContent(), 'Publish a Tailnet service to the LAN');
    await f.page.locator('#wizard-close').click();
    await f.page.locator('#goal-grid .goal-tile', { hasText: 'Monitor the gateway' }).click();
    await f.page.waitForFunction(() => document.getElementById('page-tools').classList.contains('active'));
    await f.page.evaluate(() => { location.hash = 'firewall'; });
    await f.page.waitForFunction(() => document.getElementById('page-firewall').classList.contains('active'));
    assert.equal(await f.page.locator('#fw-lists').isHidden(), true);
    assert.match(await f.page.locator('#page-firewall .adv-note').textContent(), /hidden in simple mode/);
    await f.page.locator('#page-firewall .adv-note button').click();
    assert.equal(await f.page.locator('body.ui-simple').count(), 0); assert.equal(await f.page.locator('#page-firewall .adv-note').isHidden(), true);
    assert.equal(await f.page.evaluate(() => localStorage.getItem('ui-advanced')), '1');
    await f.page.evaluate(() => { location.hash = 'system'; });
    await f.page.waitForFunction(() => document.getElementById('page-system').classList.contains('active'));
    assert.equal(await f.page.locator('#ui-advanced-toggle').isChecked(), true);
    await f.page.locator('#ui-mode-card .feature-switch').click();
    assert.equal(await f.page.locator('body.ui-simple').count(), 1);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Translations: browser language detection, manual switch, technical values untouched, English fallback.
    f = await fixture(browser, { page: 'network/services', locale: 'it-IT', forwardBody: { rules: [tfRule()], max: 8, uplink_ip: '192.0.2.20', observation: 'passive_snapshot' } });
    await f.page.waitForFunction(() => document.documentElement.lang === 'it' && document.querySelector('.nav-tab[data-page="network"]').textContent.includes('Rete'));
    await f.page.waitForFunction(() => document.querySelector('.tf-sum-route'));
    assert.match(await f.page.locator('.tf-sum-route').first().textContent(), /192\.0\.2\.20:15000 → 100\.64\.0\.9:5000 · TCPda 192\.168\.1\.20\/32/); // values never translated
    await f.page.locator('.tf-edit').first().click();
    await f.page.locator('.tf-name').first().fill('Rete di prova');
    assert.equal(await f.page.locator('.tf-name').first().inputValue(), 'Rete di prova');
    assert.equal(await f.page.locator('label[for="tf-dest-0"]').textContent(), 'Destinazione Tailnet');
    f.page.once('dialog', d => { assert.match(d.message(), /Eliminare questa regola/); d.dismiss(); });
    await f.page.locator('.tf-del').first().click();
    await f.page.evaluate(() => { location.hash = 'system'; });
    await f.page.waitForFunction(() => document.getElementById('page-system').classList.contains('active'));
    await f.page.selectOption('#ui-lang', 'zh');
    await f.page.waitForFunction(() => document.documentElement.lang === 'zh-Hans' && document.querySelector('.nav-tab[data-page="system"]').textContent.includes('系统'));
    await f.page.selectOption('#ui-lang', 'en');
    await f.page.waitForFunction(() => document.documentElement.lang === 'en' && document.querySelector('.nav-tab[data-page="network"]').textContent.includes('Network'));
    assert.equal(await f.page.evaluate(() => localStorage.getItem('ui-lang')), 'en');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // An unsupported browser language falls back to English.
    f = await fixture(browser, { page: 'status', locale: 'pt-BR' });
    await f.page.waitForFunction(() => document.querySelector('#goal-grid .goal-tile'));
    assert.equal(await f.page.evaluate(() => document.documentElement.lang), 'en');
    assert.match(await f.page.locator('#wizard-card .card-title').textContent(), /What do you want to do\?/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // 3.0 history: off by default, saving the switches, escaped and filtered events.
    f = await fixture(browser, { page: 'tools/history', histEvents: [
      {k: 'boot', l: 'info', b: 3, t: 1700000000, u: 1, m: 'Started 3.0.0 from ota_1, reset SW'},
      {k: 'security', l: 'warn', b: 3, t: 0, u: 300, m: 'Admin login failed <img src=x onerror=alert(1)>'},
      {k: 'crash', l: 'error', b: 2, t: 0, u: 50, m: 'Crash: task=x'}] });
    await f.page.waitForFunction(() => document.getElementById('hist-badge').textContent === 'Off');
    assert.equal(await f.page.locator('#hist-events-wrap').isHidden(), true);
    assert.equal(await f.page.locator('#hist-save').isDisabled(), true);
    await f.page.locator('#hist-card label.feature-switch', { hasText: 'Record events' }).click();
    await f.page.locator('#hist-card label.feature-switch', { hasText: 'Record trends' }).click();
    await f.page.locator('#hist-save').click();
    await f.page.waitForFunction(() => document.getElementById('hist-badge').textContent === 'On');
    assert.deepEqual(f.state.savedHistory, { events: true, metrics: true, snapshots: false });
    await f.page.waitForFunction(() => document.querySelectorAll('#hist-tbody tr').length === 3);
    assert.equal(await f.page.locator('#hist-tbody img').count(), 0, 'event text is escaped');
    assert.match(await f.page.locator('#hist-tbody').textContent(), /<img src=x/);
    assert.match(await f.page.locator('#hist-tbody tr').nth(2).textContent(), /Start 2, after/);   // no clock, other boot
    assert.match(await f.page.locator('#hist-tbody tr').nth(1).textContent(), /5m ago/);          // no clock, this boot
    await f.page.selectOption('#hist-filter', 'problems');
    await f.page.waitForFunction(() => document.querySelectorAll('#hist-tbody tr').length === 2);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Trends: offered while off (one click turns them on); tiles pick a chart with axes, legend, stats and a readout.
    f = await fixture(browser, { page: 'status' });
    await f.page.waitForFunction(() => !document.getElementById('trend-card').hidden && !document.getElementById('trend-off').hidden);
    assert.equal(await f.page.locator('#trend-on').isHidden(), true);
    assert.equal(await f.page.locator('#trend-range').isDisabled(), true);
    await f.page.locator('#trend-enable').click();
    await f.page.waitForFunction(() => document.getElementById('trend-off').hidden && !document.getElementById('trend-on').hidden);
    assert.deepEqual(f.state.savedHistory, { metrics: true });
    assert.match(await f.page.locator('#trend-status').textContent(), /first sample arrives a minute/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { page: 'status', histConfig: { events: false, metrics: true, snapshots: false },
      histPoints: [[0, 3, 600, 45000, 30000, 7000000, 750000, 75000, -60, 20, 4, 3], [0, 3, 540, 46000, 31000, 7100000, 0, 0, 0, -1, 4, 1],
                   [0, 2, 9000, 47000, 31000, 7200000, 300000, 30000, -55, 10, 2, 3]] });
    await f.page.waitForFunction(() => document.querySelectorAll('#trend-tiles .trend-tile').length === 6);
    const tileText = await f.page.locator('#trend-tiles').textContent();
    assert.match(tileText, /Internal RAM free43\.9 KB/);                 // newest point last
    assert.match(tileText, /Uplink traffic100 kbit\/s/);                 // 750000 B in 60 s
    assert.match(tileText, /Wi-Fi signal-60 dBm/);
    assert.equal(await f.page.locator('#trend-tiles .trend-tile[aria-pressed="true"]').textContent().then(t => t.startsWith('Internal RAM free')), true);
    assert.equal(await f.page.locator('#trend-main').isVisible(), true);
    assert.equal(await f.page.locator('#trend-plot svg path').count(), 2, 'free and largest block');
    assert.equal(await f.page.locator('#trend-legend span').count(), 2);
    assert.match(await f.page.locator('#trend-plot').textContent(), /KB/, 'value axis with units');
    await f.page.locator('#trend-tiles .trend-tile', { hasText: 'Uplink traffic' }).click();
    assert.equal(await f.page.locator('#trend-title').textContent(), 'Uplink traffic');
    assert.match(await f.page.locator('#trend-stats').textContent(), /Lowest 0\.0 kbit\/s.*Highest 100 kbit\/s/);
    const plot = await f.page.locator('#trend-plot svg').boundingBox();
    await f.page.mouse.move(plot.x + plot.width - 20, plot.y + plot.height / 2);
    await f.page.waitForFunction(() => !document.querySelector('#trend-plot .trend-tip').hidden);
    assert.match(await f.page.locator('#trend-plot .trend-tip').textContent(), /Download: 100 kbit\/s.*Upload: 10\.0 kbit\/s/);
    assert.equal(await f.page.evaluate(() => localStorage.getItem('ui-trend-measure')), 'traffic', 'the chosen measure is remembered');
    await f.page.locator('#trend-tiles .trend-tile', { hasText: 'CPU load' }).click();
    assert.equal(await f.page.locator('#trend-main').isVisible(), false, 'a single CPU value draws no chart');
    await f.page.selectOption('#trend-range', 'week');
    await f.page.waitForFunction(() => document.getElementById('trend-status').textContent.includes('One point every 1 minutes'));
    assert.ok(f.calls.includes('/api/history'));
    await f.page.setViewportSize({ width: 390, height: 844 });
    await f.page.locator('#trend-tiles .trend-tile', { hasText: 'Internal RAM free' }).click();
    assert.equal(await f.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'no sideways scroll on a phone');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // With the web UI lock off, actions that need a password session say so and stay disabled.
    f = await fixture(browser, { page: 'system/maintenance', lockOff: true, migrationBody: {layout: '2.x', bridge: true, needed: true, supported: true, busy: false,
      physical_flash: 16777216, state: 'idle', progress: 0, target: '', error: ''} });
    await f.page.waitForFunction(() => !document.getElementById('mig-card').hidden && !document.getElementById('mig-lock').hidden);
    assert.match(await f.page.locator('#mig-lock').textContent(), /Needs the web UI lock: turn on Require the admin password/);
    await f.page.locator('label:has(#mig-confirm)').click();
    assert.equal(await f.page.locator('#mig-start').isDisabled(), true, 'Migrate stays off without the lock');
    await f.page.waitForFunction(() => !document.getElementById('snap-lock').hidden);
    assert.equal(await f.page.locator('#snap-tbody button[data-snap-restore="1"]').isDisabled(), true);
    assert.equal(await f.page.locator('#snap-tbody button[data-snap-delete="1"]').isDisabled(), true);
    assert.equal(await f.page.locator('#snap-take').isDisabled(), false, 'saving a copy needs no lock');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Settings copies: list, escaped firmware text, restore and delete need a confirmation.
    f = await fixture(browser, { page: 'system/backup' });
    f.page.on('dialog', dialog => dialog.accept());
    await f.page.waitForFunction(() => document.getElementById('snap-badge').textContent === '1 of 3');
    assert.equal(await f.page.locator('#snap-tbody b').count(), 0, 'firmware text escaped');
    assert.equal(await f.page.locator('#snap-tbody button[data-snap-restore]').count(), 1);
    await f.page.locator('#snap-take').click();
    await f.page.waitForFunction(() => document.getElementById('snap-status').textContent.includes('only by hand'));
    await f.page.locator('#snap-tbody button[data-snap-delete="1"]').click();
    await f.page.locator('#snap-tbody button[data-snap-restore="1"]').click();
    await f.page.waitForFunction(() => document.getElementById('snap-status').textContent.includes('Restarting'));
    assert.deepEqual(f.state.snapPosts, [{ action: 'take' }, { action: 'delete', slot: 1, confirm: true }, { action: 'restore', slot: 1, confirm: true }]);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Tailnet names, notifications and the throughput test.
    f = await fixture(browser, { page: 'tailscale/options' });
    await f.page.waitForFunction(() => document.getElementById('tsn-status').textContent.startsWith('Off'));
    await f.page.locator('#tsn-card label.feature-switch', { hasText: 'Answer tailnet names' }).click();
    await f.page.locator('#tsn-save').click();
    await f.page.waitForFunction(() => document.getElementById('tsn-badge').textContent === 'On');
    assert.deepEqual(f.state.savedNames, { enabled: true, lan: false });
    assert.match(await f.page.locator('#tsn-status').textContent(), /5 tailnet peers known/);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { page: 'automation/notifications' });
    await f.page.waitForFunction(() => document.getElementById('nt-tg-note').textContent === 'Off.' && document.getElementById('nt-mail-note').textContent === 'Off.');
    assert.match(await f.page.locator('#nt-tg-status').textContent(), /401: Unauthorized/);
    assert.ok(await f.page.locator('#nt-mail-save').isDisabled(), 'email untouched by Telegram edits');
    await f.page.locator('#nt-tg-card label.feature-switch', { hasText: 'Send to Telegram' }).click();
    await f.page.fill('#nt-tg-token', '123456789:AAH4kq_ZXcvbnm-1234567890qwertyuiopASD');
    await f.page.fill('#nt-tg-chat', ' 42 ');
    await f.page.selectOption('#nt-tg-events', 'all');
    assert.ok(await f.page.locator('#nt-mail-save').isDisabled());
    await f.page.locator('#nt-tg-save').click();
    await f.page.waitForFunction(() => document.getElementById('nt-tg-badge').textContent === 'On');
    assert.equal(f.state.savedNotify.telegram.token, '123456789:AAH4kq_ZXcvbnm-1234567890qwertyuiopASD');
    assert.equal(f.state.savedNotify.telegram.chat, '42'); assert.equal(f.state.savedNotify.telegram.events, 'all');
    assert.equal(f.state.savedNotify.email, undefined, 'saving Telegram sends nothing about email');
    assert.equal(await f.page.locator('#nt-mail-badge').textContent(), 'Off');
    assert.equal(await f.page.inputValue('#nt-tg-token'), '', 'token cleared from the form');
    assert.equal(await f.page.getAttribute('#nt-tg-token', 'placeholder'), 'Saved — leave empty to keep');
    await f.page.selectOption('#nt-mail-security', 'starttls');
    assert.equal(await f.page.inputValue('#nt-mail-port'), '587', 'STARTTLS suggests port 587');
    assert.ok(!(await f.page.locator('#nt-mail-save').isDisabled()), 'email edits enable its own Save');
    await f.page.locator('#nt-test-tg').click();
    await f.page.waitForFunction(() => document.getElementById('nt-tg-note').textContent.includes('queued'));
    assert.deepEqual(f.state.notifyTest, { channel: 'telegram' });
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { page: 'network/internet' });
    await f.page.waitForFunction(() => document.getElementById('ddns-status').textContent === 'Off.');
    assert.equal(await f.page.locator('#ddns-badge').textContent(), 'Off');
    await f.page.selectOption('#ddns-provider', 'duckdns');
    assert.equal(await f.page.locator('#ddns-zone').isHidden(), true); assert.equal(await f.page.locator('#ddns-url').isHidden(), true);
    assert.equal(await f.page.locator('#ddns-name-label').textContent(), 'Sub-domain');
    await f.page.fill('#ddns-name', 'myhome'); await f.page.fill('#ddns-token', 'a7c4d2e1-0b3f-4c5d-9e8f-1234567890ab');
    await f.page.locator('#ddns-save').click();
    await f.page.waitForFunction(() => document.getElementById('ddns-token').value === '');
    assert.deepEqual(f.state.savedDdns, { provider: 'duckdns', name: 'myhome', zone: '', token: 'a7c4d2e1-0b3f-4c5d-9e8f-1234567890ab', url: '', update_now: false });
    await f.page.selectOption('#ddns-provider', 'custom');
    assert.equal(await f.page.locator('#ddns-url').isVisible(), true); assert.equal(await f.page.locator('#ddns-name').isHidden(), true);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    f = await fixture(browser, { page: 'tools' });
    await f.page.waitForSelector('#thr-start');
    await f.page.fill('#thr-url', 'http://100.64.0.7/big.iso');
    await f.page.locator('#thr-start').click();
    await f.page.waitForFunction(() => document.getElementById('thr-status').textContent.includes('time limit reached'), null, { timeout: 8000 });
    assert.deepEqual(f.state.savedSpeed, { url: 'http://100.64.0.7/big.iso', seconds: 10 });
    assert.match(await f.page.locator('#thr-status').textContent(), /12\.0 MB in 10\.0 s — 10\.07 Mbit\/s/);
    assert.equal(await f.page.locator('#thr-start').isDisabled(), false);
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    // Sub-sections: one group at a time, deep links, keyboard, remembered choice, guides open the right group.
    f = await fixture(browser, { page: 'network' });
    await f.page.waitForSelector('#page-network.active .subnav');
    const visibleGroups = () => f.page.evaluate(() => [...document.querySelectorAll('#page-network .subpage')].filter(g => !g.hidden).map(g => g.dataset.sub));
    assert.deepEqual(await visibleGroups(), ['internet']);
    assert.equal(await f.page.locator('#page-network .subnav-tab[aria-selected="true"]').textContent(), 'Internet');
    await f.page.locator('#page-network .subnav-tab[data-sub="services"]').click();
    assert.deepEqual(await visibleGroups(), ['services']);
    assert.equal(await f.page.evaluate(() => location.hash), '#network/services');
    assert.equal(await f.page.locator('#tf-add').isVisible(), true);
    await f.page.locator('#page-network .subnav-tab[data-sub="services"]').focus();
    await f.page.keyboard.press('ArrowLeft');
    assert.deepEqual(await visibleGroups(), ['clients']);
    await f.page.keyboard.press('Home');
    assert.deepEqual(await visibleGroups(), ['internet']);
    await f.page.keyboard.press('End');
    assert.deepEqual(await visibleGroups(), ['services']);
    await f.page.evaluate(() => { location.hash = 'firewall'; });
    await f.page.waitForFunction(() => document.getElementById('page-firewall').classList.contains('active'));
    await f.page.evaluate(() => { location.hash = 'network'; });
    await f.page.waitForFunction(() => document.getElementById('page-network').classList.contains('active'));
    assert.deepEqual(await visibleGroups(), ['services'], 'the last group is remembered');
    await f.page.evaluate(() => { location.hash = 'system/about'; });
    await f.page.waitForFunction(() => document.getElementById('page-system').classList.contains('active'));
    assert.equal(await f.page.locator('#page-system .subnav-tab[aria-selected="true"]').textContent(), 'About');
    await f.page.evaluate(() => { location.hash = 'status'; });
    await f.page.waitForFunction(() => document.getElementById('page-status').classList.contains('active'));
    await f.page.locator('#uplink-lan-name-edit').click();
    await f.page.waitForFunction(() => document.activeElement && document.activeElement.id === 'net-hostname');
    assert.deepEqual(await visibleGroups(), ['internet'], '"Change" opens the group with the name field');
    assert.equal(await f.page.locator('#page-tailscale .subnav-tab').count(), 3);
    assert.equal(await f.page.evaluate(() => document.querySelectorAll('.page-section').length), 8);
    assert.equal(await f.page.evaluate(() => [...document.querySelectorAll('.page-section')].every(s => s.parentElement.classList.contains('page-container'))), true,
      'every page inside the centred container');
    assert.deepEqual(f.errors, []); await f.context.close(); count++;
    console.log(`PASS: ${count} browser scenarios (synthetic APIs, including operational/health settings, profiles, guided setup, MQTT backoff, Service Gateway destination tests and malformed/stale-state refusal)`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
