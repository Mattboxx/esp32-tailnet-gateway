/* README screenshots of the real embedded Web UI (main/index.html) with the
 * synthetic documentation data of ui_fixture.cjs: no device, credential or
 * real network appears. The version shown is the firmware's PROJECT_VER.
 * Run: NODE_PATH=<playwright> node tools/readme_screenshots.cjs <folder>
 * The first-boot wizard is captured by tools/test_first_boot_ui.cjs <folder>. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { install, data } = require('./ui_fixture.cjs');

const folder = process.argv[2];
if (!folder) { console.error('usage: node tools/readme_screenshots.cjs <folder>'); process.exit(2); }
fs.mkdirSync(folder, { recursive: true });
const cmake = fs.readFileSync(path.join(__dirname, '..', 'CMakeLists.txt'), 'utf8');
const version = /set\(PROJECT_VER "([^"]+)"\)/.exec(cmake)[1];
const shots = [
  // [file, UI route, advanced mode, viewport width, viewport height, card to crop]
  ['status', 'status', false, 1440, 900],
  ['status-phone', 'status', false, 390, 844],
  ['service-gateway', 'network/services', true, 1440, 900],
  ['trends', 'status', false, 1440, 900, '#trend-card'],
  ['history', 'tools/history', true, 1440, 900],
  ['firewall', 'firewall', true, 1440, 900],
  ['recovery', 'operations', true, 1440, 900],
  ['notifications', 'automation/notifications', true, 1440, 900, '#nt-tg-card'],
  ['roles', 'status', false, 1440, 900, '#wizard-card'],
  ['interface-mode', 'system', false, 1440, 900, '#ui-mode-card'],
  ['profiles', 'system', true, 1440, 900, '#profile-card'],
  ['login', 'status', false, 1440, 900, '#loginForm'],
];
const fixtures = {
  '/api/status': { ...data['/api/status'], version, mem_internal_free: 46800,
    sta: { ...data['/api/status'].sta, ssid: 'Example-Lab' } },
  '/api/system': { ...data['/api/system'], version },
  '/api/operations': { ...data['/api/operations'], internal_min: 38200, internal_largest: 31744 },
  '/api/events': { ...data['/api/events'], events: data['/api/events'].events.map(event =>
    event.k === 'boot' ? { ...event, m: 'Started ' + version + ' from ota_0, reset SW: web ota' } : event) },
};

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome', args: ['--lang=en-US'] });
  try {
    for (const [file, hash, advanced, width, height, anchor] of shots) {
      const touch = width < 768;
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: touch ? 2 : 1, hasTouch: touch, isMobile: touch, locale: 'en-US', timezoneId: 'UTC', serviceWorkers: 'block' });
      await context.addInitScript(a => { try { localStorage.setItem('ui-advanced', a ? '1' : '0'); } catch (e) {} }, advanced);
      // Route the entire browser context through the synthetic device. Abort
      // anything else, including external fonts or resources in firmware markup.
      await context.route('**/*', route => route.abort('blockedbyclient'));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      const overrides = file === 'login' ? { ...fixtures,
        '/api/auth/status': { ...data['/api/auth/status'], authenticated: false } } : fixtures;
      await install(page, overrides);
      await page.goto('http://esp32.test/#' + hash);
      await page.waitForTimeout(1200);
      const options = { path: path.join(folder, file + '.png'), animations: 'disabled' };
      if (anchor) {
        // Sticky bars must not cover the top of a card when Chromium scrolls to it.
        await page.evaluate(() => {
          for (const element of document.querySelectorAll('header, nav, [role=tablist]')) {
            if (getComputedStyle(element).position === 'sticky') element.style.position = 'static';
          }
        });
        await page.locator(anchor).screenshot(options);
      } else {
        await page.screenshot(options);
      }
      if (errors.length) throw new Error(file + ': ' + errors.join('; '));
      await context.close();
      console.log('saved', file);
    }
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
