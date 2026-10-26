"""Prepare notice-only companions from public tags and verified image metadata.

Never builds/flashes firmware or modifies releases. SDK inventories deliberately
include unlinked material; they are legal coverage, not a precise linked SBOM.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from package_release import source_notice_blocks

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.c', '.h', '.cc', '.cpp', '.hpp', '.cxx', '.s'}


def leading_source_text(raw):
    # Some SDK test bodies contain legacy-encoded strings. Decode only the
    # leading comments that are actually inspected, never unrelated C bodies.
    pattern = re.compile(rb'\s*(/\*[\s\S]*?\*/|//[^\n]*(?:\n[ \t]*//[^\n]*)*)')
    end = 0
    while (match := pattern.match(raw, end)) is not None:
        end = match.end()
    return raw[:end].decode('utf-8', errors='strict')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def app_description(data):
    assert len(data) >= 208 and data[0] == 0xe9 and data[32:36] == bytes.fromhex('3254cdab'), 'Not an ESP application image'
    def field(offset, length):
        return data[32+offset:32+offset+length].split(b'\0', 1)[0].decode('ascii')
    return {'version': field(16, 32), 'project': field(48, 32),
            'sdk': field(112, 32), 'elf_sha256': data[176:208].hex()}


def git(*args, repository=ROOT):
    return subprocess.check_output(['git', '-C', str(repository), *args])


def git_records(revision, repository, prefix):
    tree = git('ls-tree', '-r', '-z', revision, repository=repository)
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        _, kind, oid = metadata.split()
        path = Path(name.decode())
        legal = path.name.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE'))
        if kind != b'blob' or not (legal or path.suffix.lower() in EXTENSIONS):
            continue
        raw = git('cat-file', 'blob', oid.decode(), repository=repository)
        if legal and path.suffix.lower() in ('', '.md', '.txt', '.rst'):
            yield prefix+'/'+path.as_posix(), raw.decode('utf-8', errors='strict')
        else:
            for block in source_notice_blocks(leading_source_text(raw[:65536])):
                yield prefix+'/'+path.as_posix()+' (source notice)', block


def sdk_records(sdk):
    assert (sdk/'LICENSE').is_file()
    yield 'ESP-IDF/LICENSE', (sdk/'LICENSE').read_text(encoding='utf-8')
    for path in sorted((sdk/'components').rglob('*')):
        if not path.is_file():
            continue
        label = 'ESP-IDF/'+path.relative_to(sdk).as_posix()
        legal = path.name.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE'))
        if (legal and path.suffix.lower() in ('', '.md', '.txt', '.rst')) or path == sdk/'components/wpa_supplicant/README':
            yield label, path.read_text(encoding='utf-8')
        elif path.suffix.lower() in EXTENSIONS:
            with path.open('rb') as stream:
                prefix = stream.read(65536)
            for block in source_notice_blocks(leading_source_text(prefix)):
                yield label+' (source notice)', block


def runtime_records(compiler):
    for relative in ('newlib/COPYING.NEWLIB', 'newlib/COPYING.LIBGLOSS',
                     'gcc/COPYING3', 'gcc/COPYING3.LIB', 'gcc/COPYING.RUNTIME'):
        path = compiler/'share/licenses'/relative
        assert path.is_file(), 'Missing runtime notice: '+relative
        yield 'toolchain/'+relative, path.read_text(encoding='utf-8')


def render(records):
    seen = set()
    result = []
    for name, text in records:
        if text in seen:
            continue
        seen.add(text)
        result.append('\n\n===== '+name+' =====\n\n'+text)
    return ''.join(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--release-snapshot', type=Path, required=True)
    ap.add_argument('--download-cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--sdk-531', type=Path, required=True)
    ap.add_argument('--sdk-553', type=Path, required=True)
    ap.add_argument('--compiler-13', type=Path, required=True)
    ap.add_argument('--compiler-14', type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    profiles = {'5.3.1': (a.sdk_531, a.compiler_13), '5.5.3': (a.sdk_553, a.compiler_14)}
    sdk_text = {}
    inventory = []
    for release in json.loads(a.release_snapshot.read_text(encoding='utf-8')):
        if release['draft']:
            continue
        tag = release['tag_name']
        assert re.fullmatch(r'v[0-9A-Za-z.+-]+', tag)
        commit = git('rev-parse', tag+'^{commit}').decode().strip()
        link = git('ls-tree', tag, 'external/microlink').decode().split()[2]
        folder = a.download_cache/tag
        images = []
        for asset in release['assets']:
            path = folder/asset['name']
            if not path.exists() or path.suffix != '.zip':
                continue
            data = path.read_bytes()
            assert not asset.get('digest') or asset['digest'] == 'sha256:'+digest(data)
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if Path(name).name in ('firmware.bin', 'firmware-eth.bin'):
                        raw = archive.read(name)
                        images.append(dict(archive=path.name, member=name, sha256=digest(raw), **app_description(raw)))
        if not images:
            # A migration bridge has no desktop ZIP; the downloaded OTA asset is
            # checked against its immutable digest from the release API snapshot.
            asset = next(x for x in release['assets'] if x['name'] == 'firmware.bin')
            path = folder/asset['name']
            raw = path.read_bytes()
            assert asset.get('digest') == 'sha256:'+digest(raw)
            images.append(dict(archive=None, member=path.name, sha256=digest(raw), **app_description(raw)))
        sdks = {image['sdk'] for image in images}
        assert len(sdks) == 1, 'Mixed SDKs need separate notice companions'
        version = next(iter(sdks))
        assert version in profiles, 'Unreviewed SDK '+version
        assert all(image['project'] == 'esp32_tsr' for image in images)
        if version not in sdk_text:
            sdk, compiler = profiles[version]
            sdk_text[version] = render([*sdk_records(sdk), *runtime_records(compiler)])
        original = list(git_records(commit, ROOT, 'project'))
        assert any(name == 'project/LICENSE' for name, _ in original)
        original += list(git_records(link, ROOT/'external/microlink', 'MicroLink'))
        header = ('Firmware copyright and license companion — '+tag+'\n'
                  'Original authors retain their notices. Independent Mattboxx Edition.\n'
                  'Source: https://github.com/Mattboxx/esp32-tailnet-gateway/tree/'+tag+'\n'
                  'Source revision: '+commit+'\nMicroLink gitlink: '+link+'\n'
                  'Image app descriptor identifies ESP-IDF '+version+'.\n'
                  'Conservative source/SDK/runtime notice coverage; includes unlinked or disabled material.\n'
                  'Compiler-runtime profile follows the SDK/toolchain generation; historical per-symbol or exact compiler provenance is not asserted.\n'
                  'This supplements the original download without changing any firmware byte.\n'
                  'Desktop esptool retains its independent GPL terms and accompanying source download.\n')
        text = header+render(original)+sdk_text[version]
        dest = a.out/tag;dest.mkdir(exist_ok=True)
        (dest/'FIRMWARE-LICENSES-ADDENDUM.txt').write_bytes(text.encode('utf-8'))
        row = dict(tag=tag, source_commit=commit, microlink_gitlink=link, sdk_version=version,
                   images=images, notice_sha256=digest(text.encode('utf-8')))
        (dest/'license-provenance.json').write_text(json.dumps(row, indent=2)+'\n', encoding='utf-8')
        inventory.append(row)
        print('PASS', tag, 'SDK', version, 'notices',len(text.encode('utf-8')),flush=True)
    (a.out/'inventory.json').write_text(json.dumps(inventory, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
