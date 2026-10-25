"""Actual tools/check_release_list.py bridge_check() on synthetic release lists.

The frozen 2.1.0 bridge (ADR-033) migrates to the newest stable 3.x in the
release list; the check must name that release and fail when the bridge
would skip it: prerelease/draft/2.x/non-plain tags ignored, highest version
wins regardless of order, missing asset, missing digest, not uploaded, size
limits (inclusive) of firmware/bootloader/partitions, and no 3.x at all.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_release_list', ROOT / 'tools/check_release_list.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def asset(name, size, digest=True, state='uploaded'):
    return {'name': name, 'size': size, 'state': state, 'digest': 'sha256:' + 'ab' * 32 if digest else None}


def release(tag, pre=False, draft=False, assets=None):
    if assets is None:
        assets = [asset('firmware.bin', 2264880), asset('bootloader.bin', 18768), asset('partitions.bin', 3072)]
    return {'tag_name': tag, 'prerelease': pre, 'draft': draft, 'assets': assets}


def main():
    check = mod.bridge_check
    ok = [release('v3.0.1'), release('v3.1.0-rc.1', pre=True), release('v3.0.2'), release('v2.1.0'),
          release('v3.0.9', draft=True), release('v4.0.0-beta.1', pre=False), release('v3.0.10', pre=True)]
    assert check(ok) == ('v3.0.2', []), check(ok)
    assert check([release('v3.0.2'), release('v3.0.10')]) == ('v3.0.10', [])        # numeric, not text order
    assert check([release('v2.1.0'), release('v2.0.2')]) == (None, ['no stable 3.x release in the list the bridge reads'])
    assert check([]) == (None, ['no stable 3.x release in the list the bridge reads'])
    base = [asset('firmware.bin', 0x380000), asset('bootloader.bin', 0x8000), asset('partitions.bin', 0xC00)]
    assert check([release('v3.0.3', assets=base)]) == ('v3.0.3', [])                  # limits inclusive
    for i, name, limit in ((0, 'firmware.bin', 0x380000), (1, 'bootloader.bin', 0x8000), (2, 'partitions.bin', 0xC00)):
        big = list(base); big[i] = asset(name, limit + 1)
        tag, problems = check([release('v3.0.3', assets=big)])
        assert tag == 'v3.0.3' and len(problems) == 1 and name in problems[0], problems
        tiny = list(base); tiny[i] = asset(name, 31)
        assert len(check([release('v3.0.3', assets=tiny)])[1]) == 1
        missing = [a for j, a in enumerate(base) if j != i]
        assert check([release('v3.0.3', assets=missing)])[1] == [f'{name} missing']
        nodigest = list(base); nodigest[i] = asset(name, 100, digest=False)
        assert 'digest' in check([release('v3.0.3', assets=nodigest)])[1][0]
        pending = list(base); pending[i] = asset(name, 100, state='new')
        assert 'not uploaded' in check([release('v3.0.3', assets=pending)])[1][0]
    # A broken newest stable release is reported, not silently replaced by an older one.
    tag, problems = check([release('v3.0.2'), release('v3.0.3', assets=base[:2])])
    assert tag == 'v3.0.3' and problems == ['partitions.bin missing']
    print('PASS: actual check_release_list bridge_check: newest stable 3.x as the frozen 2.1.0 bridge picks it, '
          'asset presence/digest/state/size limits, no 3.x (synthetic lists, no network)')


if __name__ == '__main__':
    main()
