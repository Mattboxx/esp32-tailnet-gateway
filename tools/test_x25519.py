"""X25519 used by WireGuard (MicroLink refc/x25519.c) on the host.

The dedicated squaring (3.0.9) must not change a single output:
- RFC 7748 section 5.2 vector and the iterated test (1 and 1,000 rounds);
- 3,000 random scalar/point pairs against pyca/cryptography's X25519;
- the same pairs against the previous implementation (git HEAD~ of the file,
  squaring through the generic multiplication), plus edge points (0, 1, p-1,
  p, 2^255-1, high bit set);
- a broken squaring (one doubling bit lost) is detected.
"""
import os
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REL = 'components/microlink/components/wireguard_lwip/src/crypto/refc'
SRC = ROOT / 'external/microlink' / REL / 'x25519.c'
new = SRC.read_text(encoding='utf-8').replace('\r\n', '\n')
_sqr = new[new.index('static void sqr(fe out, const fe a) {'):]
_sqr = _sqr[:_sqr.index('\n}\n')]
assert 'limb_t accum[2*NLIMBS] = {0};' in _sqr and 'accum[i] = (v << 1) | top;' in _sqr, 'dedicated C squaring'
old = subprocess.run(['git', '-C', str(ROOT / 'external/microlink'), 'log', '--format=%H', '-n', '20', '--', REL + '/x25519.c'],
                     capture_output=True, text=True, check=True).stdout.split()
ref_old = None
for sha in old:
    text = subprocess.run(['git', '-C', str(ROOT / 'external/microlink'), 'show', f'{sha}:{REL}/x25519.c'],
                          capture_output=True, text=True, check=True).stdout.replace('\r\n', '\n')
    if 'static void sqr(fe out, const fe a) { mul(out,a,a,NLIMBS); }' in text:
        ref_old = text
        break
assert ref_old, 'previous implementation not found in history'
header = (ROOT / 'external/microlink' / REL / 'x25519.h').read_text(encoding='utf-8')

DRIVER = r'''
#include <stdint.h>
#include <stdio.h>
#include "x25519.h"
int x25519_old(uint8_t out[32], const uint8_t s[32], const uint8_t u[32], int clamp);
static int hex(const char *h, uint8_t *o) { for (int i = 0; i < 32; i++) { unsigned v; if (sscanf(h + 2 * i, "%2x", &v) != 1) return 0; o[i] = (uint8_t)v; } return 1; }
int main(void) {
    char a[80], b[80]; uint8_t s[32], u[32], r1[32], r2[32];
    while (scanf("%79s %79s", a, b) == 2) {
        if (!hex(a, s) || !hex(b, u)) return 2;
        x25519(r1, s, u, 1); x25519_old(r2, s, u, 1);
        for (int i = 0; i < 32; i++) printf("%02x", r1[i]); printf(" ");
        for (int i = 0; i < 32; i++) printf("%02x", r2[i]); printf("\n");
    }
    return 0;
}
'''


def build(tmp, new_src):
    t = Path(tmp)
    (t / 'x25519.h').write_text(header, encoding='utf-8')
    (t / 'new.c').write_text(new_src, encoding='utf-8')
    (t / 'old.c').write_text('#define x25519 x25519_old\n#define X25519_BASE_POINT X25519_BASE_POINT_old\n' + ref_old, encoding='utf-8')
    (t / 'drv.c').write_text(DRIVER, encoding='utf-8')
    exe = t / ('x.exe' if os.name == 'nt' else 'x')
    flags = ['-std=gnu11', '-O2', '-w', '-I', str(t), '-DBYTE_ORDER=1234', '-DLITTLE_ENDIAN=1234']
    if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined']
    subprocess.run(['gcc', *flags, str(t / 'new.c'), str(t / 'old.c'), str(t / 'drv.c'), '-o', str(exe)], check=True)
    return exe


def run(exe, pairs):
    text = ''.join(f'{s.hex()} {u.hex()}\n' for s, u in pairs)
    out = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True, timeout=600).stdout.split('\n')
    return [tuple(bytes.fromhex(x) for x in line.split()) for line in out if line.strip()]


try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
except ImportError:  # pragma: no cover
    X25519PrivateKey = None

rng = random.Random(25519)
P = 2**255 - 19
edges = [0, 1, P - 1, P, P + 1, 2**255 - 1, 2**256 - 1, 9, 2**254]
pairs = [(rng.randbytes(32), (e % 2**256).to_bytes(32, 'little')) for e in edges]
pairs += [(rng.randbytes(32), rng.randbytes(32)) for _ in range(3000)]
vec = (bytes.fromhex('a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4'),
       bytes.fromhex('e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c'))
pairs.insert(0, vec)

with tempfile.TemporaryDirectory() as tmp:
    exe = build(tmp, new)
    res = run(exe, pairs)
    assert len(res) == len(pairs)
    assert res[0][0].hex() == 'c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552', res[0][0].hex()
    for (s, u), (got, before) in zip(pairs, res):
        assert got == before, (s.hex(), u.hex(), got.hex(), before.hex())
    if X25519PrivateKey:
        checked = 0
        for (s, u), (got, _) in zip(pairs, res):
            try:
                want = X25519PrivateKey.from_private_bytes(s).exchange(X25519PublicKey.from_public_bytes(u))
            except ValueError:          # low-order point: pyca refuses the all-zero result
                assert got == bytes(32)
                continue
            assert got == want, (s.hex(), u.hex())
            checked += 1
        assert checked >= 3000
    # RFC 7748 iterated test: k = u = 9, k <- X25519(k, u), u <- old k.
    k = u = (9).to_bytes(32, 'little')
    for i in range(1000):
        nk = run(exe, [(k, u)])[0][0]
        u, k = k, nk
        if i == 0:
            assert k.hex() == '422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079', k.hex()
    assert k.hex() == '684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51', k.hex()

    broken = new.replace('accum[i] = (v << 1) | top;', 'accum[i] = (v << 1);')
    assert broken != new
    exe2 = build(tmp + '/m' if False else tmp, broken)
    bad = run(exe2, pairs[:50])
    assert any(g != b for g, b in bad), 'broken squaring not detected'
    # the dedicated a24 multiplication (3.0.12): a wrong fold is detected
    broken = new.replace('out[0] = umaal(&c2, t[0], 38, carry);', 'out[0] = umaal(&c2, t[0], 37, carry);')
    assert broken != new
    bad = run(build(tmp, broken), pairs[:50])
    assert any(g != b for g, b in bad), 'broken a24 multiplication not detected'
print('x25519: RFC 7748 vector and 1,000-round iteration, 3,000+ random pairs equal pyca and the previous code; broken squaring and a24 multiplication detected')
