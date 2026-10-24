"""Actual tailnet-name resolver core of main/tailnet_names.c on DNS wire data.

Covered: short and full MagicDNS names (Tailscale and a Headscale-style base
domain), case, trailing dots, A/ANY/AAAA/other types, NXDOMAIN inside the
tailnet domain and forwarding of every other name, malformed and hostile
packets (compression in the question, oversize labels, truncation, several
questions, responses, other opcodes and classes), output limits and peers
without an address. The relay sockets, the LAN listener and real clients
are NOT covered. NAMES_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / 'main/tailnet_names.c').read_text(encoding='utf-8')
core = core.split('/* --- names core (begin) --- */', 1)[1].split('/* --- names core (end) --- */', 1)[0]


def query(name, qtype=1, qclass=1, flags=0x0100, qd=1, an=0, extra=b''):
    labels = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.') if p) + b'\0'
    return struct.pack('>HHHHHH', 0x1234, flags, qd, an, 0, 0) + labels + struct.pack('>HH', qtype, qclass) + extra


CASES = []


def case(label, packet, expect, cap=512):
    """expect: None = forward (0), 'nx' = NXDOMAIN, 'nodata', or an IPv4 string."""
    CASES.append((label, packet, expect, cap))


case('short name', query('nas'), '100.64.0.7')
case('short name, upper case', query('NaS'), '100.64.0.7')
case('full name', query('nas.tail1234.ts.net'), '100.64.0.7')
case('full name, mixed case', query('Laptop.TAIL1234.ts.NET'), '100.101.102.103')
case('headscale base domain', query('pi.user.example.org'), '100.64.9.9')
case('headscale short name', query('pi'), '100.64.9.9')
case('ANY', query('nas', qtype=255), '100.64.0.7')
case('AAAA for a peer: no data, not forwarded', query('nas', qtype=28), 'nodata')
case('MX for a peer: no data', query('nas.tail1234.ts.net', qtype=15), 'nodata')
case('unknown name inside the tailnet', query('ghost.tail1234.ts.net'), 'nx')
case('unknown name in the other domain', query('ghost.user.example.org'), 'nx')
case('unknown name, AAAA, inside the tailnet', query('ghost.tail1234.ts.net', qtype=28), 'nx')
case('unknown short name: forwarded', query('printer'), None)
case('public name: forwarded', query('www.example.com'), None)
case('one dot: forwarded', query('nas.lan'), None)
case('domain itself: forwarded', query('tail1234.ts.net'), None)
case('suffix look-alike: forwarded', query('nas.xtail1234.ts.net'), None)
case('peer without an address is not answered', query('ghostpeer'), None)
case('class CH: forwarded', query('nas', qclass=3), None)
case('response, not a query', query('nas', flags=0x8100), None)
case('other opcode', query('nas', flags=0x2800), None)
case('two questions', query('nas', qd=2), None)
case('answer count set', query('nas', an=1), None)
case('compression in the question', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\xc0\x0c' + b'\0\x01\0\x01', None)
case('label longer than 63', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\x40' + b'a' * 64 + b'\0\0\x01\0\x01', None)
case('truncated question', query('nas')[:-3], None)
case('label past the end', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\x09nas', None)
case('root name', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\0\0\x01\0\x01', None)
case('dot inside a label', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\x03n.s\0\0\x01\0\x01', None)
case('NUL inside a label', struct.pack('>HHHHHH', 1, 0x100, 1, 0, 0, 0) + b'\x03n\0s\0\0\x01\0\x01', None)
case('EDNS additional record kept out of the answer', query('nas', extra=b'\0\0\x29\x10\0\0\0\0\0\0\0'), '100.64.0.7')
case('header only', b'\x12\x34\x01\x00\0\x01\0\0\0\0\0\0', None)
case('output too small', query('nas'), None, cap=20)
long_name = '.'.join(['a' * 63] * 4)
case('255-byte name: forwarded', query(long_name[:253]), None)


def c_bytes(data):
    return '{' + ','.join(str(b) for b in data) + '}' if data else '{0}'


body = []
for i, (label, packet, expect, cap) in enumerate(CASES):
    exp = 0 if expect is None else 1 if expect == 'nx' else 2 if expect == 'nodata' else 3
    ip = bytes(int(x) for x in expect.split('.')) if exp == 3 else b'\0\0\0\0'
    body.append(f'    {{static const uint8_t q[] = {c_bytes(packet)}; check({i}, "{label}", q, {len(packet)}, {exp}, (const uint8_t[]){c_bytes(ip)}, {cap});}}')

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tailnet_names.h"
''' + core + r'''
static const struct {const char *fqdn; const char *ip;} PEERS[] = {
    {"nas.tail1234.ts.net", "\x64\x40\x00\x07"}, {"laptop.tail1234.ts.net.", "\x64\x65\x66\x67"},
    {"pi.user.example.org", "\x64\x40\x09\x09"}, {"ghostpeer.tail1234.ts.net", "\0\0\0\0"}};
static int calls;
static bool peer(void *ctx, int i, char fqdn[TN_NAME_MAX], uint32_t *ip){
    (void)ctx; calls++;
    if (i >= (int)(sizeof PEERS / sizeof PEERS[0])) return false;
    memset(fqdn, 'x', TN_NAME_MAX);                     /* the core must terminate it */
    strcpy(fqdn, PEERS[i].fqdn); memcpy(ip, PEERS[i].ip, 4); return true;
}
static void check(int n, const char *label, const uint8_t *q, int len, int expect, const uint8_t ip[4], int cap){
    uint8_t out[600]; memset(out, 0xAA, sizeof out);
    int r = tailnet_names_answer(q, len, out, cap, peer, NULL);
    if (expect == 0) {if (r != 0) {printf("case %d (%s): answered\n", n, label); exit(1);} return;}
    if (r <= 12 || r > cap) {printf("case %d (%s): length %d\n", n, label, r); exit(1);}
    assert(out[0] == q[0] && out[1] == q[1]);               /* same id */
    assert((out[2] & 0x80) && (out[2] & 0x04) && (out[2] & 0x01) == (q[2] & 0x01));
    assert(out[4] == 0 && out[5] == 1 && !out[8] && !out[9] && !out[10] && !out[11]);   /* no authority/additional */
    int qend = 12; while (q[qend]) qend += q[qend] + 1; qend += 5;
    assert(!memcmp(out + 12, q + 12, (size_t)(qend - 12)));  /* question echoed */
    if (expect == 1) {assert((out[3] & 0x0F) == 3 && out[7] == 0 && r == qend); return;}
    assert((out[3] & 0x0F) == 0);
    if (expect == 2) {assert(out[7] == 0 && r == qend); return;}
    assert(out[7] == 1 && r == qend + 16);
    const uint8_t rr[] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, TN_TTL, 0, 4};
    assert(!memcmp(out + qend, rr, sizeof rr) && !memcmp(out + qend + 12, ip, 4));
    assert(out[r] == 0xAA);                                 /* nothing written past the answer */
}
int main(void){
''' + '\n'.join(body) + r'''
    uint8_t out[64];
    static const uint8_t q[] = {0x12,0x34,1,0,0,1,0,0,0,0,0,0,3,'n','a','s',0,0,1,0,1};
    assert(tailnet_names_answer(NULL, 21, out, 64, peer, NULL) == 0 && tailnet_names_answer(q, 21, NULL, 64, peer, NULL) == 0);
    assert(tailnet_names_answer(q, 21, out, 64, NULL, NULL) == 0 && tailnet_names_answer(q, 600, out, 64, peer, NULL) == 0);
    calls = 0; static const uint8_t pub[] = {1,2,1,0,0,1,0,0,0,0,0,0,7,'e','x','a','m','p','l','e',3,'c','o','m',0,0,1,0,1};
    assert(tailnet_names_answer(pub, sizeof pub, out, 64, peer, NULL) == 0 && calls == 0);   /* one dot: no peer scan */
    printf("tailnet names: %d cases ok\n", CASECOUNT);
    return 0;
}
'''.replace('CASECOUNT', str(len(CASES)))


def main():
    with tempfile.TemporaryDirectory(prefix='names-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'names.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('names.exe' if os.name == 'nt' else 'names')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-overlength-strings', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('NAMES_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'names.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
