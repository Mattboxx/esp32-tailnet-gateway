"""Synthetic fixtures are constructed at runtime, never real credentials."""
import base64
import unittest
from check_sensitive_data import credential_findings


class ScannerTests(unittest.TestCase):
    def test_blocked_file_names_and_exact_exceptions(self):
        from check_sensitive_data import blocked_file
        config = {'blocked_files': ['*HANDOFF*.md', 'secrets/**'], 'allowed_files': ['docs/CODEX-PUBLISH-HANDOFF.md']}
        self.assertFalse(blocked_file('docs/CODEX-PUBLISH-HANDOFF.md', config))
        for name in ('HANDOFF.md', 'docs/OTHER-HANDOFF.md', 'notes/CODEX-PUBLISH-HANDOFF.md', 'secrets/x'):
            self.assertTrue(blocked_file(name, config), name)

    def test_tokens(self):
        fixtures = [(b"tskey" + b"-auth-" + b"x" * 24, "Tailscale/Headscale auth key"),
                    (b"ghp" + b"_" + b"x" * 36, "GitHub token"),
                    (b"AKIA" + b"X" * 16, "AWS access key")]
        for data, expected in fixtures:
            self.assertIn(expected, credential_findings(data))

    def test_parser_markers_are_not_private_keys(self):
        begin = b"-----BEGIN " + b"PRIVATE KEY-----"
        end = b"-----END " + b"PRIVATE KEY-----"
        self.assertFalse(credential_findings(begin + b"\0" + end))
        data = begin + b"\n" + base64.b64encode(b"test-fixture" * 8) + end
        self.assertIn("Embedded private key", credential_findings(data))

    def test_artifact_paths_and_userinfo(self):
        self.assertIn("Developer home path", credential_findings(b"/home/" + b"example/build", True))
        self.assertIn("Credentials embedded in URL",
                      credential_findings(b"https://" + b"user:password@example.invalid", True))
        self.assertFalse(credential_findings(b"https://example.invalid"))


if __name__ == "__main__":
    unittest.main()
