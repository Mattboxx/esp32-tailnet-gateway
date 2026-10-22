"""Release-channel labeling must be explicit and match the build version."""
import unittest
import json
import tempfile
from pathlib import Path
from package_release import (validate_release_version, collect_release_notices,
                             upstream_release_reference, validate_build_description,
                             release_readme, release_manifest, VARIANTS)


class PackagingVersionTests(unittest.TestCase):
    def test_variants_have_distinct_assets_and_honest_readme(self):
        version = '0.1.38-Mattboxx-1.14-dev.6'
        self.assertEqual(VARIANTS['wifi'][1], 'firmware.bin')
        self.assertEqual(VARIANTS['eth'][1], 'firmware-eth.bin')
        self.assertEqual(len({v[1] for v in VARIANTS.values()} | {v[2] for v in VARIANTS.values()}), 4)
        wifi, eth = release_readme(version, True, 'wifi'), release_readme(version, True, 'eth')
        self.assertIn('ESP32 TAILNET GATEWAY', wifi)
        self.assertIn('Development candidate (pre-release)', wifi)
        self.assertIn('not an official Tailscale client', wifi)
        self.assertNotIn('firmware-eth', wifi)
        self.assertIn('W5500', eth); self.assertIn('not validated on real', eth); self.assertIn('firmware-eth-factory.bin', eth)
        self.assertIn('Stable community release', release_readme('0.1.38-Mattboxx-1.14', False, 'wifi'))
        manifest = release_manifest(version, True, 'eth', {'firmware-eth.bin': {'sha256': '0' * 64, 'bytes': 1}}, {'project_name': 'esp32_tsr'})
        self.assertEqual((manifest['channel'], manifest['update_asset'], manifest['app_identity']), ('pre-release', 'firmware-eth.bin', 'esp32_tsr'))

    def test_external_build_directory_has_exact_project_and_version(self):
        root = Path(__file__).resolve().parents[1]
        version = '0.1.38-Mattboxx-1.13-dev.1'
        description = dict(project_name='esp32_tsr', project_version=version, project_path=str(root))
        validate_build_description(description, root, version)
        legacy = dict(description)
        legacy['project_dir'] = legacy.pop('project_path')
        validate_build_description(legacy, root, version)
        for field, value in (('project_name', 'other'), ('project_version', '0.1.1'),
                             ('project_path', str(root.parent)), ('project_path', '')):
            with self.assertRaises(AssertionError):
                validate_build_description({**description, field: value}, root, version)

    def test_flashing_instructions_follow_upstream_base(self):
        for version in ('0.1.31-Mattboxx-1.11', '0.1.33-Mattboxx-1.12',
                        '0.1.33-Mattboxx-1.12-dev.1', '0.1.99-Mattboxx-2.0'):
            base = version.split('-Mattboxx-', 1)[0]
            self.assertEqual(upstream_release_reference(version),
                             f'Based on Csontikka/esp32-tailscale-subnet-router v{base}.')
        with self.assertRaises(AssertionError):
            upstream_release_reference('not-a-release')

    def test_stable(self):
        validate_release_version('0.1.31-Mattboxx-1.10', '0.1.31-Mattboxx-1.10', False)

    def test_candidate(self):
        version = '0.1.31-Mattboxx-1.10-dev.10'
        validate_release_version(version, version, True)

    def test_mismatches(self):
        stable = '0.1.31-Mattboxx-1.10'
        beta = stable + '-dev.10'
        for version, current, prerelease in ((beta, beta, False), (stable, stable, True),
                                            (beta, stable, True), (stable, beta, False),
                                            ('0.1.31', '0.1.31', False),
                                            (beta + '-other', beta + '-other', True)):
            with self.assertRaises(AssertionError):
                validate_release_version(version, current, prerelease)

    def test_original_notices_and_no_local_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, idf, build = base / 'project', base / 'sdk', base / 'build'
            names = ['LICENSE', 'NOTICE.md', 'external/microlink/LICENSE',
                     'external/microlink/x25519-license.txt',
                     'external/microlink/components/microlink/components/wireguard_lwip/LICENSE']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('Original copyright: ' + name, encoding='utf-8')
            idf.mkdir(); build.mkdir()
            (idf / 'LICENSE').write_text('Original SDK license', encoding='utf-8')
            component = idf / 'components/example'
            component.mkdir(parents=True)
            (component / 'COPYING').write_text('Component redistribution terms', encoding='utf-8')
            (component / 'NOTICE.c').write_text('Not a license document', encoding='utf-8')
            (build / 'project_description.json').write_text(json.dumps({
                'idf_path': str(idf), 'build_component_paths': [str(component), '']}), encoding='utf-8')
            notices = collect_release_notices(root, build)
            for name in names:
                self.assertIn('Original copyright: ' + name, notices)
            self.assertIn('Original SDK license', notices)
            self.assertIn('Component redistribution terms', notices)
            self.assertNotIn(str(base), notices)
            self.assertNotIn('Not a license document', notices)

    def test_missing_original_license_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'project_description.json').write_text(json.dumps({
                'idf_path': str(root), 'build_component_paths': []}), encoding='utf-8')
            with self.assertRaises(AssertionError):
                collect_release_notices(root, root)


if __name__ == '__main__':
    unittest.main()
