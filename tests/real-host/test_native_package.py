"""Public packaging CLI: real artifacts only for successful native roundtrips."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import tempfile
import tomllib
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/package_native_release.py'
VERSION = tomllib.loads((SCRIPT.parents[1] / 'Cargo.toml').read_text())['workspace']['package']['version']


class NativePackageTests(unittest.TestCase):
    def invoke(self, root, candidate, reference, output=None, app=None, target=None):
        reference_path = root / 'reference.json'
        reference_path.write_text(json.dumps(reference))
        command = [sys.executable, str(SCRIPT), '--reference', str(reference_path),
                   '--platform', target or ('macos-arm64' if sys.platform == 'darwin' else 'linux-x86_64'),
                   '--cli', str(candidate), '--output', str(output or root / 'output')]
        if app:
            command += ['--app', str(app)]
        return subprocess.run(command, text=True, capture_output=True)

    def fixture(self, root):
        marker = root / 'executed'
        candidate = root / 'candidate'
        candidate.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
        candidate.chmod(0o755)
        reference = {'version': VERSION, 'reviewed_implementation_commit': '0' * 40, 'release': {
            'mac_cli_sha256': '0' * 64, 'linux_cli_sha256': '0' * 64}}
        return candidate, reference, marker

    def test_wrong_hash_cannot_execute_or_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, reference, marker = self.fixture(root)
            result = self.invoke(root, candidate, reference)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((root / 'output').exists())

    def test_matching_hash_with_bad_architecture_cannot_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, reference, marker = self.fixture(root)
            checksum = hashlib.sha256(candidate.read_bytes()).hexdigest()
            reference['release'] = dict.fromkeys(reference['release'], checksum)
            result = self.invoke(root, candidate, reference)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((root / 'output').exists())

    def test_wrong_release_version_cannot_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, reference, marker = self.fixture(root)
            reference['version'] = '1.0.0'
            result = self.invoke(root, candidate, reference)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((root / 'output').exists())

    def test_existing_output_and_symlink_target_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, reference, marker = self.fixture(root)
            destination = root / 'existing'
            destination.mkdir()
            sentinel = destination / 'keep'
            sentinel.write_bytes(b'operator-owned-data')
            link = root / 'link'
            link.symlink_to(destination, target_is_directory=True)
            for output in (destination, link):
                result = self.invoke(root, candidate, reference, output=output)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(sentinel.read_bytes(), b'operator-owned-data')
                self.assertEqual(list(destination.iterdir()), [sentinel])
                self.assertFalse(marker.exists())
            self.assertTrue(link.is_symlink())

    def test_extra_bundle_files_and_escaping_links_are_rejected(self):
        if not os.environ.get('FLEET_PACKAGE_INPUTS'):
            self.skipTest('requires explicit native artifact inputs')
        inputs = json.loads(Path(os.environ['FLEET_PACKAGE_INPUTS']).read_text())
        if not inputs.get('app'):
            self.skipTest('macOS bundle guard')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = json.loads(Path(inputs['reference']).read_text())
            app = root / 'Agent Fleet.app'
            shutil.copytree(inputs['app'], app, symlinks=True)
            extra = app / 'Contents' / '.env'
            extra.write_text('controlled-test-secret')
            result = self.invoke(root, Path(inputs['cli']), reference, app=app)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse((root / 'output').exists())
            extra.unlink()
            resource = app / 'Contents/Resources/app.icns'
            resource.unlink()
            outside = root / 'outside'
            outside.write_bytes(b'operator-owned-data')
            resource.symlink_to(outside)
            result = self.invoke(root, Path(inputs['cli']), reference, app=app)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse((root / 'output').exists())
            self.assertEqual(outside.read_bytes(), b'operator-owned-data')

    def test_output_cannot_modify_the_input_app(self):
        if not os.environ.get('FLEET_PACKAGE_INPUTS'):
            self.skipTest('requires explicit native artifact inputs')
        inputs = json.loads(Path(os.environ['FLEET_PACKAGE_INPUTS']).read_text())
        if not inputs.get('app'):
            self.skipTest('macOS bundle output guard')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'Agent Fleet.app'
            shutil.copytree(inputs['app'], app, symlinks=True)
            before = {str(path.relative_to(app)) for path in app.rglob('*')}
            reference = json.loads(Path(inputs['reference']).read_text())
            result = self.invoke(root, Path(inputs['cli']), reference,
                                 output=app / 'Contents' / 'output', app=app)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual({str(path.relative_to(app)) for path in app.rglob('*')}, before)

    def test_verified_native_artifact_roundtrips_repeatably(self):
        if not os.environ.get('FLEET_PACKAGE_INPUTS'):
            self.skipTest('set FLEET_PACKAGE_INPUTS to explicit trusted operator input JSON')
        inputs = json.loads(Path(os.environ['FLEET_PACKAGE_INPUTS']).read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = []
            for name in ('first', 'second'):
                destination = root / name
                command = [sys.executable, str(SCRIPT), '--reference', inputs['reference'],
                           '--platform', inputs['platform'], '--cli', inputs['cli'],
                           '--output', str(destination)]
                if inputs.get('app'):
                    command += ['--app', inputs['app']]
                result = subprocess.run(command, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                manifest = json.loads((destination / 'manifest.json').read_text())
                archive = destination / manifest['archive']['name']
                self.assertTrue(manifest['roundtrip']['cli_version_verified'])
                self.assertEqual(manifest['roundtrip']['cli_sha256'], inputs['cli_sha256'])
                if inputs.get('app'):
                    self.assertTrue(manifest['roundtrip']['codesign_deep_strict'])
                with tarfile.open(archive) as package:
                    binary = package.extractfile('target/release/agent-fleet').read()
                    self.assertEqual(hashlib.sha256(binary).hexdigest(), inputs['cli_sha256'])
                    self.assertTrue(package.getmember('target/release/agent-fleet').mode & 0o111)
                    self.assertIn('scripts/install_native.sh', package.getnames())
                outputs.append((archive.read_bytes(), (destination / 'manifest.json').read_bytes()))
            self.assertEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
