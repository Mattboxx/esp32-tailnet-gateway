"""Behavior tests with synthetic legal/image fixtures, no device or remote writes."""
from pathlib import Path
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from collect_historical_notices import app_description, leading_source_text
from prepare_license_archive import prepare, source_bundle_index

URL='https://github.com/Mattboxx/esp32-tailnet-gateway/releases/download/v3.0.2/source.tar.gz'


class RemediationTests(unittest.TestCase):
    def archive_case(self,prefix):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'original.zip';new=root/'legal.zip'
            entries={prefix+'firmware.bin':b'synthetic image\x00\xff',prefix+'esptool.exe':b'synthetic tool',
                     prefix+'install.sh':b'#!/bin/sh\nexit 0\n',prefix+'FIRMWARE-LICENSES.txt':b'Original notice must survive',
                     prefix+'release-manifest.json':json.dumps({'version':'fixture','files':{}}).encode()}
            with zipfile.ZipFile(old,'w') as z:
                for n,b in entries.items():z.writestr(n,b)
            before=old.read_bytes()
            prepare(old,new,b'Expanded original copyright terms',b'Desktop license',URL,'a'*64)
            self.assertEqual(before,old.read_bytes())
            with zipfile.ZipFile(new) as z:
                for n in ('firmware.bin','esptool.exe','install.sh'):self.assertEqual(z.read(prefix+n),entries[prefix+n])
                self.assertIn(entries[prefix+'FIRMWARE-LICENSES.txt'],z.read(prefix+'FIRMWARE-LICENSES.txt'))
                self.assertIn(b'Expanded original copyright terms',z.read(prefix+'FIRMWARE-LICENSES.txt'))
                for line in z.read(prefix+'SHA256SUMS.txt').decode().splitlines():
                    sha,name=line.split('  ',1);self.assertEqual(hashlib.sha256(z.read(prefix+name)).hexdigest(),sha)

    def test_flat_archive(self):self.archive_case('')
    def test_nested_archive(self):self.archive_case('Gateway/')

    def test_never_overwrite_original(self):
        with self.assertRaisesRegex(AssertionError,'Never replace'):
            prepare(Path('same.zip'),Path('same.zip'),b'',b'',URL,'a'*64)

    def test_untrusted_source_url_rejected(self):
        with self.assertRaises(AssertionError):prepare(Path('old.zip'),Path('new.zip'),b'',b'','http://example.invalid/','a'*64)

    def bundle(self,path,tamper=False):
        source=b'synthetic source';source_hash=hashlib.sha256(source).hexdigest()
        doc={'executable_sha256':'a'*64,'verified_python_modules':1,'archives':[{'filename':'esptool-5.3.1.tar.gz','sha256':source_hash},{'filename':'legacy-stub.tar.gz','sha256':source_hash}]}
        raw=json.dumps(doc).encode();digest=hashlib.sha256(raw).hexdigest()
        items={'source-index.json':raw,'SHA256SUMS.txt':((('b'*64) if tamper else digest)+'  source-index.json\n').encode(),
               'sources/esptool-5.3.1.tar.gz':source,'sources/legacy-stub.tar.gz':source,
               'verified-modules.json':json.dumps([{'matched':True}]).encode()}
        with tarfile.open(path,'w:gz') as z:
            for n,b in items.items():info=tarfile.TarInfo(n);info.size=len(b);z.addfile(info,io.BytesIO(b))

    def test_tool_digest_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.tar.gz';self.bundle(p)
            self.assertEqual(source_bundle_index(p,'a'*64)['executable_sha256'],'a'*64)
            with self.assertRaisesRegex(AssertionError,'does not match'):source_bundle_index(p,'b'*64)

    def test_tampered_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.tar.gz';self.bundle(p,True)
            with self.assertRaisesRegex(AssertionError,'checksum mismatch'):source_bundle_index(p,'a'*64)

    def test_descriptor_and_malformed_images(self):
        data=bytearray(208);data[0]=0xe9;data[32:36]=bytes.fromhex('3254cdab')
        for offset,value in ((48,b'fixture'),(80,b'esp32_tsr'),(144,b'5.3.1')):data[offset:offset+len(value)]=value
        self.assertEqual(app_description(data)['sdk'],'5.3.1')
        for bad in (b'',b'bad',bytes(208)):
            with self.assertRaises(AssertionError):app_description(bad)

    def test_non_utf8_code_body_does_not_corrupt_notices(self):
        raw=b'/* Copyright original author */\nint legacy = 1; /* \xb5 */'
        self.assertEqual(leading_source_text(raw),'/* Copyright original author */')


if __name__=='__main__':unittest.main()
