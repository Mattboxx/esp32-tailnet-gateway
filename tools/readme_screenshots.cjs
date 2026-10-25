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
  // [file, hash, advanced, width, height, element to bring to the top]
  ['status', 'status', false, 1440, 900],
  ['service-gateway', 'network', true, 1440, 900],
  ['tailscale', 'tailscale', true, 1440, 900],
  ['firewall', 'firewall', true, 1440, 900],
  ['status-phone', 'status', false, 390, 844],
  ['network-services', 'network/services', true, 1440, 900],
  ['history', 'tools/history', true, 1440, 900],
  ['firmware', 'system/firmware', true, 1440, 900],
  ['backup', 'system/backup', true, 1440, 900],
  ['notifications', 'automation/notifications', true, 1440, 900],
  ['devices', 'operations', true, 1440, 900],
  ['trends', 'status', false, 1440, 900, '#trend-card'],
];
// Memory figures in the range measured on an N16R8 with every option on
// (see docs/VALIDATION-STATUS.md), so the pictures do not suggest a starved board.
const status = Object.assign({}, data['/api/status'], { version, mem_internal_free: 46800 });
const system = Object.assign({}, data['/api/system'], { version });
const operations = Object.assign({}, data['/api/operations'], { internal_min: 38200, internal_largest: 31744 });

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome', args: ['--lang=en-US'] });
  try {
    for (const [file, hash, advanced, width, height, anchor] of shots) {
      const touch = width < 768;
      const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: touch ? 2 : 1, hasTouch: touch, isMobile: touch, locale: 'en-US' });
      await context.addInitScript(a => { try { localStorage.setItem('ui-advanced', a ? '1' : '0'); } catch (e) {} }, advanced);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await install(page, { '/api/status': status, '/api/system': system, '/api/operations': operations });
      await page.goto('http://esp32.test/#' + hash);
      await page.waitForTimeout(1200);
      if (anchor) {
        await page.locator(anchor).evaluate(e => { window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 72); });
        await page.waitForTimeout(400);
      }
      if (errors.length) throw new Error(`${file}: ${errors.join('; ')}`);
      await page.screenshot({ path: path.join(folder, `${file}.png`) });
      await context.close();
      console.log('saved', file);
    }
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
