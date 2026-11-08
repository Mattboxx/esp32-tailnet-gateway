"""X25519 Xtensa multiplication (refc/x25519_mul_xtensa.S) on a host emulator.

The routine is executed instruction by instruction with Xtensa semantics
(32-bit registers, MULL/MULUH, SALTU, windowed ENTRY/RETW) and compared with
Python's exact integer product:
- 20,000 random operand pairs, plus all-ones, zero, one, single-bit and
  alternating patterns (maximal carries in every column);
- it writes exactly out[0..15] and nothing else, reads only a[0..7] and
  b[0..7], and keeps the stack pointer;
- the .S file is what the generator produces (no hand edits);
- mutants (a dropped carry, a swapped accumulator) are detected.
The device also compares it with the C product before first use (x25519.c).
"""
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gen_x25519_mul_xtensa as gen  # noqa: E402

M32 = 0xFFFFFFFF
SRC = gen.OUT.read_bytes().decode('ascii').replace('\r\n', '\n')
assert SRC == gen.generate(), 'x25519_mul_xtensa.S differs from its generator'


def parse(source):
    text = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    program, labels = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('.'):
            continue
        if line.endswith(':'):
            labels[line[:-1]] = len(program)
            continue
        name, _, rest = line.partition(' ')
        program.append((name, [x.strip() for x in rest.split(',')] if rest.strip() else []))
    return program, labels


PROGRAM, LABELS = parse(SRC)
A_BASE, B_BASE, OUT_BASE, SP = 0x3FC80000, 0x3FC81000, 0x3FC82000, 0x3FC90000


def run(program, a_limbs, b_limbs):
    mem = {}
    for i in range(8):
        mem[A_BASE + 4 * i] = a_limbs[i]
        mem[B_BASE + 4 * i] = b_limbs[i]
    for i in range(-4, 20):
        mem[OUT_BASE + 4 * i] = 0xDEADBEEF          # guard words around out
    r = [0] * 16
    r[1], r[2], r[3], r[4] = SP, OUT_BASE, A_BASE, B_BASE

    def reg(x):
        assert re.fullmatch(r'a(1[0-5]|[0-9])', x), x
        return int(x[1:])

    pc = LABELS['x25519_mul_xtensa']
    written = set()
    for _ in range(5000):
        name, ops = program[pc]
        pc += 1
        if name == 'entry':
            assert ops == ['a1', '32']
            r[1] = SP - 32
        elif name == 'retw':
            assert r[1] == SP - 32
            return [mem[OUT_BASE + 4 * i] for i in range(16)], written, mem
        elif name == 'movi':
            r[reg(ops[0])] = int(ops[1], 0) & M32
        elif name == 'l32i':
            addr = (r[reg(ops[1])] + int(ops[2])) & M32
            assert A_BASE <= addr < A_BASE + 32 or B_BASE <= addr < B_BASE + 32, f'read {addr:#x}'
            r[reg(ops[0])] = mem[addr]
        elif name == 's32i':
            addr = (r[reg(ops[1])] + int(ops[2])) & M32
            assert OUT_BASE <= addr < OUT_BASE + 64, f'write {addr:#x}'
            mem[addr] = r[reg(ops[0])]
            written.add(addr)
        elif name == 'mull':
            r[reg(ops[0])] = (r[reg(ops[1])] * r[reg(ops[2])]) & M32
        elif name == 'muluh':
            r[reg(ops[0])] = (r[reg(ops[1])] * r[reg(ops[2])]) >> 32
        elif name == 'add':
            r[reg(ops[0])] = (r[reg(ops[1])] + r[reg(ops[2])]) & M32
        elif name == 'saltu':
            r[reg(ops[0])] = int(r[reg(ops[1])] < r[reg(ops[2])])
        else:
            raise AssertionError(f'instruction not modelled: {name}')
    raise AssertionError('no return')


def limbs(n):
    return [(n >> (32 * i)) & M32 for i in range(8)]


def check(program, a, b):
    out, written, mem = run(program, limbs(a), limbs(b))
    got = sum(w << (32 * i) for i, w in enumerate(out))
    return got == a * b and len(written) == 16 and all(mem[OUT_BASE + 4 * i] == 0xDEADBEEF for i in list(range(-4, 0)) + list(range(16, 20)))


rng = random.Random(0x25519)
edges = [0, 1, 2**256 - 1, 2**255 - 19, 2**255 - 1, 2**32 - 1, 2**224, int('AA' * 32, 16), int('55' * 32, 16), 2**128 + 1]
cases = [(x, y) for x in edges for y in edges] + [(rng.getrandbits(256), rng.getrandbits(256)) for _ in range(20000)]
for x, y in cases:
    assert check(PROGRAM, x, y), (hex(x), hex(y))
instructions = sum(1 for n, _ in PROGRAM)

# mutants: a carry dropped, an accumulator word added to the wrong register
lines = SRC.split('\n')
idx = [i for i, l in enumerate(lines) if l.strip().startswith('add     a8, a8, a7')][10]   # a mid-column product: carries happen
m1 = '\n'.join(lines[:idx] + lines[idx + 1:])
idx2 = [i for i, l in enumerate(lines) if l.strip().startswith('add     a11, a11, a8')][5]
m2 = '\n'.join(lines[:idx2] + [lines[idx2].replace('add     a11, a11, a8', 'add     a10, a10, a8')] + lines[idx2 + 1:])
for mutant in (m1, m2):
    prog, _ = parse(mutant)
    assert not all(check(prog, x, y) for x, y in cases[:400]), 'mutant not detected'
print(f'x25519 xtensa mul: {len(cases)} products exact on the emulator ({instructions} instructions), '
      'writes only out[0..15], generator in sync, mutants detected')
