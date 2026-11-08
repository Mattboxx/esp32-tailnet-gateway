"""DERP frame reader (actual MicroLink poll_derp_read) on the host.

mbedtls_ssl_read() returns at most the rest of one TLS record, and DERP
servers do not align records with DERP frames, so a 5-byte frame header can
arrive in pieces. Until 3.0.7-beta.11 a split header dropped the relay
connection. Checked with a scripted TLS reader:
- a header split 2+3 and 1+1+1+1+1 (with WANT_READ / timeout gaps) is read
  and the frame dispatched with the right type, sender key and payload;
- RecvPacket payload is shifted in place (one allocation per frame);
- EOF or an error inside the header and a header that never completes (5 s)
  fail; oversized frames (> 64 KiB), allocation failure and a payload that
  stops arriving fail; empty frames dispatch with no payload;
- the pre-fix reader (partial header = error) fails the split cases.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'external/microlink/components/microlink/src/ml_derp.c').read_text(encoding='utf-8').replace('\r\n', '\n')
start = source.index('static int poll_derp_read(microlink_t *ml) {')
code = source[start:source.index('\n}\n', start) + 3]
assert 'memmove(buf, buf + 32, len - 32);' in code

PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define TAG "test"
#define MBEDTLS_ERR_SSL_WANT_READ  -0x6900
#define MBEDTLS_ERR_SSL_WANT_WRITE -0x6880
#define MBEDTLS_ERR_SSL_TIMEOUT    -0x6800
#define DERP_FRAME_RECV_PACKET 0x05
#define DERP_FRAME_KEEP_ALIVE  0x06
#define pdMS_TO_TICKS(ms) (ms)
typedef struct { int unused; } mbedtls_ssl_context;
typedef struct { struct { bool connected; int sockfd; mbedtls_ssl_context ssl; } derp; } microlink_t;
static uint64_t now_ms = 1000;
static uint64_t ml_get_time_ms(void) { return now_ms; }
/* The socket wait of a partial frame: a scripted socket has no fd, so model
 * the bounded wait as 20 ms of time passing. */
#define DERP_RX_IDLE_WAIT_US 20000
static int waits;
static int derp_wait_readable(microlink_t *ml, long us) { (void)ml; waits++; now_ms += (uint64_t)(us / 1000); return 0; }
static int fail_alloc, allocs;
static void *ml_psram_malloc(size_t n) { if (fail_alloc) return NULL; allocs++; return malloc(n); }

/* Scripted reader: each step is a chunk (the rest of one TLS record) or a code. */
typedef struct { const uint8_t *data; int len; int code; } step_t;
static step_t steps[64]; static int nsteps, pos; static size_t off;
static void script(int i, const uint8_t *d, int len, int code) { steps[i].data = d; steps[i].len = len; steps[i].code = code; nsteps = i + 1; }
static int mbedtls_ssl_read(mbedtls_ssl_context *s, unsigned char *out, size_t want) {
    (void)s;
    if (pos >= nsteps) { now_ms += 100; return MBEDTLS_ERR_SSL_TIMEOUT; }   /* recv timeout */
    step_t *st = &steps[pos];
    if (!st->data) { pos++; if (st->code == MBEDTLS_ERR_SSL_TIMEOUT) now_ms += 100; return st->code; }
    size_t left = (size_t)st->len - off, n = want < left ? want : left;
    memcpy(out, st->data + off, n); off += n;
    if (off == (size_t)st->len) { pos++; off = 0; }
    return (int)n;
}
static int dispatched; static uint8_t got_type, got_key[32]; static uint8_t got_payload[70000]; static size_t got_len; static bool got_null;
static void dispatch_derp_frame(microlink_t *ml, uint8_t type, uint8_t *key, uint8_t *payload, size_t len) {
    (void)ml; dispatched++; got_type = type; memcpy(got_key, key, 32); got_len = len; got_null = payload == NULL;
    if (payload) { memcpy(got_payload, payload, len); free(payload); }
}
static void reset(void) { nsteps = pos = 0; off = 0; dispatched = 0; got_len = 0; fail_alloc = 0; allocs = 0; }
'''

MAIN = r'''
static uint8_t frame[5 + 32 + 1400];
static size_t build(uint8_t type, uint32_t plen) {
    frame[0] = type; frame[1] = plen >> 24; frame[2] = plen >> 16; frame[3] = plen >> 8; frame[4] = plen;
    for (uint32_t i = 0; i < plen && i < sizeof frame - 5; i++) frame[5 + i] = (uint8_t)(i * 7 + 3);
    return 5 + plen;
}
static void check_recv(int r) {
    assert(r == 1 && dispatched == 1 && got_type == DERP_FRAME_RECV_PACKET && got_len == 1400);
    assert(memcmp(got_key, frame + 5, 32) == 0 && memcmp(got_payload, frame + 37, 1400) == 0);
}
int main(void) {
    microlink_t ml = { .derp = { .connected = true, .sockfd = 3 } };
    size_t n = build(DERP_FRAME_RECV_PACKET, 32 + 1400);

    /* whole frame in one record */
    reset(); script(0, frame, (int)n, 0);
    check_recv(poll_derp_read(&ml)); assert(allocs == 1);

    /* header split 2 + 3 across records */
    reset(); script(0, frame, 2, 0); script(1, frame + 2, (int)n - 2, 0);
    check_recv(poll_derp_read(&ml));

    /* header byte by byte with WANT_READ and timeout gaps */
    reset(); script(0, frame, 1, 0); script(1, NULL, 0, MBEDTLS_ERR_SSL_WANT_READ);
    script(2, frame + 1, 1, 0); script(3, NULL, 0, MBEDTLS_ERR_SSL_TIMEOUT);
    script(4, frame + 2, 1, 0); script(5, frame + 3, 1, 0); script(6, frame + 4, 1, 0);
    script(7, frame + 5, 500, 0); script(8, frame + 505, (int)n - 505, 0);
    check_recv(poll_derp_read(&ml));

    /* no data: 0, nothing dispatched */
    reset(); script(0, NULL, 0, MBEDTLS_ERR_SSL_TIMEOUT);
    assert(poll_derp_read(&ml) == 0 && dispatched == 0);

    /* the relay closes the session before a frame: an error (reconnect), not "no data" */
    reset(); script(0, NULL, 0, 0);
    assert(poll_derp_read(&ml) < 0 && dispatched == 0);

    /* EOF and error inside the header */
    reset(); script(0, frame, 3, 0); script(1, NULL, 0, 0);
    assert(poll_derp_read(&ml) < 0 && dispatched == 0);
    reset(); script(0, frame, 3, 0); script(1, NULL, 0, -0x7880);
    assert(poll_derp_read(&ml) == -0x7880 && dispatched == 0);

    /* header that never completes: bounded */
    reset(); script(0, frame, 4, 0);
    uint64_t t0 = now_ms; int w0 = waits;
    assert(poll_derp_read(&ml) < 0 && dispatched == 0);
    assert(now_ms - t0 > 5000 && now_ms - t0 < 5300);
    assert(waits - w0 >= 20 && waits - w0 <= 260);   /* bounded socket waits, not a spin */

    /* empty frame: dispatched without payload */
    reset(); build(DERP_FRAME_KEEP_ALIVE, 0); script(0, frame, 5, 0);
    assert(poll_derp_read(&ml) == 1 && dispatched == 1 && got_null && got_len == 0 && allocs == 0);

    /* oversized frame, header split: refused */
    reset(); build(DERP_FRAME_RECV_PACKET, 65537); script(0, frame, 1, 0); script(1, frame + 1, 4, 0);
    assert(poll_derp_read(&ml) == -1 && dispatched == 0);

    /* allocation failure */
    reset(); n = build(DERP_FRAME_RECV_PACKET, 32 + 1400); fail_alloc = 1; script(0, frame, (int)n, 0);
    assert(poll_derp_read(&ml) == -1 && dispatched == 0);

    /* payload stops arriving: bounded */
    reset(); script(0, frame, 200, 0);
    assert(poll_derp_read(&ml) == -1 && dispatched == 0);

    /* RecvPacket of exactly 32 bytes keeps the previous behaviour */
    reset(); n = build(DERP_FRAME_RECV_PACKET, 32); script(0, frame, (int)n, 0);
    assert(poll_derp_read(&ml) == 1 && got_len == 32);

    /* disconnected relay */
    ml.derp.connected = false; reset();
    assert(poll_derp_read(&ml) == -1);
    puts("derp frame read ok");
    return 0;
}
'''


def run(body):
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'derp.c'
        c.write_text(PREFIX + body + MAIN, encoding='utf-8')
        exe = Path(tmp) / ('derp.exe' if os.name == 'nt' else 'derp')
        extra = [] if os.name == 'nt' else ['-fsanitize=address,undefined']
        subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', *extra, str(c), '-o', str(exe)], check=True)
        return subprocess.run([str(exe)], capture_output=True, text=True)


ok = run(code)
assert ok.returncode == 0 and 'derp frame read ok' in ok.stdout, (ok.stdout, ok.stderr)

old = code[:code.index('    /* mbedtls_ssl_read() never crosses')] + '''    if (n < 5) return -1;
''' + code[code.index('    uint8_t frame_type = header[0];'):]
mutant = run(old)
assert mutant.returncode != 0, 'pre-fix reader must fail the split-header cases'
print('derp frame read: split headers kept, limits enforced, pre-fix reader rejected')
