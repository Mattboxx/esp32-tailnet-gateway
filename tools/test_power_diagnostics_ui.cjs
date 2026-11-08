// Actual System-tab TX-power field, reset-history card and boot-fault modal
// from main/index.html, with a deterministic DOM fixture. No browser/device.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '../main/index.html'), 'utf8').replace(/\r\n/g, '\n');
function slice(startText, endText, includeEnd) {
  const a = html.indexOf(startText);
  assert.ok(a >= 0, 'missing ' + startText);
  const b = html.indexOf(endText, a + startText.length);
  assert.ok(b >= 0, 'missing end of ' + startText);
  return html.slice(a, b + (includeEnd ? endText.length : 0));
}
const fnEnd = '\n    }\n';
const code = [
  slice('    function escapeHtml(s) {', fnEnd, true),
  slice('    var s_txLive = null;', fnEnd, true),
  slice('    function _resetReasonClass(reason) {', fnEnd, true),
  slice('    function _fmtWallclock(ts) {', fnEnd, true),
  slice('    /* Brownout rows:', '    function renderResetHistory(hist) {', false),
  slice('    function renderResetHistory(hist) {', fnEnd, true),
  slice('    function checkPanicAndWarn() {', fnEnd, true),
  'function loadTx(d) {\n' + slice('          var txShown', '          updateTxPowerDbm(txShown);', true) + '\n}',
].join('\n');

const elements = {};
function el(id) {
  return elements[id] || (elements[id] = {
    id, value: '', textContent: '', innerHTML: '', className: '', listeners: {},
    classList: { set: new Set(), add(c) { this.set.add(c); }, remove(c) { this.set.delete(c); } },
    addEventListener(t, f) { this.listeners[t] = f; }, removeEventListener(t) { delete this.listeners[t]; },
  });
}
let systemBody = null;
const session = new Map();
const context = {
  document: { getElementById: el },
  sessionStorage: { getItem: k => session.has(k) ? session.get(k) : null, setItem: (k, v) => session.set(k, v) },
  apiFetch: () => Promise.resolve({ json: () => Promise.resolve(systemBody) }),
};
vm.createContext(context);
vm.runInContext(code, context);
const turn = () => new Promise(setImmediate);
const row = (reason, who, crash) => ({ wallclock: 1792000000, reason, who: who || '', crash: crash || '' });

(async () => {
  /* TX power: the field shows only the persisted override; the live value is
   * reported beside it and never becomes the next save's override. */
  context.loadTx({ tx_power: 80 });
  assert.equal(el('sys-tx-power').value, 0);
  assert.equal(el('sys-tx-power-dbm').textContent, '= IDF default (now 20.00 dBm)');
  context.loadTx({ tx_power: 60, tx_power_nvs: 0 });   /* override just removed, reboot pending */
  assert.equal(el('sys-tx-power').value, 0);
  assert.equal(el('sys-tx-power-dbm').textContent, '= IDF default (now 15.00 dBm)');
  context.loadTx({ tx_power: 60, tx_power_nvs: 60 });
  assert.equal(el('sys-tx-power').value, 60);
  assert.equal(el('sys-tx-power-dbm').textContent, '≈ 15.00 dBm (now 15.00 dBm)');
  context.loadTx({ tx_power_nvs: 84 });                /* no live value; PHY limit 20 dBm */
  assert.equal(el('sys-tx-power').value, 84);
  assert.equal(el('sys-tx-power-dbm').textContent, '≈ 20.00 dBm');
  context.loadTx({});
  assert.equal(el('sys-tx-power').value, 0);

  /* Reset-history card. */
  context.renderResetHistory([row('SW', 'web ota'), row('POWERON')]);
  assert.equal(el('sys-hist-badge').textContent, '2');
  assert.equal(el('sys-hist-badge').className, 'badge badge-success');
  assert.ok(!el('sys-hist-tbody').innerHTML.includes('brownout'));
  context.renderResetHistory([row('POWERON'), row('BROWNOUT'), row('SW')]);
  assert.equal(el('sys-hist-badge').textContent, '1× brownout / 3');
  assert.equal(el('sys-hist-badge').className, 'badge badge-danger');
  assert.ok(el('sys-hist-tbody').innerHTML.includes('Check power supply and USB cable.'));
  assert.ok(!el('sys-hist-tbody').innerHTML.includes('Multiple brownout'));
  context.renderResetHistory([row('BROWNOUT'), row('ROLLBACK', 'after BROWNOUT'), row('PANIC', '', 'task=x'), row('SW')]);
  assert.equal(el('sys-hist-badge').textContent, '1× crash, 2× brownout / 4');
  assert.ok(el('sys-hist-tbody').innerHTML.includes('Multiple brownout resets detected (2 of the last 4 boots). Check power supply and USB cable.'));
  context.renderResetHistory([row('FLASH', 'after BROWNOUT<script>')]);   /* only the exact marker counts */
  assert.equal(el('sys-hist-badge').textContent, '1');
  context.renderResetHistory([]);
  assert.equal(el('sys-hist-badge').textContent, '0');

  /* Boot-fault modal. */
  const modal = () => el('panicAlertModal').classList.set.has('open');
  async function check(hist) {
    el('panicAlertModal').classList.set.clear(); el('panic-crash').textContent = '';
    systemBody = { reset_history: hist }; context.checkPanicAndWarn(); await turn(); await turn();
  }
  await check([row('SW'), row('BROWNOUT')]);
  assert.equal(modal(), false, 'an older brownout alone opens no modal');
  await check([row('BROWNOUT'), row('SW')]);
  assert.equal(modal(), true);
  assert.equal(el('panic-crash').textContent,
    'The supply voltage dropped below the brownout threshold; no crash dump is expected. Check power supply and USB cable.');
  el('panic-ack').listeners.click();
  assert.equal(modal(), false);
  await check([row('BROWNOUT'), row('SW')]);
  assert.equal(modal(), false, 'acknowledged once per session');
  await check([Object.assign(row('BROWNOUT'), { wallclock: 1792000100 }), row('BROWNOUT'), row('BROWNOUT'), row('SW')]);
  assert.equal(modal(), true);
  assert.equal(el('panic-crash').textContent,
    'Multiple brownout resets detected (3 of the last 4 boots). Check power supply and USB cable.');
  await check([row('ROLLBACK', 'after BROWNOUT'), row('SW')]);
  assert.equal(modal(), true, 'a brownout behind ROLLBACK still warns');
  assert.ok(el('panic-crash').textContent.includes('Check power supply'));
  await check([row('FLASH', 'after TASK_WDT'), row('SW')]);
  assert.equal(modal(), true);
  assert.equal(el('panic-crash').textContent, '(no crash one-liner stored — check coredump partition)');
  await check([Object.assign(row('PANIC', '', 'task=main pc=0x1'), { wallclock: 1792000200 })]);
  assert.equal(el('panic-crash').textContent, 'task=main pc=0x1');
  await check([row('FLASH', 'web ota'), row('POWERON')]);
  assert.equal(modal(), false);
  console.log('PASS actual power diagnostics UI: TX default stays default, live value shown, PHY cap, ' +
              'brownout badge/advice, multiple-brownout text, ROLLBACK/FLASH cause, modal ack, crash rows unchanged');
})().catch(e => { console.error(e); process.exit(1); });
