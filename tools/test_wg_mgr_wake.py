"""WireGuard manager wake/rest policy (MicroLink ml_wg_mgr.c), host checks.

The actual wg_mgr_must_rest() is compiled and checked: it rests while frames
remain queued and after the busy budget, otherwise it may wait for the next
frame. A small simulation drives the same decision with synthetic work and
arrival patterns and shows that lower-priority tasks keep at least one 10 ms
rest per WG_MGR_MAX_BUSY_MS + one iteration of work (saturated, continuous
and bursty traffic), while an idle or lightly loaded manager waits for frames
instead of polling. Structural checks: every WG frame enqueued by net_io or
DERP RX gives wg_rx_wake, and the semaphore lives and dies with the queue.
These are host checks of the decision and wiring, not a FreeRTOS scheduler
or device timing test.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
mgr = (ML / 'src/ml_wg_mgr.c').read_text(encoding='utf-8')
net = (ML / 'src/ml_net_io.c').read_text(encoding='utf-8')
derp = (ML / 'src/ml_derp.c').read_text(encoding='utf-8')
life = (ML / 'src/microlink.c').read_text(encoding='utf-8')
internal = (ML / 'include/microlink_internal.h').read_text(encoding='utf-8').replace('\r\n', '\n')
lanes = re.search(r'static inline BaseType_t ml_wg_rx_enqueue.*?\n}\n.*?static inline BaseType_t ml_wg_rx_dequeue.*?\n}\n',
                  internal, re.S).group(0)

policy = re.search(r'#define WG_MGR_MAX_BUSY_MS.*?\n}\n', mgr, re.S).group(0)
PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
''' + policy + r'''
/* Simulated loop: each iteration does `work` ms; the manager then rests 10 ms
 * (others run) or waits until the next arrival (others run while it waits). */
static double others_share(int work, int gap_ms, int queued_after, int iterations) {
    uint64_t busy = 0, now = 0, others = 0;
    for (int i = 0; i < iterations; i++) {
        now += (uint64_t)work; busy += (uint64_t)work;
        if (wg_mgr_must_rest(queued_after > 0, busy)) { now += 10; others += 10; busy = 0; }
        else { now += (uint64_t)gap_ms; others += (uint64_t)gap_ms; if (gap_ms >= WG_MGR_REST_MS) busy = 0; }
    }
    return (double)others / (double)now;
}
int main(void) {
    assert(wg_mgr_must_rest(true, 0));
    assert(!wg_mgr_must_rest(false, 0) && !wg_mgr_must_rest(false, WG_MGR_MAX_BUSY_MS - 1));
    assert(wg_mgr_must_rest(false, WG_MGR_MAX_BUSY_MS) && wg_mgr_must_rest(false, UINT64_MAX));
    assert(WG_MGR_REST_MS > 0 && WG_MGR_REST_MS <= 10 && WG_MGR_MAX_BUSY_MS >= 10);
    /* Saturated: rests every iteration exactly as before the change. */
    assert(others_share(30, 0, 1, 1000) >= 10.0 / 40.0 - 1e-9);
    /* Continuous arrivals keeping the queue just drained, never a real wait. */
    double continuous = others_share(3, 0, 0, 10000);
    assert(continuous >= 10.0 / (WG_MGR_MAX_BUSY_MS + 3 + 10) - 1e-9);
    /* Short waits below WG_MGR_REST_MS do not reset the budget. */
    assert(others_share(3, WG_MGR_REST_MS - 1, 0, 10000) >= 0.15);
    /* Light load: waits for frames, no forced polling. */
    assert(others_share(1, 50, 0, 1000) > 0.95);
    printf("continuous-load share for other tasks: %.3f\n", continuous);
    return 0;
}
'''


# The actual ml_wg_rx_enqueue/ml_wg_rx_dequeue with bounded FIFO stand-ins for FreeRTOS queues.
LANES_HEAD = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
typedef int BaseType_t;
#define pdTRUE 1
#define pdFALSE 0
#define ML_WG_RX_SMALL_MAX 160
typedef struct { size_t len; int id; } ml_rx_packet_t;
typedef struct { ml_rx_packet_t items[64]; int head, count, depth; } fifo_t;
typedef fifo_t *QueueHandle_t;
typedef struct { QueueHandle_t wg_rx_queue, wg_rx_prio_queue; } microlink_t;
static BaseType_t xQueueSend(QueueHandle_t q, const ml_rx_packet_t *p, int wait) {
    (void)wait;
    if (q->count == q->depth) return pdFALSE;
    q->items[(q->head + q->count++) % 64] = *p;
    return pdTRUE;
}
static BaseType_t xQueueReceive(QueueHandle_t q, ml_rx_packet_t *p, int wait) {
    (void)wait;
    if (!q->count) return pdFALSE;
    *p = q->items[q->head]; q->head = (q->head + 1) % 64; q->count--;
    return pdTRUE;
}
'''
LANES_TEST = r'''
int main(void) {
    fifo_t big = { .depth = 32 }, small = { .depth = 16 };
    microlink_t ml = { &big, &small };
    ml_rx_packet_t p, out;
    /* 10 data packets, then a ping and an ACK: the small ones come out first, data keeps its order. */
    for (int i = 0; i < 10; i++) { p = (ml_rx_packet_t){ 1420, i }; assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE); }
    p = (ml_rx_packet_t){ 128, 100 }; assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE);
    p = (ml_rx_packet_t){ 96, 101 };  assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE);
    assert(big.count == 10 && small.count == 2);
    assert(ml_wg_rx_dequeue(&ml, &out) == pdTRUE && out.id == 100);
    assert(ml_wg_rx_dequeue(&ml, &out) == pdTRUE && out.id == 101);
    for (int i = 0; i < 10; i++) assert(ml_wg_rx_dequeue(&ml, &out) == pdTRUE && out.id == i);
    assert(ml_wg_rx_dequeue(&ml, &out) == pdFALSE);
    /* Boundary: 160 bytes is small, 161 is not. */
    p = (ml_rx_packet_t){ 160, 1 }; ml_wg_rx_enqueue(&ml, &p); assert(small.count == 1 && big.count == 0);
    p = (ml_rx_packet_t){ 161, 2 }; ml_wg_rx_enqueue(&ml, &p); assert(small.count == 1 && big.count == 1);
    while (ml_wg_rx_dequeue(&ml, &out) == pdTRUE) {}
    /* A full small lane falls back to the normal queue; both full refuses (the caller counts it). */
    for (int i = 0; i < 16; i++) { p = (ml_rx_packet_t){ 100, i }; assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE); }
    p = (ml_rx_packet_t){ 100, 16 }; assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE && big.count == 1);
    for (int i = 1; i < 32; i++) { p = (ml_rx_packet_t){ 1420, 100 + i }; assert(ml_wg_rx_enqueue(&ml, &p) == pdTRUE); }
    p = (ml_rx_packet_t){ 1420, 999 }; assert(ml_wg_rx_enqueue(&ml, &p) == pdFALSE);
    p = (ml_rx_packet_t){ 100, 998 };  assert(ml_wg_rx_enqueue(&ml, &p) == pdFALSE);
    /* No lane (creation not reached): everything uses the normal queue. */
    fifo_t only = { .depth = 32 };
    microlink_t bare = { &only, NULL };
    p = (ml_rx_packet_t){ 96, 7 }; assert(ml_wg_rx_enqueue(&bare, &p) == pdTRUE && only.count == 1);
    assert(ml_wg_rx_dequeue(&bare, &out) == pdTRUE && out.id == 7);
    puts("lanes ok");
    return 0;
}
'''


def main():
    # Wiring: every successful WG enqueue wakes the manager; lifetime = the queue's.
    assert re.search(r'ml_wg_rx_enqueue\(ml, &pkt\) != pdTRUE.*?\} else \{\s*xSemaphoreGive\(ml->wg_rx_wake\)', net, re.S)
    assert re.search(r'else if \(target == ml->wg_rx_queue\) \{\s*xSemaphoreGive\(ml->wg_rx_wake\)', derp)
    assert net.count('ml_wg_rx_enqueue(ml, &pkt)') == 1 and derp.count('ml_wg_rx_enqueue(ml, &pkt)') == 1
    assert 'xQueueSend(ml->wg_rx_queue' not in net and 'xQueueReceive(ml->wg_rx_queue' not in mgr
    assert mgr.count('ml_wg_rx_dequeue(ml, &wg_pkt) == pdTRUE') == 2
    assert 'ml->wg_rx_wake = xSemaphoreCreateBinary();' in life and '!ml->wg_rx_wake' in life
    assert life.index('vQueueDelete(ml->wg_rx_queue)') < life.index('vSemaphoreDelete(ml->wg_rx_wake)')
    assert life.index('vQueueDelete(ml->wg_rx_prio_queue)') < life.index('vSemaphoreDelete(ml->wg_rx_wake)')
    assert '!ml->wg_rx_prio_queue' in life and 'ml->wg_rx_prio_queue, ml->stun_rx_queue' in life
    loop = mgr[mgr.index('uint64_t iteration_end_ms'):]
    loop = loop[:loop.index('#undef WG_MGR_BUDGET_LEFT')]
    assert 'vTaskDelay(pdMS_TO_TICKS(10));' in loop and 'xSemaphoreTake(ml->wg_rx_wake, pdMS_TO_TICKS(10))' in loop
    assert loop.index('wg_mgr_must_rest(uxQueueMessagesWaiting(ml->wg_rx_queue) + '
                      'uxQueueMessagesWaiting(ml->wg_rx_prio_queue) > 0, busy_ms)') < loop.index('vTaskDelay')
    with tempfile.TemporaryDirectory(prefix='wg-mgr-wake-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('t.exe' if os.name == 'nt' else 't')
        subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', str(path / 'test.c'), '-o', str(exe)], check=True)
        out = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30).stdout.strip()
        (path / 'lanes.c').write_text(LANES_HEAD + lanes + LANES_TEST, encoding='utf-8')
        lanes_exe = path / ('l.exe' if os.name == 'nt' else 'l')
        subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', str(path / 'lanes.c'),
                        '-o', str(lanes_exe)], check=True)
        subprocess.run([str(lanes_exe)], check=True, timeout=30)
    print(f'PASS: actual wg_mgr rest policy ({out}); saturated rests as before, light load waits for frames; '
          'WG enqueue wakes the manager; semaphore lifetime equals the queue; small-packet lane: small first, '
          'full lane falls back, large never on the lane, order kept per lane (host checks)')


if __name__ == '__main__':
    main()
