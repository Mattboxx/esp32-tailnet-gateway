"""Check that the GitHub release list still fits every shipped updater (run before and after publishing).

Updaters read `GET /repos/<repo>/releases?per_page=10` whole into a fixed
buffer and give up when it does not fit: 2.x firmware (already in the field)
256 KiB, the 2.1 migration bridge and 3.x 512 KiB. Long release notes and
many assets make the list grow; this fails before it reaches 75 % of the
smallest buffer still in use, so there is time to shorten notes.

The 2.1.0 bridge is frozen (ADR-033): it migrates 2.x gateways to the newest
stable 3.x it finds in that list. This also fails when the newest stable 3.x
release is one the published bridge would skip (assets missing, without a
digest or larger than its limits), so a release never strands 2.x gateways
on an older 3.x or none.

    python tools/check_release_list.py [--repository Mattboxx/esp32-tailnet-gateway]
"""
import argparse
import json
import re
import sys
import urllib.request

LIMITS = {'2.x updater (field)': 256 * 1024, '2.1 bridge and 3.x': 512 * 1024}
MARGIN = 0.75
# Published 2.1.0 bridge (v2.1.0 main/layout_migration.c): assets and size
# limits it accepts (MIG_V3_SLOT, MIG_BOOT_LIMIT, MIG_TABLE_SIZE).
BRIDGE_ASSETS = {'firmware.bin': 0x380000, 'bootloader.bin': 0x8000, 'partitions.bin': 0xC00}
STABLE_TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')


def bridge_check(releases):
    """(newest stable 3.x tag, problems with its assets) as the 2.1.0 bridge sees them."""
    best = None
    for r in releases:
        m = STABLE_TAG.match(r.get('tag_name') or '')
        if r.get('draft') is not False or r.get('prerelease') is not False or not m or int(m.group(1)) < 3:
            continue
        version = tuple(int(x) for x in m.groups())
        if best is None or version > best[0]:
            best = (version, r)
    if best is None:
        return None, ['no stable 3.x release in the list the bridge reads']
    release, problems = best[1], []
    assets = {a.get('name'): a for a in release.get('assets', [])}
    for name, limit in BRIDGE_ASSETS.items():
        a = assets.get(name)
        if not a:
            problems.append(f'{name} missing')
        elif a.get('state') != 'uploaded' or not str(a.get('digest') or '').startswith('sha256:'):
            problems.append(f'{name} not uploaded or without a sha256 digest')
        elif not 32 <= int(a.get('size', 0)) <= limit:
            problems.append(f"{name} {a.get('size')} B outside 32..{limit} B")
    return release['tag_name'], problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--repository', default='Mattboxx/esp32-tailnet-gateway')
    a = p.parse_args()
    req = urllib.request.Request(f'https://api.github.com/repos/{a.repository}/releases?per_page=10',
                                 headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Mattboxx-release-check'})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    releases = json.loads(body)
    size = len(body)
    print(f'{len(releases)} releases, {size / 1024:.0f} KiB')
    for r in releases:
        print(f"  {r['tag_name']:<32} notes {len(r.get('body') or '') / 1024:5.1f} KiB, {len(r.get('assets', []))} assets")
    failed = False
    for name, limit in LIMITS.items():
        share = size / limit
        ok = share <= MARGIN
        failed |= not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {share:.0%} of {limit // 1024} KiB")
    tag, problems = bridge_check(releases)
    failed |= bool(problems)
    print(f"{'OK  ' if not problems else 'FAIL'} 2.1.0 bridge target: {tag or 'none'}"
          + (f" ({'; '.join(problems)})" if problems else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
