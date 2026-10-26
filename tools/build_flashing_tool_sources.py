"""Build a checksum-locked, source-only esptool companion; never flash a device."""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import tarfile
import urllib.request


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(index, cache, destination, verification):
    assert index['tool'] == 'esptool' and index['version'] == '5.3.1'
    assert len(verification) == 617 and all(r['matched'] for r in verification)
    notice = [b'Desktop esptool and source-collection notices\n'
              b'Original authors retain their terms. Not the firmware MIT license.\n'
              b'Conservative source inventories include unlinked/test material; no new application license conditions are imposed.\n']
    seen = set()
    payloads = {}
    for entry in index['archives']:
        name = entry['filename']
        assert Path(name).name == name and name not in payloads
        raw = (cache/name).read_bytes()
        assert sha(raw) == entry['sha256'], 'Source digest mismatch: '+name
        payloads['sources/'+name] = raw
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
            for member in archive.getmembers():
                filename = Path(member.name).name.upper()
                if not member.isfile() or member.size > 5*1024*1024 or not filename.startswith(('LICENSE','COPYING','COPYRIGHT','NOTICE')):
                    continue
                if Path(member.name).suffix.lower() not in ('','.txt','.md','.rst'):
                    continue
                text = archive.extractfile(member).read()
                if text not in seen:
                    notice.append(b'\n\n===== '+(name+'/'+member.name).encode()+b' =====\n\n'+text)
                    seen.add(text)
    legal = b''.join(notice)
    payloads['FLASHING-TOOL-LICENSES.txt'] = legal
    payloads['source-index.json'] = (json.dumps(index,indent=2)+'\n').encode()
    payloads['verified-modules.json'] = (json.dumps(verification,indent=2)+'\n').encode()
    payloads['README.txt'] = (
        'Corresponding source companion for the unmodified Espressif esptool 5.3.1 Windows executable.\n'
        'Executable SHA-256: '+index['executable_sha256']+'\n\n'
        'Original source archives, build scripts, licenses and hashes are supplied together.\n'
        'The PyPI esptool sdist and Git snapshot contain the program; the Git snapshot includes the CI build workflow.\n'
        'Use the included python-binary-action snapshot, Python 3.13.14 and PyInstaller 6.11.1 for the upstream build procedure.\n'
        'Pinned Python dependencies are identified in source-index.json; source trees include their original build files.\n'
        'Extract each source archive under a separate directory. Reassemble Git submodules at the parent/path recorded in the index.\n'
        'Tibs Cargo.lock pins the included .crate sources; these can be used as a Cargo source cache/vendor input.\n'
        'The Rust snapshot supplies standard-library source; only library submodules are needed here, not compiler LLVM submodules.\n'
        'Legacy stub v1.11.1 (GPL-2.0-or-later) and new stub v1.0.0 (MIT/Apache-2.0) sources and submodules are included.\n'
        'Source access is supplied with the download, without creating a written source offer or additional approval requirement.\n'
        'No private signing keys are supplied or required to build an unsigned tool. Byte-identical executable rebuilding is not asserted.\n'
        'Windows OS/runtime components retain Microsoft terms; they are not relicensed or claimed as project-owned open source.\n'
        'Do not confuse these desktop-tool terms with the separate firmware license.\n').encode()
    payloads['SHA256SUMS.txt'] = ''.join(sha(raw)+'  '+name+'\n' for name,raw in sorted(payloads.items())).encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as stream, gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as archive:
            for name, raw in sorted(payloads.items()):
                info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644
                archive.addfile(info,io.BytesIO(raw))
    return legal


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index',type=Path,required=True)
    ap.add_argument('--cache',type=Path,required=True)
    ap.add_argument('--verification',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--notice-out',type=Path,required=True)
    ap.add_argument('--fetch',action='store_true',help='Fetch missing pinned source archives only')
    a=ap.parse_args();index=json.loads(a.index.read_text(encoding='utf-8'))
    if a.fetch:
        a.cache.mkdir(parents=True,exist_ok=True)
        for entry in index['archives']:
            assert Path(entry['filename']).name==entry['filename']
            target=a.cache/entry['filename']
            if not target.exists():
                url=entry['url']
                assert url.startswith(('https://files.pythonhosted.org/','https://codeload.github.com/',
                                       'https://static.crates.io/','https://www.python.org/ftp/python/'))
                with urllib.request.urlopen(url,timeout=120) as response:
                    raw=response.read(160*1024*1024+1)
                assert len(raw)<=160*1024*1024 and sha(raw)==entry['sha256']
                target.write_bytes(raw)
    notices=build(index,a.cache,a.out,json.loads(a.verification.read_text(encoding='utf-8')))
    a.notice_out.write_bytes(notices)
    print('PASS source companion',a.out.name,'sha256',sha(a.out.read_bytes()),'notices',len(notices))


if __name__=='__main__':
    main()
