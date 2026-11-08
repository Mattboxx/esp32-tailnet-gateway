"""Generate refc/x25519_mul_pie.S: the 256 x 256 -> 512-bit product of X25519
on the ESP32-S3 vector unit (PIE), and check the generated program offline.

    python tools/gen_x25519_mul_pie.py           # write the .S and self-check
    python tools/gen_x25519_mul_pie.py --check   # self-check only

The operands are seen as 16 halfwords each. Column k of the halfword product
is c_k = sum a[i] * b[k-i]. With P = 16 zero halfwords, b reversed, 16 zero
halfwords (48 halfwords, six 8-lane blocks of which only blocks 2 and 3 are
not zero), c_k = dot(a[0..16), P[s..s+16)) with s = 31 - k: two 8-lane
EE.VMULAS.U16.ACCX, a window of P being EE.SRC.Q of two blocks shifted by
SAR_BYTE = 2 * (s mod 8) bytes. All-zero windows are skipped (46 vector
multiply-accumulates instead of 62).

The 40-bit ACCX keeps the carry: after column k it holds c_k plus the carry
of the previous columns; its low halfword is halfword k of the product and
the rest is written back as the starting value of column k + 1. Every
column value is below 16 * (2^16 - 1)^2 + 2^21 < 2^37, inside ACCX.

Semantics relied upon (as used by Espressif's esp-dsp dspi_dotprod_*_aes3.S,
Apache-2.0): EE.LD.128.USAR.IP loads the aligned block holding the address and
sets SAR_BYTE to its low four bits; EE.SRC.Q qa, qs0, qs1 is the low 128 bits
of {qs1, qs0} >> 8 * SAR_BYTE; RUR.ACCX_0/1 are bits 0..31 and 32..39 of ACCX.
The firmware compares this routine with the C product before use and keeps
the scalar code on any difference, so a wrong assumption costs speed only.
"""
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/crypto/refc/x25519_mul_pie.S'

A_LO, A_HI, B2, B3, Z, W_LO, W_HI, T = 'q0', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7'
BLOCK = {0: Z, 1: Z, 2: B2, 3: B3, 4: Z, 5: Z}


def program():
    ops = []
    o = ops.append
    # a: three aligned blocks around a (no read past its 32 bytes), aligned by SAR_BYTE = a & 15
    o(('mov', 'a5', 'a3'))
    o(('addi', 'a6', 'a3', 31))
    o(('ld.usar', A_LO, 'a5', 16))
    o(('vld', A_HI, 'a5', 0))
    o(('vld', T, 'a6', 0))
    o(('src.q', A_LO, A_LO, A_HI))
    o(('src.q', A_HI, A_HI, T))
    # b reversed: block 2 = halfwords b[15..8], block 3 = b[7..0]; a word of P is a
    # word of b with its halves swapped (rotate by 16)
    o(('ssai', 16))
    for u in range(8):
        r = f'a{6 + u}'
        o(('l32i', r, 'a4', 4 * (7 - u)))
    for u in range(8):
        r = f'a{6 + u}'
        o(('src', r, r, r))
        o(('movi.32.q', B2 if u < 4 else B3, r, u % 4))
    o(('zero.q', Z))
    o(('zero.accx',))
    o(('movi', 'a15', 0))
    sar = None
    for k in range(31):
        s = 31 - k
        m, r = s >> 3, s & 7
        if r and sar != 2 * r:
            o(('movi', 'a5', 2 * r))
            o(('wur.sar_byte', 'a5'))
            sar = 2 * r
        for half, lo_blk, dst, a_reg in ((0, m, W_LO, A_LO), (1, m + 1, W_HI, A_HI)):
            q0, q1 = BLOCK[lo_blk], BLOCK.get(lo_blk + 1, Z)
            if r == 0:
                if q0 == Z:
                    continue
                o(('vmulas', a_reg, q0))
            else:
                if q0 == Z and q1 == Z:
                    continue
                o(('src.q', dst, q0, q1))
                o(('vmulas', a_reg, dst))
        o(('rur.accx_0', 'a6'))
        o(('rur.accx_1', 'a7'))
        o(('s16i', 'a6', 'a2', 2 * k))
        o(('src', 'a6', 'a7', 'a6'))          # SAR is still 16: (hi:lo) >> 16
        o(('wur.accx_0', 'a6'))
        o(('wur.accx_1', 'a15'))
    o(('s16i', 'a6', 'a2', 62))
    return ops


def render(ops):
    text = []
    for op in ops:
        n, *args = op
        if n == 'mov':
            text.append(f'    mov     {args[0]}, {args[1]}')
        elif n == 'addi':
            text.append(f'    addi    {args[0]}, {args[1]}, {args[2]}')
        elif n == 'ld.usar':
            text.append(f'    ee.ld.128.usar.ip {args[0]}, {args[1]}, {args[2]}')
        elif n == 'vld':
            text.append(f'    ee.vld.128.ip {args[0]}, {args[1]}, {args[2]}')
        elif n == 'src.q':
            text.append(f'    ee.src.q {args[0]}, {args[1]}, {args[2]}')
        elif n == 'ssai':
            text.append(f'    ssai    {args[0]}')
        elif n == 'l32i':
            text.append(f'    l32i    {args[0]}, {args[1]}, {args[2]}')
        elif n == 'src':
            text.append(f'    src     {args[0]}, {args[1]}, {args[2]}')
        elif n == 'movi.32.q':
            text.append(f'    ee.movi.32.q {args[0]}, {args[1]}, {args[2]}')
        elif n == 'zero.q':
            text.append(f'    ee.zero.q {args[0]}')
        elif n == 'zero.accx':
            text.append('    ee.zero.accx')
        elif n == 'movi':
            text.append(f'    movi    {args[0]}, {args[1]}')
        elif n in ('wur.sar_byte', 'rur.accx_0', 'rur.accx_1', 'wur.accx_0', 'wur.accx_1'):
            text.append(f'    {n} {args[0]}')
        elif n == 'vmulas':
            text.append(f'    ee.vmulas.u16.accx {args[0]}, {args[1]}')
        elif n == 's16i':
            text.append(f'    s16i    {args[0]}, {args[1]}, {args[2]}')
        else:
            raise ValueError(n)
    return text


def simulate(ops, a_words, b_words, a_offset):
    """Run the program on a model of the instructions (see the module doc)."""
    mem = {}
    base_a, base_b, base_out = 0x1000 + a_offset, 0x2000, 0x3000
    for i, w in enumerate(a_words):
        mem[base_a + 4 * i] = w
    for i, w in enumerate(b_words):
        mem[base_b + 4 * i] = w
    # neighbouring words exist but hold noise: the program must not use them
    for addr in range(0x1000 - 16, 0x1000 + 64, 4):
        mem.setdefault(addr, random.getrandbits(32))
    reg = {'a2': base_out, 'a3': base_a, 'a4': base_b}
    q = {f'q{i}': 0 for i in range(8)}
    st = {'sar': 0, 'sar_byte': 0, 'accx': 0}
    out = {}

    def block(addr):
        addr &= ~15
        return sum(mem[addr + 4 * i] << (32 * i) for i in range(4))

    for n, *x in ops:
        if n == 'mov':
            reg[x[0]] = reg[x[1]]
        elif n == 'addi':
            reg[x[0]] = (reg[x[1]] + x[2]) & 0xffffffff
        elif n == 'ld.usar':
            q[x[0]] = block(reg[x[1]])
            st['sar_byte'] = reg[x[1]] & 15
            reg[x[1]] += x[2]
        elif n == 'vld':
            q[x[0]] = block(reg[x[1]])
            reg[x[1]] += x[2]
        elif n == 'src.q':
            q[x[0]] = ((q[x[2]] << 128 | q[x[1]]) >> (8 * st['sar_byte'])) & ((1 << 128) - 1)
        elif n == 'ssai':
            st['sar'] = x[0]
        elif n == 'l32i':
            reg[x[0]] = mem[reg[x[1]] + x[2]]
        elif n == 'src':
            reg[x[0]] = ((reg[x[1]] << 32 | reg[x[2]]) >> st['sar']) & 0xffffffff
        elif n == 'movi.32.q':
            q[x[0]] = q[x[0]] & ~(0xffffffff << (32 * x[2])) | reg[x[1]] << (32 * x[2])
        elif n == 'zero.q':
            q[x[0]] = 0
        elif n == 'zero.accx':
            st['accx'] = 0
        elif n == 'movi':
            reg[x[0]] = x[1]
        elif n == 'wur.sar_byte':
            st['sar_byte'] = reg[x[0]] & 15
        elif n == 'vmulas':
            qa, qb = q[x[0]], q[x[1]]
            st['accx'] += sum(((qa >> (16 * i)) & 0xffff) * ((qb >> (16 * i)) & 0xffff) for i in range(8))
            assert st['accx'] < 1 << 39, 'ACCX overflow'
        elif n == 'rur.accx_0':
            reg[x[0]] = st['accx'] & 0xffffffff
        elif n == 'rur.accx_1':
            reg[x[0]] = st['accx'] >> 32 & 0xff
        elif n == 'wur.accx_0':
            st['accx'] = st['accx'] & ~0xffffffff | reg[x[0]]
        elif n == 'wur.accx_1':
            st['accx'] = st['accx'] & 0xffffffff | (reg[x[0]] & 0xff) << 32
        elif n == 's16i':
            out[reg[x[1]] + x[2] - base_out] = reg[x[0]] & 0xffff
        else:
            raise ValueError(n)
    assert sorted(out) == list(range(0, 64, 2)), 'every output halfword written once'
    return sum(out[2 * h] << (16 * h) for h in range(32))


def check(ops):
    rnd = random.Random(25519)
    m = (1 << 32) - 1
    cases = [([m] * 8, [m] * 8), ([0] * 8, [m] * 8), ([1] + [0] * 7, [m] * 8),
             ([0x0000ffff] * 8, [0xffff0000] * 8), ([0xffff0000] * 8, [0x0000ffff] * 8)]
    cases += [([rnd.getrandbits(32) for _ in range(8)], [rnd.getrandbits(32) for _ in range(8)]) for _ in range(300)]
    for n, (a, b) in enumerate(cases):
        want = sum(w << (32 * i) for i, w in enumerate(a)) * sum(w << (32 * i) for i, w in enumerate(b))
        got = simulate(ops, a, b, 4 * (n % 4))
        assert got == want, (n, hex(got), hex(want))
    return len(cases)


HEAD = '''/* Generated by tools/gen_x25519_mul_pie.py -- do not edit by hand.
 *
 * void x25519_mul_pie(uint32_t out[16], const uint32_t a[8], const uint32_t b[8])
 *
 * The 512-bit product of two 256-bit numbers on the ESP32-S3 vector unit:
 * 16-bit columns as dot products (EE.VMULAS.U16.ACCX) with the carry kept in
 * ACCX. Constant time: no branch, no data-dependent address. a and b need
 * only 4-byte alignment and may be the same array; nothing outside them is
 * read. x25519.c compares it with the C product before use. Uses q0-q7,
 * ACCX, SAR_BYTE and SAR. */
    .section .text.x25519_mul_pie, "ax"
    .align  4
    .global x25519_mul_pie
    .type   x25519_mul_pie, @function
x25519_mul_pie:
    entry   a1, 32
'''


def generate(ops=None):
    body = '\n'.join(render(ops or program()))
    return HEAD + body + '\n    retw.n\n    .size   x25519_mul_pie, . - x25519_mul_pie\n'


def main():
    ops = program()
    n = check(ops)
    vm = sum(1 for op in ops if op[0] == 'vmulas')
    print(f'x25519 PIE product: {len(ops)} instructions ({vm} vector MACs), {n} products match the model')
    if '--check' in sys.argv:
        return
    OUT.write_text(generate(ops), encoding='utf-8', newline='\n')
    print(f'wrote {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
