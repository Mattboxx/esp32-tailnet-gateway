"""Easy Install macOS/Linux script (tools/easy_install/macos-linux/install.sh)
against a stub esptool: update and new-device paths write the right offsets,
and a wrong confirmation, checksum mismatch, non-ESP32-S3 chip, missing or
ambiguous port and esptool 4 all stop before any write. Needs a POSIX sh
(Linux/macOS, or Git Bash on Windows). No device access.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'tools/easy_install'
def posix_shell():
    # Windows' bash.exe may be only a WSL launcher with no Linux shell
    # installed. Prefer Git's real POSIX shell; never silently skip the tests.
    candidates = []
    if os.name == 'nt':
        for key in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA'):
            base = Path(os.environ.get(key, 'C:/Program Files'))
            candidates += [base / 'Git/bin/sh.exe', base / 'Programs/Git/bin/sh.exe']
    candidates += [shutil.which('sh'), shutil.which('bash')]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            probe = subprocess.run([str(candidate), '-c', 'printf POSIX-SHELL-OK'],
                                   capture_output=True, text=True, timeout=5)
            if probe.returncode == 0 and probe.stdout == 'POSIX-SHELL-OK':
                return str(candidate)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None

SH = posix_shell()
assert SH, 'POSIX sh required'

STUB = r'''#!/bin/sh
if [ "$1" = version ]; then echo "esptool v${STUB_MAJOR:-5}.3.1"; echo "${STUB_MAJOR:-5}.3.1"; exit 0; fi
echo "$*" >> "$STUB_LOG"
case "$*" in *chip-id*) exit ${STUB_CHIP_RC:-0};; esac
exit 0
'''


def package(folder: Path):
    fw = folder / 'firmware'
    fw.mkdir(parents=True)
    names = ['bootloader.bin', 'partitions.bin', 'ota_data_initial.bin', 'firmware.bin', 'firmware-it.bin', 'firmware-es.bin', 'firmware-zh.bin']
    for n in names:
        (fw / n).write_bytes(n.encode() * 16)
    shutil.copytree(TEMPLATE / 'macos-linux', folder / 'macos-linux')
    (folder / 'SHA256SUMS.txt').write_bytes(''.join(
        f'{hashlib.sha256((fw / n).read_bytes()).hexdigest()}  firmware/{n}\n' for n in names).encode('ascii'))


def run(folder, args, *, answer='', env=None):
    bindir = folder / 'stubbin'
    bindir.mkdir(exist_ok=True)
    stub = bindir / 'esptool'
    stub.write_text(STUB, encoding='utf-8', newline='\n')
    stub.chmod(0o755)
    log = folder / 'calls.log'
    if log.exists():
        log.unlink()
    e = dict(os.environ, STUB_LOG=str(log).replace('\\', '/'), PATH=str(bindir) + os.pathsep + os.environ['PATH'])
    e.update(env or {})
    p = subprocess.run([SH, 'macos-linux/install.sh', *args], cwd=folder, input=answer, text=True,
                       capture_output=True, env=e, timeout=60)
    calls = log.read_text().splitlines() if log.exists() else []
    return p.returncode, p.stdout + p.stderr, calls


def writes(calls):
    return [c for c in calls if 'write-flash' in c or 'erase-flash' in c]


with tempfile.TemporaryDirectory() as d:
    pkg = Path(d)
    package(pkg)
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0'])
    assert rc == 0, out
    w = writes(calls)
    assert len(w) == 1 and '--port /dev/ttyFAKE0' in w[0], calls
    for part in ('0x0 firmware/bootloader.bin', '0x8000 firmware/partitions.bin', '0x19000 firmware/ota_data_initial.bin',
                 '0x20000 firmware/firmware.bin', '--flash-mode dio --flash-freq 80m --flash-size 4MB'):
        assert part in w[0], (part, w[0])
    assert 'erase' not in w[0]
    rc, out, calls = run(pkg, ['new', '/dev/ttyFAKE0'], answer='ERASE\n')
    w = writes(calls)
    assert rc == 0 and len(w) == 2 and 'erase-flash' in w[0] and '0x0 firmware/bootloader.bin' in w[1] and '0x20000 firmware/firmware.bin' in w[1], (out, calls)
    # Web UI language: the chosen image goes to the app slot, in both modes.
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0', 'it'])
    w = writes(calls)
    assert rc == 0 and len(w) == 1 and '0x20000 firmware/firmware-it.bin' in w[0] and '0x0 firmware/bootloader.bin' in w[0], (out, calls)
    rc, out, calls = run(pkg, ['new', '/dev/ttyFAKE0', 'zh'], answer='ERASE\n')
    w = writes(calls)
    assert rc == 0 and len(w) == 2 and 'erase-flash' in w[0] and '0x20000 firmware/firmware-zh.bin' in w[1], (out, calls)
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0', '3'])
    assert rc == 0 and '0x20000 firmware/firmware-es.bin' in writes(calls)[0], (out, calls)
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0', 'xx'])
    assert rc == 1 and not calls and 'unknown language' in out
    rc, out, calls = run(pkg, ['new', '/dev/ttyFAKE0', 'xx'], answer='ERASE\n')
    assert rc == 1 and not calls
    rc, out, calls = run(pkg, ['new', '/dev/ttyFAKE0'], answer='yes\n')
    assert rc == 2 and not writes(calls) and 'Nothing was written' in out
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0'], env={'STUB_CHIP_RC': '2'})
    assert rc == 1 and not writes(calls) and 'ESP32-S3' in out
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0'], env={'STUB_MAJOR': '4'})
    assert rc == 1 and not calls and 'esptool 5 is required' in out
    rc, out, calls = run(pkg, ['update'], env={'SERIAL_CANDIDATES': str(pkg / 'none*').replace('\\', '/')})
    assert rc == 1 and not calls and 'no USB serial port found' in out
    (pkg / 'ttyACM0').write_text(''); (pkg / 'ttyACM1').write_text('')
    rc, out, calls = run(pkg, ['update'], env={'SERIAL_CANDIDATES': str(pkg / 'ttyACM*').replace('\\', '/')})
    assert rc == 1 and not calls and 'Several serial ports' in out
    (pkg / 'ttyACM1').unlink()
    rc, out, calls = run(pkg, ['update'], env={'SERIAL_CANDIDATES': str(pkg / 'ttyACM*').replace('\\', '/')})
    assert rc == 0 and len(writes(calls)) == 1 and 'ttyACM0' in writes(calls)[0], (out, calls)
    rc, out, calls = run(pkg, ['bogus'])
    assert rc == 2 and not calls
    (pkg / 'firmware/firmware.bin').write_bytes(b'tampered')
    rc, out, calls = run(pkg, ['update', '/dev/ttyFAKE0'])
    assert rc == 1 and not calls and 'checksum' in out
# Regression: packages built on Windows must keep LF checksum lists.
for sums in (ROOT / 'build').glob('release-v*/**/SHA256SUMS.txt'):
    assert b'\r' not in sums.read_bytes(), f'CRLF in {sums}'
print('PASS: Easy Install install.sh: update/new offsets, language images, ERASE confirmation, checksum, chip, port discovery and esptool version guards (stub esptool)')
