/* The page the firmware actually serves: minified, SJCL injected and one
 * script per language, by main/gen_index_html_gz.py. UI_SOURCE=raw tests
 * index.html as is (English only). */
let built = null;
function build() {
  if (built) return built;
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), { spawnSync } = require('node:child_process');
  const src = path.join(__dirname, '../main/index.html');
  if (process.env.UI_SOURCE === 'raw') return (built = { html: fs.readFileSync(src, 'utf8'), assets: {} });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tailnet-gateway-ui-'));
  const out = path.join(dir, 'index.html');
  const r = spawnSync(process.env.PYTHON || 'python', [path.join(__dirname, '../main/gen_index_html_gz.py'), '--html', src, out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('UI build failed: ' + r.stderr + r.stdout);
  const assets = {}, langDir = path.join(dir, 'i18n');
  if (fs.existsSync(langDir)) for (const name of fs.readdirSync(langDir)) assets['/i18n/' + name] = fs.readFileSync(path.join(langDir, name), 'utf8');
  built = { html: fs.readFileSync(out, 'utf8'), assets };
  fs.rmSync(dir, { recursive: true, force: true });
  return built;
}
const builtHtml = () => build().html;
/* Answers a language script request the way the firmware does; false for any other path. */
async function serveAsset(route, pathname) {
  const body = build().assets[pathname];
  if (body === undefined) return false;
  await route.fulfill({ status: 200, contentType: 'text/javascript; charset=utf-8', body });
  return true;
}
module.exports = { builtHtml, serveAsset };
