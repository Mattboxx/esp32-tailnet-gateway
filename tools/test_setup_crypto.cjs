/* First-boot setup crypto in the real Web UI code (main/index.html, FBX)
 * against Node's independent X25519/AES-GCM: random keys, an RFC 7748
 * vector, low-order rejection, the exact key derivation and sealed-request
 * layout the firmware opens (AAD = session id || big-endian sequence).
 * Host-only; no device. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'main/index.html'), 'utf8');
const start = html.indexOf('    var FBX = (function () {');
const end = html.indexOf('    var FirstBoot = (function () {');
assert.ok(start > 0 && end > start, 'FBX block not found');
const ctx = { window: { crypto: { getRandomValues: (a) => crypto.randomFillSync(a) } }, TextEncoder, Uint8Array, Float64Array, Math, JSON, Error };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'main/vendor/sjcl.min.js'), 'utf8'), ctx);
vm.runInContext(html.slice(start, end) + '\nthis.FBX = FBX;', ctx);
const FBX = ctx.FBX;

const PKCS8 = Buffer.from('302e020100300506032b656e04220420', 'hex');
const SPKI = Buffer.from('302a300506032b656e032100', 'hex');
const priv = (raw) => crypto.createPrivateKey({ key: Buffer.concat([PKCS8, Buffer.from(raw)]), format: 'der', type: 'pkcs8' });
const pub = (raw) => crypto.createPublicKey({ key: Buffer.concat([SPKI, Buffer.from(raw)]), format: 'der', type: 'spki' });
const rawPub = (k) => crypto.createPublicKey(k).export({ format: 'der', type: 'spki' }).subarray(12);

// RFC 7748 section 5.2, first test vector.
const v = FBX.scalarmult(FBX.unhex('a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4'),
  FBX.unhex('e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c'));
assert.equal(FBX.hex(v), 'c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552');

// 200 random keys: public keys and shared secrets equal Node's.
for (let i = 0; i < 200; i++) {
  const a = crypto.randomBytes(32), b = crypto.randomBytes(32);
  const kp = FBX.scalarmult(a, (() => { const g = new Uint8Array(32); g[0] = 9; return g; })());
  assert.equal(FBX.hex(kp), rawPub(priv(a)).toString('hex'));
  const bp = rawPub(priv(b));
  const mine = FBX.scalarmult(a, bp);
  const theirs = crypto.diffieHellman({ privateKey: priv(a), publicKey: pub(bp) });
  assert.equal(FBX.hex(mine), theirs.toString('hex'));
}

// A low-order (all-zero result) gateway key is refused.
assert.throws(() => FBX.deriveKey(crypto.randomBytes(32), new Uint8Array(32), new Uint8Array(32)), /invalid gateway key/);

// Key derivation and seal match what the firmware recomputes and opens.
const label = Buffer.from('mattboxx-tailnet-gateway-setup-v1');
const kpc = FBX.keypair();
const devPriv = crypto.randomBytes(32), devPub = rawPub(priv(devPriv));
const key = FBX.deriveKey(kpc.priv, kpc.pub, devPub);
const shared = crypto.diffieHellman({ privateKey: priv(devPriv), publicKey: pub(Buffer.from(kpc.pub)) });
const expect = crypto.createHash('sha256').update(Buffer.concat([label, shared, devPub, Buffer.from(kpc.pub)])).digest();
assert.equal(FBX.hex(key), expect.toString('hex'));
const sid = crypto.randomBytes(16).toString('hex');
const message = { action: 'finish', admin_password: 'correct horse ✓', wifi: { ssid: 'Home', password: 'p'.repeat(63) } };
for (const seq of [1, 2, 0x01020304, 0xffffffff]) {
  const s = FBX.seal(key, sid, seq, message);
  assert.equal(s.sid, sid); assert.equal(s.seq, seq);
  assert.equal(s.iv.length, 24); assert.equal(s.tag.length, 32);
  const aad = Buffer.concat([Buffer.from(sid, 'hex'), Buffer.from([seq >>> 24 & 255, seq >>> 16 & 255, seq >>> 8 & 255, seq & 255])]);
  const d = crypto.createDecipheriv('aes-256-gcm', Buffer.from(expect), Buffer.from(s.iv, 'hex'));
  d.setAAD(aad); d.setAuthTag(Buffer.from(s.tag, 'hex'));
  const pt = Buffer.concat([d.update(Buffer.from(s.ct, 'hex')), d.final()]).toString('utf8');
  assert.deepEqual(JSON.parse(pt), message);
  // Any other sequence or a flipped bit fails authentication.
  const bad = crypto.createDecipheriv('aes-256-gcm', Buffer.from(expect), Buffer.from(s.iv, 'hex'));
  bad.setAAD(Buffer.concat([aad.subarray(0, 16), Buffer.from([0, 0, 0, 9])])); bad.setAuthTag(Buffer.from(s.tag, 'hex'));
  bad.update(Buffer.from(s.ct, 'hex'));
  assert.throws(() => bad.final());
}
const ivs = new Set();
for (let i = 0; i < 500; i++) ivs.add(FBX.seal(key, sid, i + 1, {}).iv);
assert.equal(ivs.size, 500, 'IVs must be fresh');
console.log('PASS: Web UI X25519 (RFC 7748 + 200 Node cross-checks, low-order refusal), key derivation and AES-256-GCM seal interoperate with Node');
