"""Passive serial soak of the attached board (no settings changed).

Resets the board once over USB-Serial/JTAG, records the console for the given
number of minutes into a PRIVATE log (the log contains identifiers: keep it
under the git-ignored build/private-device/), and prints only aggregate
numbers: internal heap minimum/maximum, task stack minimum, resets, panics,
watchdogs and allocation failures.

    python tools/soak_serial.py --port COM3 --minutes 60 \
        --log build/private-device/soak-<name>.log
"""
import argparse
import re
import time
from pathlib import Path

import serial  # pyserial (bundled with the PlatformIO/ESP-IDF Python)

PATTERNS = {
    'panic': r'Guru Meditation|abort\(\) was called|Backtrace:',
    'watchdog': r'task_wdt|Task watchdog got triggered|Interrupt wdt',
    'reboot': r'rst:0x[0-9a-f]+ \(',
    'alloc_fail': r'(?i)alloc(?:ation)? failed|ESP_ERR_NO_MEM|out of memory|No memory',
    'brownout': r'(?i)brownout',
}


def summarise(text):
    heap = [int(x) for x in re.findall(r'heap_internal_free=(\d+)', text)]
    stack = [int(x) for x in re.findall(r'stack_free=(\d+)', text)]
    out = {name: len(re.findall(p, text)) for name, p in PATTERNS.items()}
    out['heap_samples'] = len(heap)
    if heap:
        out['heap_internal_min'] = min(heap)
        out['heap_internal_max'] = max(heap)
        out['heap_internal_last'] = heap[-1]
    if stack:
        out['task_stack_free_min'] = min(stack)
    out['direct_handshakes'] = len(re.findall(r'HANDSHAKE COMPLETE', text))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--minutes', type=float, default=60)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--no-reset', action='store_true')
    args = parser.parse_args()
    port = serial.Serial(args.port, 115200, timeout=0.5)
    if not args.no_reset:
        port.dtr = False
        port.rts = True
        time.sleep(0.1)
        port.rts = False
    start = time.time()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open('wb') as log:
        while time.time() - start < args.minutes * 60:
            chunk = port.read(4096)
            if chunk:
                log.write(chunk.replace(b'\n', ('\n[+%.1f] ' % (time.time() - start)).encode()))
                log.flush()
    port.close()
    text = args.log.read_text(encoding='utf-8', errors='replace')
    for key, value in summarise(text).items():
        print(f'{key}: {value}')


if __name__ == '__main__':
    main()
