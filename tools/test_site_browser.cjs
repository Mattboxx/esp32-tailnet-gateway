// Browser checks for the static website at representative viewports.
// Usage: python tools/build_site.py && node tools/test_site_browser.cjs [shots-dir]
// Needs the playwright package (NODE_PATH) and a Chrome channel. Offline:
// serves build/site from a local HTTP server; no external requests.
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.resolve(process.env.SITE_TEST_DIR || path.join(__dirname, '..', 'build', 'site'));
const shots = process.argv[2];
const homepage = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const canonical = homepage.match(/rel="canonical" href="([^"]+)"/)[1];
const expectsPreviewNotice = homepage.includes('aria-label="Firmware availability"');
const projectPath = new URL(canonical).pathname;
const remoteBase = process.env.SITE_TEST_BASE_URL;
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.xml': 'application/xml', '.txt': 'text/plain', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  const requestPath = decodeURIComponent(req.url.split('?')[0]);
  if (!requestPath.startsWith(projectPath)) { res.writeHead(404); return res.end('wrong project path'); }
  let file = path.join(root, requestPath.slice(projectPath.length));
  if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) { res.writeHead(404); return res.end('missing'); }
  res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

const viewports = [[320, 640], [360, 740], [390, 844], [430, 932], [768, 1024], [1024, 768], [1440, 900], [1920, 1080], [844, 390]];
const pages = fs.readdirSync(root, { withFileTypes: true }).filter(d => d.isDirectory() && fs.existsSync(path.join(root, d.name, 'index.html'))
  && !/noindex/.test(fs.readFileSync(path.join(root, d.name, 'index.html'), 'utf8'))).map(d => d.name + '/');
pages.unshift('');

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = remoteBase || `http://127.0.0.1:${server.address().port}${projectPath}`;
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
  const failures = [];
  try {
    for (const [width, height] of viewports) {
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: width < 768 });
      // Never contact payment providers: exercise the real links with local fixtures.
      const providerUrls = ['https://github.com/sponsors/Mattboxx', 'https://ko-fi.com/mattboxx'];
      let providerRequests = 0;
      for (const url of providerUrls) await context.route(url, route => {
        providerRequests++;
        return route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>Payment provider fixture</title>' });
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('requestfailed', r => errors.push('request failed ' + r.url()));
      for (const slug of pages) {
        await page.goto(base + slug, { waitUntil: 'load' });
        if (await page.isVisible('.release-note') !== expectsPreviewNotice) failures.push(`${slug}: release availability notice does not match built release state`);
        const actualCanonical = await page.locator('link[rel="canonical"]').getAttribute('href');
        if (actualCanonical !== canonical + slug) failures.push(`${slug}: wrong canonical ${actualCanonical}`);
        const where = `${width}x${height} /${slug}`;
        const r = await page.evaluate(() => {
          const doc = document.documentElement;
          const small = [];
          document.querySelectorAll('header button, header a, .btn, .menu').forEach(el => {
            const b = el.getBoundingClientRect();
            if (b.width && b.height && b.height < 44 && getComputedStyle(el).display !== 'none') small.push(el.textContent.trim().slice(0, 20) + ':' + Math.round(b.height));
          });
          const clipped = [...document.querySelectorAll('main *')].filter(el => {
            const b = el.getBoundingClientRect();
            return b.right > window.innerWidth + 1 && getComputedStyle(el).position !== 'fixed' && !el.closest('table, pre, figure.diagram');
          }).map(el => el.tagName + '.' + el.className).slice(0, 3);
          return { overflow: doc.scrollWidth - window.innerWidth, small, clipped, fontMin: Math.min(...[...document.querySelectorAll('main p, main li')].map(e => parseFloat(getComputedStyle(e).fontSize))) };
        });
        if (r.overflow > 0) failures.push(`${where}: horizontal page overflow ${r.overflow}px`);
        if (r.clipped.length) failures.push(`${where}: content beyond viewport ${r.clipped.join(', ')}`);
        if (width < 768 && r.small.length) failures.push(`${where}: touch targets under 44px ${r.small.join(', ')}`);
        if (r.fontMin < 14) failures.push(`${where}: body text ${r.fontMin}px`);
        if (shots && (slug === '' || slug === 'service-gateway/') ) await page.screenshot({ path: path.join(shots, `site-${width}x${height}-${slug.replace('/', '') || 'home'}.png`), fullPage: false });
      }
      if (width < 768) {
        await page.goto(base, { waitUntil: 'load' });
        await page.click('.menu');
        if (!(await page.isVisible('#site-nav'))) failures.push(`${width}: mobile menu does not open`);
        if (shots) await page.screenshot({ path: path.join(shots, `site-${width}-menu.png`) });
      }
      await page.goto(base, { waitUntil: 'load' });
      if (width > 760 && await page.isVisible('.menu')) failures.push(`${width}: mobile menu button visible on a wide screen`);
      if (width > 760 && !(await page.isVisible('#site-nav'))) failures.push(`${width}: main navigation hidden on a wide screen`);
      await page.click('.search-open');
      await page.fill('#search-input', 'headscale');
      const hits = await page.locator('#search-results a').count();
      if (!hits) failures.push(`${width}: search found nothing for "headscale"`);
      await page.keyboard.press('Escape');
      // Donation choice is opt-in, keyboard accessible and fits phone/desktop screens.
      if (providerRequests) failures.push(`${width}: provider requested before a choice`);
      const support = page.locator('.tools [data-support-open]');
      const dialog = page.locator('#support-dialog');
      await support.click();
      await dialog.waitFor({ state: 'visible' });
      const dialogBox = await dialog.boundingBox();
      if (dialogBox.x < 0 || dialogBox.y < 0 || dialogBox.x + dialogBox.width > width || dialogBox.y + dialogBox.height > height)
        failures.push(`${width}: support dialog outside viewport`);
      if (await dialog.evaluate(el => el.scrollWidth > el.clientWidth)) failures.push(`${width}: support dialog horizontal overflow`);
      for (const url of providerUrls) {
        const link = dialog.locator(`a[href="${url}"]`);
        if (await link.count() !== 1 || await link.getAttribute('target') !== '_blank' || !(await link.getAttribute('rel')).includes('noopener'))
          failures.push(`${width}: wrong support provider destination or opener protection`);
        const box = await link.boundingBox();
        if (box.height < 44 || box.width < 44) failures.push(`${width}: small support choice target`);
      }
      await page.keyboard.press('Tab');
      if (!(await page.evaluate(() => !!document.activeElement.closest('#support-dialog')))) failures.push(`${width}: modal focus escaped`);
      await page.keyboard.press('/');
      if (await page.isVisible('.search-panel')) failures.push(`${width}: search opens behind support dialog`);
      if (shots && (width === 390 || width === 1440)) {
        for (const theme of ['dark', 'light']) {
          await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
          await page.screenshot({ path: path.join(shots, `support-${width}-${theme}.png`) });
        }
        await page.evaluate(() => document.documentElement.removeAttribute('data-theme'));
      }
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      if (!(await support.evaluate(el => el === document.activeElement))) failures.push(`${width}: support trigger focus not restored`);
      await support.click();
      await dialog.locator('.support-close').click();
      await dialog.waitFor({ state: 'hidden' });
      await support.click();
      await page.mouse.click(4, 4);
      await dialog.waitFor({ state: 'hidden' });
      if (providerRequests) failures.push(`${width}: opening or dismissing support contacted a provider`);
      await page.locator('footer [data-support-open]').click();
      await dialog.waitFor({ state: 'visible' });
      for (const url of providerUrls) {
        const [popup] = await Promise.all([context.waitForEvent('page'), dialog.locator(`a[href="${url}"]`).click()]);
        await popup.waitForLoadState('domcontentloaded');
        if (popup.url() !== url) failures.push(`${width}: provider choice opened wrong address`);
        await popup.close();
      }
      await dialog.locator('.support-close').click();
      await page.goto(base + 'about/', { waitUntil: 'load' });
      await page.locator('main [data-support-open]').click();
      await dialog.waitFor({ state: 'visible' });
      await page.keyboard.press('Escape');
      await page.goto(base + 'screenshots/', { waitUntil: 'load' });
      const uiImages = page.locator('main img');
      for (let i = 0; i < await uiImages.count(); i++) {
        const img = uiImages.nth(i);
        await img.scrollIntoViewIfNeeded();
        await img.evaluate(el => el.decode());
        const dimensions = await img.evaluate(el => ({w:el.naturalWidth,h:el.naturalHeight,
          expectedW:Number(el.getAttribute('width')),expectedH:Number(el.getAttribute('height'))}));
        if (dimensions.w !== dimensions.expectedW || dimensions.h !== dimensions.expectedH)
          failures.push(`${width}: screenshot dimensions mismatch ${await img.getAttribute('src')}`);
      }
      if (errors.length) failures.push(`${width}: console/page errors ${[...new Set(errors)].slice(0, 3).join(' | ')}`);
      await context.close();
    }
    const noJs = await browser.newContext({ javaScriptEnabled: false });
    const fallback = await noJs.newPage();
    await fallback.goto(base);
    for (const url of ['https://github.com/sponsors/Mattboxx', 'https://ko-fi.com/mattboxx']) {
      if (!(await fallback.locator(`footer noscript a[href="${url}"]`).isVisible())) failures.push('Support destination missing without JavaScript');
    }
    await noJs.close();
  } finally {
    await browser.close(); server.close();
  }
  if (failures.length) { console.log(failures.join('\n')); console.log(`FAIL ${failures.length}`); process.exit(1); }
  console.log(`PASS: website ${pages.length} pages x ${viewports.length} viewports: layout, navigation, support choice/focus/dismissal/provider links/no-JS fallback, search, no console errors`);
})();
