"""Actual v2 packaging helpers with synthetic files; no firmware/device access."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from package_v2 import (CURRENT_REPOSITORY, LAYOUT, RENAMED_REPOSITORY, check_variant,
                        language_variants, repository_url, validate_version, write_sums, zip_dir)

WIFI_ASSETS = b'firmware.bin\0firmware-it.bin\0firmware-es.bin\0firmware-zh.bin\0'


def synthetic_build(folder, root, language='en', ethernet=False, version='2.0.0', boot=b'boot'):
    """Metadata-only build folder: not an ESP image."""
    (folder/'config').mkdir(parents=True, exist_ok=True)
    (folder/'project_description.json').write_text(json.dumps({
        'project_name': 'esp32_tsr', 'project_version': version, 'project_path': str(root)}))
    flags = '#define CONFIG_LWIP_MAX_SOCKETS 31\n#define CONFIG_TSR_UI_LANGUAGE "%s"\n' % language
    if ethernet: flags += '#define CONFIG_ETH_SPI_ETHERNET_W5500 1\n'
    (folder/'config/sdkconfig.h').write_text(flags)
    assets = b'firmware-eth.bin\0' if ethernet else WIFI_ASSETS
    (folder/'firmware.bin').write_bytes(f'synthetic {version} {language} '.encode() + assets)
    for name in LAYOUT:
        if name != 'firmware.bin': (folder/name).write_bytes(boot + name.encode())


class V2PackagingTests(unittest.TestCase):
    def test_repository_does_not_rename_itself(self):
        self.assertEqual(repository_url(CURRENT_REPOSITORY),
                         'https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery')
        self.assertEqual(repository_url(RENAMED_REPOSITORY),
                         'https://github.com/Mattboxx/esp32-tailnet-gateway')
        for value in ('https://example.com', '../other', 'OtherOwner/firmware', ''):
            with self.assertRaises(AssertionError): repository_url(value)

    def test_version_channel_is_explicit(self):
        validate_version('2.0.0', '2.0.0', False)
        validate_version('2.0.0-rc.1', '2.0.0-rc.1', True)
        for version, source, prerelease in (('2.0.0-rc.1', '2.0.0-rc.1', False),
                                            ('2.0.0', '2.0.0-rc.1', False),
                                            ('2.0.0', '2.0.0', True),
                                            ('0.1.38-Mattboxx-1.99', '0.1.38-Mattboxx-1.99', False)):
            with self.assertRaises(AssertionError): validate_version(version, source, prerelease)

    def test_exact_checksums_lf_and_reproducible_archive_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); package = base/'package'; package.mkdir()
            payload = b'synthetic binary fixture, not firmware\x00\xff'
            (package/'firmware.bin').write_bytes(payload)
            (package/'install.sh').write_bytes(b'#!/bin/sh\nexit 0\n')
            write_sums(package, ['install.sh', 'firmware.bin'])
            checks = (package/'SHA256SUMS.txt').read_bytes()
            self.assertNotIn(b'\r', checks)
            self.assertIn(hashlib.sha256(payload).hexdigest().encode()+b'  firmware.bin\n', checks)
            first, second = base/'a.zip', base/'b.zip'
            zip_dir(package, first, 'Gateway'); zip_dir(package, second, 'Gateway')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.read('Gateway/firmware.bin'), payload)
                self.assertEqual((archive.getinfo('Gateway/install.sh').external_attr >> 16) & 0o777, 0o755)

    def test_variant_metadata_and_updater_asset_guards(self):
        # Metadata checks only: not ESP image validation or hardware.
        from package_v2 import ROOT
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for ethernet in (False, True):
                synthetic_build(folder, ROOT, ethernet=ethernet)
                self.assertEqual(check_variant(folder, ethernet, '2.0.0')['project_name'], 'esp32_tsr')
                with self.assertRaises(AssertionError): check_variant(folder, not ethernet, '2.0.0')
                with self.assertRaises(AssertionError): check_variant(folder, ethernet, '2.0.1')
                with self.assertRaises(AssertionError): check_variant(folder, ethernet, '2.0.0', 'it')
            (folder/'config/sdkconfig.h').write_text('#define CONFIG_LWIP_MAX_SOCKETS 16\n')
            with self.assertRaises(AssertionError): check_variant(folder, False, '2.0.0')

    def test_language_variants_are_tested_and_share_boot_files(self):
        import hashlib
        from package_v2 import ROOT
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            english, italian, spanish = base/'en', base/'it', base/'es'
            synthetic_build(english, ROOT); synthetic_build(italian, ROOT, 'it'); synthetic_build(spanish, ROOT, 'es')
            digest = lambda folder: hashlib.sha256((folder/'firmware.bin').read_bytes()).hexdigest()
            found = language_variants(english, [f'it={italian}', f'es={spanish}'],
                                      [f'it={digest(italian)}', f'es={digest(spanish)}'], '2.0.0')
            self.assertEqual(list(found), ['it', 'es'])
            self.assertEqual(language_variants(english, [], [], '2.0.0'), {})
            bad = ([f'it={italian}'], [f'it={"0" * 64}'])                       # untested image
            with self.assertRaises(AssertionError): language_variants(english, *bad, '2.0.0')
            with self.assertRaises(AssertionError):                            # no hash given
                language_variants(english, [f'it={italian}'], [], '2.0.0')
            with self.assertRaises(AssertionError):                            # wrong language
                language_variants(english, [f'es={italian}'], [f'es={digest(italian)}'], '2.0.0')
            with self.assertRaises(AssertionError):                            # unknown language
                language_variants(english, [f'fr={italian}'], [f'fr={digest(italian)}'], '2.0.0')
            synthetic_build(italian, ROOT, 'it', boot=b'other')                # different boot files
            with self.assertRaises(AssertionError):
                language_variants(english, [f'it={italian}'], [f'it={digest(italian)}'], '2.0.0')


if __name__ == '__main__': unittest.main()
