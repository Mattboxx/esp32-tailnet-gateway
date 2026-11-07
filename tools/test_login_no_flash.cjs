/* The dashboard must not be visible before the session is known (3.0.8).
 * Actual SPA, synthetic APIs, Chromium via Playwright. /api/auth/status is
 * held back for 1.2 s; the navigation bar and page content are sampled
 * every animation frame from the first paint until the answer arrives:
 * - signed out: never visible, then the login form is shown and the
 *   dashboard stays hidden;
 * - signed in and no password required: hidden while waiting, then visible;
 * - status endpoint unreachable (file preview): dashboard shown, as before;
 * - before any script runs (the page is painted while it streams from the
 *   ESP) the markup alone keeps the dashboard hidden; the old markup
 *   (<body> without auth-open) shows it, so the check detects the defect. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { builtHtml, serveAsset } = require('./ui_build.cjs');

const fixed = builtHtml();
assert.ok(fixed.includes('<body class="auth-open">'), 'page must start hidden');
const old = fixed.replace('<body class="auth-open">', '<body>');

async function run(browser, html, status) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let answered = false;
  await page.route('http://esp32.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
    if (url.pathname.startsWith('/i18n/') && await serveAsset(route, url.pathname)) return;
    if (url.pathname === '/api/auth/status') {
      await new Promise(r => setTimeout(r, 1200));
      answered = true;
      if (status === 'unreachable') return route.abort();
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(status) });
    }
    /* Other APIs: empty answers once signed in, 401 while signed out. */
    if (status !== 'unreachable' && status.auth_required && !status.authenticated)
      return route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"auth required"}' });
    return route.fulfill({ contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(() => {
    window.__samples = [];
    const sample = () => {
      const nav = document.querySelector('body > .nav');
      const pageEl = document.querySelector('body > .page-container');
      if (nav && pageEl) {
        const vis = el => getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
        window.__samples.push({ nav: vis(nav), page: vis(pageEl), t: performance.now() });
      }
      requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
  await page.goto('http://esp32.test/');
  await page.waitForFunction(() => window.__samples.length > 5);
  const before = await page.evaluate(() => window.__samples.slice());
  assert.equal(answered, false, 'samples must be taken before the status answer');
  await page.waitForTimeout(1800);
  const after = await page.evaluate(() => {
    const vis = el => el && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
    return { nav: vis(document.querySelector('body > .nav')), login: vis(document.getElementById('authLogin')),
             samples: window.__samples.length };
  });
  await context.close();
  return { shownWhileWaiting: before.some(s => s.nav || s.page), before: before.length, after, errors };
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    const signedOut = { password_set: true, auth_enabled: true, auth_required: true, authenticated: false, session_timeout_s: 0 };
    let r = await run(browser, fixed, signedOut);
    assert.equal(r.shownWhileWaiting, false, 'dashboard visible before sign-in');
    assert.equal(r.after.login, true, 'login form shown');
    assert.equal(r.after.nav, false, 'dashboard hidden behind the login');

    const signedIn = { ...signedOut, authenticated: true };
    r = await run(browser, fixed, signedIn);
    assert.equal(r.shownWhileWaiting, false, 'hidden until the session is confirmed');
    assert.equal(r.after.nav, true, 'dashboard shown once signed in');
    assert.equal(r.after.login, false);

    const open = { password_set: true, auth_enabled: false, auth_required: false, authenticated: true, session_timeout_s: 0 };
    r = await run(browser, fixed, open);
    assert.equal(r.shownWhileWaiting, false);
    assert.equal(r.after.nav, true, 'no password required: dashboard shown');

    r = await run(browser, fixed, 'unreachable');
    assert.equal(r.after.nav, true, 'unreachable status keeps the preview fallback');

    /* Before any script runs (the page arrives slowly from the ESP and is
     * painted while it streams): what the markup alone shows. */
    const preScript = async html => {
      const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 800 } });
      const page = await context.newPage();
      await page.route('http://esp32.test/**', route => route.fulfill({ contentType: 'text/html', body: html }));
      await page.goto('http://esp32.test/');
      const shown = await page.evaluate(() => ['body > .nav', 'body > .page-container'].some(s => {
        const el = document.querySelector(s); return el && getComputedStyle(el).visibility !== 'hidden'; }));
      await context.close();
      return shown;
    };
    assert.equal(await preScript(fixed), false, 'dashboard painted before the script runs');
    assert.equal(await preScript(old), true, 'the check must detect the old flash');
    console.log('PASS: dashboard hidden from first paint until /api/auth/status answers (signed out: login only; ' +
                'signed in / no password: shown after the answer; unreachable: preview fallback); old markup detected');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
