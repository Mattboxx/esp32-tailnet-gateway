"""DERP reader waits (actual MicroLink ml_derp.c, 3.0.11) on the host.

A relayed packet used to wait up to a 10 ms sleep before it was read; the
idle reader now waits on the socket (select, 20 ms bound). 3.0.10 (never
published) spun at data-plane priority when the relay closed the session:
a closed socket is always "readable", the 0-byte read was taken as "no
data", and nothing slept. Checked here:
- derp_wait_readable: select on the relay fd with the bound; no socket or a
  failing select sleeps a tick instead;
- the reader loop (actual statements of ml_derp_rx_task, driven by a scripted
  socket): a readable socket that yields nothing sleeps a tick on the next
  pass, so it cannot spin; data resets the guard;
- poll_derp_read: a 0-byte read (session closed) is an error, so the writer
  reconnects at once instead of after the 90 s silence watchdog;
- the partial header/payload waits use the socket wait (5 ms is 0 ticks);
- rest policy: 10 ms after 40 ms of continuous work; data-plane priority.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'external/microlink/components/microlink/src/ml_derp.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def body(sig):
    s = src.index(sig)
    return src[s:src.index('\n}\n', s) + 3]


wait = body('static int derp_wait_readable(microlink_t *ml, long us)')
rest = body('static bool derp_must_rest(bool worked, uint64_t now_ms, uint64_t *busy_since_ms)')
task = body('void ml_derp_rx_task(void *arg) {')
poll = body('static int poll_derp_read(microlink_t *ml) {')
hdr = (ROOT / 'external/microlink/components/microlink/include/microlink_internal.h').read_text(encoding='utf-8')
assert '#define ML_TASK_DERP_TX_PRIO    ML_TASK_DATAPLANE_PRIO' in hdr and '#define ML_DERP_MAX_BUSY_MS     40' in hdr
assert '#define DERP_RX_IDLE_WAIT_US 20000' in src
assert 'pdMS_TO_TICKS(5)' not in poll, 'a 5 ms wait is 0 ticks at 100 Hz'
assert poll.count('derp_wait_readable(ml, DERP_RX_IDLE_WAIT_US);') == 2
assert 'if (n == 0) {' in poll and 'return n < 0 ? n : -1;   /* 0 = the relay closed the session */' in poll
assert 'derp_must_rest(tx_count == 32, ml_get_time_ms(), &tx_busy_since)' in src
teardown = src[src.index('for (int i = 0; i < 20 && !ml->derp.rx_parked; i++)'):][:120]
assert 'pdMS_TO_TICKS(10)' in teardown   # 20 x 10 ms = 200 ms > the 20 ms bound

# The loop body of ml_derp_rx_task, run as a function of one pass.
loop = task[task.index('    while (!(xEventGroupGetBits'):]
loop_body = loop[loop.index('{') + 1:loop.rindex('    ESP_LOGI(TAG, "DERP RX task exiting");')]
loop_body = loop_body[:loop_body.rindex('}')]
assert 'readable_idle' in loop_body

PROGRAM = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define DERP_RX_IDLE_WAIT_US 20000
#define ML_DERP_MAX_BUSY_MS 40
#define ML_EVT_DERP_RECONNECT 1
#define pdMS_TO_TICKS(ms) (ms)
#define ESP_LOGW(...) ((void)0)
#define TAG "t"
typedef struct { unsigned bits; } fd_set;
#define FD_ZERO(s) ((s)->bits = 0)
#define FD_SET(fd, s) ((s)->bits |= 1u << (fd))
struct timeval { long tv_sec, tv_usec; };
typedef struct { struct { int sockfd; bool connected; bool rx_parked; uint64_t last_recv_ms; } derp; int events; } microlink_t;
static int delays, delay_ms, selects, sel_nfds, sel_bits, sel_us, sel_rc, reconnects;
static uint64_t now_ms = 1000;
static uint32_t s_derp_frames_rx;
static void vTaskDelay(int ms) { delays++; delay_ms = ms; now_ms += (uint64_t)ms; }
static uint64_t ml_get_time_ms(void) { return now_ms; }
static void xEventGroupSetBits(int ev, int bits) { (void)ev; (void)bits; reconnects++; }
static int ml_select_fds(int nfds, fd_set *rd, fd_set *wr, fd_set *ex, struct timeval *tv) {
    (void)wr; (void)ex; selects++; sel_nfds = nfds; sel_bits = rd->bits; sel_us = (int)(tv->tv_sec * 1000000 + tv->tv_usec); return sel_rc; }
static int poll_rc[64], poll_n, poll_i;
static int poll_derp_read(microlink_t *ml) { (void)ml; return poll_i < poll_n ? poll_rc[poll_i++] : 0; }
@@REST@@
@@WAIT@@
static void one_pass(microlink_t *ml, uint64_t *rx_busy_since_p, bool *readable_idle_p) {
    uint64_t rx_busy_since = *rx_busy_since_p; bool readable_idle = *readable_idle_p;
    do {   /* one pass of the task's while loop; its continue ends the pass */
@@LOOP@@
    } while (0);
    *rx_busy_since_p = rx_busy_since; *readable_idle_p = readable_idle;
}
#define CHECK(c) do { if (!(c)) { printf("FAIL %d\n", __LINE__); return 1; } } while (0)
int main(void) {
    microlink_t ml = { .derp = { .sockfd = 7, .connected = true } };
    sel_rc = 0; CHECK(derp_wait_readable(&ml, DERP_RX_IDLE_WAIT_US) == 0);
    CHECK(selects == 1 && delays == 0 && sel_nfds == 8 && sel_bits == (1 << 7) && sel_us == 20000);
    sel_rc = -1; CHECK(derp_wait_readable(&ml, 20000) == -1 && delays == 1 && delay_ms == 10);
    ml.derp.sockfd = -1; CHECK(derp_wait_readable(&ml, 20000) == -1 && selects == 2 && delays == 2);
    ml.derp.sockfd = 7;

    /* a socket that stays readable and yields nothing: every second pass sleeps */
    uint64_t since = 0; bool ri = false;
    selects = delays = 0; sel_rc = 1; poll_n = 0;
    for (int i = 0; i < 100; i++) one_pass(&ml, &since, &ri);
    CHECK(delays == 50 && selects == 50);
    /* data arrives: read, guard reset; then idle with nothing readable: select only */
    poll_rc[0] = 1; poll_rc[1] = 1; poll_rc[2] = 0; poll_n = 3; poll_i = 0;
    selects = delays = 0; sel_rc = 0; ri = true;
    one_pass(&ml, &since, &ri);
    CHECK(s_derp_frames_rx == 2 && !ri && delays == 0 && selects == 0);
    one_pass(&ml, &since, &ri);
    CHECK(selects == 1 && delays == 0 && !ri);
    /* read error: reconnect requested, connection marked down */
    poll_rc[0] = -1; poll_n = 1; poll_i = 0;
    one_pass(&ml, &since, &ri);
    CHECK(reconnects == 1 && !ml.derp.connected);

    /* rest policy */
    since = 0;
    CHECK(!derp_must_rest(true, 1000, &since) && since == 1000);
    CHECK(!derp_must_rest(true, 1039, &since));
    CHECK(derp_must_rest(true, 1040, &since) && since == 0);
    CHECK(!derp_must_rest(false, 1080, &since) && since == 0);
    CHECK(!derp_must_rest(true, 0, &since) && since == 1);
    puts("derp rx wait ok");
    return 0;
}
'''

prog = PROGRAM.replace('@@REST@@', rest).replace('@@WAIT@@', wait).replace('@@LOOP@@', loop_body)
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'w.c'
    c.write_text(prog, encoding='utf-8')
    exe = Path(tmp) / ('w.exe' if os.name == 'nt' else 'w')
    subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', str(c), '-o', str(exe)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True)
    assert out.returncode == 0 and 'derp rx wait ok' in out.stdout, (out.returncode, out.stdout)
    # The 3.0.10 loop (no guard): a readable empty socket never sleeps.
    old = loop_body[:loop_body.index('        /* Idle: wait for bytes (bounded).')] + \
        '        if (!got) (void)derp_wait_readable(ml, DERP_RX_IDLE_WAIT_US);\n' + \
        loop_body[loop_body.index('        if (derp_must_rest(got'):]
    c.write_text(PROGRAM.replace('@@REST@@', rest).replace('@@WAIT@@', wait).replace('@@LOOP@@', old), encoding='utf-8')
    subprocess.run(['gcc', '-std=c11', '-O1', '-w', str(c), '-o', str(exe)], check=True)
    bad = subprocess.run([str(exe)], capture_output=True, text=True)
    assert bad.returncode != 0, 'the 3.0.10 spin must be detected'
print('derp rx wait: socket wait bounded; a readable empty socket cannot spin (3.0.10 spin detected); '
      'session close is an error; partial waits on the socket; rest policy; data-plane priority')
