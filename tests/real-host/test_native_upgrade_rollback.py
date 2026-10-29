"""Safety checks exercise the opt-in harness as a process, not its internals."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/test_native_upgrade_rollback.py"


@unittest.skipIf(os.name == "nt", "Linux handover harness uses executable POSIX fixtures")
class UpgradeRollbackSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fleet-upgrade-safety-")
        self.root = Path(self.temp.name)
        self.programs = []
        for name, version in (("old", "0.4.2"), ("new", "0.5.0"), ("provider", "controlled-native-provider-0.5")):
            path = self.root / name
            path.write_text("#!" + sys.executable + "\nprint(" + repr(version) + ")\n")
            path.chmod(0o700)
            self.programs.append(path)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, scratch, *extra):
        old, new, provider = self.programs
        return subprocess.run([
            sys.executable, str(SCRIPT), "--old-executable", str(old),
            "--new-executable", str(new), "--provider-executable", str(provider),
            "--old-sha256", hashlib.sha256(old.read_bytes()).hexdigest(),
            "--new-sha256", hashlib.sha256(new.read_bytes()).hexdigest(),
            "--scratch-root", str(scratch), "--validate-only", *extra,
        ], text=True, capture_output=True, timeout=10)

    def test_rejects_a_pool_ancestor_without_creating_test_state(self):
        pool = self.root / "existing-pool"
        pool.mkdir()
        (pool / "queue.sqlite3").write_text("production-like sentinel; not a real database")
        scratch = pool / "native-upgrade-rollback.guard"
        result = self.call(scratch)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("pool", result.stderr.lower())
        self.assertFalse(scratch.exists())

    def test_rejects_reuse_without_touching_existing_contents(self):
        scratch = self.root / "native-upgrade-rollback.existing"
        scratch.mkdir()
        sentinel = scratch / "sentinel"
        sentinel.write_text("leave existing state alone")
        result = self.call(scratch)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "leave existing state alone")
        self.assertEqual(sorted(path.name for path in scratch.iterdir()), ["sentinel"])

    def test_hash_mismatch_is_rejected_before_scratch_creation(self):
        scratch = self.root / "native-upgrade-rollback.hash"
        result = self.call(scratch, "--new-sha256", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha-256", result.stderr.lower())
        self.assertFalse(scratch.exists())

    def test_validate_only_checks_programmes_without_creating_a_pool(self):
        scratch = self.root / "native-upgrade-rollback.preflight"
        result = self.call(scratch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["versions"], {"old": "0.4.2", "new": "0.5.0"})
        self.assertFalse(scratch.exists())

    def test_wrong_runtime_version_is_rejected_before_pool_creation(self):
        scratch = self.root / "native-upgrade-rollback.version"
        result = self.call(scratch, "--new-version", "9.9.9")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version", result.stderr.lower())
        self.assertFalse(scratch.exists())

    def test_real_provider_is_rejected_before_pool_creation(self):
        self.programs[2].write_text("#!" + sys.executable + "\nprint('codex-cli-real-provider')\n")
        scratch = self.root / "native-upgrade-rollback.provider"
        result = self.call(scratch)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controlled", result.stderr.lower())
        self.assertFalse(scratch.exists())


if __name__ == "__main__":
    unittest.main()
