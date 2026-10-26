"""Add legal material to a NEW ZIP, preserving every original executable/image.

No remote operations; original ZIP and release assets remain untouched.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import tarfile
import zipfile

SOURCE_NAME = 'esptool-5.3.1-CORRESPONDING-SOURCE.tar.gz'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_bundle_index(path, executable_sha):
    with tarfile.open(path, 'r:gz') as archive:
        member=archive.getmember('source-index.json')
        assert member.size < 256*1024
        index=json.loads(archive.extractfile(member).read())
        assert index['executable_sha256'] == executable_sha, 'Tool source does not match executable'
        for entry in index['archives']:
            name=entry['filename']
            assert PurePosixPath(name).name==name and name not in ('','.','..')
            assert sha(archive.extractfile('sources/'+name).read())==entry['sha256'], 'Incomplete or changed source archive'
        checks=archive.extractfile('SHA256SUMS.txt').read().decode('ascii')
        for line in checks.splitlines():
            expected,name=line.split('  ',1)
            assert name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
            assert sha(archive.extractfile(name).read())==expected, 'Tool-source checksum mismatch: '+name
        verification=json.loads(archive.extractfile('verified-modules.json').read())
        assert verification and len(verification)==index['verified_python_modules'] and all(r['matched'] for r in verification)
        assert any(e['filename'].startswith('esptool-5.3.1') for e in index['archives'])
        assert any('legacy-stub' in e['filename'] for e in index['archives'])
    return index


def prepare(original, destination, firmware_notices, tool_notices, source_url, source_sha):
    assert original.resolve()!=destination.resolve(), 'Never replace the original ZIP'
    assert source_url.startswith('https://github.com/Mattboxx/esp32-tailnet-gateway/releases/download/')
    with zipfile.ZipFile(original) as z:
        assert z.testzip() is None
        infos={i.filename:i for i in z.infolist() if not i.is_dir()}
        payload={name:z.read(name) for name in infos}
    assert len(payload)==len(infos)
    assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in payload)
    root=next(iter(payload)).split('/')[0]+'/' if all('/' in n for n in payload) and len({n.split('/')[0] for n in payload})==1 else ''
    allowed={root+'FIRMWARE-LICENSES.txt',root+'release-manifest.json'}
    allowed.update(n for n in payload if PurePosixPath(n).name=='SHA256SUMS.txt')
    originals=dict(payload)
    name=root+'FIRMWARE-LICENSES.txt'
    payload[name]=payload.get(name,b'')+b'\n\n===== Expanded legal companion =====\n\n'+firmware_notices
    payload[root+'FLASHING-TOOL-LICENSES.txt']=tool_notices
    payload[root+'SOURCE-DOWNLOAD.txt']=(
        'Corresponding source for the separately bundled esptool 5.3.1 Windows tool:\n'+source_url+'\n'
        'SHA-256: '+source_sha+'\n'
        'The source download is supplied beside this ZIP, without a written source offer.\n'
        'Original licenses remain applicable. This does not relicense the firmware GPL.\n').encode()
    proof={'original_archive_sha256':sha(original.read_bytes()),'tool_source_url':source_url,
           'tool_source_sha256':source_sha,'unchanged_executable_images':{n:sha(b) for n,b in originals.items() if PurePosixPath(n).suffix.lower() in ('.bin','.exe')}}
    payload[root+'LICENSE-PROVENANCE.json']=(json.dumps(proof,indent=2)+'\n').encode()
    manifest=root+'release-manifest.json'
    if manifest in payload:
        doc=json.loads(payload[manifest]);doc['license_remediation']=proof
        if isinstance(doc.get('files'),dict):
            for n in ('FIRMWARE-LICENSES.txt','FLASHING-TOOL-LICENSES.txt','SOURCE-DOWNLOAD.txt','LICENSE-PROVENANCE.json'):
                raw=payload[root+n];doc['files'][n]={'sha256':sha(raw),'bytes':len(raw)}
        payload[manifest]=(json.dumps(doc,indent=1)+'\n').encode()
    sums=[n for n in payload if PurePosixPath(n).name=='SHA256SUMS.txt']
    if not sums:sums=[root+'SHA256SUMS.txt']
    for filename in sums:
        folder=filename.rsplit('/',1)[0]+'/' if '/' in filename else ''
        payload[filename]=''.join(sha(b)+'  '+n[len(folder):]+'\n' for n,b in sorted(payload.items())
                                  if n.startswith(folder) and n not in sums).encode('ascii')
    for n,b in originals.items():
        assert n in allowed or payload[n]==b, 'Original executable/script/data changed: '+n
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(payload.items()):
            info=infos.get(name,zipfile.ZipInfo(name,(2026,10,26,0,0,0)))
            if name not in infos:info.external_attr=0o644<<16
            z.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        for n,b in originals.items():
            assert n in allowed or z.read(n)==b
        for filename in sums:
            folder=filename.rsplit('/',1)[0]+'/' if '/' in filename else ''
            for line in z.read(filename).decode('ascii').splitlines():
                expected,name=line.split('  ',1)
                assert sha(z.read(folder+name))==expected
    return proof
