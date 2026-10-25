// Render the real vendored installer, including the no-Web-Serial phone path.
// No USB device is requested or flashed. Chromium emulation, not physical iOS.
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const root = path.resolve(__dirname, '..', 'build', 'site');
const shots = process.argv[2];
const projectPath = new URL(fs.readFileSync(path.join(root, 'index.html'), 'utf8')
  .match(/rel="canonical" href="([^"]+)"/)[1]).pathname;
const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'};
const server = http.createServer((req,res) => {
  const url = new URL(req.url,'http://localhost');
  const file = path.resolve(root,'.'+decodeURIComponent(url.pathname.slice(projectPath.length-1)));
  if (!url.pathname.startsWith(projectPath) || !file.startsWith(root+path.sep)) {res.writeHead(404);return res.end();}
  const target = fs.existsSync(file) && fs.statSync(file).isDirectory() ? path.join(file,'index.html') : file;
  if (!fs.existsSync(target)) {res.writeHead(404);return res.end();}
  res.writeHead(200,{'Content-Type':types[path.extname(target)]||'application/octet-stream'});
  fs.createReadStream(target).pipe(res);
});
(async () => {
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
  const failures=[];
  try {
    if (shots) fs.mkdirSync(shots,{recursive:true});
    for (const [width,height] of [[320,640],[390,844],[844,390],[1440,900]]) {
      for (const theme of ['dark','light']) {
        const mobile = width!==1440;
        const context = await browser.newContext({viewport:{width,height},isMobile:mobile,hasTouch:mobile,colorScheme:theme});
        if (mobile) await context.addInitScript(()=>{delete Navigator.prototype.serial;});
        const page = await context.newPage();
        const errors=[];
        page.on('pageerror',e=>errors.push(String(e)));
        await page.goto(`http://127.0.0.1:${server.address().port}${projectPath}install-firmware/`);
        await page.waitForFunction(()=>customElements.get('esp-web-install-button'));
        const label=`${width}x${height}-${theme}`;
        if (shots) await page.screenshot({path:path.join(shots,`installer-${label}.png`),fullPage:true});
        try {
          const cssVersion=createHash('sha256').update(fs.readFileSync(path.join(root,'assets/site.css'))).digest('hex').slice(0,12);
          assert.equal(new URL(await page.locator('link[rel="stylesheet"]').getAttribute('href'),page.url()).searchParams.get('v'),cssVersion,'fresh CSS URL after deployment');
          assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'page must fit viewport');
          const installer=page.locator('esp-web-install-button');
          if (mobile) {
            assert.equal(await page.evaluate(()=> 'serial' in navigator),false,'exercise actual unsupported branch');
            assert.equal(await installer.getAttribute('install-unsupported'),'');
            const note=page.locator('[slot="unsupported"]');
            assert.equal(await note.isVisible(),true);
            assert.equal(await note.evaluate(el=>el.getClientRects().length),1,'unsupported notice must be one unfragmented panel');
            const metrics=await note.evaluate(el=>{const a=el.getBoundingClientRect();const b=el.closest('main').getBoundingClientRect();return {left:a.left,right:a.right,bLeft:b.left,bRight:b.right};});
            assert(metrics.left>=metrics.bLeft && metrics.right<=metrics.bRight+1,'notice must stay inside content');
            assert.equal(await page.locator('[slot="activate"]').isVisible(),false,'unsupported browser must not offer USB connect');
          } else {
            assert.equal(await installer.getAttribute('install-supported'),'');
            assert.equal(await page.locator('[slot="activate"]').isVisible(),true);
            assert.equal(await page.locator('[slot="unsupported"]').isVisible(),false);
          }
          assert.equal(errors.length,0,errors.join('; '));
        } catch(error) {failures.push(label+': '+error.message);}
        await context.close();
      }
    }
  } finally {await browser.close();server.close();}
  if (failures.length) {console.log(failures.join('\n'));process.exitCode=1;}
  else console.log('PASS installer: phone no-Web-Serial and desktop supported paths, 8 light/dark layouts, no USB operations');
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
