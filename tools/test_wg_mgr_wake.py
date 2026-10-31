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


def main():
    # Wiring: every successful WG enqueue wakes the manager; lifetime = the queue's.
    assert re.search(r'xQueueSend\(ml->wg_rx_queue.*?\} else \{\s*xSemaphoreGive\(ml->wg_rx_wake\)', net, re.S)
    assert re.search(r'else if \(target == ml->wg_rx_queue\) \{\s*xSemaphoreGive\(ml->wg_rx_wake\)', derp)
    assert net.count('xQueueSend(ml->wg_rx_queue') == 1 and derp.count('xQueueSend(target') == 1
    assert 'ml->wg_rx_wake = xSemaphoreCreateBinary();' in life and '!ml->wg_rx_wake' in life
    assert life.index('vQueueDelete(ml->wg_rx_queue)') < life.index('vSemaphoreDelete(ml->wg_rx_wake)')
    loop = mgr[mgr.index('uint64_t iteration_end_ms'):]
    loop = loop[:loop.index('#undef WG_MGR_BUDGET_LEFT')]
    assert 'vTaskDelay(pdMS_TO_TICKS(10));' in loop and 'xSemaphoreTake(ml->wg_rx_wake, pdMS_TO_TICKS(10))' in loop
    assert loop.index('wg_mgr_must_rest(uxQueueMessagesWaiting(ml->wg_rx_queue) > 0, busy_ms)') < loop.index('vTaskDelay')
    with tempfile.TemporaryDirectory(prefix='wg-mgr-wake-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('t.exe' if os.name == 'nt' else 't')
        subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', str(path / 'test.c'), '-o', str(exe)], check=True)
        out = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    print(f'PASS: actual wg_mgr rest policy ({out}); saturated rests as before, light load waits for frames; '
          'WG enqueue wakes the manager; semaphore lifetime equals the queue (host checks)')


if __name__ == '__main__':
    main()
