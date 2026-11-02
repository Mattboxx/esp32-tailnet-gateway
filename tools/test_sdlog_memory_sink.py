"""sdlog memory sink (components/sdlog/sdlog.c), actual code compiled on the host.

The actual level parser, master-level computation, sdlog_set_memory_sink()
and the sdlog_vprintf() console/memory gates are compiled with stubs (SD
recorder disabled, so its branch is not exercised here). Checks that with
the console at ERROR and the memory sink at WARN:
- warnings reach the ring;
- errors reach the console only once and are not duplicated into the sink;
- info lines are dropped;
- un-leveled raw output keeps going to the console;
- a fragmented line stays with one sink;
- the master log level is raised to WARN so warnings are generated at all.
It also covers a NULL or OFF sink and the case where the console already
prints warnings.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'components/sdlog/sdlog.c').read_text(encoding='utf-8').replace('\r\n', '\n')
MAIN = (ROOT / 'main/main.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def between(start, end):
    i = SRC.index(start)
    return SRC[i:SRC.index(end, i) + len(end)]


levels = between('static char extract_level(', 'default:  return true;              /* raw / un-leveled: keep unless OFF */\n    }\n}\n')
master = between('static void apply_master_level(void)', 'apply_master_level();\n}\n')
hook = between('static int sdlog_vprintf(const char *fmt, va_list args)', '    tl_in_sdlog = false;\n    return ret;\n}\n')
assert MAIN.index('sdlog_set_memory_sink(log_capture_store, SDLOG_LVL_WARN);') > MAIN.index('sdlog_init();')

PROLOGUE = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SDLOG_LVL_OFF 0
#define SDLOG_LVL_ERROR 1
#define SDLOG_LVL_WARN 2
#define SDLOG_LVL_INFO 3
#define SDLOG_LINE_MAX 256
#define pdTRUE 1
typedef int (*vprintf_like_t)(const char *, va_list);
typedef int esp_log_level_t;
typedef void *QueueHandle_t;
typedef void *SemaphoreHandle_t;
typedef struct { char data[SDLOG_LINE_MAX]; uint16_t len; } sdlog_msg_t;
static int master_level = -1;
static void esp_log_level_set(const char *tag, esp_log_level_t l) { (void)tag; master_level = l; }
static atomic_bool s_enabled = false;
static _Atomic uint8_t s_sd_level = SDLOG_LVL_WARN;
static _Atomic uint8_t s_console_level = SDLOG_LVL_ERROR;
static _Atomic uint32_t s_dropped;
static QueueHandle_t s_queue = NULL;
static SemaphoreHandle_t s_fmt_mutex = NULL;
static char *s_rawbuf = NULL, *s_pktbuf = NULL;
static int s_rawpos = 0;
static _Thread_local bool tl_in_sdlog = false;
static int xSemaphoreTake(SemaphoreHandle_t m, int t) { (void)m; (void)t; return 0; }
static void xSemaphoreGive(SemaphoreHandle_t m) { (void)m; }
static int xQueueSend(QueueHandle_t q, const void *m, int t) { (void)q; (void)m; (void)t; return 0; }
static int strip_ansi(const char *src, char *dst, int max) { (void)src; (void)dst; (void)max; return 0; }
static char console[2048], ring[2048];
static int to_console(const char *fmt, va_list a) { size_t n = strlen(console); return vsnprintf(console + n, sizeof console - n, fmt, a); }
static int to_ring(const char *fmt, va_list a) { size_t n = strlen(ring); return vsnprintf(ring + n, sizeof ring - n, fmt, a); }
static vprintf_like_t s_original_vprintf = to_console;
static vprintf_like_t s_mem_store = NULL;
static _Atomic uint8_t s_mem_level = SDLOG_LVL_OFF;
'''

TEST = r'''
static void emit(const char *fmt, ...) { va_list a; va_start(a, fmt); sdlog_vprintf(fmt, a); va_end(a); }
static void reset(void) { console[0] = ring[0] = 0; }
int main(void) {
    /* Before a sink: console at ERROR, SD off -> master ERROR, warnings dropped. */
    apply_master_level();
    assert(master_level == SDLOG_LVL_ERROR);
    emit("W (%d) ml_coord: Control plane watchdog timeout\n", 1);
    assert(!console[0] && !ring[0]);
    /* Sink at WARN: master raised, warnings to the ring only, errors to the console only. */
    sdlog_set_memory_sink(to_ring, SDLOG_LVL_WARN);
    assert(master_level == SDLOG_LVL_WARN);
    reset();
    emit("W (%d) ml_coord: Long-poll connection lost\n", 2);
    assert(strstr(ring, "Long-poll connection lost") && !console[0]);
    reset();
    emit("E (%d) ml_coord: TCP connect failed, retrying...\n", 3);
    assert(strstr(console, "TCP connect failed") && !ring[0]);
    reset();
    emit("I (%d) ml_coord: Reconnecting in %d ms\n", 4, 1000);
    assert(!console[0] && !ring[0]);
    reset();
    emit("\033[0;33mW (%d) wifi: colour-coded warning\033[0m\n", 5);
    assert(strstr(ring, "colour-coded warning") && !console[0]);
    reset();
    emit("raw boot line without a level\n");
    assert(strstr(console, "raw boot line") && !ring[0]);
    /* Fragmented line: the continuation follows its line start. */
    reset();
    emit("W (%d) wifi: split ", 6);
    emit("continuation of the warning\n");
    emit("E (%d) x: next error\n", 7);
    assert(strstr(ring, "split continuation of the warning") && !strstr(ring, "next error"));
    assert(strstr(console, "next error") && !strstr(console, "split"));
    /* Console already at WARN: warnings go to the console path only (no duplicate). */
    atomic_store(&s_console_level, SDLOG_LVL_WARN);
    reset();
    emit("W (%d) t: shown on console\n", 8);
    assert(strstr(console, "shown on console") && !ring[0]);
    atomic_store(&s_console_level, SDLOG_LVL_ERROR);
    /* Sink OFF or NULL: master back to the console level, nothing to the ring. */
    sdlog_set_memory_sink(to_ring, SDLOG_LVL_OFF);
    assert(master_level == SDLOG_LVL_ERROR);
    reset(); emit("W (%d) t: dropped\n", 9); assert(!ring[0] && !console[0]);
    sdlog_set_memory_sink(NULL, SDLOG_LVL_WARN);
    assert(master_level == SDLOG_LVL_ERROR);
    reset(); emit("W (%d) t: dropped\n", 10); assert(!ring[0]);
    /* An out-of-range level is clamped to WARN. */
    sdlog_set_memory_sink(to_ring, 9);
    assert(master_level == SDLOG_LVL_WARN);
    puts("PASS: sdlog memory sink (console ERROR + ring WARN: warnings to ring only, errors to console only, info "
         "dropped, raw to console, ANSI-coloured and fragmented lines, no duplicate when the console shows "
         "warnings, OFF/NULL sink, clamp; master level follows the sinks); main.c registers the ring after sdlog_init");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='sdlog-sink-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROLOGUE + levels + master + hook + TEST, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-format-security']
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
