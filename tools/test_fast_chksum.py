"""Fast IPv4 UDP/TCP checksum glue (main/fast_chksum.c) against lwIP itself.

The Xtensa loop (fast_chksum_xtensa.S) returns the plain sum of 16-bit words;
here a C model of it runs under the actual folding code of fast_chksum.c,
compared with lwIP's own inet_chksum_pseudo() / lwip_standard_chksum()
(algorithm 2) taken from the pinned SDK (LWIP_SOURCE), and with an
independent RFC 1071 checksum over the pseudo header and data:
- every start alignment, lengths 0..1600, single pbufs and chains of up to
  five parts with odd and even lengths and misaligned parts, UDP and TCP;
- 400,000 random cases plus edge data (all 0x00, all 0xFF);
- mutants (no byte swap for an odd start, no swap tracking across a chain)
  are detected.
The loop itself runs on the board: fast_chksum.c compares it with lwIP
before first use and falls back to lwIP on any difference
(/api/system/diag fast_checksum).
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
mine = (ROOT / 'main/fast_chksum.c').read_text(encoding='utf-8').replace('\r\n', '\n')
asm = (ROOT / 'main/fast_chksum_xtensa.S').read_text(encoding='utf-8')
assert 'loopnez a6, .Lblocks_done' in asm and asm.count('l16ui') == 9
cmake = (ROOT / 'main/CMakeLists.txt').read_text(encoding='utf-8')
assert '"-Wl,--wrap=ip_chksum_pseudo"' in cmake and 'ITEMS udp_sendto ip_chksum_pseudo' not in cmake

sdk = os.environ.get('LWIP_SOURCE')
if not sdk:
    sdk = str(Path.home() / '.platformio/packages/framework-espidf/components/lwip/lwip')
lwip = (Path(sdk) / 'src/core/inet_chksum.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def body(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


alg2 = lwip[lwip.index('#if (LWIP_CHKSUM_ALGORITHM == 2)'):]
alg2 = alg2[:alg2.index('#endif', alg2.index('lwip_standard_chksum('))]
alg2 = alg2.split('\n', 1)[1]
lwip_code = (alg2.replace('u16_t\nlwip_standard_chksum(', 'static u16_t\nlwip_standard_chksum(')
             + 'static u16_t\n' + body(lwip, 'inet_cksum_pseudo_base(struct pbuf *p')
             + 'static u16_t\n' + body(lwip, 'inet_chksum_pseudo(struct pbuf *p'))
lwip_code = re.sub(r'/\*LWIP_DEBUGF.*?\*/', '', lwip_code)
lwip_code = re.sub(r'LWIP_DEBUGF\([^;]*\);', '', lwip_code)
assert lwip_code.count('static u16_t') == 3

macros = ''.join(line + '\n' for line in mine.split('\n') if line.startswith(('#define FC_FOLD', '#define FC_SWAP')))
assert macros.count('#define') == 2
fast_code = macros + body(mine, 'static u16_t fc_standard(') + body(mine, 'static u16_t fc_pseudo_v4(')

PROGRAM = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8_t; typedef uint16_t u16_t; typedef uint32_t u32_t; typedef uintptr_t mem_ptr_t;
struct pbuf { struct pbuf *next; void *payload; u16_t tot_len; u16_t len; };
typedef struct { u32_t addr; } ip4_addr_t;
#define ip4_addr_get_u32(a) ((a)->addr)
static u16_t lwip_htons(u16_t x) { return (u16_t)((x << 8) | (x >> 8)); }
#define FOLD_U32T(u) ((u32_t)(((u) >> 16) + ((u) & 0x0000ffffUL)))
#define SWAP_BYTES_IN_WORD(w) (((w) & 0xff) << 8) | (((w) & 0xff00) >> 8)
#define LWIP_CHKSUM lwip_standard_chksum
#define IP_PROTO_UDP 17
#define IP_PROTO_TCP 6
/* C model of the Xtensa loop: the plain sum of halfwords as stored (LE). */
static uint32_t tsr_csum_halfwords(const void *p, uint32_t nhalf) {
    const u8_t *b = p; uint32_t s = 0;
    for (uint32_t i = 0; i < nhalf; i++) { u16_t w; memcpy(&w, b + 2 * i, 2); s += w; }
    return s;
}
@@LWIP@@
@@FAST@@
/* RFC 1071 over the pseudo header and the data, big-endian words. */
static u16_t rfc1071(const u8_t *data, int len, u32_t src, u32_t dst, u8_t proto) {
    u8_t ph[12]; memcpy(ph, &src, 4); memcpy(ph + 4, &dst, 4); ph[8] = 0; ph[9] = proto; ph[10] = len >> 8; ph[11] = len;
    uint64_t s = 0;
    for (int i = 0; i < 12; i += 2) s += (ph[i] << 8) | ph[i + 1];
    for (int i = 0; i + 1 < len; i += 2) s += (data[i] << 8) | data[i + 1];
    if (len & 1) s += data[len - 1] << 8;
    while (s >> 16) s = (s & 0xffff) + (s >> 16);
    u16_t r = (u16_t)~s;
    return lwip_htons(r);    /* lwIP returns it in network order as stored */
}
static uint32_t seed = 0xC0FFEE;
static uint32_t rnd(void) { seed = seed * 1664525u + 1013904223u; return seed >> 7; }
static u8_t buf[1700];
static int check(int off, int len, int parts, u8_t proto, ip4_addr_t *s, ip4_addr_t *d) {
    struct pbuf q[5]; int cuts[6]; cuts[0] = 0; cuts[parts] = len;
    for (int i = 1; i < parts; i++) cuts[i] = len ? (int)(rnd() % (len + 1)) : 0;
    for (int i = 1; i < parts; i++) for (int j = i + 1; j < parts; j++) if (cuts[j] < cuts[i]) { int t = cuts[i]; cuts[i] = cuts[j]; cuts[j] = t; }
    /* each part copied to its own place, possibly misaligned, like separate pbufs */
    static u8_t store[5][1700 + 8];
    for (int i = 0; i < parts; i++) {
        int l = cuts[i + 1] - cuts[i], mis = (int)(rnd() % 4);
        memcpy(store[i] + mis, buf + off + cuts[i], l);
        q[i].payload = store[i] + mis; q[i].len = (u16_t)l; q[i].next = i + 1 < parts ? &q[i + 1] : NULL;
    }
    for (int i = parts - 1, tot = 0; i >= 0; i--) { tot += q[i].len; q[i].tot_len = (u16_t)tot; }
    u16_t a = inet_chksum_pseudo(&q[0], proto, (u16_t)len, s, d);
    u16_t b = fc_pseudo_v4(&q[0], proto, (u16_t)len, s, d);
    u16_t c = rfc1071(buf + off, len, s->addr, d->addr, proto);
    if (a != b || a != c) { printf("MISMATCH off=%d len=%d parts=%d lwip=%04x fast=%04x rfc=%04x\n", off, len, parts, a, b, c); return 0; }
    return 1;
}
int main(void) {
    ip4_addr_t s, d;
    for (int round = 0; round < 3; round++) {
        for (int i = 0; i < (int)sizeof buf; i++) buf[i] = round == 0 ? (u8_t)rnd() : round == 1 ? 0 : 0xFF;
        s.addr = rnd(); d.addr = rnd();
        for (int off = 0; off < 4; off++)
            for (int len = 0; len <= 1600; len++)
                if (!check(off, len, 1, (len & 1) ? IP_PROTO_TCP : IP_PROTO_UDP, &s, &d)) return 1;
    }
    for (int i = 0; i < (int)sizeof buf; i++) buf[i] = (u8_t)rnd();
    for (int it = 0; it < 400000; it++) {
        s.addr = rnd() ^ (rnd() << 9); d.addr = rnd() ^ (rnd() << 11);
        int len = (int)(rnd() % 1601), off = (int)(rnd() % 4), parts = 1 + (int)(rnd() % 5);
        if (!check(off, len, parts, (it & 1) ? IP_PROTO_TCP : IP_PROTO_UDP, &s, &d)) return 1;
    }
    puts("fast chksum ok");
    return 0;
}
'''


def run(fast):
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'ck.c'
        c.write_text(PROGRAM.replace('@@LWIP@@', lwip_code).replace('@@FAST@@', fast), encoding='utf-8')
        exe = Path(tmp) / ('ck.exe' if os.name == 'nt' else 'ck')
        subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                        '-Wno-sign-compare', '-Wno-parentheses', str(c), '-o', str(exe)], check=True)
        return subprocess.run([str(exe)], capture_output=True, text=True, timeout=600)


ok = run(fast_code)
assert ok.returncode == 0 and 'fast chksum ok' in ok.stdout, (ok.returncode, ok.stdout[-400:], ok.stderr[-400:])
for old, new in (('    if (odd) {\n        sum = FC_SWAP(sum);\n    }\n', ''),
                 ('            swapped = !swapped;\n            acc = FC_SWAP(acc);\n', '            swapped = !swapped;\n')):
    assert fast_code.count(old) == 1
    bad = run(fast_code.replace(old, new))
    assert bad.returncode != 0, 'mutant not detected: ' + old.strip()
print('fast chksum: equal to lwIP inet_chksum_pseudo and RFC 1071 on 420k cases; mutants detected')
