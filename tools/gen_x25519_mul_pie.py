"""Generate refc/x25519_mul_pie.S: the 256 x 256 -> 512-bit product of X25519
on the ESP32-S3 vector unit (PIE), alone and fused with the field reduction,
and check the generated programs offline.

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

The fused routine (x25519_mulred_pie) stores the product in its own frame
and reduces it exactly as x25519.c mul() does, with the eight result words in
registers: out[j] = lo[j] + 38 * hi[j] + carry, then propagate() (the top bit
and the last carry folded back as 19 * (2 * carry + top bit)). It replaces
the separate C reduction, its loop and the indirect call.

Semantics relied upon (as used by Espressif's esp-dsp dspi_dotprod_*_aes3.S,
Apache-2.0): EE.LD.128.USAR.IP loads the aligned block holding the address and
sets SAR_BYTE to its low four bits; EE.SRC.Q qa, qs0, qs1 is the low 128 bits
of {qs1, qs0} >> 8 * SAR_BYTE; RUR.ACCX_0/1 are bits 0..31 and 32..39 of ACCX.
The firmware compares these routines with C before use and keeps the scalar
code on any difference, so a wrong assumption costs speed only. Confirmed on
the board with 3.0.12-pre1 (product: 412 cycles, 690 Xtensa, 1,077 C).
"""
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/crypto/refc/x25519_mul_pie.S'

A_LO, A_HI, B2, B3, Z, W_LO, W_HI, T = 'q0', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7'
BLOCK = {0: Z, 1: Z, 2: B2, 3: B3, 4: Z, 5: Z}
M32 = 0xffffffff


def program(dst='a2'):
    """The product; halfword k of it is stored at dst + 2k."""
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

    def column(k):
        """SAR_BYTE and the windows of column k, and its vector MACs."""
        s = 31 - k
        m, r = s >> 3, s & 7
        win, macs = [], []
        if r:
            win += [('movi', 'a5', 2 * r), ('wur.sar_byte', 'a5')]
        for lo_blk, dst_q, a_reg in ((m, W_LO, A_LO), (m + 1, W_HI, A_HI)):
            q0, q1 = BLOCK[lo_blk], BLOCK.get(lo_blk + 1, Z)
            if r == 0:
                if q0 != Z:
                    macs.append(('vmulas', a_reg, q0))
            elif q0 != Z or q1 != Z:
                win.append(('src.q', dst_q, q0, q1))
                macs.append(('vmulas', a_reg, dst_q))
        return win, macs

    # Scheduled for the vector unit's latencies: the windows of column k + 1
    # are formed (their registers are free once column k's MACs issued)
    # between column k's last MAC and the ACCX read, and the halfword store
    # sits between the ACCX write-back and the next MAC.
    win, macs = column(0)
    ops.extend(win)
    for k in range(31):
        ops.extend(macs)
        if k < 30:
            win, macs = column(k + 1)
            ops.extend(win)
        o(('rur.accx_0', 'a6'))
        o(('rur.accx_1', 'a7'))
        o(('src', 'a8', 'a7', 'a6'))          # SAR is still 16: (hi:lo) >> 16
        o(('wur.accx_0', 'a8'))
        o(('wur.accx_1', 'a15'))
        o(('s16i', 'a6', dst, 2 * k))
    o(('s16i', 'a8', dst, 62))
    return ops


X = [f'a{i}' for i in range(3, 11)]          # the 8 result words during the reduction


def program_mulred():
    """out = a * b reduced as x25519.c mul(): the product in the 64-byte frame
    at a1, then out[j] = lo[j] + 38 * hi[j] + carry, then propagate(). out may
    be a or b: the product is complete before out is written."""
    ops = program('a1')
    o = ops.append
    L, R1, R3, CY, K = 'a12', 'a11', 'a13', 'a14', 'a15'
    # Scheduled so that no load or multiplication result is used by the next
    # instruction: the low words are loaded up front, and hi[j + 1] is loaded
    # while word j is folded.
    o(('movi', K, 38))
    o(('l32i', R1, 'a1', 32))               # hi[0]
    o(('l32i', X[0], 'a1', 0))
    o(('l32i', R3, 'a1', 36))               # hi[1]
    o(('mull', L, R1, K))
    o(('l32i', X[1], 'a1', 4))
    o(('muluh', R1, R1, K))
    for j in range(2, 8):
        o(('l32i', X[j], 'a1', 4 * j))
    o(('add', X[0], X[0], L))
    o(('saltu', L, X[0], L))
    o(('add', CY, R1, L))                   # 38 * hi < 2^38: its high word is at most 37
    h, n = R3, R1
    for j in range(1, 8):
        x = X[j]
        o(('mull', L, h, K))
        o(('muluh', h, h, K))
        if j < 7:
            o(('l32i', n, 'a1', 32 + 4 * (j + 1)))
        o(('add', x, x, L))
        o(('saltu', L, x, L))
        o(('add', h, h, L))
        o(('add', x, x, CY))
        o(('saltu', CY, x, CY))
        o(('add', CY, CY, h))
        h, n = n, h
    TT, C = 'a12', 'a13'
    o(('movi', K, 19))
    o(('srli', TT, X[7], 31))
    o(('slli', X[7], X[7], 1))             # clear the top bit (EXTUI takes at most 16 bits)
    o(('srli', X[7], X[7], 1))
    o(('addx2', TT, CY, TT))                # over = carry << 1 | top bit
    o(('mull', C, TT, K))
    for j in range(8):
        o(('add', X[j], X[j], C))
        o(('saltu', C, X[j], C))
        o(('s32i', X[j], 'a2', 4 * j))
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
        elif n in ('mull', 'muluh', 'add', 'saltu', 'addx2', 'srli', 'slli', 's32i'):
            text.append(f'    {n:7} {args[0]}, {args[1]}, {args[2]}')
        elif n == 'extui':
            text.append(f'    extui   {args[0]}, {args[1]}, {args[2]}, {args[3]}')
        else:
            raise ValueError(n)
    return text


def machine(ops, words, reg):
    """Run ops on a model of the instructions (see the module doc). words maps
    4-byte-aligned addresses to 32-bit words; a read of any other address
    fails. Returns the addresses of the halfword stores."""
    q = {f'q{i}': 0 for i in range(8)}
    st = {'sar': 0, 'sar_byte': 0, 'accx': 0}
    stores = []

    def word(addr):
        assert addr % 4 == 0 and addr in words, f'read outside the operands at {addr:#x}'
        return words[addr]

    def block(addr):
        addr &= ~15
        return sum(word(addr + 4 * i) << (32 * i) for i in range(4))

    for n, *x in ops:
        if n == 'mov':
            reg[x[0]] = reg[x[1]]
        elif n == 'addi':
            reg[x[0]] = (reg[x[1]] + x[2]) & M32
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
            reg[x[0]] = word(reg[x[1]] + x[2])
        elif n == 'src':
            reg[x[0]] = ((reg[x[1]] << 32 | reg[x[2]]) >> st['sar']) & M32
        elif n == 'movi.32.q':
            q[x[0]] = q[x[0]] & ~(M32 << (32 * x[2])) | reg[x[1]] << (32 * x[2])
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
            reg[x[0]] = st['accx'] & M32
        elif n == 'rur.accx_1':
            reg[x[0]] = st['accx'] >> 32 & 0xff
        elif n == 'wur.accx_0':
            st['accx'] = st['accx'] & ~M32 | reg[x[0]]
        elif n == 'wur.accx_1':
            st['accx'] = st['accx'] & M32 | (reg[x[0]] & 0xff) << 32
        elif n == 's16i':
            addr = reg[x[1]] + x[2]
            stores.append(addr)
            w, sh = addr & ~3, 16 * ((addr & 3) // 2)
            words[w] = words.get(w, 0) & ~(0xffff << sh) | (reg[x[0]] & 0xffff) << sh
        elif n == 's32i':
            words[reg[x[1]] + x[2]] = reg[x[0]]
        elif n == 'mull':
            reg[x[0]] = reg[x[1]] * reg[x[2]] & M32
        elif n == 'muluh':
            reg[x[0]] = reg[x[1]] * reg[x[2]] >> 32
        elif n == 'add':
            reg[x[0]] = (reg[x[1]] + reg[x[2]]) & M32
        elif n == 'saltu':
            reg[x[0]] = int(reg[x[1]] < reg[x[2]])
        elif n == 'addx2':
            reg[x[0]] = (reg[x[1]] * 2 + reg[x[2]]) & M32
        elif n == 'srli':
            reg[x[0]] = reg[x[1]] >> x[2]
        elif n == 'slli':
            reg[x[0]] = reg[x[1]] << x[2] & M32
        elif n == 'extui':
            reg[x[0]] = reg[x[1]] >> x[2] & ((1 << x[3]) - 1)
        else:
            raise ValueError(n)
    return stores


def _operands(a_words, b_words, a_offset):
    words = {}
    base_a, base_b = 0x1000 + a_offset, 0x2000
    for i, w in enumerate(a_words):
        words[base_a + 4 * i] = w
    for i, w in enumerate(b_words):
        words[base_b + 4 * i] = w
    # the aligned 16-byte blocks holding a also hold other data: noise, unused
    for addr in range(base_a & ~15, ((base_a + 31) & ~15) + 16, 4):
        words.setdefault(addr, random.getrandbits(32))
    return words, base_a, base_b


def simulate(ops, a_words, b_words, a_offset):
    """The product program: the 512-bit result from out[0..15]."""
    words, base_a, base_b = _operands(a_words, b_words, a_offset)
    base_out = 0x3000
    stores = machine(ops, words, {'a1': 0x7000, 'a2': base_out, 'a3': base_a, 'a4': base_b})
    assert sorted(stores) == [base_out + 2 * h for h in range(32)], 'every output halfword written once'
    return sum(words[base_out + 4 * i] << (32 * i) for i in range(16))


def simulate_mulred(ops, a_words, b_words, a_offset, out_is='new'):
    """The fused program: out[0..7]; out_is 'a' or 'b' makes out alias it."""
    words, base_a, base_b = _operands(a_words, b_words, a_offset)
    base_out = {'new': 0x3000, 'a': base_a, 'b': base_b}[out_is]
    frame = 0x7000
    for i in range(16):                       # the frame holds noise before use
        words[frame + 4 * i] = random.getrandbits(32)
    stores = machine(ops, words, {'a1': frame, 'a2': base_out, 'a3': base_a, 'a4': base_b})
    assert sorted(stores) == [frame + 2 * h for h in range(32)], 'product halfwords written once, in the frame'
    return [words[base_out + 4 * i] for i in range(8)]


def mul_reference(a_words, b_words):
    """x25519.c mul() with nb = 8, word for word: umaal with 38, propagate()."""
    acc = sum(w << (32 * i) for i, w in enumerate(a_words)) * sum(w << (32 * i) for i, w in enumerate(b_words))
    lo = [(acc >> (32 * j)) & M32 for j in range(8)]
    hi = [(acc >> (32 * (j + 8))) & M32 for j in range(8)]
    out, carry = [], 0
    for j in range(8):
        v = lo[j] + 38 * hi[j] + carry
        out.append(v & M32)
        carry = v >> 32
    over = out[7] >> 31 | carry << 1
    out[7] &= 0x7fffffff
    c = over * 19
    for j in range(8):
        v = out[j] + c
        out[j] = v & M32
        c = v >> 32
    return out


def value(words):
    return sum(w << (32 * i) for i, w in enumerate(words))


def check(ops):
    rnd = random.Random(25519)
    m = M32
    cases = [([m] * 8, [m] * 8), ([0] * 8, [m] * 8), ([1] + [0] * 7, [m] * 8),
             ([0x0000ffff] * 8, [0xffff0000] * 8), ([0xffff0000] * 8, [0x0000ffff] * 8)]
    cases += [([rnd.getrandbits(32) for _ in range(8)], [rnd.getrandbits(32) for _ in range(8)]) for _ in range(300)]
    for n, (a, b) in enumerate(cases):
        got = simulate(ops, a, b, 4 * (n % 4))
        assert got == value(a) * value(b), (n, hex(got))
    return len(cases)


def check_mulred(ops):
    rnd = random.Random(19)
    m = M32
    p = 2**255 - 19
    cases = [([m] * 8, [m] * 8), ([0] * 8, [m] * 8), ([1] + [0] * 7, [m] * 8), ([m] * 7 + [0x7fffffff], [m] * 8)]
    cases += [([rnd.getrandbits(32) for _ in range(8)], [rnd.getrandbits(32) for _ in range(8)]) for _ in range(300)]
    for n, (a, b) in enumerate(cases):
        got = simulate_mulred(ops, a, b, 4 * (n % 4), ('new', 'a', 'b')[n % 3])
        assert got == mul_reference(a, b), (n, got)
        assert value(got) % p == value(a) * value(b) % p
    return len(cases)


HEAD = '''/* Generated by tools/gen_x25519_mul_pie.py -- do not edit by hand.
 *
 * void x25519_mul_pie(uint32_t out[16], const uint32_t a[8], const uint32_t b[8])
 *   The 512-bit product of two 256-bit numbers on the ESP32-S3 vector unit:
 *   16-bit columns as dot products (EE.VMULAS.U16.ACCX) with the carry kept
 *   in ACCX.
 * void x25519_mulred_pie(uint32_t out[8], const uint32_t a[8], const uint32_t b[8])
 *   The same product reduced exactly as x25519.c mul() does (fold by 38,
 *   propagate), the product in its frame and the result in registers; out
 *   may be a or b.
 *
 * Constant time: no branch, no data-dependent address. a and b need only
 * 4-byte alignment and may be the same array. The vector loads read the
 * aligned 16-byte blocks that hold a (other bytes there are not used);
 * nothing else outside a and b is read.
 * x25519.c compares both with C before use. Uses q0-q7, ACCX, SAR_BYTE, SAR.
 */
'''


def function(name, frame, ops):
    return (f'    .section .text.{name}, "ax"\n    .align  4\n    .global {name}\n    .type   {name}, @function\n'
            f'{name}:\n    entry   a1, {frame}\n' + '\n'.join(render(ops)) +
            f'\n    retw.n\n    .size   {name}, . - {name}\n')


def generate(ops=None):
    return (HEAD + function('x25519_mul_pie', 32, ops or program()) + '\n' +
            function('x25519_mulred_pie', 96, program_mulred()))


def main():
    ops = program()
    n = check(ops)
    vm = sum(1 for op in ops if op[0] == 'vmulas')
    print(f'x25519 PIE product: {len(ops)} instructions ({vm} vector MACs), {n} products match the model')
    red = program_mulred()
    n = check_mulred(red)
    print(f'x25519 PIE product + reduction: {len(red)} instructions, {n} results equal x25519.c mul() (aliased outputs too)')
    if '--check' in sys.argv:
        return
    OUT.write_text(generate(ops), encoding='utf-8', newline='\n')
    print(f'wrote {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
