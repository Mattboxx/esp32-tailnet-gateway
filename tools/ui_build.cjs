/* The page the firmware actually serves: minified, translations and SJCL
 * injected by main/gen_index_html_gz.py. UI_SOURCE=raw tests index.html as is. */
function builtHtml() {
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), { spawnSync } = require('node:child_process');
  const src = path.join(__dirname, '../main/index.html');
  if (process.env.UI_SOURCE === 'raw') return fs.readFileSync(src, 'utf8');
  const out = path.join(os.tmpdir(), 'tailnet-gateway-ui-' + process.pid + '.html');
  const r = spawnSync(process.env.PYTHON || 'python', [path.join(__dirname, '../main/gen_index_html_gz.py'), '--html', src, out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('UI build failed: ' + r.stderr + r.stdout);
  const html = fs.readFileSync(out, 'utf8'); fs.unlinkSync(out); return html;
}
module.exports = { builtHtml };
