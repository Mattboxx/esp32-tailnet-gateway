"""Boot timeline (main/boot_timeline.c) on the host, and its wiring.

The module is compiled as is (BOOT_TIMELINE_HOST_TEST supplies the clock):
- every milestone starts unset (0) and keeps its first value: a later mark
  (a reconnect, a second IP, another association) never moves it;
- time 0 is stored as 1 ms (0 means "not reached"); a clock beyond 2^32 ms
  saturates; out-of-range milestones are ignored;
- eight threads racing to mark the same milestone leave exactly one of
  their values.
The firmware hooks are checked in the source: each milestone is marked at its
event, the MicroLink stages are copied once at the first control session,
the first WireGuard session is set once, and the diag publishes every key
(null until reached). No NVS, flash or task is involved.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'


def src(path):
    return path.read_text(encoding='utf-8').replace('\r\n', '\n')


main_c = src(ROOT / 'main/main.c')
for mark, anchor in (('BOOT_TL_APP_MAIN', 'void app_main(void)\n{\n    boot_timeline_mark(BOOT_TL_APP_MAIN);'),
                     ('BOOT_TL_NVS', 'startup_settings_failed(ret);\n        return;\n    }\n    boot_timeline_mark(BOOT_TL_NVS);'),
                     ('BOOT_TL_WIFI_START', 'ESP_ERROR_CHECK(esp_wifi_start() );\n    boot_timeline_mark(BOOT_TL_WIFI_START);'),
                     ('BOOT_TL_WIFI_ASSOC', 'WIFI_EVENT_STA_CONNECTED) {\n        boot_timeline_mark(BOOT_TL_WIFI_ASSOC);'),
                     ('BOOT_TL_IP', 'event_data;\n        boot_timeline_mark(BOOT_TL_IP);'),
                     ('BOOT_TL_WEB', 'web_ui_init();\n    if (admin_start == ESP_OK) boot_timeline_mark(BOOT_TL_WEB);')):
    assert anchor in main_c, mark
assert 'boot_timeline_mark(BOOT_TL_TIME);' in src(ROOT / 'main/tailscale_manager.c')
coord = src(ML / 'src/ml_coord.c')
assert 'if (!ml->boot_ms[ML_BOOT_CONNECTED]) {' in coord and coord.count('ml->boot_ms[ML_BOOT_TCP_TLS + i]') == 1
assert 'if (!ml->boot_ms[ML_BOOT_START]) {' in src(ML / 'src/microlink.c')
assert 'if (!wireguard_first_session_ms) {' in src(ML / 'components/wireguard_lwip/src/wireguard.c')
web = src(ROOT / 'main/web_ui.c')
for key in ('"app_main", "nvs", "wifi_start", "wifi_assoc", "ip", "web", "time_sync"',
            '"tailnet_start", "tcp_tls", "noise", "register", "map"', '"stream_map", "derp", "control_connected", "first_tunnel"'):
    assert key in web, key
module = src(ROOT / 'main/boot_timeline.c')
assert 'nvs' not in module.lower() and 'xTaskCreate' not in module

PROGRAM = r'''
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include "boot_timeline.h"
uint64_t boot_timeline_test_now_us;
static void *racer(void *arg) {
    (void)arg;
    boot_timeline_mark(BOOT_TL_IP);
    return NULL;
}
int main(void) {
    uint32_t t[BOOT_TL_COUNT];
    boot_timeline_get(t);
    for (int i = 0; i < BOOT_TL_COUNT; i++) assert(t[i] == 0);
    boot_timeline_test_now_us = 0;            /* time 0 is stored as 1 ms */
    boot_timeline_mark(BOOT_TL_APP_MAIN);
    boot_timeline_test_now_us = 2500999;      /* 2,500 ms */
    boot_timeline_mark(BOOT_TL_WIFI_START);
    boot_timeline_test_now_us = 9000000;
    boot_timeline_mark(BOOT_TL_WIFI_START);   /* a second start keeps the first */
    boot_timeline_mark(BOOT_TL_APP_MAIN);
    boot_timeline_mark((boot_timeline_mark_t)BOOT_TL_COUNT);   /* ignored */
    boot_timeline_mark((boot_timeline_mark_t)-1);
    boot_timeline_test_now_us = (uint64_t)5000000000ull * 1000u; /* beyond 2^32 ms */
    boot_timeline_mark(BOOT_TL_TIME);
    boot_timeline_get(t);
    assert(t[BOOT_TL_APP_MAIN] == 1 && t[BOOT_TL_WIFI_START] == 2500 && t[BOOT_TL_TIME] == UINT32_MAX);
    assert(t[BOOT_TL_NVS] == 0 && t[BOOT_TL_IP] == 0 && t[BOOT_TL_WEB] == 0);
    /* concurrent first marks: exactly one value wins */
    boot_timeline_test_now_us = 7000000;
    pthread_t th[8];
    for (int i = 0; i < 8; i++) assert(pthread_create(&th[i], NULL, racer, NULL) == 0);
    for (int i = 0; i < 8; i++) pthread_join(th[i], NULL);
    boot_timeline_get(t);
    assert(t[BOOT_TL_IP] == 7000);
    puts("boot timeline ok");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='boot-tl-') as folder:
    path = Path(folder)
    (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
    exe = path / ('t.exe' if os.name == 'nt' else 't')
    flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-DBOOT_TIMELINE_HOST_TEST', '-I', str(ROOT / 'main')]
    if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), str(ROOT / 'main/boot_timeline.c'),
                    '-o', str(exe), '-lpthread'], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and 'boot timeline ok' in out.stdout, (out.returncode, out.stdout, out.stderr)
print('boot timeline: set once per milestone, 0 ms stored as 1, saturation, out-of-range ignored, '
      'concurrent first marks; hooks at each milestone, MicroLink stages copied once, diag keys')
