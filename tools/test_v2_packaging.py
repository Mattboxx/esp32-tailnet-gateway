"""Actual v2 packaging helpers with synthetic files; no firmware/device access."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from package_v2 import (CURRENT_REPOSITORY, RENAMED_REPOSITORY, check_variant,
                        repository_url, validate_version, write_sums, zip_dir)


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
            folder = Path(directory); (folder/'config').mkdir()
            (folder/'project_description.json').write_text(json.dumps({
                'project_name': 'esp32_tsr', 'project_version': '2.0.0', 'project_path': str(ROOT)}))
            for ethernet in (False, True):
                flags = '#define CONFIG_LWIP_MAX_SOCKETS 31\n'
                if ethernet: flags += '#define CONFIG_ETH_SPI_ETHERNET_W5500 1\n'
                (folder/'config/sdkconfig.h').write_text(flags)
                asset = b'/firmware-eth.bin' if ethernet else b'/firmware.bin'
                (folder/'firmware.bin').write_bytes(b'synthetic 2.0.0 '+asset)
                self.assertEqual(check_variant(folder, ethernet, '2.0.0')['project_name'], 'esp32_tsr')
                with self.assertRaises(AssertionError): check_variant(folder, not ethernet, '2.0.0')
                with self.assertRaises(AssertionError): check_variant(folder, ethernet, '2.0.1')
            (folder/'config/sdkconfig.h').write_text('#define CONFIG_LWIP_MAX_SOCKETS 16\n')
            with self.assertRaises(AssertionError): check_variant(folder, False, '2.0.0')


if __name__ == '__main__': unittest.main()
