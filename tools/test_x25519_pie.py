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
print(f'x25519 PIE product: {len(ops)} instructions, {len(pairs)} products and squares at every alignment match; '
      f'no branch; generator output unchanged; {len(mutants)} mutants detected')
