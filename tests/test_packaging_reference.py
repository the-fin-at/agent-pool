"""Packaging references follow the checked-out source, not a prior workstation build."""
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.package_native_release import load_reference


class PackagingReferenceTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'Cargo.toml'
        self.version = tomllib.loads(source.read_text())['workspace']['package']['version']

    def reference(self, version, commit='a' * 40):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'reference.json'
            path.write_text(json.dumps({'version': version, 'reviewed_implementation_commit': commit}))
            return load_reference(path)

    def test_current_source_version_can_be_packaged(self):
        self.assertEqual(self.reference(self.version)['version'], self.version)

    def test_reference_for_a_different_source_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'current source version'):
            self.reference('0.0.0')

    def test_source_provenance_is_required(self):
        with self.assertRaisesRegex(ValueError, 'reviewed source commit'):
            self.reference(self.version, 'unreviewed')
