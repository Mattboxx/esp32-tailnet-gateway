/* Diagnostics → Hardware "Connection & security" section (3.0.8): the actual
 * SPA with synthetic /api/system/diag and /api/operations, Chromium.
 * - assembly self-test states (active / C fallback / not checked), checksum
 *   cycles, TLS distrust counters, DNS relay stray answers;
 * - reconnect counters, last reconnect duration and stages, DERP relay
 *   reconnects and the sum of dropped/refused packets;
 * - values from the device are escaped (a loss reason with markup stays text);
 * - /api/operations failing keeps the diag part;
 * - the labels are translated (Italian). */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');
const html = builtHtml();

const diag = {
  chip: {}, heap: {}, partitions: [], tasks: [], sd: {}, nvs: {},
  crypto_asm: { chacha20: 1, poly1305: -1, x25519_mul: 2, x25519_sqr_pie: true, x25519_calls: 4, x25519_us_last: 9876,
                x25519_us_max: 12345, x25519_ctrl_calls: 3, x25519_ctrl_us_last: 10250, x25519_mul_cycles: [1500, 820, 610, 1100] },
  fast_checksum: { checked: true, active: true, cycles_1400_fast: 1633, cycles_1400_lwip: 2260 },
  tls_distrust: { distrusted_cas: 8, refused_chains: 2 },
  dns_cache: { enabled: true, healthy: true, queries: 10, hits: 4, misses: 6, hit_pct: 40, entries: 3, capacity: 256,
               evictions: 0, upstream_stray: 5, cache_bytes: 331776 },
};
const ops = {
  tailnet_reconnects: { control_losses: 3, last_loss: 'server sent GOAWAY <b>x</b>', failed_attempts_since: 1,
    last_failed_attempt: 'TCP connect failed', last_reconnect_ms: 2400, last_reconnect_stages: 'tcp 120 ms, noise 80 ms',
    derp_retry: 1, derp_rx_watchdog: 1 },
  forward_drops: { sta_input_shed: 4, wg_rx_queue_full: 3, wg_tx_send_failed: 0 },
};

async function page(browser, opts) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: opts.lang ? 'it-IT' : 'en-US' });
  if (opts.lang) await context.addInitScript(l => { try { localStorage.setItem('ui-lang', l); localStorage.setItem('ui-advanced', '1'); } catch (e) {} }, opts.lang);
  else await context.addInitScript(() => { try { localStorage.setItem('ui-advanced', '1'); } catch (e) {} });
  const p = await context.newPage();
  const errors = [];
  p.on('pageerror', e => errors.push(e.message));
  await p.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
    const json = b => route.fulfill({ contentType: 'application/json', body: JSON.stringify(b) });
    if (url.pathname === '/api/auth/status')
      return json({ password_set: true, auth_enabled: true, auth_required: true, authenticated: true, session_timeout_s: 0 });
    if (url.pathname === '/api/system/diag') return json(diag);
    if (url.pathname === '/api/operations') return opts.opsFail ? route.fulfill({ status: 500, body: '' }) : json(ops);
    return json({});
  });
  await p.goto('http://esp32.test/#tools');
  await p.waitForFunction(() => typeof loadDiag === 'function');
  await p.evaluate(() => loadDiag());
  await p.waitForFunction(() => { const e = document.getElementById('diag-conn'); return e && !/Loading|Caricamento/.test(e.textContent) && e.textContent.length > 40; });
  await p.waitForTimeout(300);
  const out = await p.evaluate(() => ({ conn: document.getElementById('diag-conn').textContent,
    connHtml: document.getElementById('diag-conn').innerHTML, dns: document.getElementById('diag-dnscache').textContent }));
  await context.close();
  return { ...out, errors };
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    let r = await page(browser, {});
    assert.deepEqual(r.errors, []);
    assert.match(r.conn, /ChaCha20\s*active/);
    assert.match(r.conn, /Poly1305\s*C fallback/);
    assert.match(r.conn, /checksum\s*active\s*\(1633 \/ 2260/);
    assert.match(r.conn, /Key exchange \(X25519\):\s*vector unit \(PIE\)\s*·\s*squares on PIE/);
    assert.match(r.conn, /WireGuard, last:\s*9\.9 ms\s*\(max\s*12\.3 ms\)/);
    assert.match(r.conn, /control plane, last:\s*10\.3 ms/);
    assert.match(r.conn, /Field product cycles \(C \/ assembly \/ PIE\):\s*1500 \/ 820 \/ 610/);
    assert.match(r.conn, /Compromised certificate authorities blocked:\s*8/);
    assert.match(r.conn, /refused connections:\s*2/);
    assert.match(r.conn, /Control-plane losses since boot:\s*3/);
    assert.match(r.conn, /Last control reconnect:\s*2\.4 s \(tcp 120 ms, noise 80 ms\)/);
    assert.match(r.conn, /failed attempts:\s*1 \(TCP connect failed\)/);
    assert.match(r.conn, /Relay reconnects \(DERP\):\s*2/);
    assert.match(r.conn, /packets dropped or refused since boot:\s*7/);
    assert.ok(r.conn.includes('server sent GOAWAY <b>x</b>') && !r.connHtml.includes('<b>x</b>'), 'device text escaped');
    assert.match(r.dns, /Stray upstream answers discarded:\s*5/);

    const fullCa = diag.crypto_asm;
    /* scalar assembly chosen, no handshake yet: no timing, no PIE squares, no PIE cycles */
    diag.crypto_asm = { chacha20: 1, poly1305: 1, x25519_mul: 1, x25519_sqr_pie: false, x25519_calls: 0, x25519_mul_cycles: [1500, 820, 0, 1100] };
    r = await page(browser, {});
    assert.match(r.conn, /Key exchange \(X25519\):\s*assembly/);
    assert.ok(!/squares on PIE|WireGuard, last|control plane, last/.test(r.conn));
    assert.match(r.conn, /1500 \/ 820 \/ —/);
    diag.crypto_asm = { chacha20: 1, poly1305: -1, x25519_mul: -1 };
    r = await page(browser, {});
    assert.match(r.conn, /Key exchange \(X25519\):\s*C fallback/);
    assert.ok(!/Field product cycles/.test(r.conn));
    diag.crypto_asm = fullCa;
    r = await page(browser, { opsFail: true });
    assert.match(r.conn, /Compromised certificate authorities blocked:\s*8/);
    assert.ok(!/Control-plane losses/.test(r.conn));

    r = await page(browser, { lang: 'it' });
    assert.match(r.conn, /Crittografia in assembly:/);
    assert.match(r.conn, /Scambio di chiavi \(X25519\):\s*unità vettoriale \(PIE\)/);
    assert.match(r.conn, /Perdite del piano di controllo dall’avvio:\s*3/);
    assert.match(r.dns, /Risposte upstream estranee scartate:\s*5/);
    console.log('PASS: Diagnostics connection & security section: self-tests, TLS distrust, DNS strays, reconnect ' +
                'duration/stages, DERP and drop counters, X25519 implementation/timings/cycles (PIE, assembly, C), escaping, '
                + 'operations failure, Italian labels');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
