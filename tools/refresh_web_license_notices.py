"""Collect unmodified npm license texts for the pinned browser installer.

Never changes installer code. Verifies the original tarball and every shipped
JS file, then uses the release's pinned lockfile/integrities for its runtime
dependency closure. Requires network; ordinary builds use the checked-in texts.
"""
from pathlib import Path
import base64
import hashlib
import io
import json
import subprocess
import tarfile
import urllib.request
from package_release import source_notice_blocks

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'website/assets/esp-web-tools/10.4.0'
REV = 'fab2ba48253d19fd29a15af57bec771d34978b62'
TARBALL_SHA = 'f18da75335d2f0dca044c4bb052848c0696e7b03cc23d61d8530dd6eba0a9008'
SHIM_LICENSE = 'https://raw.githubusercontent.com/lit/lit/b4e3c0ef472b89aee09c1ecf194e2bbb9b1441f7/LICENSE'

def fetch(url):
    assert url==SHIM_LICENSE or url.startswith(('https://registry.npmjs.org/','https://raw.githubusercontent.com/esphome/esp-web-tools/'))
    with urllib.request.urlopen(url,timeout=45) as r:
        data=r.read(20*1024*1024+1)
    assert len(data)<=20*1024*1024,'Oversized notice input'
    return data

def archive(data):
    return tarfile.open(fileobj=io.BytesIO(data),mode='r:gz')

def resolve(packages,parent,name):
    while True:
        candidate=(parent+'/' if parent else '')+'node_modules/'+name
        if candidate in packages: return candidate
        assert parent,'Dependency missing from pinned lock: '+name
        parent=parent.rsplit('/node_modules/',1)[0] if '/node_modules/' in parent else ''

def main():
    meta=json.loads(fetch('https://registry.npmjs.org/esp-web-tools/10.4.0'))
    assert meta['gitHead']==REV
    bundle=fetch(meta['dist']['tarball'])
    assert hashlib.sha256(bundle).hexdigest()==TARBALL_SHA
    with archive(bundle) as tar:
        for p in DEST.glob('*.js'):
            original=tar.extractfile('package/dist/web/'+p.name).read()
            tracked=subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
            assert original==tracked,p.name+' Git payload differs from original npm distribution'
            assert p.read_bytes().replace(b'\r\n',b'\n')==tracked.replace(b'\r\n',b'\n'),p.name+' has working-tree code changes'
    lock_bytes=fetch(f'https://raw.githubusercontent.com/esphome/esp-web-tools/{REV}/package-lock.json')
    packages=json.loads(lock_bytes)['packages']
    pending=[('',name) for name in packages['']['dependencies']]
    selected=set()
    while pending:
        parent,name=pending.pop()
        key=resolve(packages,parent,name)
        if key in selected: continue
        selected.add(key)
        pending.extend((key,n) for n in packages[key].get('dependencies',{}))
    records=[]; texts=[]
    for key in sorted(selected):
        entry=packages[key]
        data=fetch(entry['resolved'])
        algorithm,expected=entry['integrity'].split('-',1)
        assert algorithm in ('sha512','sha1')
        assert base64.b64encode(hashlib.new(algorithm,data).digest()).decode()==expected,key
        found=[]
        headers=set()
        with archive(data) as tar:
            for member in tar.getmembers():
                name=Path(member.name).name.upper()
                if member.isfile() and member.name.endswith(('.js','.mjs','.cjs')):
                    prefix=tar.extractfile(member).read(65536).decode('utf-8')
                    for block in source_notice_blocks(prefix):
                        if block not in headers:
                            texts.append('\n\n===== '+key+' @ '+entry['version']+' / '+member.name+' (source notice) =====\n\n'+block)
                            headers.add(block)
                if not member.isfile() or not name.startswith(('LICENSE','LICENCE','COPYING','NOTICE','COPYRIGHT')):
                    continue
                assert member.size<=1024*1024,'Oversized legal text'
                payload=tar.extractfile(member).read()
                text=payload.decode('utf-8')
                texts.append('\n\n===== '+key+' @ '+entry['version']+' / '+member.name+' =====\n\n'+text)
                found.append(dict(path=member.name,sha256=hashlib.sha256(payload).hexdigest()))
        if not found and key=='node_modules/@lit-labs/ssr-dom-shim':
            assert entry['version']=='1.2.0','Re-audit the shim source license on version changes'
            payload=fetch(SHIM_LICENSE)
            texts.append('\n\n===== '+key+' @ 1.2.0 / upstream monorepo LICENSE =====\n\n'+payload.decode('utf-8'))
            found.append(dict(path='upstream LICENSE',url=SHIM_LICENSE,sha256=hashlib.sha256(payload).hexdigest()))
        assert found,'No license text found for '+key
        records.append(dict(lock_path=key,version=entry['version'],tarball=entry['resolved'],
                            integrity=entry['integrity'],notices=found,source_header_notice_count=len(headers)))
    header=('Verbatim upstream license and copyright texts for the runtime dependency closure\n'
            'of ESP Web Tools 10.4.0. Conservative inclusion does not assert that every\n'
            'dependency survives browser bundling. Each dependency retains its own terms.\n'
            'Installer code is unmodified. Reproduce with tools/refresh_web_license_notices.py.\n')
    (DEST/'DEPENDENCY-LICENSES.txt').write_bytes((header+''.join(texts)).encode('utf-8'))
    provenance=dict(installer_version='10.4.0',source_revision=REV,tarball_sha256=TARBALL_SHA,
                    lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),dependencies=records)
    (DEST/'dependency-license-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(f'PASS original installer JS verified; {len(records)} pinned dependency packages with verbatim legal texts')

if __name__=='__main__': main()
