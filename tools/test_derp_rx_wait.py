"""DERP reader idle wait (actual MicroLink derp_rx_wait, 3.0.9) on the host.

A relayed packet used to wait up to a 10 ms sleep before it was read. Now
the idle reader waits on the socket: select() on the relay fd with a 20 ms
bound (the writer waits up to 200 ms for the reader to park on teardown);
no fd or a disconnected relay, and a failing select(), sleep instead of
spinning. The reader task calls it only when nothing was read.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'external/microlink/components/microlink/src/ml_derp.c').read_text(encoding='utf-8').replace('\r\n', '\n')
start = src.index('static void derp_rx_wait(microlink_t *ml)')
code = src[start:src.index('\n}\n', start) + 3]
rs = src.index('static bool derp_must_rest(bool worked, uint64_t now_ms, uint64_t *busy_since_ms)')
code = src[rs:src.index('\n}\n', rs) + 3] + code
task = src[src.index('void ml_derp_rx_task(void *arg) {'):]
task = task[:task.index('\n}\n')]
hdr = (ROOT / 'external/microlink/components/microlink/include/microlink_internal.h').read_text(encoding='utf-8')
assert '#define ML_TASK_DERP_TX_PRIO    ML_TASK_DATAPLANE_PRIO' in hdr and '#define ML_DERP_MAX_BUSY_MS     40' in hdr
assert 'if (derp_must_rest(got, ml_get_time_ms(), &rx_busy_since)) vTaskDelay(pdMS_TO_TICKS(10));' in task
assert 'derp_must_rest(tx_count == 32, ml_get_time_ms(), &tx_busy_since)' in src
assert 'if (!got) derp_rx_wait(ml);' in task and 'if (!got) vTaskDelay' not in task
assert '#define DERP_RX_IDLE_WAIT_US 20000' in src
teardown = src[src.index('for (int i = 0; i < 20 && !ml->derp.rx_parked; i++)'):][:120]
assert 'pdMS_TO_TICKS(10)' in teardown   # 20 x 10 ms = 200 ms > the 20 ms bound

PROGRAM = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#define DERP_RX_IDLE_WAIT_US 20000
#define ML_DERP_MAX_BUSY_MS 40
#define pdMS_TO_TICKS(ms) (ms)
typedef struct { unsigned bits; } fd_set;
#define FD_ZERO(s) ((s)->bits = 0)
#define FD_SET(fd, s) ((s)->bits |= 1u << (fd))
struct timeval { long tv_sec, tv_usec; };
typedef struct { struct { int sockfd; bool connected; } derp; } microlink_t;
static int delays, delay_ms, selects, sel_nfds, sel_bits, sel_us, sel_rc;
static void vTaskDelay(int ms) { delays++; delay_ms = ms; }
static int ml_select_fds(int nfds, fd_set *rd, fd_set *wr, fd_set *ex, struct timeval *tv) {
    (void)wr; (void)ex; selects++; sel_nfds = nfds; sel_bits = rd->bits; sel_us = (int)(tv->tv_sec * 1000000 + tv->tv_usec); return sel_rc; }
@@CODE@@
#define CHECK(c) do { if (!(c)) { printf("FAIL %d\n", __LINE__); return 1; } } while (0)
int main(void) {
    microlink_t ml = { .derp = { .sockfd = 7, .connected = true } };
    sel_rc = 0; derp_rx_wait(&ml);                       /* timeout: no data */
    CHECK(selects == 1 && delays == 0 && sel_nfds == 8 && sel_bits == (1 << 7) && sel_us == 20000);
    sel_rc = 1; derp_rx_wait(&ml);                       /* data arrived: return at once */
    CHECK(selects == 2 && delays == 0);
    sel_rc = -1; derp_rx_wait(&ml);                      /* select failed: sleep, never spin */
    CHECK(selects == 3 && delays == 1 && delay_ms == 10);
    ml.derp.sockfd = -1; derp_rx_wait(&ml);
    CHECK(selects == 3 && delays == 2);
    ml.derp.sockfd = 7; ml.derp.connected = false; derp_rx_wait(&ml);
    CHECK(selects == 3 && delays == 3);
    /* rest policy: 40 ms of continuous work, then a rest; idle resets */
    uint64_t since = 0;
    CHECK(!derp_must_rest(true, 1000, &since) && since == 1000);
    CHECK(!derp_must_rest(true, 1039, &since));
    CHECK(derp_must_rest(true, 1040, &since) && since == 0);
    CHECK(!derp_must_rest(true, 1050, &since) && since == 1050);
    CHECK(!derp_must_rest(false, 1080, &since) && since == 0);
    CHECK(!derp_must_rest(true, 1085, &since) && !derp_must_rest(true, 1120, &since));
    CHECK(derp_must_rest(true, 1125, &since));
    CHECK(!derp_must_rest(true, 0, &since) && since == 1);   /* time 0 still opens a window */
    puts("derp rx wait ok");
    return 0;
}
'''

with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'w.c'
    c.write_text(PROGRAM.replace('@@CODE@@', code), encoding='utf-8')
    exe = Path(tmp) / ('w.exe' if os.name == 'nt' else 'w')
    subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True)
    assert out.returncode == 0 and 'derp rx wait ok' in out.stdout, (out.returncode, out.stdout)
print('derp rx wait: select on the relay fd (20 ms bound), sleep only without a socket or on select failure; data-plane priority with a 10 ms rest after 40 ms of continuous work')
