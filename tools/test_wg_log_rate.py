"""WireGuard handshake MAC failures are logged at a bounded rate (actual
wireguardif.c log_mac_failure, 3.0.7-beta.11).

Anyone who can reach the WireGuard port can send handshake-sized datagrams
with a wrong MAC. Each one used to write an INFO and a WARN line. Checked:
one line for a 10,000-packet flood inside 30 s, the next line after 30 s
reports how many were suppressed, and no INFO is logged before the MAC check.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/wireguardif.c'
          ).read_text(encoding='utf-8').replace('\r\n', '\n')
start = source.index('static void log_mac_failure(const char *what) {')
code = source[start:source.index('\n}\n', start) + 3]

rx = source[source.index('void wireguardif_network_rx('):]
rx = rx[:rx.index('\n}\n')]
for kind in ('initiation', 'response'):
    case = rx[rx.index(f'wireguardif_check_{kind}_message('):]
    before = rx[:rx.index(f'wireguardif_check_{kind}_message(')]
    before = before[before.rindex('case MESSAGE_HANDSHAKE_'):]
    assert 'ESP_LOG' not in before, f'{kind}: log before the MAC check'
assert rx.count('log_mac_failure(') == 2 and 'MAC check FAILED' not in rx

PROGRAM = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static int64_t now_us = 5000000;
static int64_t esp_timer_get_time(void) { return now_us; }
static int lines; static char last[160];
#define TAG "wg"
#define ESP_LOGW(tag, ...) do { (void)tag; lines++; snprintf(last, sizeof last, __VA_ARGS__); } while (0)
@@CODE@@
int main(void) {
    log_mac_failure("Initiation");
    if (lines != 1 || !strstr(last, "Initiation MAC check FAILED (0 more")) return 1;
    for (int i = 0; i < 10000; i++) { now_us += 2000; log_mac_failure(i & 1 ? "Response" : "Initiation"); }
    if (lines != 1) return 2;                      /* 20 s of flood: still one line */
    now_us += 10000000;                            /* past 30 s */
    log_mac_failure("Response");
    if (lines != 2 || !strstr(last, "Response MAC check FAILED (10000 more")) return 3;
    log_mac_failure("Response");
    if (lines != 2) return 4;
    puts("wg log rate ok");
    return 0;
}
'''

with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / 'rate.c'
    c.write_text(PROGRAM.replace('@@CODE@@', code), encoding='utf-8')
    exe = Path(tmp) / ('rate.exe' if os.name == 'nt' else 'rate')
    subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True)
    assert out.returncode == 0 and 'wg log rate ok' in out.stdout, (out.returncode, out.stdout)
print('wg log rate: one line per 30 s with the suppressed count; nothing logged before the MAC check')
