"""ESP32-S3 ChaCha20 assembly (chacha20_xtensa.S) and its C dispatcher, host checks.

1. The actual .S file is parsed (macros expanded) and executed by a small
   Xtensa interpreter covering exactly the instructions it uses, including the
   zero-overhead loop (LBEG/LEND/LCOUNT). Its output is compared with an
   independent Python ChaCha20 (RFC 8439 2.3.2 test vector) and with the
   actual chacha20() C loop compiled from chacha20.c on the host:
   - all-ones and random states, a block counter wrapping, 1-4 blocks;
   - in place and into a separate buffer.
   The interpreter also checks that the routine:
   - reads only the state, the input and frame words it wrote;
   - writes only the output, the block counter and its own frame (never the
     register save areas);
   - keeps the windowed-ABI frame and returns with the caller's a0;
   - uses aligned words;
   - never branches inside the hardware loop and synchronises it with ISYNC.
   Mutated copies of the assembly must be rejected.
2. The dispatcher is compiled with CHACHA20_XTENSA_ASM=1 and a C stub in place
   of the assembly:
   - With a correct stub, outputs equal Python ChaCha20 for input/output
     offsets 0-3, in place or not, and lengths 0-200. Aligned whole blocks go
     straight to the block function; the rest goes through its key stream.
   - With a wrong stub, the check rejects it once and every output still
     comes from the C code.
The interpreter encodes this tool's reading of the Xtensa ISA; that reading is
confirmed on the device by the same comparison (chacha20_asm_check()) before
first use. HOTLOOP_SANITIZE=1 enables ASan/UBSan for the C parts on Linux.
"""
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WG = ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src'
REFC = WG / 'crypto/refc'
ASM = (REFC / 'chacha20_xtensa.S').read_text(encoding='utf-8').replace('\r\n', '\n')
M32 = 0xffffffff
SIGMA = (0x61707865, 0x3320646e, 0x79622d32, 0x6b206574)


def rotl(v, n):
    return ((v << n) | (v >> (32 - n))) & M32


def block_ref(state):
    """RFC 8439 2.3: key-stream words of one block."""
    x = list(state)

    def qr(a, b, c, d):
        x[a] = (x[a] + x[b]) & M32; x[d] = rotl(x[d] ^ x[a], 16)
        x[c] = (x[c] + x[d]) & M32; x[b] = rotl(x[b] ^ x[c], 12)
        x[a] = (x[a] + x[b]) & M32; x[d] = rotl(x[d] ^ x[a], 8)
        x[c] = (x[c] + x[d]) & M32; x[b] = rotl(x[b] ^ x[c], 7)
    for _ in range(10):
        qr(0, 4, 8, 12); qr(1, 5, 9, 13); qr(2, 6, 10, 14); qr(3, 7, 11, 15)
        qr(0, 5, 10, 15); qr(1, 6, 11, 12); qr(2, 7, 8, 13); qr(3, 4, 9, 14)
    return [(a + b) & M32 for a, b in zip(x, state)]


def stream_ref(state, data):
    """XOR data with the key stream; returns (output, state after)."""
    state, out = list(state), bytearray()
    for i in range(0, len(data), 64):
        ks = struct.pack('<16I', *block_ref(state))
        out += bytes(a ^ b for a, b in zip(data[i:i + 64], ks))
        state[12] = (state[12] + 1) & M32
    return bytes(out), state


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
            head = line[len('.macro'):].strip()
            name, _, params = head.partition(' ')
            current = name
            macros[name] = ([p.strip() for p in params.split(',') if p.strip()], [])
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
            assert len(params) == len(args), (name, args)
            for body_line in body:
                for param, value in sorted(zip(params, args), key=lambda pv: -len(pv[0])):
                    body_line = body_line.replace('\\' + param, value)
                assert '\\' not in body_line, body_line
                n, _, r = body_line.partition(' ')
                program.append((n, [a.strip() for a in r.split(',')] if r.strip() else []))
        else:
            program.append((name, args))
    return program, labels


class Machine:
    FRAME = 80
    BRANCHES = ('bnez', 'beqz', 'j', 'bltui', 'bgeui', 'bne', 'beq')

    def __init__(self, program, labels):
        self.program, self.labels = program, labels

    def run(self, state_addr, out_addr, in_addr, blocks, memory, out_len):
        """memory: addr -> word (state and input). Returns (memory, steps, a0 ok)."""
        words = dict(memory)
        readable = set(words)
        writable = {state_addr + 48} | {out_addr + 4 * i for i in range(out_len // 4)}
        state_words = {state_addr + 4 * i for i in range(16)}
        a = [0] * 16
        sp, ra = 0x3fc90000, 0x80001234
        a[0], a[1], a[2], a[3], a[4], a[5] = ra, sp, state_addr, out_addr, in_addr, blocks
        sar, lbeg, lend, lcount, synced = None, None, None, 0, True
        pc, steps = self.labels['chacha20_blocks_xtensa'], 0

        def reg(name):
            assert re.fullmatch(r'a(1[0-5]|[0-9])', name), name
            return int(name[1:])

        while True:
            name, ops = self.program[pc]
            pc += 1
            steps += 1
            assert steps < 200000
            if lbeg is not None and lbeg <= pc - 1 < lend:
                assert name not in self.BRANCHES and name != 'retw', 'branch inside the hardware loop'
            if name == 'entry':
                assert reg(ops[0]) == 1 and int(ops[1]) == self.FRAME and a[1] == sp
                a[1] = sp - self.FRAME
            elif name == 'retw':
                assert a[1] == sp - self.FRAME, 'stack pointer changed'
                assert lcount == 0, 'hardware loop still armed'
                return words, steps, a[0] == ra
            elif name in ('l32i', 's32i', 'l32i.n', 's32i.n'):
                t, s, off = reg(ops[0]), reg(ops[1]), int(ops[2])
                assert 0 <= off <= 1020 and off % 4 == 0
                addr = (a[s] + off) & M32
                assert addr % 4 == 0, 'unaligned word'
                frame = s == 1
                if frame:
                    assert off < self.FRAME - 32, 'register save area touched'
                if name.startswith('l32i'):
                    assert addr in readable, f'load from unknown/unwritten memory {addr:#x}'
                    a[t] = words[addr]
                else:
                    assert frame or addr in writable, f'store outside output/counter/frame {addr:#x}'
                    if not frame and addr in state_words:
                        assert addr == state_addr + 48
                    words[addr] = a[t]
                    readable.add(addr)
            elif name == 'movi':
                a[reg(ops[0])] = self.labels[ops[1]] if ops[1] in self.labels else int(ops[1], 0) & M32
            elif name.startswith('wsr.'):
                sr, v = name[4:], a[reg(ops[0])]
                if sr == 'lbeg':
                    lbeg = v
                elif sr == 'lend':
                    lend = v
                elif sr == 'lcount':
                    lcount = v
                else:
                    raise AssertionError(f'special register not modelled: {sr}')
                synced = False
            elif name == 'isync':
                synced = True
            elif name == 'ssai':
                sar = int(ops[0])
                assert 0 <= sar <= 31
            elif name == 'src':
                assert sar is not None
                a[reg(ops[0])] = (((a[reg(ops[1])] << 32) | a[reg(ops[2])]) >> sar) & M32
            elif name in ('add', 'add.n'):
                a[reg(ops[0])] = (a[reg(ops[1])] + a[reg(ops[2])]) & M32
            elif name in ('addi', 'addi.n'):
                imm = int(ops[2]); assert -128 <= imm <= 127
                a[reg(ops[0])] = (a[reg(ops[1])] + imm) & M32
            elif name == 'xor':
                a[reg(ops[0])] = a[reg(ops[1])] ^ a[reg(ops[2])]
            elif name == 'bnez':
                if a[reg(ops[0])] != 0:
                    pc = self.labels[ops[1]]
                    continue
            else:
                raise AssertionError(f'instruction not modelled: {name}')
            assert all(0 <= v <= M32 for v in a)
            if lend is not None and pc == lend and lcount > 0:
                assert synced, 'loop registers written without ISYNC'
                lcount -= 1
                pc = lbeg


def run_asm(source, state, data, inplace):
    program, labels = parse(source)
    st, src = 0x3fca0000, 0x3fcb0000
    dst = src if inplace else 0x3fcc0000
    memory = {st + 4 * i: v for i, v in enumerate(state)}
    memory.update({src + 4 * i: w for i, w in enumerate(struct.unpack(f'<{len(data) // 4}I', data))})
    words, steps, ra_ok = Machine(program, labels).run(st, dst, src, len(data) // 64, memory, len(data))
    assert ra_ok, 'return address not restored'
    out = struct.pack(f'<{len(data) // 4}I', *(words.get(dst + 4 * i, 0) for i in range(len(data) // 4)))
    return out, [words[st + 4 * i] for i in range(16)], steps


HARNESS = r'''
#include <stdio.h>
#include "chacha20.c"
int main(void) {
    unsigned long v; unsigned n;
    while (scanf("%u", &n) == 1) {
        struct chacha20_ctx ctx; static uint8_t buf[512];
        for (int i = 0; i < 16; i++) { if (scanf("%lx", &v) != 1) return 2; ctx.state[i] = (uint32_t)v; }
        for (unsigned i = 0; i < n; i++) { if (scanf("%lx", &v) != 1) return 2; buf[i] = (uint8_t)v; }
        chacha20(&ctx, buf, buf, n);
        for (unsigned i = 0; i < n; i++) printf("%02x", buf[i]);
        for (int i = 0; i < 16; i++) printf(" %lx", (unsigned long)ctx.state[i]);
        printf("\n");
    }
    return chacha20_asm_status() == 0 ? 0 : 3;
}
'''

DISPATCH = r'''
#include <assert.h>
#include <stdio.h>
#include "chacha20.c"
static unsigned stub_calls;
void chacha20_blocks_xtensa(uint32_t *state, uint32_t *out, const uint32_t *in, uint32_t blocks) {
    assert((((uintptr_t)out | (uintptr_t)in) & 3) == 0 && blocks >= 1);
    assert(out == in || (const uint8_t *)out + 64 * blocks <= (const uint8_t *)in ||
           (const uint8_t *)in + 64 * blocks <= (const uint8_t *)out);
    stub_calls++;
    struct chacha20_ctx c;
    memcpy(c.state, state, sizeof c.state);
    chacha20_c(&c, (uint8_t *)out, (const uint8_t *)in, 64 * blocks);
#ifdef STUB_WRONG
    out[blocks * 16 - 1] ^= 0x100;
#endif
    memcpy(state, c.state, sizeof c.state);
}
int main(void) {
    static uint32_t inbuf[80], outbuf[80];
    unsigned long v; unsigned ioff, ooff, inplace, len;
    assert(chacha20_asm_status() == 0);
    while (scanf("%u %u %u %u", &ioff, &ooff, &inplace, &len) == 4) {
        struct chacha20_ctx ctx;
        uint8_t *in = (uint8_t *)inbuf + ioff, *out = inplace ? in : (uint8_t *)outbuf + ooff;
        for (int i = 0; i < 16; i++) { if (scanf("%lx", &v) != 1) return 2; ctx.state[i] = (uint32_t)v; }
        for (unsigned i = 0; i < len; i++) { if (scanf("%lx", &v) != 1) return 2; in[i] = (uint8_t)v; }
        chacha20(&ctx, out, in, len);
        for (unsigned i = 0; i < len; i++) printf("%02x", out[i]);
        printf(" %lx\n", (unsigned long)ctx.state[12]);
    }
    printf("status %d %u\n", chacha20_asm_status(), stub_calls);
    return 0;
}
'''


def compile_c(folder, name, source, extra=()):
    path = Path(folder)
    (path / (name + '.c')).write_text(source, encoding='utf-8')
    (path / 'esp_log.h').write_text('#define ESP_LOGE(tag, ...) fprintf(stderr, __VA_ARGS__)\n')
    exe = path / (name + ('.exe' if os.name == 'nt' else ''))
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
             '-I', str(path), '-I', str(REFC), '-I', str(WG)]
    if os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, *extra, str(path / (name + '.c')), '-o', str(exe)], check=True)
    return exe


def asm_cases():
    rng = random.Random(8439)
    key = list(range(0, 32))
    rfc_key = [int.from_bytes(bytes(key[i:i + 4]), 'little') for i in range(0, 32, 4)]
    # RFC 8439 2.3.2: counter 1, nonce 00:00:00:09:00:00:00:4a:00:00:00:00, zero input = key stream.
    rfc = [*SIGMA, *rfc_key, 1, 0x09000000, 0x4a000000, 0]
    cases = [(rfc, bytes(64), True), ([M32] * 16, bytes([0xff]) * 128, False)]
    wrap = [rng.getrandbits(32) for _ in range(16)]
    wrap[12] = M32
    cases.append((wrap, bytes(rng.getrandbits(8) for _ in range(192)), True))
    for i in range(200):
        state = [*SIGMA, *(rng.getrandbits(32) for _ in range(12))] if i % 2 else [rng.getrandbits(32) for _ in range(16)]
        blocks = 1 + i % 4
        cases.append((state, bytes(rng.getrandbits(8) for _ in range(64 * blocks)), bool(i & 4)))
    return cases


def c_results(exe, cases):
    text = ''.join(f'{len(d)} ' + ' '.join(f'{w:x}' for w in s) + ' ' + ' '.join(f'{b:x}' for b in d) + '\n'
                   for s, d, _ in cases)
    out = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True, timeout=60).stdout.split('\n')
    results = []
    for line in out[:len(cases)]:
        data, *state = line.split()
        results.append((bytes.fromhex(data), [int(v, 16) for v in state]))
    return results


def check_asm(exe):
    cases = asm_cases()
    expected = c_results(exe, cases)
    rfc_stream = bytes.fromhex(
        '10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e'
        'd2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e')
    assert stream_ref(cases[0][0], cases[0][1])[0] == rfc_stream, 'Python reference disagrees with RFC 8439'
    steps_by_blocks = {}
    for (state, data, inplace), (c_out, c_state) in zip(cases, expected):
        want, want_state = stream_ref(state, data)
        assert c_out == want and c_state == want_state, 'C loop disagrees with the Python reference'
        got, got_state, steps = run_asm(ASM, state, data, inplace)
        assert got == want, (state, inplace)
        assert got_state == want_state, 'state after the call'
        steps_by_blocks.setdefault(len(data) // 64, set()).add(steps)
    assert all(len(v) == 1 for v in steps_by_blocks.values()), 'data-dependent instruction count'
    steps = {k: next(iter(v)) for k, v in steps_by_blocks.items()}
    per_block = steps[2] - steps[1]
    assert all(steps[n] == steps[1] + (n - 1) * per_block for n in steps)
    mutants = [
        ('ssai    25', 'ssai    24'),                                   # wrong rotation
        ('movi    a3, 9 ', 'movi    a3, 8 '),                           # nine double rounds
        ('    l32i    a0, a1, 24\n    QR2', '    l32i    a0, a1, 20\n    QR2'),   # wrong exchange
        ('    LAST    20, 48', '    LAST    20, 52'),                   # word 12 feed-forward
        ('    addi    a4, a4, 1\n', '    addi    a4, a4, 2\n'),         # counter step
    ]
    for old, new in mutants:
        mutant = ASM.replace(old, new, 1)
        assert mutant != ASM, old
        caught = False
        for state, data, inplace in cases[:12]:
            try:
                got, got_state, _ = run_asm(mutant, state, data, inplace)
            except AssertionError:
                caught = True
                break
            if (got, got_state) != stream_ref(state, data):
                caught = True
                break
        assert caught, f'mutant not caught: {old!r}'
    return len(cases), per_block, len(mutants)


def check_dispatch(folder, wrong):
    exe = compile_c(folder, 'dispatch' + ('_wrong' if wrong else ''), DISPATCH,
                    ['-DCHACHA20_XTENSA_ASM=1'] + (['-DSTUB_WRONG'] if wrong else []))
    rng = random.Random(7539)
    rows, want = [], []
    for length in range(0, 201):
        for ioff in range(4):
            ooff, inplace = rng.randrange(4), (length + ioff) % 3 == 0
            state = [*SIGMA, *(rng.getrandbits(32) for _ in range(12))]
            if length % 7 == 0:
                state[12] = M32 - rng.randrange(3)
            data = bytes(rng.getrandbits(8) for _ in range(length))
            rows.append(f'{ioff} {ooff} {int(inplace)} {length} ' + ' '.join(f'{w:x}' for w in state) + ' '
                        + ' '.join(f'{b:x}' for b in data))
            out, st = stream_ref(state, data)
            want.append(f'{out.hex()} {st[12]:x}')
    out = subprocess.run([str(exe)], input='\n'.join(rows) + '\n', capture_output=True, text=True,
                         check=True, timeout=60).stdout.split('\n')
    assert [line.strip() for line in out[:len(want)]] == [w.strip() for w in want], 'output mismatch'
    status, total = out[len(want)].split()[1:]
    if wrong:   # the check stops at its first mismatch; the stub is never used again
        assert status == '-1' and int(total) == 1, (status, total)
    else:       # 16 check rounds, then every message of at least one byte
        assert status == '1' and int(total) >= 16 + len(want) - 4, (status, total)


def main():
    program, labels = parse(ASM)
    assert program[labels['chacha20_blocks_xtensa']][0] == 'entry'
    with tempfile.TemporaryDirectory(prefix='chacha20-xtensa-') as folder:
        exe = compile_c(folder, 'harness', HARNESS)
        count, per_block, mutants = check_asm(exe)
        check_dispatch(folder, wrong=False)
        check_dispatch(folder, wrong=True)
    print(f'PASS: actual chacha20_xtensa.S interpreted = Python RFC 8439 ChaCha20 = actual C loop on {count} cases '
          f'(RFC 2.3.2 vector, counter wrap, 1-4 blocks, in place/separate), {per_block} instructions per block, '
          f'only output/counter/own frame written, {mutants} mutants caught; dispatcher: offsets 0-3, 0-200 B, '
          'in place/separate = Python, wrong block function rejected once with C fallback '
          '(host checks; device check before first use)')


if __name__ == '__main__':
    main()
