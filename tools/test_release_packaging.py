"""Release-channel labeling must be explicit and match the build version."""
import unittest
import json
import tempfile
from pathlib import Path
from package_release import validate_release_version, collect_release_notices


class PackagingVersionTests(unittest.TestCase):
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
