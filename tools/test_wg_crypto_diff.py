"""Differential test: the current WireGuard ChaCha20/Poly1305 C against the
previous implementation (MicroLink 6d63b5f, formerly 403e596, built side by side with renamed
symbols) on deterministic random inputs.

Covers lengths 0-1600, every input/output misalignment 0-3, in-place and
separate buffers, the 32-bit block-counter wrap, Poly1305 updates split into
random chunks (so blocks arrive at every alignment and through the leftover
buffer), AEAD encrypt/decrypt including tampered tag, ciphertext and AAD, and
HChaCha20/XChaCha20. WG_CRYPTO_DIFF_SANITIZE=1 enables ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink'
REL = 'components/microlink/components/wireguard_lwip/src'
# Last MicroLink revision with the original reference ChaCha20/Poly1305 code.
OLD_REV = os.environ.get('WG_CRYPTO_DIFF_BASE', '6d63b5f11b00e9299969d87d71125ad9bc329dbc')  # was 403e596 before the 2026-11-08 history rewrite (same tree)
FILES = ['crypto.h', 'ml_perf.h', 'crypto/refc/chacha20.c', 'crypto/refc/chacha20.h',
         'crypto/refc/chacha20poly1305.c', 'crypto/refc/chacha20poly1305.h', 'crypto/refc/poly1305-donna.c',
         'crypto/refc/poly1305-donna.h', 'crypto/refc/poly1305-donna-32.h', 'crypto/refc/wg_hotloop.h',
         'crypto/refc/blake2s.h', 'crypto/refc/x25519.h']
RENAME = ['chacha20', 'chacha20_init', 'hchacha20', 'poly1305_init', 'poly1305_update', 'poly1305_finish',
          'chacha20poly1305_encrypt', 'chacha20poly1305_decrypt', 'xchacha20poly1305_encrypt',
          'xchacha20poly1305_decrypt']
TEST = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "crypto/refc/chacha20.h"
#include "crypto/refc/chacha20poly1305.h"
#include "crypto/refc/poly1305-donna.h"
#define OLD(f) old_##f
void old_chacha20_init(struct chacha20_ctx *, const uint8_t *, const uint64_t);
void old_chacha20(struct chacha20_ctx *, uint8_t *, const uint8_t *, uint32_t);
void old_hchacha20(uint8_t *, const uint8_t *, const uint8_t *);
void old_poly1305_init(poly1305_context *, const unsigned char[32]);
void old_poly1305_update(poly1305_context *, const unsigned char *, size_t);
void old_poly1305_finish(poly1305_context *, unsigned char[16]);
void old_chacha20poly1305_encrypt(uint8_t *, const uint8_t *, size_t, const uint8_t *, size_t, uint64_t, const uint8_t *);
bool old_chacha20poly1305_decrypt(uint8_t *, const uint8_t *, size_t, const uint8_t *, size_t, uint64_t, const uint8_t *);
void old_xchacha20poly1305_encrypt(uint8_t *, const uint8_t *, size_t, const uint8_t *, size_t, const uint8_t *, const uint8_t *);

static uint64_t rng = 0x243f6a8885a308d3ull;
static uint32_t next(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)(rng >> 16); }
static void fill(uint8_t *p, size_t n) { for (size_t i = 0; i < n; i++) p[i] = (uint8_t)next(); }

int main(void) {
    static uint8_t in[1700 + 8], a[1700 + 32], b[1700 + 32], key[32], aad[64], mac_a[16], mac_b[16];
    unsigned long cases = 0;
    for (int it = 0; it < 6000; it++) {
        size_t len = it < 1601 ? (size_t)it : next() % 1601;
        size_t ia = next() & 3, oa = next() & 3;
        int inplace = next() & 1;
        uint64_t nonce = ((uint64_t)next() << 32) | next();
        fill(key, 32); fill(in + ia, len);
        struct chacha20_ctx c1, c2;
        chacha20_init(&c1, key, nonce); old_chacha20_init(&c2, key, nonce);
        if (it % 50 == 0) { c1.state[12] = c2.state[12] = 0xFFFFFFFFu - (next() & 3); }   /* counter wrap */
        uint8_t *pa = a + oa, *pb = b + oa;
        memset(a, 0x5a, sizeof a); memset(b, 0x5a, sizeof b);
        if (inplace) { memcpy(pa, in + ia, len); memcpy(pb, in + ia, len); chacha20(&c1, pa, pa, (uint32_t)len); old_chacha20(&c2, pb, pb, (uint32_t)len); }
        else { chacha20(&c1, pa, in + ia, (uint32_t)len); old_chacha20(&c2, pb, in + ia, (uint32_t)len); }
        assert(!memcmp(a, b, sizeof a));                       /* output and untouched guard bytes */
        assert(!memcmp(&c1, &c2, sizeof c1));                  /* block counter advanced alike */
        /* Poly1305 with random chunking: blocks at every alignment and via the leftover buffer */
        poly1305_context p1, p2;
        poly1305_init(&p1, key); old_poly1305_init(&p2, key);
        for (size_t off = 0; off < len;) {
            size_t step = 1 + next() % 70; if (step > len - off) step = len - off;
            poly1305_update(&p1, in + ia + off, step); old_poly1305_update(&p2, in + ia + off, step); off += step;
        }
        poly1305_finish(&p1, mac_a); old_poly1305_finish(&p2, mac_b);
        assert(!memcmp(mac_a, mac_b, 16));
        /* AEAD */
        size_t adlen = next() % 64; fill(aad, adlen);
        memset(a, 0, sizeof a); memset(b, 0, sizeof b);
        chacha20poly1305_encrypt(a + oa, in + ia, len, aad, adlen, nonce, key);
        old_chacha20poly1305_encrypt(b + oa, in + ia, len, aad, adlen, nonce, key);
        assert(!memcmp(a, b, sizeof a));
        uint8_t *plain = b + 4 - oa + 8;   /* different alignment for the decrypt output */
        assert(chacha20poly1305_decrypt(plain, a + oa, len + 16, aad, adlen, nonce, key) && !memcmp(plain, in + ia, len));
        assert(old_chacha20poly1305_decrypt(plain, a + oa, len + 16, aad, adlen, nonce, key));
        size_t flip = next() % (len + 16);
        a[oa + flip] ^= (uint8_t)(1u << (next() & 7));
        assert(!chacha20poly1305_decrypt(plain, a + oa, len + 16, aad, adlen, nonce, key));
        assert(!old_chacha20poly1305_decrypt(plain, a + oa, len + 16, aad, adlen, nonce, key));
        a[oa + flip] ^= 0;  /* keep the flip; also check AAD tampering on a fresh encryption */
        if (adlen) {
            chacha20poly1305_encrypt(a + oa, in + ia, len, aad, adlen, nonce, key);
            aad[next() % adlen] ^= 1;
            assert(!chacha20poly1305_decrypt(plain, a + oa, len + 16, aad, adlen, nonce, key));
        }
        if (it % 10 == 0) {
            uint8_t xn[24], h1[32], h2[32]; fill(xn, 24);
            hchacha20(h1, xn, key); old_hchacha20(h2, xn, key); assert(!memcmp(h1, h2, 32));
            memset(a, 0, sizeof a); memset(b, 0, sizeof b);
            xchacha20poly1305_encrypt(a, in + ia, len, aad, adlen, xn, key);
            old_xchacha20poly1305_encrypt(b, in + ia, len, aad, adlen, xn, key);
            assert(!memcmp(a, b, sizeof a));
        }
        cases++;
    }
    printf("%lu cases\n", cases);
    return 0;
}
'''


def noise_test_source():
    source = (ML / 'components/microlink/src/ml_noise.c').read_text(encoding='utf-8')
    start = source.index('static int noise_aead_encrypt(')
    end = source.index('/* ===', start)
    key = bytes(range(32))
    nonce = 0x0123456789ABCDEF
    aad = b'Noise test context'
    plaintext = b'control frame'
    cipher = ChaCha20Poly1305(key)
    vectors = [cipher.encrypt(bytes(4) + nonce.to_bytes(8, 'big'), data, aad)
               for data in (plaintext, b'')]
    arrays = '\n'.join(f'static const uint8_t expected_{i}[] = {{'
                        + ','.join(map(str, vector)) + '};'
                        for i, vector in enumerate(vectors))
    return '#include <limits.h>\n' + source[start:end] + arrays + r'''
static void test_noise(void)
{
    uint8_t key[32], sealed[32], opened[sizeof "control frame"];
    static const uint8_t aad[] = "Noise test context";
    static const uint8_t plaintext[] = "control frame";
    const uint64_t nonce = 0x0123456789ABCDEFULL;
    for (unsigned i = 0; i < sizeof key; ++i) key[i] = (uint8_t)i;
    assert(noise_aead_encrypt(key, nonce, aad, sizeof aad - 1,
                              plaintext, sizeof plaintext - 1, sealed) == 0);
    assert(!memcmp(sealed, expected_0, sizeof expected_0));
    assert(noise_aead_decrypt(key, nonce, aad, sizeof aad - 1,
                              sealed, sizeof expected_0, opened) == 0);
    assert(!memcmp(opened, plaintext, sizeof plaintext - 1));
    sealed[sizeof expected_0 - 1] ^= 1;
    assert(noise_aead_decrypt(key, nonce, aad, sizeof aad - 1,
                              sealed, sizeof expected_0, opened) != 0);
    assert(noise_aead_encrypt(key, nonce, aad, sizeof aad - 1, NULL, 0, sealed) == 0);
    assert(!memcmp(sealed, expected_1, sizeof expected_1));
    assert(noise_aead_decrypt(key, nonce, aad, sizeof aad - 1,
                              sealed, sizeof expected_1, NULL) == 0);
}
'''


def main():
    cc = os.environ.get('CC', 'gcc')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2']
    if os.environ.get('WG_CRYPTO_DIFF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    with tempfile.TemporaryDirectory(prefix='wg-crypto-diff-') as folder:
        tmp = Path(folder)
        old = tmp / 'old' / 'src'
        for name in FILES:
            target = old / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.run(['git', '-C', str(ML), 'show', f'{OLD_REV}:{REL}/{name}'],
                                              capture_output=True, check=True).stdout)
        objects = []
        renames = [f'-D{n}=old_{n}' for n in RENAME]
        for src in ('chacha20.c', 'chacha20poly1305.c', 'poly1305-donna.c'):
            obj = tmp / f'old_{src}.o'
            # The previous upstream code has its own warnings; only the new code is -Werror.
            old_flags = [f for f in flags if f != '-Werror'] + ['-w']
            subprocess.run([cc, *old_flags, *renames, '-I', str(old), '-I', str(old / 'crypto/refc'), '-c',
                            str(old / 'crypto/refc' / src), '-o', str(obj)], check=True)
            objects.append(obj)
            obj = tmp / f'new_{src}.o'
            subprocess.run([cc, *flags, '-I', str(ML / REL), '-I', str(ML / REL / 'crypto/refc'), '-c',
                            str(ML / REL / 'crypto/refc' / src), '-o', str(obj)], check=True)
            objects.append(obj)
        shared = tmp / 'crypto.o'   # crypto_zero/crypto_equal, unchanged and shared by both
        subprocess.run([cc, *flags, '-I', str(ML / REL), '-I', str(ML / REL / 'crypto/refc'), '-c',
                        str(ML / REL / 'crypto.c'), '-o', str(shared)], check=True)
        objects.append(shared)
        start = TEST.index('int main(void) {')
        body = TEST[:start] + noise_test_source() + TEST[start:]
        body = body.replace('int main(void) {', 'int main(void) {\n    test_noise();')
        (tmp / 'test.c').write_text(body, encoding='utf-8')
        exe = tmp / ('diff.exe' if os.name == 'nt' else 'diff')
        subprocess.run([cc, *flags, '-I', str(ML / REL), str(tmp / 'test.c'), *map(str, objects), '-o', str(exe)], check=True)
        out = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=300).stdout.strip()
    print(f'PASS: current ChaCha20/Poly1305/AEAD/HChaCha20/XChaCha20 identical to MicroLink {OLD_REV} on {out} '
          '(lengths 0-1600, alignment, in-place, counter wrap, tampering, Noise nonce and empty-frame vectors)')


if __name__ == '__main__':
    main()
