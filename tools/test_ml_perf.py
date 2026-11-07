"""Actual MicroLink ml_perf.c/ml_perf.h (test-only packet-path profiling) on the host.

Profiling build (TSR_PERF_PROFILE=1) with stub cycle counter, core id and
spinlock: cycles of a stage measured on one core are added with bytes, count
and maximum; a sample whose task changed core is only counted as migrated;
queue residence is added as given; out-of-range stages are ignored; snapshot
copies and optionally resets; begin/end works across counter wrap-around.
Release build (macro undefined): the macros expand to nothing (a begin/end
pair compiles with no variable and no call) and ml_perf.c defines no symbol.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src'

STUBS = {
    'esp_cpu.h': '#pragma once\n#include <stdint.h>\nextern uint32_t fake_cycles;\n'
                 'static inline uint32_t esp_cpu_get_cycle_count(void) { return fake_cycles; }\n',
    'esp_timer.h': '#pragma once\n#include <stdint.h>\nstatic inline int64_t esp_timer_get_time(void) { return 0; }\n',
    'freertos/FreeRTOS.h': '#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\n'
                           'extern int fake_lock_depth;\n'
                           '#define portENTER_CRITICAL_SAFE(m) ((void)(m), ++fake_lock_depth)\n'
                           '#define portEXIT_CRITICAL_SAFE(m) ((void)(m), --fake_lock_depth)\n',
    'freertos/task.h': '#pragma once\nextern int fake_core;\nstatic inline int xPortGetCoreID(void) { return fake_core; }\n',
}

PROFILE = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ml_perf.h"
uint32_t fake_cycles; int fake_core, fake_lock_depth;
int main(void) {
    ml_perf_counter_t c[ML_PERF_STAGES];
    ml_perf_snapshot(c, 1);
    for (int i = 0; i < ML_PERF_STAGES; i++) assert(c[i].count == 0 && ml_perf_stage_names[i]);
    assert(!strcmp(ml_perf_stage_names[ML_PERF_RX_QUEUE_US], "rx_queue_us") && !strcmp(ml_perf_stage_names[ML_PERF_TX_OUTPUT], "tx_output"));
    fake_cycles = 1000; { ML_PERF_BEGIN(m); fake_cycles = 1600; ML_PERF_END(ML_PERF_RX_CHACHA, m, 1420); }
    fake_cycles = 0xFFFFFF00u; { ML_PERF_BEGIN(m); fake_cycles = 0x100; ML_PERF_END(ML_PERF_RX_CHACHA, m, 80); }  /* wrap */
    { ML_PERF_BEGIN(m); fake_core = 1; fake_cycles += 999999; ML_PERF_END(ML_PERF_RX_CHACHA, m, 1); fake_core = 0; }  /* moved */
    ML_PERF_US(ML_PERF_RX_QUEUE_US, 250);
    ml_perf_add(ML_PERF_STAGES, 5, 5, 0);             /* out of range: ignored */
    ml_perf_add((ml_perf_stage_t)-1, 5, 5, 0);
    assert(fake_lock_depth == 0);
    ml_perf_snapshot(c, 0);
    assert(c[ML_PERF_RX_CHACHA].count == 2 && c[ML_PERF_RX_CHACHA].total == 600 + 0x200);
    assert(c[ML_PERF_RX_CHACHA].bytes == 1500 && c[ML_PERF_RX_CHACHA].max == 600 && c[ML_PERF_RX_CHACHA].migrated == 1);
    assert(c[ML_PERF_RX_QUEUE_US].total == 250 && c[ML_PERF_RX_QUEUE_US].count == 1 && c[ML_PERF_RX_QUEUE_US].bytes == 0);
    ml_perf_snapshot(c, 1);                             /* reset after copy */
    assert(c[ML_PERF_RX_CHACHA].count == 2);
    ml_perf_snapshot(c, 0);
    for (int i = 0; i < ML_PERF_STAGES; i++) assert(c[i].count == 0 && c[i].total == 0 && c[i].migrated == 0);
    assert(fake_lock_depth == 0);
    puts("profile ok");
    return 0;
}
'''

RELEASE = r'''
#include "ml_perf.h"
int work(int x) {
    ML_PERF_BEGIN(m);
    x += 1;
    ML_PERF_END(ML_PERF_TX_TOTAL, m, x);
    ML_PERF_US(ML_PERF_RX_QUEUE_US, x);
    return x;
}
'''


def main():
    cc = os.environ.get('CC', 'gcc')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('ML_PERF_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    with tempfile.TemporaryDirectory(prefix='ml-perf-') as folder:
        path = Path(folder)
        (path / 'freertos').mkdir()
        for name, text in STUBS.items():
            (path / name).write_text(text, encoding='utf-8')
        (path / 'profile.c').write_text(PROFILE, encoding='utf-8')
        exe = path / ('profile.exe' if os.name == 'nt' else 'profile')
        subprocess.run([cc, *flags, '-DTSR_PERF_PROFILE=1', '-I', str(path), '-I', str(SRC),
                        str(path / 'profile.c'), str(SRC / 'ml_perf.c'), '-o', str(exe)], check=True)
        assert subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30).stdout.strip() == 'profile ok'
        # Release: no stub headers on the include path, so any reference to the
        # profiling API or its headers would fail to compile.
        (path / 'release.c').write_text(RELEASE, encoding='utf-8')
        out = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-E', '-I', str(SRC), str(path / 'release.c')],
                             check=True, capture_output=True, text=True).stdout
        body = out[out.index('int work'):]
        assert 'ml_perf_begin' not in body and 'ml_perf_add' not in body and 'mark' not in body.replace('do { } while (0)', '')
        obj = path / 'release.o'
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-c', '-I', str(SRC), str(path / 'release.c'), '-o', str(obj)], check=True)
        empty = path / 'ml_perf_release.o'
        subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-c', '-I', str(SRC), str(SRC / 'ml_perf.c'), '-o', str(empty)], check=True)
        syms = subprocess.run(['nm', str(empty)], capture_output=True, text=True).stdout
        assert 'ml_perf' not in syms, syms
    print('PASS: actual ml_perf counters (cycles, bytes, max, core migration, wrap, queue microseconds, '
          'reset, bounds); release build expands to nothing and defines no symbol (host stubs)')


if __name__ == '__main__':
    main()
