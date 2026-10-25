"""The built image reports the exact source it was built from.

System > About shows the build commit compiled into web_ui.c. A build that
reuses a stale CMake configuration keeps the previous commit id (seen in a
linked worktree on 3.0.1-beta.1), and a dirty tree adds "-dirty". This reads
the actual firmware.bin and compares it with `git rev-parse HEAD` and
`git status`. Usage: check_image_provenance.py <build dir with firmware.bin>
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
image = (Path(sys.argv[1]) / 'firmware.bin').read_bytes()
head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--short=12', 'HEAD'], text=True).strip()
dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
m = re.search(rb'edition\x00([0-9a-f]{12}(?:-dirty)?)\x00', image)
assert m, 'build commit not found next to the edition string'
embedded = m.group(1).decode()
expected = head + ('-dirty' if dirty else '')
assert embedded == expected, f'image reports {embedded}, source is {expected}'
assert not dirty, 'tracked files differ from the commit: not a release candidate'
print(f'PASS: image reports build commit {embedded}, the checked-out clean source')
