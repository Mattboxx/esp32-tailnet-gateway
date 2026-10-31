"""ESP32-S3 Poly1305 assembly (poly1305_xtensa.S) and its C dispatcher, host checks.

1. The actual .S file is parsed (macros expanded) and executed by a small
   Xtensa interpreter covering exactly the instructions it uses, then compared
   with the actual poly1305_blocks_c() compiled from poly1305-donna.c on the
   host: all-ones, clamped/real-sized and (where unsigned long is 32-bit, as on
   the device) full-range limbs, both hibit values, 1-8 blocks. The interpreter
   also checks that the routine only writes h and its own stack frame, keeps
   the windowed-ABI frame and loads aligned words. A mutated copy of the
   assembly must be rejected.
2. The dispatcher is compiled with POLY1305_XTENSA_ASM=1 and a C stub in place
   of the assembly: with a correct stub, aligned input goes straight to the
   block function and unaligned input one aligned copy at a time (tags equal a
   Python Poly1305 for offsets 0-3, lengths 0-130); with a wrong stub the
   check rejects it once and every tag still comes from the C code.
The interpreter encodes this tool's reading of the Xtensa ISA; that reading is
confirmed on the device by the same comparison (poly1305_asm_check()) before
first use. HOTLOOP_SANITIZE=1 enables ASan/UBSan for the C parts on Linux.
"""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REFC = ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/crypto/refc'
ASM = (REFC / 'poly1305_xtensa.S').read_text(encoding='utf-8')
M32 = 0xffffffff
CLAMP = (0x3ffffff, 0x3ffff03, 0x3ffc0ff, 0x3f03fff, 0x00fffff)


def parse(source):
    """Instruction list [(mnemonic, operands)] and label -> index, macros expanded."""
    text = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    macros, program, labels, current = {}, [], {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if current is not None:
            if line == '.endm':
                current = None
            else:
                macros[current][1].append(line)
            continue
        if line.startswith('.macro'):
            parts = line.split()
            current = parts[1]
            macros[current] = (parts[2:], [])
            continue
        if line.endswith(':'):
            labels[line[:-1]] = len(program)
            continue
        if line.startswith('.'):
            continue
        name, _, rest = line.partition(' ')
        args = [a.strip() for a in rest.split(',')] if rest.strip() else []
        if name in macros:
            params, body = macros[name]
            for body_line in body:
                for param, value in zip(params, args):
                    body_line = body_line.replace('\\' + param, value)
                n, _, r = body_line.partition(' ')
                program.append((n, [a.strip() for a in r.split(',')]))
        else:
            program.append((name, args))
    return program, labels


class Machine:
    FRAME = 80

    def __init__(self, program, labels):
        self.program, self.labels = program, labels
        self.words, self.writable = {}, set()

    def run(self, st, m, nbytes, hibit, entry='poly1305_blocks_xtensa'):
        a = [0] * 16
        sp = 0x3fc90000
        a[1], a[2], a[3], a[4], a[5] = sp, st, m, nbytes, hibit
        sar, pc, steps = None, self.labels[entry], 0

        def reg(name):
            assert re.fullmatch(r'a(1[0-5]|[0-9])', name), name
            return int(name[1:])

        def load(addr):
            assert addr % 4 == 0, 'unaligned load'
            assert addr in self.words, f'load outside known memory {addr:#x}'
            return self.words[addr]

        while True:
            name, ops = self.program[pc]
            pc += 1
            steps += 1
            assert steps < 100000
            if name == 'entry':
                assert reg(ops[0]) == 1 and int(ops[1]) == self.FRAME and a[1] == sp
                a[1] = sp - self.FRAME
                for off in range(0, self.FRAME, 4):
                    self.writable.add(a[1] + off)
                    self.words.setdefault(a[1] + off, 0)
            elif name == 'retw':
                assert a[1] == sp - self.FRAME, 'stack pointer changed'
                return steps
            elif name in ('l32i', 's32i'):
                t, s, off = reg(ops[0]), reg(ops[1]), int(ops[2])
                assert 0 <= off <= 1020 and off % 4 == 0
                addr = (a[s] + off) & M32
                if name == 'l32i':
                    a[t] = load(addr)
                else:
                    assert addr in self.writable, f'store outside h/frame {addr:#x}'
                    assert s == 1 or addr >= st + 20, 'store to r'
                    if s == 1:
                        assert addr < a[1] + self.FRAME - 32, 'store into the register save areas'
                    self.words[addr] = a[t]
            elif name == 'ssai':
                sar = int(ops[0])
                assert 0 <= sar <= 31
            elif name == 'src':
                assert sar is not None
                a[reg(ops[0])] = (((a[reg(ops[1])] << 32) | a[reg(ops[2])]) >> sar) & M32
            elif name == 'slli':
                sa = int(ops[2]); assert 1 <= sa <= 31
                a[reg(ops[0])] = (a[reg(ops[1])] << sa) & M32
            elif name == 'srli':
                sa = int(ops[2]); assert 0 <= sa <= 15
                a[reg(ops[0])] = a[reg(ops[1])] >> sa
            elif name == 'extui':
                shift, bits = int(ops[2]), int(ops[3]); assert 0 <= shift <= 31 and 1 <= bits <= 16
                a[reg(ops[0])] = (a[reg(ops[1])] >> shift) & ((1 << bits) - 1)
            elif name == 'addx4':
                a[reg(ops[0])] = (a[reg(ops[1])] * 4 + a[reg(ops[2])]) & M32
            elif name == 'add':
                a[reg(ops[0])] = (a[reg(ops[1])] + a[reg(ops[2])]) & M32
            elif name == 'addi':
                imm = int(ops[2]); assert -128 <= imm <= 127
                a[reg(ops[0])] = (a[reg(ops[1])] + imm) & M32
            elif name == 'or':
                a[reg(ops[0])] = a[reg(ops[1])] | a[reg(ops[2])]
            elif name == 'mov':
                a[reg(ops[0])] = a[reg(ops[1])]
            elif name == 'mull':
                a[reg(ops[0])] = (a[reg(ops[1])] * a[reg(ops[2])]) & M32
            elif name == 'muluh':
                a[reg(ops[0])] = (a[reg(ops[1])] * a[reg(ops[2])]) >> 32
            elif name == 'saltu':
                a[reg(ops[0])] = int(a[reg(ops[1])] < a[reg(ops[2])])
            elif name == 'bltui':
                imm = int(ops[1]); assert imm in (2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 32, 64, 128, 256, 32768, 65536)
                if a[reg(ops[0])] < imm:
                    pc = self.labels[ops[2]]
            elif name == 'j':
                pc = self.labels[ops[0]]
            else:
                raise AssertionError(f'instruction not modelled: {name}')
            assert all(0 <= v <= M32 for v in a)


def run_asm(source, r, h, msg_words, final):
    program, labels = parse(source)
    machine = Machine(program, labels)
    st, m = 0x3fca0000, 0x3fcb0000
    for i in range(5):
        machine.words[st + 4 * i] = r[i]
        machine.words[st + 20 + 4 * i] = h[i]
        machine.writable.add(st + 20 + 4 * i)
    for i, w in enumerate(msg_words):
        machine.words[m + 4 * i] = w
    steps = machine.run(st, m, 4 * len(msg_words), 0 if final else 1 << 24)
    return [machine.words[st + 20 + 4 * i] for i in range(5)], steps


HARNESS = r'''
#include <stdio.h>
#include "poly1305-donna.c"
int main(void) {
    printf("%u\n", (unsigned)sizeof(unsigned long));
    unsigned long r[5], h[5]; unsigned fin, n;
    while (scanf("%lx %lx %lx %lx %lx %lx %lx %lx %lx %lx %u %u", &r[0], &r[1], &r[2], &r[3], &r[4],
                 &h[0], &h[1], &h[2], &h[3], &h[4], &fin, &n) == 12) {
        poly1305_state_internal_t st; uint32_t msg[64];
        memset(&st, 0, sizeof st);
        for (int i = 0; i < 5; i++) { st.r[i] = r[i]; st.h[i] = h[i]; }
        for (unsigned i = 0; i < n; i++) { unsigned long w; if (scanf("%lx", &w) != 1) return 2; msg[i] = (uint32_t)w; }
        st.final = (unsigned char)fin;
        poly1305_blocks_c(&st, (const unsigned char *)msg, 4 * n);
        printf("%lx %lx %lx %lx %lx\n", st.h[0] & 0xffffffffUL, st.h[1] & 0xffffffffUL, st.h[2] & 0xffffffffUL,
               st.h[3] & 0xffffffffUL, st.h[4] & 0xffffffffUL);
    }
    return poly1305_asm_status() == 0 ? 0 : 3;
}
'''

DISPATCH = r'''
#include <assert.h>
#include <stdio.h>
#include "poly1305-donna.c"
static unsigned stub_calls;
void poly1305_blocks_xtensa(poly1305_state_internal_t *st, const unsigned char *m, size_t bytes, unsigned long hibit) {
    assert(((uintptr_t)m & 3) == 0 && bytes >= 16 && bytes % 16 == 0);
    assert(hibit == (st->final ? 0 : (1UL << 24)));
    stub_calls++;
    poly1305_blocks_c(st, m, bytes);
#ifdef STUB_WRONG
    st->h[2] ^= 1;
#endif
}
int main(void) {
    unsigned long key_words[8]; unsigned off, len;
    unsigned char buf[160 + 4];
    assert(poly1305_asm_status() == 0);
    while (scanf("%lx %lx %lx %lx %lx %lx %lx %lx %u %u", &key_words[0], &key_words[1], &key_words[2], &key_words[3],
                 &key_words[4], &key_words[5], &key_words[6], &key_words[7], &off, &len) == 10) {
        unsigned char key[32], tag[16];
        for (int i = 0; i < 32; i++) key[i] = (unsigned char)(key_words[i / 4] >> (8 * (i % 4)));
        for (unsigned i = 0; i < len; i++) { unsigned v; if (scanf("%x", &v) != 1) return 2; buf[off + i] = (unsigned char)v; }
        poly1305_context ctx;
        poly1305_init(&ctx, key);
        poly1305_update(&ctx, buf + off, len);
        poly1305_finish(&ctx, tag);
        for (int i = 0; i < 16; i++) printf("%02x", tag[i]);
        printf("\n");
    }
    printf("status %d %u\n", poly1305_asm_status(), stub_calls);
    return 0;
}
'''


def poly1305_ref(key, msg):
    r = int.from_bytes(key[:16], 'little') & 0x0ffffffc0ffffffc0ffffffc0fffffff
    s = int.from_bytes(key[16:], 'little')
    p, acc = (1 << 130) - 5, 0
    for i in range(0, len(msg), 16):
        block = msg[i:i + 16]
        acc = (acc + int.from_bytes(block + b'\x01', 'little')) * r % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, 'little')


def compile_c(folder, name, source, extra=()):
    path = Path(folder)
    (path / (name + '.c')).write_text(source, encoding='utf-8')
    (path / 'esp_log.h').write_text('#define ESP_LOGE(tag, ...) fprintf(stderr, __VA_ARGS__)\n')
    exe = path / (name + ('.exe' if os.name == 'nt' else ''))
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare', '-I', str(path), '-I', str(REFC)]
    if os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, *extra, str(path / (name + '.c')), '-o', str(exe)], check=True)
    return exe


def asm_cases(full_range):
    rng = random.Random(1305)
    cases = [([M32] * 5, [M32] * 5, [M32] * 4 * n, f) for n in (1, 2, 8) for f in (0, 1)]
    cases += [([0] * 5, [0] * 5, [0] * 4, 0), (list(CLAMP), [0x3ffffff] * 5, [M32] * 16, 0)]
    for i in range(400):
        n = 1 + i % 8
        r = [rng.getrandbits(32) & c for c in CLAMP]
        h = [rng.getrandbits(27) for _ in range(5)]
        cases.append((r, h, [rng.getrandbits(32) for _ in range(4 * n)], (i >> 3) & 1))
        if full_range:
            cases.append(([rng.getrandbits(32) for _ in range(5)], [rng.getrandbits(32) for _ in range(5)],
                          [rng.getrandbits(32) for _ in range(4 * n)], (i >> 4) & 1))
    return cases


def c_results(exe, cases):
    text = ''.join(' '.join(f'{v:x}' for v in r + h) + f' {fin} {len(m)} ' + ' '.join(f'{w:x}' for w in m) + '\n'
                   for r, h, m, fin in cases)
    out = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True, timeout=60).stdout.split('\n')
    return [[int(v, 16) for v in line.split()] for line in out[1:1 + len(cases)]]


def check_asm(exe, long_size):
    cases = asm_cases(full_range=long_size == 4)
    expected = c_results(exe, cases)
    steps_per_block = set()
    for (r, h, m, fin), want in zip(cases, expected):
        got, steps = run_asm(ASM, r, h, m, fin)
        assert got == want, (r, h, fin, got, want)
        steps_per_block.add((len(m) // 4, steps))
    by_blocks = dict(steps_per_block)
    per_block = by_blocks[2] - by_blocks[1]
    assert all(by_blocks[n] == by_blocks[1] + (n - 1) * per_block for n in by_blocks)
    # A one-character mutation of the carry must be caught.
    mutant = ASM.replace('ssai    26\n    src     a5, a12, a11', 'ssai    25\n    src     a5, a12, a11', 1)
    assert mutant != ASM
    r, h, m, fin = cases[0]
    assert run_asm(mutant, r, h, m, fin)[0] != expected[0] or any(
        run_asm(mutant, *case)[0] != want for case, want in zip(cases[:40], expected[:40]))
    return len(cases), per_block


def check_dispatch(folder, wrong):
    exe = compile_c(folder, 'dispatch' + ('_wrong' if wrong else ''), DISPATCH,
                    ['-DPOLY1305_XTENSA_ASM=1'] + (['-DSTUB_WRONG'] if wrong else []))
    rng = random.Random(8439)
    rows, want = [], []
    for length in range(0, 131):
        for off in range(4):
            key = bytes(rng.getrandbits(8) for _ in range(32))
            msg = bytes(rng.getrandbits(8) for _ in range(length))
            words = [int.from_bytes(key[i:i + 4], 'little') for i in range(0, 32, 4)]
            rows.append(' '.join(f'{w:x}' for w in words) + f' {off} {length} ' + ' '.join(f'{b:x}' for b in msg))
            want.append(poly1305_ref(key, msg).hex())
    out = subprocess.run([str(exe)], input='\n'.join(rows) + '\n', capture_output=True, text=True,
                         check=True, timeout=60).stdout.split('\n')
    assert out[:len(want)] == want, 'tag mismatch'
    status, total = out[len(want)].split()[1:]
    if wrong:   # the check stops at its first mismatch; the stub is never used again
        assert status == '-1' and int(total) == 1, (status, total)
    else:       # 64 check rounds, then every message of at least one byte
        assert status == '1' and int(total) >= 64 + len(want) - 4, (status, total)


def main():
    program, labels = parse(ASM)
    assert 'poly1305_blocks_xtensa' in labels and program[labels['poly1305_blocks_xtensa']][0] == 'entry'
    with tempfile.TemporaryDirectory(prefix='poly1305-xtensa-') as folder:
        exe = compile_c(folder, 'harness', HARNESS)
        long_size = int(subprocess.run([str(exe)], input='', capture_output=True, text=True, check=True).stdout.split()[0])
        count, per_block = check_asm(exe, long_size)
        check_dispatch(folder, wrong=False)
        check_dispatch(folder, wrong=True)
    print(f'PASS: actual poly1305_xtensa.S interpreted = actual poly1305_blocks_c on {count} cases '
          f'({"incl. full-range limbs" if long_size == 4 else "realistic limbs; 64-bit long host"}), '
          f'{per_block} instructions per 16-byte block, writes only h/own frame, mutant caught; '
          'dispatcher: aligned/unaligned (offsets 0-3, 0-130 B) tags = Python Poly1305, wrong block function '
          'rejected once with C fallback (host checks; device check before first use)')


if __name__ == '__main__':
    main()
