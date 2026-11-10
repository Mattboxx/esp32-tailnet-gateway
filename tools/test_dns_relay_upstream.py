"""AP DNS relay upstream answers (actual dns_relay.c helpers) on the host.

Until 3.0.7-beta.11 a worker took the first datagram on its upstream socket
as the answer: a late answer to an earlier, timed-out query (or a forged
datagram from any host able to reach the port) was sent to the client and
cached under the new question. Checked with a scripted recvfrom():
- the matching answer from the server is accepted;
- other source address or port, other ID, a query (QR=0), other opcode,
  other question, QDCOUNT != 1, a short datagram: discarded, the right
  answer after them still accepted; ASCII case differences accepted;
- at most DNS_RELAY_MAX_STRAY strays per query, then no answer (bounded);
- timeout -> 0, socket error -> -1;
- dns_resp_ttl: short responses not cached, names ending in a compression
  pointer after labels parsed, min TTL clamped; every byte access bounds-
  checked over 200,000 random mutations;
- the worker sends a random ID upstream and restores the client's ID.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'components/dns_relay/dns_relay.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}\n', start) + 3]


worker = function('static void worker_task(void *arg)')
assert 'uint32_t up_id = esp_random();' in worker and 'rbuf[0] = client_id[0];' in worker
assert 'upstream_recv(up, rbuf, w->q, w->qlen, &up_addr)' in worker
assert 'recvfrom(up, rbuf, DNS_RELAY_BUF_SIZE, 0, NULL, NULL)' not in source

helpers = (function('static int dns_question_len(') + function('static uint32_t dns_resp_ttl(')
           + function('static bool dns_reply_matches(') + function('static int upstream_recv('))
checked = re.sub(r'\bp\[([^\]]+)\]', r'AT(\1)', helpers)
cache_decl = source.split('/* ---- SPIRAM direct-mapped response cache ---- */', 1)[1].split('static atomic_uint s_cache_epoch;', 1)[0]
cache_helpers = cache_decl + function('static uint32_t fnv1a(') + function('static bool cache_get(') + function('static void cache_put(')

PROGRAM = r'''
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DNS_RELAY_BUF_SIZE 1024
#define DNS_CACHE_KEY_MAX 256
#define DNS_CACHE_ENTRIES 4
#define DNS_CACHE_TTL_NEG_S 30
#define DNS_CACHE_TTL_MIN_S 10
#define DNS_CACHE_TTL_MAX_S 3600
#define DNS_RELAY_MAX_STRAY 8
#ifndef EWOULDBLOCK
#define EWOULDBLOCK EAGAIN
#endif
typedef unsigned socklen_t;
struct in_addr_ { uint32_t s_addr; };
struct sockaddr { int x; };
struct sockaddr_in { uint16_t sin_family; uint16_t sin_port; struct in_addr_ sin_addr; };
static volatile uint32_t st_stray;
static size_t cur_len; static const uint8_t *cur_p;
static uint8_t at_(const uint8_t *p, int i) {
    if (p == cur_p && (i < 0 || (size_t)i >= cur_len)) { printf("OOB %d of %u\n", i, (unsigned)cur_len); exit(3); }
    return p[i];
}
#define AT(i) at_(p, (int)(i))
/* scripted upstream socket */
typedef struct { uint8_t d[600]; int len; uint32_t ip; uint16_t port; int err; } dgram_t;
static dgram_t script[32]; static int nscript, spos;
static int recvfrom(int s, void *buf, size_t cap, int fl, struct sockaddr *from, socklen_t *fl_) {
    (void)s; (void)fl; (void)fl_;
    if (spos >= nscript) { errno = EAGAIN; return -1; }
    dgram_t *d = &script[spos++];
    if (d->err) { errno = d->err; return -1; }
    struct sockaddr_in *f = (struct sockaddr_in *)from; f->sin_addr.s_addr = d->ip; f->sin_port = d->port;
    int n = d->len < (int)cap ? d->len : (int)cap; memcpy(buf, d->d, n); return n;
}
@@HELPERS@@
typedef void *SemaphoreHandle_t;
#define portMAX_DELAY 0
#define xSemaphoreTake(mutex, ticks) ((void)(mutex), (void)(ticks))
#define xSemaphoreGive(mutex) ((void)(mutex))
static int64_t esp_timer_get_time(void) { return 1000000; }
static uint32_t st_inserts, st_evictions;
@@CACHE@@
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d\n", __LINE__); return 1; } } while (0)
static uint8_t q[64]; static int qlen;
static uint8_t r[600]; static int rlen;
static void build_q(uint16_t id, const char *name) {
    q[0] = id >> 8; q[1] = id; q[2] = 0x01; q[3] = 0; q[4] = 0; q[5] = 1; memset(q + 6, 0, 6); qlen = 12;
    const char *s = name;
    while (*s) { const char *dot = strchr(s, '.'); int l = dot ? (int)(dot - s) : (int)strlen(s);
        q[qlen++] = (uint8_t)l; memcpy(q + qlen, s, l); qlen += l; s += l; if (*s) s++; }
    q[qlen++] = 0; q[qlen++] = 0; q[qlen++] = 1; q[qlen++] = 0; q[qlen++] = 1;
}
static void build_r(uint32_t ttl) {           /* answer to q: one A record via pointer */
    memcpy(r, q, qlen); r[2] = 0x81; r[3] = 0x80; r[7] = 1; rlen = qlen;
    uint8_t rr[] = {0xC0, 0x0C, 0, 1, 0, 1, ttl >> 24, ttl >> 16, ttl >> 8, ttl, 0, 4, 192, 0, 2, 1};
    memcpy(r + rlen, rr, sizeof rr); rlen += sizeof rr;
}
static void add(const uint8_t *d, int len, uint32_t ip, uint16_t port) {
    dgram_t *g = &script[nscript++]; memcpy(g->d, d, len); g->len = len; g->ip = ip; g->port = port; g->err = 0;
}
static int recv_now(uint8_t *buf) { struct sockaddr_in srv = {2, 53, {0x0101A8C0}}; return upstream_recv(1, buf, q, qlen, &srv); }
int main(void) {
    uint8_t buf[DNS_RELAY_BUF_SIZE];
    const uint32_t SRV = 0x0101A8C0; const uint16_t P53 = 53;
    build_q(0xBEEF, "www.example.com"); build_r(300);
    dns_cache_entry_t entries[DNS_CACHE_ENTRIES] = {0};
    s_cache = entries;
    s_cache_mtx = entries;
    int key_len = qlen - 12, cached_len = 0;
    cache_put(q, key_len, SRV, 1, r, rlen, 300);
    CHECK(cache_get(q, key_len, SRV, 1, buf, &cached_len) && cached_len == rlen);
    CHECK(!cache_get(q, key_len, SRV + 1, 1, buf, &cached_len));
    CHECK(!cache_get(q, key_len, SRV, 2, buf, &cached_len));

    nscript = spos = 0; add(r, rlen, SRV, P53);
    CHECK(recv_now(buf) == rlen && memcmp(buf, r, rlen) == 0);

    /* strays first, then the answer */
    uint8_t bad[600]; st_stray = 0; nscript = spos = 0;
    add(r, rlen, 0x0201A8C0, P53);                                   /* other host */
    add(r, rlen, SRV, 5353);                                         /* other port */
    memcpy(bad, r, rlen); bad[1] ^= 1; add(bad, rlen, SRV, P53);     /* other ID (late answer) */
    memcpy(bad, r, rlen); bad[2] &= 0x7F; add(bad, rlen, SRV, P53);  /* not a response */
    memcpy(bad, r, rlen); bad[2] |= 0x10; add(bad, rlen, SRV, P53);  /* other opcode */
    memcpy(bad, r, rlen); bad[14] = 'x'; add(bad, rlen, SRV, P53);   /* other question */
    memcpy(bad, r, rlen); bad[5] = 2; add(bad, rlen, SRV, P53);      /* QDCOUNT 2 */
    add(r, 11, SRV, P53);                                            /* short */
    add(r, 20, SRV, P53);                                            /* question truncated */
    CHECK(recv_now(buf) == 0 && st_stray == 9);                      /* bounded: 9 strays, no answer */
    st_stray = 0; spos = 1;                                          /* from the 2nd stray: 8 strays then answer */
    script[9] = script[0]; script[9].ip = SRV; nscript = 10;
    CHECK(recv_now(buf) == rlen && st_stray == 8);

    /* 0x20 case randomisation by the resolver */
    nscript = spos = 0; memcpy(bad, r, rlen); bad[13] = 'W'; bad[18] = 'X'; add(bad, rlen, SRV, P53);
    CHECK(recv_now(buf) == rlen);

    /* timeout and socket error */
    nscript = spos = 0; CHECK(recv_now(buf) == 0);
    nscript = 1; spos = 0; script[0].err = EBADF; CHECK(recv_now(buf) == -1); script[0].err = 0;

    /* TTL parsing */
    int ql = dns_question_len(q, qlen); CHECK(ql == qlen - 12);
    cur_p = r; cur_len = rlen;
    CHECK(dns_resp_ttl(r, rlen, ql) == 300);
    build_r(2); CHECK(dns_resp_ttl(r, rlen, ql) == DNS_CACHE_TTL_MIN_S);
    build_r(999999); CHECK(dns_resp_ttl(r, rlen, ql) == DNS_CACHE_TTL_MAX_S);
    cur_len = 11; CHECK(dns_resp_ttl(r, 11, ql) == 0);
    /* answer name "a" + pointer: labels then compression */
    build_r(300); { int at = qlen; uint8_t nm[] = {1, 'a', 0xC0, 0x0C}; memmove(r + at + 4, r + at + 2, rlen - at - 2);
        memcpy(r + at, nm, 4); rlen += 2; }
    cur_len = rlen; CHECK(dns_resp_ttl(r, rlen, ql) == 300);

    /* random mutations: no out-of-bounds access */
    build_r(300); uint8_t base[600]; int blen = rlen; memcpy(base, r, rlen);
    uint32_t seed = 0xD15EA5E;
    for (int it = 0; it < 200000; it++) {
        memcpy(r, base, blen); rlen = blen;
        for (int j = 0; j < 1 + it % 4; j++) { seed = seed * 1664525u + 1013904223u; r[12 + (seed >> 8) % (blen - 12)] = (uint8_t)(seed >> 2); }
        seed = seed * 1664525u + 1013904223u; int len = (seed & 1) ? blen : (int)(seed >> 8) % (blen + 1);
        uint8_t *heap = malloc(len ? len : 1); memcpy(heap, r, len);
        cur_p = heap; cur_len = (size_t)len;
        (void)dns_resp_ttl(heap, len, ql);
        (void)dns_reply_matches(heap, len, q, qlen);
        (void)dns_question_len(heap, len);
        free(heap);
    }
    puts("dns relay upstream ok");
    return 0;
}
'''


def run(code):
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'relay.c'
        c.write_text(PROGRAM.replace('@@HELPERS@@', code).replace('@@CACHE@@', cache_helpers), encoding='utf-8')
        exe = Path(tmp) / ('relay.exe' if os.name == 'nt' else 'relay')
        subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-unused-variable', str(c), '-o', str(exe)], check=True)
        return subprocess.run([str(exe)], capture_output=True, text=True)


ok = run(checked)
assert ok.returncode == 0 and 'dns relay upstream ok' in ok.stdout, (ok.returncode, ok.stdout, ok.stderr)
# The pre-fix behaviour: the first datagram is the answer.
mutant = checked.replace('dns_reply_matches(rbuf, rlen, q, qlen))', 'true)').replace(
    'from.sin_addr.s_addr == server->sin_addr.s_addr && from.sin_port == server->sin_port &&', '')
assert mutant != checked
bad = run(mutant)
assert bad.returncode != 0, 'accepting the first datagram must fail'
print('dns relay upstream: only matching answers accepted, bounded, TTL parser in bounds')
