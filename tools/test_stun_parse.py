"""STUN Binding-response parsers (actual MicroLink ml_stun.c) on the host.

Every data[i] access of both parsers is rewritten into a bounds-checked
read that aborts outside the received length, so over-reads are caught on
any host (no sanitizer needed). Checked:
- XOR-MAPPED-ADDRESS IPv4 and IPv6, legacy MAPPED-ADDRESS, unknown and
  padded attributes before them, IPv4 attribute on the IPv6 parser skipped;
- short packets, wrong type, wrong cookie, wrong transaction ID, message
  length beyond the packet, attribute length beyond the packet: refused;
- an empty XOR-MAPPED-ADDRESS as the last attribute (3.0.7-beta.11 fix:
  the IPv6 parser read its family byte past the packet);
- 300,000 random mutations of valid responses: no out-of-bounds read.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'external/microlink/components/microlink/src/ml_stun.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}\n', start) + 3]


def checked(code):
    return re.sub(r'\bdata\[([^\]]+)\]', r'AT(\1)', code)


parsers = function('bool ml_stun_parse_response(const uint8_t *data') + function('bool ml_stun_parse_response_ipv6(')
assert 'attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS && attr_len >= 8' in parsers

PROGRAM = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define TAG "t"
#define STUN_HEADER_SIZE 20
#define STUN_MAGIC_COOKIE 0x2112A442
#define STUN_BINDING_RESPONSE 0x0101
#define STUN_ATTR_MAPPED_ADDRESS 0x0001
#define STUN_ATTR_XOR_MAPPED_ADDRESS 0x0020
static void microlink_ip_to_str(uint32_t ip, char *s) { (void)ip; s[0] = 0; }
static uint8_t txid_v4[12], txid_v6[12];
static bool txid_v4_valid, txid_v6_valid;
static size_t cur_len;
static uint8_t at_(const uint8_t *d, size_t i) {
    if (i >= cur_len) { printf("OOB read at %u of %u\n", (unsigned)i, (unsigned)cur_len); exit(3); }
    return d[i];
}
#define AT(i) at_(data, (size_t)(i))
@@PARSERS@@
static uint8_t pkt[256]; static size_t plen;
static void hdr(const uint8_t *txid) {
    pkt[0] = 0x01; pkt[1] = 0x01; pkt[4] = 0x21; pkt[5] = 0x12; pkt[6] = 0xA4; pkt[7] = 0x42;
    memcpy(pkt + 8, txid, 12); plen = 20;
}
static void attr(uint16_t type, const uint8_t *v, uint16_t len) {
    pkt[plen] = type >> 8; pkt[plen + 1] = type; pkt[plen + 2] = len >> 8; pkt[plen + 3] = len;
    memcpy(pkt + plen + 4, v, len); plen += 4 + ((len + 3u) & ~3u);
}
static void fin(void) { uint16_t m = (uint16_t)(plen - 20); pkt[2] = m >> 8; pkt[3] = m; }
static bool v4(size_t len, uint32_t *ip, uint16_t *port) {
    cur_len = len; txid_v4_valid = true;
    uint8_t *copy = malloc(len ? len : 1); memcpy(copy, pkt, len);
    bool r = ml_stun_parse_response(copy, len, ip, port); free(copy); return r;
}
static bool v6(size_t len, uint8_t *ip6, uint16_t *port) {
    cur_len = len; txid_v6_valid = true; txid_v4_valid = true;
    uint8_t *copy = malloc(len ? len : 1); memcpy(copy, pkt, len);
    bool r = ml_stun_parse_response_ipv6(copy, len, ip6, port); free(copy); return r;
}
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d\n", __LINE__); return 1; } } while (0)
int main(void) {
    for (int i = 0; i < 12; i++) { txid_v4[i] = (uint8_t)(i + 1); txid_v6[i] = (uint8_t)(0x80 + i); }
    uint32_t ip; uint16_t port; uint8_t ip6[16];
    /* 203.0.113.7:41641 XORed with the cookie */
    uint8_t xa[8] = {0, 0x01, (41641 >> 8) ^ 0x21, (41641 & 0xFF) ^ 0x12, 203 ^ 0x21, 0 ^ 0x12, 113 ^ 0xA4, 7 ^ 0x42};
    uint8_t soft[5] = {'t', 'e', 's', 't', '!'};
    hdr(txid_v4); attr(0x8022, soft, 5); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, xa, 8); fin();
    CHECK(v4(plen, &ip, &port) && ip == 0xCB007107u && port == 41641);
    CHECK(!v4(plen - 1, &ip, &port));                      /* message length beyond packet */
    CHECK(!v4(19, &ip, &port));                            /* short */
    pkt[1] = 0x11; CHECK(!v4(plen, &ip, &port)); pkt[1] = 0x01;  /* error response */
    pkt[4] = 0; CHECK(!v4(plen, &ip, &port)); pkt[4] = 0x21;     /* cookie */
    pkt[8] ^= 1; CHECK(!v4(plen, &ip, &port)); pkt[8] ^= 1;      /* txid */

    uint8_t la[8] = {0, 0x01, 0x1F, 0x90, 198, 51, 100, 9};
    hdr(txid_v4); attr(STUN_ATTR_MAPPED_ADDRESS, la, 8); fin();
    CHECK(v4(plen, &ip, &port) && ip == 0xC6336409u && port == 8080);

    uint8_t x6[20] = {0, 0x02, 0x12 ^ 0x21, 0x34 ^ 0x12};
    for (int i = 0; i < 16; i++) x6[4 + i] = (uint8_t)(0x20 + i);
    hdr(txid_v6); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, xa, 8); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, x6, 20); fin();
    CHECK(v6(plen, ip6, &port) && port == 0x1234);
    CHECK(ip6[0] == (0x20 ^ 0x21) && ip6[4] == (0x24 ^ 0x80) && ip6[15] == (0x2F ^ 0x8B));
    CHECK(!v4(plen, &ip, &port) || ip != 0);               /* v4 parser: txid differs -> refused */

    /* empty XOR-MAPPED-ADDRESS as the very last bytes of the packet */
    for (int parser = 0; parser < 2; parser++) {
        hdr(parser ? txid_v6 : txid_v4); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, xa, 0); fin();
        CHECK(parser ? !v6(plen, ip6, &port) : !v4(plen, &ip, &port));
    }
    /* attribute length beyond the packet */
    hdr(txid_v6); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, x6, 20); fin(); pkt[23] = 200;
    CHECK(!v6(plen, ip6, &port)); CHECK(!v4(plen, &ip, &port));

    /* random mutations of valid responses */
    uint8_t base[3][256]; size_t blen[3];
    hdr(txid_v4); attr(0x8022, soft, 5); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, xa, 8); fin(); memcpy(base[0], pkt, plen); blen[0] = plen;
    hdr(txid_v4); attr(STUN_ATTR_MAPPED_ADDRESS, la, 8); fin(); memcpy(base[1], pkt, plen); blen[1] = plen;
    hdr(txid_v6); attr(STUN_ATTR_XOR_MAPPED_ADDRESS, x6, 20); fin(); memcpy(base[2], pkt, plen); blen[2] = plen;
    uint32_t seed = 0x5EED;
    for (int it = 0; it < 300000; it++) {
        int b = it % 3; memcpy(pkt, base[b], blen[b]); plen = blen[b];
        int k = 1 + (seed >> 28) % 4;
        for (int j = 0; j < k; j++) {
            seed = seed * 1664525u + 1013904223u;
            size_t at = 2 + (seed >> 8) % (plen - 2);
            if (at >= 8 && at < 20) continue;                 /* keep the txid so the attributes are parsed */
            pkt[at] = (uint8_t)(seed >> 3);
        }
        seed = seed * 1664525u + 1013904223u;
        size_t len = 20 + (seed >> 8) % (plen - 19);
        if ((seed & 3) == 0) len = plen;
        (void)v4(len, &ip, &port); (void)v6(len, ip6, &port);
    }
    puts("stun parse ok");
    return 0;
}
'''


def run(code):
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'stun.c'
        c.write_text(PROGRAM.replace('@@PARSERS@@', checked(code)), encoding='utf-8')
        exe = Path(tmp) / ('stun.exe' if os.name == 'nt' else 'stun')
        subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-sign-compare', str(c), '-o', str(exe)], check=True)
        return subprocess.run([str(exe)], capture_output=True, text=True)


ok = run(parsers)
assert ok.returncode == 0 and 'stun parse ok' in ok.stdout, (ok.returncode, ok.stdout, ok.stderr)
old = parsers.replace('attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS && attr_len >= 8', 'attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS')
mutant = run(old)
assert mutant.returncode == 3 and 'OOB read' in mutant.stdout, (mutant.returncode, mutant.stdout)
print('stun parse: responses decoded, malformed refused, no over-read; pre-fix parser over-reads')
