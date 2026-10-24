/* Full-page review captures of every Web UI tab with ui_fixture.cjs data
 * (invented documentation values), for interface reviews. Not a test.
 * Run: NODE_PATH=<playwright> node tools/ui_review_shots.cjs <folder> [overrides.json] */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { install } = require('./ui_fixture.cjs');

const folder = process.argv[2];
if (!folder) { console.error('usage: node tools/ui_review_shots.cjs <folder> [overrides.json]'); process.exit(2); }
const overrides = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], 'utf8')) : {};
fs.mkdirSync(folder, { recursive: true });
const tabs = ['status', 'network', 'tailscale', 'firewall', 'tools', 'operations', 'automation', 'system'];
const runs = [['desktop-adv', 1440, 900, true], ['desktop-simple', 1440, 900, false], ['phone-simple', 390, 844, false]];

(async () => {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  try {
    for (const [label, width, height, advanced] of runs) {
      const touch = width < 768;
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch, isMobile: touch, locale: 'en-US' });
      await context.addInitScript(a => { try { localStorage.setItem('ui-advanced', a ? '1' : '0'); localStorage.setItem('setup-roles-opened', 'x'); } catch (e) {} }, advanced);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await install(page, overrides);
      await page.goto('http://esp32.test/#status');
      await page.waitForTimeout(800);
      for (const tab of tabs) {
        await page.evaluate(t => { location.hash = t; }, tab);
        await page.waitForTimeout(700);
        await page.screenshot({ path: path.join(folder, `${label}-${tab}.png`), fullPage: true });
      }
      if (errors.length) console.log(label, 'page errors:', errors.join('; '));
      await context.close();
    }
  } finally { await browser.close(); }
  console.log('saved', runs.length * tabs.length, 'captures to', folder);
})().catch(e => { console.error(e); process.exit(1); });
