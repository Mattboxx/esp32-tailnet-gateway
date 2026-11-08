"""Control-plane X25519 (MicroLink ml_x25519) through the WireGuard X25519.

On the device ml_x25519() (Noise, node key, DISCO shared keys, DERP boxes,
first-boot sealing) now calls x25519_control() in wireguard_lwip
refc/x25519.c, the implementation whose field product is chosen on the device.
Both are STROBE X25519; this compiles, on the host:
- A: MicroLink's own implementation (ml_x25519.c without ESP_PLATFORM);
- B: ml_x25519.c with ESP_PLATFORM, i.e. the delegation actually built into
  the firmware, linked with refc/x25519.c;
and runs the same inputs through both, with clamp 1 and 0:
- outputs and return values are identical for the RFC 7748 vector, edge
  points (0, 1, p-1, p, p+1, 2^255-1, 2^256-1, 9, 2^254, high bit set) and
  2,000 random scalar/point pairs; clamped results equal pyca/cryptography;
- a broken delegation (clamp argument dropped) is detected.
"""
import os
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
REFC = ML / 'components/wireguard_lwip/src/crypto/refc'
src_ml = (ML / 'src/ml_x25519.c').read_text(encoding='utf-8').replace('\r\n', '\n')
assert 'return x25519_control(out, scalar, x1, clamp);' in src_ml

DRIVER = r'''
#include <stdint.h>
#include <stdio.h>
int ml_x25519(uint8_t out[32], const uint8_t s[32], const uint8_t u[32], int clamp);
static int hex(const char *h, uint8_t *o) { for (int i = 0; i < 32; i++) { unsigned v; if (sscanf(h + 2 * i, "%2x", &v) != 1) return 0; o[i] = (uint8_t)v; } return 1; }
int main(void) {
    char a[80], b[80]; int clamp; uint8_t s[32], u[32], r[32];
    while (scanf("%79s %79s %d", a, b, &clamp) == 3) {
        if (!hex(a, s) || !hex(b, u)) return 2;
        int ret = ml_x25519(r, s, u, clamp);
        for (int i = 0; i < 32; i++) printf("%02x", r[i]);
        printf(" %d\n", ret);
    }
    return 0;
}
'''


def build(tmp, name, ml_source, esp):
    t = Path(tmp)
    (t / f'{name}_ml.c').write_text(ml_source, encoding='utf-8')
    (t / 'drv.c').write_text(DRIVER, encoding='utf-8')
    exe = t / (name + ('.exe' if os.name == 'nt' else ''))
    flags = ['-std=gnu11', '-O2', '-w', '-DBYTE_ORDER=1234', '-DLITTLE_ENDIAN=1234']
    if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined']
    objs = []
    # ml_x25519.c alone decides ESP_PLATFORM; refc/x25519.c is built as for the host
    ml_obj = t / f'{name}_ml.o'
    subprocess.run(['gcc', *flags, *(['-DESP_PLATFORM'] if esp else []), '-I', str(ML / 'src'), '-c',
                    str(t / f'{name}_ml.c'), '-o', str(ml_obj)], check=True)
    objs.append(str(ml_obj))
    if esp:
        wg_obj = t / f'{name}_wg.o'
        subprocess.run(['gcc', *flags, '-I', str(REFC), '-c', str(REFC / 'x25519.c'), '-o', str(wg_obj)], check=True)
        objs.append(str(wg_obj))
    subprocess.run(['gcc', *flags, str(t / 'drv.c'), *objs, '-o', str(exe)], check=True)
    return exe


def run(exe, cases):
    text = ''.join(f'{s.hex()} {u.hex()} {c}\n' for s, u, c in cases)
    out = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True, timeout=600).stdout.split('\n')
    return [(bytes.fromhex(line.split()[0]), int(line.split()[1])) for line in out if line.strip()]


rng = random.Random(0xC0)
P = 2**255 - 19
edges = [0, 1, P - 1, P, P + 1, 2**255 - 1, 2**256 - 1, 9, 2**254, 2**255]
points = [(e % 2**256).to_bytes(32, 'little') for e in edges]
vec = (bytes.fromhex('a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4'),
       bytes.fromhex('e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c'))
cases = [(vec[0], vec[1], 1)]
for p in points:
    for c in (1, 0):
        cases.append((rng.randbytes(32), p, c))
for i in range(2000):
    cases.append((rng.randbytes(32), rng.randbytes(32), i & 1))

with tempfile.TemporaryDirectory() as tmp:
    a = run(build(tmp, 'own', src_ml, False), cases)
    b = run(build(tmp, 'shared', src_ml, True), cases)
    assert len(a) == len(b) == len(cases)
    assert a[0][0].hex() == 'c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552', a[0][0].hex()
    high = 0
    for n, (x, y) in enumerate(zip(a, b)):
        s, u, clamp = cases[n]
        if clamp and u[31] & 0x80:
            # RFC 7748 section 5 masks the point's top bit; MicroLink's own
            # copy did not (checked against pyca below), the shared one does.
            high += 1
            continue
        assert x == y, (n, clamp, x, y)
    assert high >= 500
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    except ImportError:  # pragma: no cover
        X25519PrivateKey = None
    checked = legacy_off = 0
    if X25519PrivateKey:
        for (s, u, c), (own, _), (got, _) in zip(cases, a, b):
            if not c:
                continue
            try:
                want = X25519PrivateKey.from_private_bytes(s).exchange(X25519PublicKey.from_public_bytes(u))
            except ValueError:          # pyca refuses an all-zero shared secret
                assert got == bytes(32)
                continue
            assert got == want
            checked += 1
            legacy_off += own != want
        assert checked >= 900 and legacy_off >= 400, (checked, legacy_off)
    broken = src_ml.replace('return x25519_control(out, scalar, x1, clamp);', 'return x25519_control(out, scalar, x1, 1);')
    c = run(build(tmp, 'broken', broken, True), cases)
    assert any(x != y for x, y in zip(a, c)), 'broken delegation not detected'
print(f'x25519 control plane: the firmware delegation equals MicroLink\'s own X25519 on {len(cases) - high} cases '
      f'(clamp 1 and 0, outputs and return values); on the {high} clamped points with the top bit set it follows '
      f'RFC 7748 where the old copy did not; {checked} clamped results equal pyca; broken delegation detected')
