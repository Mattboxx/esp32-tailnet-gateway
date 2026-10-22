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
import json
import math
import re
import time
from pathlib import Path

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
    markers = [float(x) for x in re.findall(r'\[\+(\d+(?:\.\d+)?)\]', text)]
    out['last_capture_marker_seconds'] = max(markers) if markers else None
    out['largest_capture_marker_gap_seconds'] = max((b-a for a,b in zip(markers,markers[1:])),default=None)
    out['largest_free_block_measured'] = False
    out['unexpected_resets_proven_absent'] = False  # Initial/manual resets need independent attribution.
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--minutes', type=float, default=60)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--no-reset', action='store_true')
    parser.add_argument('--analyze', action='store_true', help='Read an existing log only; never open serial or reset')
    args = parser.parse_args()
    if not math.isfinite(args.minutes) or not 0 < args.minutes <= 1440:
        parser.error('--minutes must be finite and within (0, 1440]')
    if args.analyze:
        result=summarise(args.log.read_text(encoding='utf-8',errors='replace'))
        result['requested_seconds']=args.minutes*60
        result['full_duration_evidence']=result['last_capture_marker_seconds'] is not None and result['last_capture_marker_seconds']>=args.minutes*60-1
        print(json.dumps(result,indent=2));return
    # Loading a log for analysis must not even require pyserial. A normal run
    # starts with modem controls inactive before opening to avoid reset pulses.
    import serial  # PlatformIO/ESP-IDF Python includes pyserial.
    private=Path(__file__).resolve().parents[1]/'build/private-device'
    if not args.log.resolve().is_relative_to(private.resolve()):
        parser.error('Raw serial logs must stay under ignored build/private-device/')
    if args.log.exists():parser.error('Refusing to overwrite an existing evidence log')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    log=args.log.open('xb')
    port = serial.Serial(port=None, baudrate=115200, timeout=0.5)
    port.dtr=False;port.rts=False;port.port=args.port
    start=time.monotonic();finished=False
    try:
        port.open()
        if not args.no_reset:
            port.rts=True
            time.sleep(0.1)
            port.rts=False
        start = time.monotonic()
        while time.monotonic() - start < args.minutes * 60:
            chunk = port.read(4096)
            if chunk:
                log.write(chunk.replace(b'\n', ('\n[+%.1f] ' % (time.monotonic() - start)).encode()))
                log.flush()
        finished=True
    finally:
        elapsed=time.monotonic()-start
        port.close();log.close()
        result=summarise(args.log.read_text(encoding='utf-8',errors='replace'))
        result.update(requested_seconds=args.minutes*60,elapsed_seconds=round(elapsed,2),capture_completed=finished,reset_requested=not args.no_reset)
        args.log.with_suffix(args.log.suffix+'.summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
