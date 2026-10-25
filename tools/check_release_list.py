"""Check that the GitHub release list still fits every shipped updater (run before and after publishing).

Updaters read `GET /repos/<repo>/releases?per_page=10` whole into a fixed
buffer and give up when it does not fit: 2.x firmware (already in the field)
256 KiB, the 2.1 migration bridge and 3.x 512 KiB. Long release notes and
many assets make the list grow; this fails before it reaches 75 % of the
smallest buffer still in use, so there is time to shorten notes.

    python tools/check_release_list.py [--repository Mattboxx/esp32-tailnet-gateway]
"""
import argparse
import json
import sys
import urllib.request

LIMITS = {'2.x updater (field)': 256 * 1024, '2.1 bridge and 3.x': 512 * 1024}
MARGIN = 0.75


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
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
