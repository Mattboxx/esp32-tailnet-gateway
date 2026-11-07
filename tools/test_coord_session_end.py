"""The control server ending the map session is a transport loss, not a
revocation (3.0.7-beta.9): actual MicroLink poll_map_update() on the host.

Frames are built byte by byte (HTTP/2 frame header + Tailscale's 4-byte
little-endian length prefix) and fed through a noise_recv() fixture:
- END_STREAM with a final complete message: the message is applied first,
  the session ends (-1) and the policy is NOT reset (the caller's close
  suspends it; the control-loss mode decides);
- GOAWAY and RST_STREAM on the map stream: session ends, no reset;
- an unauthorised map, an out-of-frame length, unparseable JSON, an oversized
  HTTP/2 frame, and END_STREAM carrying an unauthorised map: reset (fail
  closed);
- a normal message: applied, session continues, no reset;
- the reconnect timing summary (note_reconnected): per-stage durations in
  order, stages not reached skipped, total, published once.
cJSON is the pinned SDK copy (CJSON_SOURCE) or libcjson.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'external/microlink/components/microlink/src/ml_coord.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def function(signature):
    """The definition (not a forward declaration) up to its closing brace."""
    start = 0
    while True:
        start = source.index(signature, start)
        head_end = source.index(')', start)
        if source[head_end + 1:head_end + 4].lstrip(' ').startswith(('{', '\n{')):
            break
        start = head_end
    return source[start:source.index('\n}\n', start) + 3]


code = '\n'.join(function(s) for s in ('static void note_ctrl_loss(', 'static void note_reconnected(',
                                       'static void note_poll_close(', 'static bool lp_acc_append(',
                                       'static int poll_map_update('))
assert 'if (malformed || !session_end) ml_policy_reset();' in code

PROGRAM = r'''
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define TAG "test"
#define ML_JSON_BUFFER_SIZE 4096
#define ML_H2_MAX_FRAME_LEN 16384
#define SOL_SOCKET 1
#define SO_RCVTIMEO 2
/* Own names: glibc's headers may already declare fd_set and timeval. */
#define fd_set test_fd_set
#define timeval test_timeval
#undef FD_ZERO
#undef FD_SET
typedef struct { int set; } fd_set;
#define FD_ZERO(s) ((s)->set = 0)
#define FD_SET(fd, s) ((s)->set = 1)
struct timeval { long tv_sec, tv_usec; };
typedef long ssize_t_;
static size_t strlcpy_(char *d, const char *s, size_t n) { size_t l = strlen(s); if (n) { size_t c = l < n - 1 ? l : n - 1; memcpy(d, s, c); d[c] = 0; } return l; }
#define strlcpy strlcpy_
typedef struct {
    bool use_tls; void *coord_tls; int coord_sock;
    uint8_t *h2_acc; size_t h2_acc_len; uint8_t *lp_acc; size_t lp_acc_len;
    uint64_t ctrl_stream_rx_ms; bool netinfo_dirty;
    const char *ctrl_close_detail; int32_t ctrl_close_code, ctrl_loss_code;
    const char *ctrl_loss_reason; const char *ctrl_retry_reason; uint32_t ctrl_retry_failures, ctrl_loss_count;
    uint64_t rt_loss_ms, rt_backoff_ms, rt_tcp_ms, rt_noise_ms, rt_register_ms, rt_fetch_ms, rt_stream_ms, rt_derp_ms;
    uint32_t ctrl_last_reconnect_ms; char ctrl_reconnect_stages[112];
} microlink_t;
typedef struct { int unused; } ml_noise_state_t;
static uint64_t now_ms = 1000;
static uint64_t ml_get_time_ms(void) { return now_ms; }
static int resets, applied, apply_ok = 1;
static void ml_policy_reset(void) { resets++; }
static void log_alloc_failure(const char *w, size_t n) { (void)w; (void)n; }
static void *ml_psram_malloc(size_t n) { return malloc(n); }
static long esp_tls_get_bytes_avail(void *t) { (void)t; return 0; }
static int ml_conn_sockfd(microlink_t *ml) { return ml->coord_sock; }
static int ml_select_fds(int n, fd_set *r, void *w, void *e, struct timeval *tv) { (void)n; (void)r; (void)w; (void)e; (void)tv; return 1; }
static int ml_setsockopt(int fd, int l, int o, const void *v, unsigned n) { (void)fd; (void)l; (void)o; (void)v; (void)n; return 0; }
static uint8_t wire[70000]; static int wire_len;
static int noise_recv(microlink_t *ml, ml_noise_state_t *n, uint8_t *out, int cap) {
    (void)ml; (void)n; assert(wire_len <= cap); memcpy(out, wire, wire_len); int r = wire_len; wire_len = 0; return r;
}
static int noise_send(microlink_t *ml, ml_noise_state_t *n, const uint8_t *d, int len) { (void)ml; (void)n; (void)d; return len; }
static int ml_h2_build_window_update(uint8_t *b, size_t n, uint32_t s, uint32_t inc) { (void)b; (void)n; (void)s; (void)inc; return 13; }
static bool apply_long_poll_map(microlink_t *ml, cJSON *m) { (void)ml; assert(m); applied++; return apply_ok; }
static void do_send_endpoint_update(microlink_t *ml, ml_noise_state_t *n) { (void)ml; (void)n; }
''' + code + r'''
static void frame(uint8_t type, uint8_t flags, uint32_t stream, const void *payload, uint32_t len) {
    uint8_t *f = wire + wire_len;
    f[0] = len >> 16; f[1] = len >> 8; f[2] = len; f[3] = type; f[4] = flags;
    f[5] = stream >> 24; f[6] = stream >> 16; f[7] = stream >> 8; f[8] = stream;
    memcpy(f + 9, payload, len); wire_len += 9 + len;
}
static void message(uint8_t flags, const char *json) {
    uint8_t buf[512]; uint32_t n = (uint32_t)strlen(json);
    buf[0] = n; buf[1] = n >> 8; buf[2] = n >> 16; buf[3] = n >> 24; memcpy(buf + 4, json, n);
    frame(0x00, flags, 5, buf, n + 4);
}
static microlink_t ml;
static int poll(void) { ml_noise_state_t noise = {0}; return poll_map_update(&ml, &noise); }
static void fresh(void) { free(ml.lp_acc); free(ml.h2_acc); memset(&ml, 0, sizeof ml); ml.coord_sock = 3; resets = applied = 0; apply_ok = 1; wire_len = 0; }
int main(void) {
    /* Normal message: applied, session continues. */
    fresh(); message(0, "{\"PeersChanged\":[]}");
    assert(poll() == 1 && applied == 1 && resets == 0);
    /* END_STREAM with a final message: applied first, session ends, policy kept. */
    fresh(); message(0x01, "{\"PeersChanged\":[]}");
    assert(poll() == -1 && applied == 1 && resets == 0);
    assert(!strcmp(ml.ctrl_close_detail, "control server ended the map session"));
    /* END_STREAM alone (empty DATA): no reset. */
    fresh(); frame(0x00, 0x01, 5, "", 0);
    assert(poll() == -1 && resets == 0);
    /* GOAWAY and RST_STREAM: no reset, codes recorded. */
    fresh(); { uint8_t g[8] = {0, 0, 0, 5, 0, 0, 0, 2}; frame(0x07, 0, 0, g, 8); }
    assert(poll() == -1 && resets == 0 && !strcmp(ml.ctrl_close_detail, "control server sent GOAWAY") && ml.ctrl_close_code == 2);
    fresh(); { uint8_t r[4] = {0, 0, 0, 8}; frame(0x03, 0, 5, r, 4); }
    assert(poll() == -1 && resets == 0 && !strcmp(ml.ctrl_close_detail, "control server reset the map stream") && ml.ctrl_close_code == 8);
    /* Malformed or unauthorised data: fail closed. */
    fresh(); apply_ok = 0; message(0, "{\"PeersChanged\":[]}");
    assert(poll() == -1 && resets == 1);
    fresh(); apply_ok = 0; message(0x01, "{\"PeersChanged\":[]}");      /* END_STREAM does not excuse it */
    assert(poll() == -1 && resets == 1 && applied == 1);
    fresh(); { uint8_t z[8] = {0, 0, 0, 0, 'x', 'y', 'z', 'w'}; frame(0x00, 0, 5, z, 8); }   /* size 0: out of frame */
    assert(poll() == -1 && resets >= 1 && !strcmp(ml.ctrl_close_detail, "map stream out of frame"));
    fresh(); message(0, "{not json");
    assert(poll() == -1 && resets >= 1 && applied == 0);
    fresh(); { uint8_t h[9] = {0x00, 0x50, 0x00, 0x00, 0, 0, 0, 0, 5}; memcpy(wire, h, 9); wire_len = 9; }  /* 20 KB frame */
    assert(poll() == -1 && resets == 1);
    /* Reconnect timing summary. */
    fresh(); now_ms = 50000; note_ctrl_loss(&ml, "control server ended the map session");
    assert(ml.rt_loss_ms == 50000);
    ml.rt_backoff_ms = 51000; ml.rt_tcp_ms = 51400; ml.rt_noise_ms = 51600; ml.rt_register_ms = 51800;
    ml.rt_fetch_ms = 111800; ml.rt_stream_ms = 0; ml.rt_derp_ms = 0;
    note_reconnected(&ml, 112000);
    assert(ml.ctrl_last_reconnect_ms == 62000 && ml.rt_loss_ms == 0);
    assert(!strcmp(ml.ctrl_reconnect_stages, "backoff 1000, tcp+tls 400, noise 200, register 200, map 60000"));
    note_reconnected(&ml, 113000);                                  /* only once per loss */
    assert(ml.ctrl_last_reconnect_ms == 62000);
    fresh();
    puts("PASS: server END_STREAM/GOAWAY/RST_STREAM end the map session without revoking the policy (final message "
         "applied first); unauthorised, out-of-frame, unparseable and oversized data still revoke; normal messages "
         "continue; reconnect stage summary and total recorded once (host, actual poll_map_update)");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='coord-session-end-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-parameter',
                 '-Wno-unused-variable', '-Wno-unused-but-set-variable']
        libs = []
        dep = os.environ.get('CJSON_SOURCE', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/json/cJSON/cJSON.c'))
        if Path(dep).exists():
            flags += ['-I', str(Path(dep).parent), dep]
        else:
            flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
            libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
        if os.environ.get('POLICY_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe), *libs], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
