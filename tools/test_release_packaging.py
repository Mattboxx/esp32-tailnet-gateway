"""Release-channel labeling must be explicit and match the build version."""
import unittest
from package_release import validate_release_version


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


if __name__ == '__main__':
    unittest.main()
