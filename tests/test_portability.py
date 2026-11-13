"""Regression checks for portable sources and reviewed distribution assets."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_portability import POLICY, audit, missing_links, text_findings


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY.read_text())

    def test_previously_published_machine_names_are_rejected_in_paths_and_text(self):
        # Store the regression input encoded so the forbidden name is not republished.
        name = bytes.fromhex("636c6177").decode() + "-remote"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = "docs/" + name + "/report.md"
            (root / path).parent.mkdir(parents=True)
            (root / path).write_text("Connect to " + name)
            result = audit(root, self.policy, {}, files=[path])
        self.assertFalse(result["passed"])
        self.assertEqual({x["rule"] for x in result["findings"]},
                         {"path-machine-or-owner-identifier", "machine-or-owner-identifier"})

    def test_unknown_personal_paths_emails_and_addresses_are_rejected(self):
        inputs = [
            ("/Users/" + "developer-account/projects/app", "personal-absolute-path"),
            ("C:" + chr(92) + "Users" + chr(92) + "developer-account" + chr(92) + "app", "personal-absolute-path"),
            ("person@" + "business.com", "non-example-email"),
            ("10." + "12.34.56", "non-example-ipv4"),
        ]
        for text, rule in inputs:
            with self.subTest(rule=rule, text=text):
                self.assertIn((1, rule), text_findings(text, self.policy))

    def test_generic_examples_runtime_homes_and_public_branding_are_allowed(self):
        text = "\n".join(["$HOME/.local/bin/agent-fleet", "/home/agentpool/bin/agent-fleet",
                          "user@example.invalid", "127.0.0.1", "192.0.2.10", "THE-FIN · Codex · Claude"])
        self.assertEqual(text_findings(text, self.policy), [])

    def test_security_fixtures_can_test_userinfo_on_real_provider_urls(self):
        self.assertEqual(text_findings("https://user@claude.com", self.policy), [])
        self.assertEqual(text_findings("https://attacker@claude.com", self.policy), [])

    def test_binary_asset_requires_its_exact_reviewed_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "sample.png"
            image.write_bytes(b"\x89PNG\0fixture")
            result = audit(root, self.policy, {}, files=[image.name])
            self.assertEqual(result["findings"][0]["rule"], "unreviewed-binary")
            assets = {image.name: {"sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                                   "purpose": "Controlled image fixture"}}
            self.assertTrue(audit(root, self.policy, assets, files=[image.name])["passed"])
            image.write_bytes(b"\x89PNG\0changed")
            self.assertFalse(audit(root, self.policy, assets, files=[image.name])["passed"])

    def test_broken_documentation_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("[Install](docs/install.md)")
            result = audit(root, self.policy, {}, files=["README.md"])
            self.assertEqual(result["findings"][0]["rule"], "missing-local-link")
            (root / "docs").mkdir()
            (root / "docs/install.md").write_text("# Install")
            self.assertTrue(audit(root, self.policy, {}, files=["README.md", "docs/install.md"])["passed"])

    def test_frontend_root_paths_resolve_against_the_public_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "desktop/public/brand").mkdir(parents=True)
            (root / "desktop/public/brand/icon.svg").write_text("<svg/>")
            self.assertEqual(missing_links(root, root / "desktop/index.html",
                                           '<link href="/brand/icon.svg">'), [])

    def test_runtime_state_cannot_be_added_even_with_generic_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'auth.json').write_text('{}')
            result = audit(root, self.policy, {}, files=['auth.json'])
            self.assertEqual(result['findings'][0]['rule'], 'runtime-state-in-source')

    def test_external_symlinks_are_checked_without_reading_the_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'external').symlink_to(root / '../missing-external')
            result = audit(root, self.policy, {}, files=['external'])
            self.assertEqual(result['files'][0]['kind'], 'symlink')
            self.assertEqual(result['findings'][0]['rule'], 'external-or-dangling-symlink')


if __name__ == "__main__":
    unittest.main()
