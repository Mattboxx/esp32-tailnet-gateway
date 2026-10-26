"""Offline attribution/notice regression checks, not a legal certification."""
from pathlib import Path
import hashlib
import json
import re
import unittest
import yaml
from package_release import source_notice_blocks, toolchain_notice_files

ROOT=Path(__file__).resolve().parents[1]

class LicenseComplianceTests(unittest.TestCase):
    def test_original_mit_notice_is_intact(self):
        payload=(ROOT/'LICENSE').read_text(encoding='utf-8').encode()
        blob=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        self.assertEqual(blob,'2694857e74627637b7f58da11e8f0556a74f7498',
                         'Recheck original upstream MIT text; no relicensing was intended')

    def test_actual_dependency_and_original_author_are_named(self):
        notice=' '.join((ROOT/'NOTICE.md').read_text(encoding='utf-8').split())
        modules=(ROOT/'.gitmodules').read_text()
        url=re.search(r'url\s*=\s*(\S+)',modules)[1].removesuffix('.git')
        self.assertIn(url,notice)
        for item in ('Csontikka/esp32-tailscale-subnet-router','Csontikka/microlink',
                     'CamM2325/microlink','Cameron Malone','2021 Daniel Hope',
                     'Cryptography Research, Inc.','GCC Runtime Library Exception'):
            self.assertIn(item,notice)
        original=(ROOT/'external/microlink/LICENSE').read_text()
        self.assertIn('Copyright (c) 2025-2026 Cameron Malone',original)
        # Upstream stores CRLF (blob befb8e0); compare normalized text across
        # Windows/Linux checkouts without changing the original license file.
        payload=original.encode('utf-8')
        self.assertEqual(hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest(),
                         'd7a5dc6489961477cf05067466cb2f3c00512b65')

    def test_citation_describes_this_edition_and_separate_upstreams(self):
        citation=yaml.safe_load((ROOT/'CITATION.cff').read_text(encoding='utf-8'))
        self.assertEqual(citation['license'],'MIT')
        stable=re.findall(r'^## \[(\d+\.\d+\.\d+)\]',(ROOT/'CHANGELOG.md').read_text(encoding='utf-8'),re.M)[0]
        self.assertEqual(citation['version'],stable)
        urls={r['repository-code'] for r in citation['references']}
        self.assertTrue({'https://github.com/Mattboxx/microlink','https://github.com/Csontikka/microlink',
                         'https://github.com/CamM2325/microlink'}.issubset(urls))
        self.assertIn('not an additional license condition',citation['message'])

    def test_verbatim_leading_notices_not_code_or_buried_comments(self):
        block='/* Copyright (c) Example\n * Redistribution and use in binary form.\n * AS IS.\n */'
        text='/* file overview */\n'+block+'\n#include <x>\n/* Copyright not a leading notice */'
        self.assertEqual(list(source_notice_blocks(text)),[block])
        line='// Copyright Example\n// Permission is hereby granted\n// AS IS.'
        self.assertEqual(list(source_notice_blocks(line+'\nint x;')),[line])

    def test_missing_compiler_does_not_silently_drop_runtime_licenses(self):
        with self.assertRaisesRegex(AssertionError,'Exact build compiler'):
            list(toolchain_notice_files({}))

    def test_website_has_full_pinned_dependency_legal_material(self):
        folder=ROOT/'website/assets/esp-web-tools/10.4.0'
        provenance=json.loads((folder/'dependency-license-provenance.json').read_text())
        text=(folder/'DEPENDENCY-LICENSES.txt').read_text(encoding='utf-8')
        self.assertEqual(provenance['installer_version'],'10.4.0')
        self.assertEqual(len(provenance['dependencies']),12)
        for package in provenance['dependencies']:
            self.assertTrue(package['notices'])
            self.assertIn(package['lock_path']+' @ '+package['version'],text)
        for phrase in ('Google LLC','Microsoft Corporation','Redistribution and use',
                       'Permission is hereby granted'):
            self.assertIn(phrase,text)

    def test_donations_and_independence_are_not_removed(self):
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn('https://ko-fi.com/mattboxx',readme)
        self.assertIn('https://github.com/sponsors/Csontikka',readme)
        self.assertIn('not affiliated',(ROOT/'NOTICE.md').read_text(encoding='utf-8').replace('\n',' ').replace('**',''))

    def test_current_firmware_supplement_covers_known_omissions(self):
        payload=(ROOT/'licenses/firmware-v3.0.2-notices.txt').read_bytes()
        text=payload.decode('utf-8')
        provenance=json.loads((ROOT/'licenses/firmware-v3.0.2-provenance.json').read_text())
        self.assertEqual(hashlib.sha256(payload).hexdigest(),provenance['notices_sha256'])
        self.assertEqual(payload,(ROOT/'website/firmware/3.0.2/FIRMWARE-LICENSES.txt').read_bytes())
        for phrase in ('Copyright (c) 2026 Csontikka','2025-2026 Cameron Malone',
                       'Copyright (c) 2021 Daniel Hope','2015 Verisure Innovation AB',
                       'toolchain/share/licenses/newlib/COPYING.NEWLIB','GCC RUNTIME LIBRARY EXCEPTION',
                       'ESP-IDF/components/wpa_supplicant/README'):
            self.assertIn(phrase,text)

if __name__=='__main__':unittest.main()
