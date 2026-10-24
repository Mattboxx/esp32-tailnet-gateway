"""Actual v2 packaging helpers with synthetic files; no firmware/device access."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from package_v2 import (CURRENT_REPOSITORY, RENAMED_REPOSITORY, check_build,
                        repository_url, validate_version, write_sums, zip_dir)


def synthetic_build(folder, root, version='3.0.0', ethernet=True, flash='8MB', assets=b'firmware.bin\0'):
    """Metadata-only build folder: not an ESP image."""
    (folder/'config').mkdir(parents=True, exist_ok=True)
    (folder/'project_description.json').write_text(json.dumps({
        'project_name': 'esp32_tsr', 'project_version': version, 'project_path': str(root)}))
    flags = '#define CONFIG_LWIP_MAX_SOCKETS 31\n#define CONFIG_ESPTOOLPY_FLASHSIZE "%s"\n' % flash
    if ethernet: flags += '#define CONFIG_ETH_SPI_ETHERNET_W5500 1\n'
    (folder/'config/sdkconfig.h').write_text(flags)
    (folder/'firmware.bin').write_bytes(f'synthetic {version} '.encode() + assets)


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

    def test_single_image_metadata_and_updater_asset_guards(self):
        # Metadata checks only: not ESP image validation or hardware.
        from package_v2 import ROOT
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            synthetic_build(folder, ROOT)
            self.assertEqual(check_build(folder, '3.0.0')['project_name'], 'esp32_tsr')
            with self.assertRaises(AssertionError): check_build(folder, '3.0.1')
            for broken in (dict(ethernet=False), dict(flash='4MB'),
                           dict(assets=b'firmware.bin\0firmware-eth.bin\0'), dict(assets=b'nothing')):
                synthetic_build(folder, ROOT, **broken)
                with self.assertRaises(AssertionError): check_build(folder, '3.0.0')
            synthetic_build(folder, ROOT)
            (folder/'config/sdkconfig.h').write_text('#define CONFIG_LWIP_MAX_SOCKETS 16\n')
            with self.assertRaises(AssertionError): check_build(folder, '3.0.0')


class BridgePackagingTests(unittest.TestCase):
    def test_only_a_release_bridge_build_is_packaged(self):
        from package_v2 import ROOT
        from package_bridge import OTA1_2X, SLOT_2X, bridge_version, check_bridge
        version = bridge_version()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder/'config').mkdir()
            (folder/'project_description.json').write_text(json.dumps({
                'project_name': 'esp32_tsr', 'project_version': version, 'project_path': str(ROOT)}))
            good = ('#define CONFIG_LWIP_MAX_SOCKETS 31\n#define CONFIG_TSR_MIGRATION_BRIDGE 1\n'
                    '#define CONFIG_TSR_MIGRATION_SOURCE_URL ""\n#define CONFIG_ESPTOOLPY_FLASHSIZE "4MB"\n')
            table = bytearray(b'\xff' * 3072); table[128:140] = OTA1_2X

            def build(config=good, image=None, part=bytes(table)):
                (folder/'config/sdkconfig.h').write_text(config)
                (folder/'firmware.bin').write_bytes(image if image is not None else f'synthetic {version}'.encode())
                (folder/'partitions.bin').write_bytes(part)
            build(); self.assertEqual(check_bridge(folder, version)['project_name'], 'esp32_tsr')
            for broken in (dict(config=good.replace('""', '"http://192.0.2.1:8765"')),           # bench source
                           dict(config=good.replace('BRIDGE 1', 'BRIDGE 0')),                     # not the bridge
                           dict(config=good.replace('"4MB"', '"8MB"')),                           # 3.x header
                           dict(config=good + '#define CONFIG_ETH_SPI_ETHERNET_W5500 1\n'),       # too big a build
                           dict(image=b'x' * (SLOT_2X + 1)),                                     # does not fit a 2.x slot
                           dict(part=b'\xff' * 3072)):                                           # not the 2.x table
                build(**broken)
                with self.assertRaises(AssertionError): check_bridge(folder, version)


if __name__ == '__main__': unittest.main()
