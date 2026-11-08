"""X25519 PIE multiplication (refc/x25519_mul_pie.S) on an instruction model.

The generated program is run on a model of the instructions it uses
(EE.LD.128.USAR.IP, EE.VLD.128.IP, EE.SRC.Q, EE.MOVI.32.Q,
EE.VMULAS.U16.ACCX, RUR/WUR.ACCX_0/1, WUR.SAR_BYTE, SSAI/SRC, S16I) and
compared with Python's exact integer product:
- 5,000 random operand pairs plus all-ones, zero, one and alternating
  halfword patterns, with a at every 4-byte alignment inside a 16-byte block
  and with a and b the same array (squares);
- every output halfword is written exactly once; ACCX never exceeds 39 bits;
- it has no branch and loads only from a and b;
- the .S file is what the generator produces (no hand edits);
- mutants (a dropped vector MAC, a wrong window shift, a lost carry, the
  carry not written back) are detected.
The model is what the generator assumes; the device compares the routine with
the C product before first use and keeps the scalar code on any difference.
"""
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gen_x25519_mul_pie as gen  # noqa: E402

SRC = gen.OUT.read_bytes().decode('ascii').replace('\r\n', '\n')
assert SRC == gen.generate(), 'x25519_mul_pie.S differs from its generator'
ops = gen.program()
assert not any(op[0].startswith('b') for op in ops), 'branch in the product'
assert all(op[2] in ('a3', 'a4', 'a5', 'a6') for op in ops if op[0] in ('l32i', 'vld', 'ld.usar')), 'loads only from a and b'


def product(a, b):
    return sum(w << (32 * i) for i, w in enumerate(a)) * sum(w << (32 * i) for i, w in enumerate(b))


def run_square(a, off):
    """a and b the same array: b's loads read a's words."""
    return gen.simulate(ops, a, a, off)


rnd = random.Random(0x25519)
M = (1 << 32) - 1
pairs = [([M] * 8, [M] * 8), ([0] * 8, [0] * 8), ([1] + [0] * 7, [M] * 8), ([0xffff] * 8, [0xffff0000] * 8),
         ([0xffff0000] * 8, [0xffff] * 8), ([0x80000001] * 8, [M] * 8)]
pairs += [([rnd.getrandbits(32) for _ in range(8)], [rnd.getrandbits(32) for _ in range(8)]) for _ in range(5000)]
for n, (a, b) in enumerate(pairs):
    off = 4 * (n % 4)
    assert gen.simulate(ops, a, b, off) == product(a, b), ('product', n)
    if n % 10 == 0:
        assert run_square(a, off) == product(a, a), ('square', n)


def mutant_detected(mut):
    try:
        for a, b in pairs[:60]:
            if gen.simulate(mut, a, b, 4) != product(a, b):
                return True
    except AssertionError:
        return True
    return False


vm = [i for i, op in enumerate(ops) if op[0] == 'vmulas']
sar = [i for i, op in enumerate(ops) if op[0] == 'movi' and op[1] == 'a5']
wacc = [i for i, op in enumerate(ops) if op[0] == 'wur.accx_0']
carry = [i for i, op in enumerate(ops) if op[0] == 'src' and op[1] == 'a6' and op[2] == 'a7']
mutants = {
    'dropped vector MAC': ops[:vm[len(vm) // 2]] + ops[vm[len(vm) // 2] + 1:],
    'wrong window shift': ops[:sar[3]] + [('movi', 'a5', ops[sar[3]][2] - 2)] + ops[sar[3] + 1:],
    'carry not written back': ops[:wacc[10]] + ops[wacc[10] + 1:],
    'lost carry high byte': ops[:carry[12]] + [('src', 'a6', 'a15', 'a6')] + ops[carry[12] + 1:],
}
for name, mut in mutants.items():
    assert mutant_detected(mut), f'mutant not detected: {name}'

# Fused product + reduction (x25519_mulred_pie): equal to x25519.c mul() word
# for word, with the output separate or aliasing a or b, squares in place.
red = gen.program_mulred()
assert not any(op[0].startswith('b') for op in red), 'branch in the fused routine'
assert all(op[2] in ('a1', 'a3', 'a4', 'a5', 'a6') for op in red if op[0] in ('l32i', 'vld', 'ld.usar'))
assert all(op[2] == 'a2' for op in red if op[0] == 's32i') and sum(op[0] == 's32i' for op in red) == 8
P = 2**255 - 19
edge = [([M] * 8, [M] * 8), ([M] * 7 + [0x7fffffff], [M] * 7 + [0x7fffffff]), ([0] * 8, [M] * 8),
        ([19] + [0] * 7, [M] * 8), ([0xffffffed] + [M] * 6 + [0x7fffffff], [2] + [0] * 7)]
rcases = edge + pairs[6:2006]
for n, (a, b) in enumerate(rcases):
    alias = ('new', 'a', 'b')[n % 3]
    got = gen.simulate_mulred(red, a, b, 4 * (n % 4), alias)
    assert got == gen.mul_reference(a, b), ('fused', n, alias)
    assert gen.value(got) % P == gen.value(a) * gen.value(b) % P and gen.value(got) < 2**255 + 2**32
    if n % 10 == 0:
        assert gen.simulate_mulred(red, a, a, 4 * (n % 4), 'a') == gen.mul_reference(a, a), ('fused square', n)


def red_mutant_detected(mut):
    try:
        return any(gen.simulate_mulred(mut, a, b, 0) != gen.mul_reference(a, b) for a, b in rcases[:80])
    except AssertionError:
        return True


idx = lambda name, pred: [i for i, op in enumerate(red) if op[0] == name and pred(op)]
k38 = idx('movi', lambda op: op[2] == 38)[0]
k19 = idx('movi', lambda op: op[2] == 19)[0]
cy = idx('add', lambda op: op[1] == 'a14')
top = idx('slli', lambda op: True)[0]
red_mutants = {
    'fold by 39': red[:k38] + [('movi', 'a15', 39)] + red[k38 + 1:],
    'fold top bit by 18': red[:k19] + [('movi', 'a15', 18)] + red[k19 + 1:],
    'carry lost in word 3': red[:cy[3]] + [('add', 'a14', 'a11', 'a15')] + red[cy[3] + 1:],
    'top bit kept': red[:top] + red[top + 2:],
}
for name, mut in red_mutants.items():
    assert red_mutant_detected(mut), f'fused mutant not detected: {name}'
print(f'x25519 PIE product: {len(ops)} instructions, {len(pairs)} products and squares at every alignment match; '
      f'no branch; generator output unchanged; {len(mutants)} mutants detected. Fused with the reduction: '
      f'{len(red)} instructions, {len(rcases)} results equal x25519.c mul() with the output separate or aliased, '
      f'squares in place; {len(red_mutants)} mutants detected')
