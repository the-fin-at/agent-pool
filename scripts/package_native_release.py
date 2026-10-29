#!/usr/bin/env python3
"""Stage a repeatable private native package from already validated 0.5 artifacts.

The reference is a trusted operator input, not an authenticity/signature service.
No build, provider, pool, GUI or installation commands are run.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile

APP_FILES = {
    'Contents/Info.plist',
    'Contents/MacOS/agent-fleet-desktop',
    'Contents/Resources/app.icns',
    'Contents/_CodeSignature/CodeResources',
}
APP_BINARY = 'Contents/MacOS/agent-fleet-desktop'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def native_header(path, target):
    with path.open('rb') as source:
        header = source.read(64)
    if target == 'macos-arm64':
        valid = len(header) >= 16 and header[:4] == b'\xcf\xfa\xed\xfe' and struct.unpack('<I', header[4:8])[0] == 0x0100000C and struct.unpack('<I', header[12:16])[0] == 2
    else:
        valid = len(header) >= 20 and header[:6] == b'\x7fELF\x02\x01' and struct.unpack('<H', header[18:20])[0] == 62
    if not valid:
        raise ValueError(f'unsupported executable architecture: {path.name}')


def verified_binary(path, expected, target):
    if path.is_symlink() or not path.is_file() or not stat.S_IMODE(path.stat().st_mode) & 0o111:
        raise ValueError('native binary must be a regular executable file')
    if digest(path) != expected:
        raise ValueError('native binary SHA-256 differs from trusted reference')
    native_header(path, target)


def verify_version(cli, version):
    if run([str(cli), '--version']) != version:
        raise ValueError('CLI version differs from reference')


def app_entries(app):
    if app.is_symlink() or not app.is_dir():
        raise ValueError('app must be a real bundle directory')
    entries = sorted(app.rglob('*'))
    files = {str(path.relative_to(app)) for path in entries if not path.is_dir() or path.is_symlink()}
    if files != APP_FILES:
        raise ValueError('app contains missing or unexpected files; allowlist requires review')
    allowed_directories = {str(parent) for name in APP_FILES for parent in PurePosixPath(name).parents if str(parent) != '.'}
    if {str(path.relative_to(app)) for path in entries if path.is_dir() and not path.is_symlink()} != allowed_directories:
        raise ValueError('app contains unexpected directories')
    for path in entries:
        if path.is_symlink():
            link = os.readlink(path)
            if Path(link).is_absolute() or not path.resolve().is_relative_to(app.resolve()) or not path.exists():
                raise ValueError('app symlink escapes its bundle or is dangling')
        elif not (path.is_dir() or path.is_file()):
            raise ValueError('unsupported app entry')
    return entries


def verify_app(app, reference, target):
    entries = app_entries(app)
    info_path = app / 'Contents/Info.plist'
    if info_path.is_symlink():
        raise ValueError('Info.plist must be regular')
    info = plistlib.loads(info_path.read_bytes())
    if any(info.get(key) != reference['version'] for key in ('CFBundleShortVersionString', 'CFBundleVersion')) or info.get('CFBundleExecutable') != 'agent-fleet-desktop':
        raise ValueError('app metadata differs from reference')
    verified_binary(app / APP_BINARY, reference['release']['app_executable_sha256'], target)
    run(['codesign', '--verify', '--deep', '--strict', str(app)])
    return entries


def inventory(entries):
    result = []
    for name, source in sorted(entries.items()):
        metadata = source.lstat() if source else None
        mode = stat.S_IMODE(metadata.st_mode) if metadata else 0o755
        item = {'path': name, 'mode': oct(mode)}
        if source and source.is_symlink():
            item.update(type='symlink', target=os.readlink(source))
        elif not source or source.is_dir():
            item.update(type='directory')
        else:
            item.update(type='file', sha256=digest(source), bytes=metadata.st_size)
        result.append(item)
    return result


def write_archive(destination, entries):
    with destination.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', compresslevel=9, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for item in inventory(entries):
                    member = tarfile.TarInfo(item['path'])
                    member.mode = int(item['mode'], 8)
                    member.mtime = member.uid = member.gid = 0
                    member.uname = member.gname = ''
                    if item['type'] == 'directory':
                        member.type = tarfile.DIRTYPE
                        archive.addfile(member)
                    elif item['type'] == 'symlink':
                        member.type = tarfile.SYMTYPE
                        member.linkname = item['target']
                        archive.addfile(member)
                    else:
                        member.size = item['bytes']
                        with entries[item['path']].open('rb') as source:
                            archive.addfile(member, source)


def roundtrip(archive_path, expected, reference, target, with_app):
    with tempfile.TemporaryDirectory(prefix='fleet-package-roundtrip-') as temporary:
        root = Path(temporary)
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
            if len(names) != len(set(names)) or set(names) != {item['path'] for item in expected}:
                raise ValueError('archive inventory differs from input')
            # Python data-filter rejects traversal, absolute paths, escaping links and devices.
            # Extract only archives just created here, to a newly owned directory.
            for member in archive.getmembers():
                expected_mode = next(int(item['mode'], 8) for item in expected if item['path'] == member.name)
                if member.mode != expected_mode:
                    raise ValueError('archive mode differs from input')
            archive.extractall(root, filter='data')
            # The safe data filter deliberately leaves directory modes to umask.
            # Restore the verified archive directory modes after safe extraction.
            for item in reversed(expected):
                if item['type'] == 'directory':
                    (root / item['path']).chmod(int(item['mode'], 8))
        actual_entries = {str(path.relative_to(root)): path for path in root.rglob('*')}
        if inventory(actual_entries) != expected:
            raise ValueError('archive roundtrip changed content, modes or links')
        cli = root / 'target/release/agent-fleet'
        key = 'mac_cli_sha256' if target == 'macos-arm64' else 'linux_cli_sha256'
        verified_binary(cli, reference['release'][key], target)
        verify_version(cli, reference['version'])
        if with_app:
            verify_app(root / 'target/release/bundle/macos/Agent Fleet.app', reference, target)
        return {'cli_sha256': digest(cli), 'cli_version_verified': True,
                'all_members_identical': True, 'codesign_deep_strict': True if with_app else None}


def package(args):
    output = Path(args.output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('output must not exist; existing paths are never modified')
    if not output.parent.is_dir():
        raise ValueError('output parent must already exist')
    reference_path = Path(args.reference)
    reference = json.loads(reference_path.read_text())
    if reference['version'] != '0.5.0':
        raise ValueError('only the validated 0.5.0 release is supported')
    native = ('macos-arm64' if sys.platform == 'darwin' and platform.machine() == 'arm64'
              else 'linux-x86_64' if sys.platform == 'linux' and platform.machine() == 'x86_64' else None)
    if native != args.platform:
        raise ValueError('package and roundtrip must run on the matching native host')
    cli = Path(args.cli).absolute()
    key = 'mac_cli_sha256' if args.platform == 'macos-arm64' else 'linux_cli_sha256'
    verified_binary(cli, reference['release'][key], args.platform)
    entries = {'target/release/agent-fleet': cli}
    if args.platform == 'macos-arm64':
        if not args.app:
            raise ValueError('macOS package requires the validated app')
        app = Path(args.app).absolute()
        if output.resolve().is_relative_to(app.resolve()):
            raise ValueError('output must be outside the input app')
        paths = verify_app(app, reference, args.platform)
        app_name = 'target/release/bundle/macos/Agent Fleet.app'
        entries[app_name] = app
        entries.update({f'{app_name}/{path.relative_to(app)}': path for path in paths})
    elif args.app:
        raise ValueError('Linux package has no desktop app')
    installer = Path(__file__).resolve().with_name('install_native.sh')
    if installer.is_symlink() or not installer.is_file():
        raise ValueError('run from the reviewed scripts directory with install_native.sh')
    entries['scripts/install_native.sh'] = installer
    for name in list(entries):
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                entries.setdefault(str(parent), None)
    # All binaries and the complete app allowlist are verified before first execution.
    verify_version(cli, reference['version'])
    expected = inventory(entries)
    archive_name = f"agent-fleet-{reference['version']}-{args.platform}.tar.gz"
    with tempfile.TemporaryDirectory(prefix='.fleet-package-stage-', dir=output.parent) as temporary:
        stage = Path(temporary)
        archive = stage / archive_name
        write_archive(archive, entries)
        proof = roundtrip(archive, expected, reference, args.platform, bool(args.app))
        manifest = {'schema': 1, 'version': reference['version'], 'platform': args.platform,
                    'source_implementation_commit': reference['reviewed_implementation_commit'],
                    'reference_sha256': digest(reference_path),
                    'scope': 'packaging repeatability from validated binaries; not compiler reproducibility',
                    'archive': {'name': archive_name, 'sha256': digest(archive), 'bytes': archive.stat().st_size},
                    'members': expected, 'roundtrip': proof}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        (stage / 'SHA256SUMS').write_text(f"{digest(archive)}  {archive_name}\n")
        # mkdir is exclusive even if another process claims the destination during validation.
        output.mkdir(mode=0o700)
        for path in sorted(stage.iterdir()):
            shutil.copy2(path, output / path.name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, help='trusted rust-tauri-validation.json')
    parser.add_argument('--platform', required=True, choices=['macos-arm64', 'linux-x86_64'])
    parser.add_argument('--cli', required=True)
    parser.add_argument('--app', help='validated macOS .app, never launched')
    parser.add_argument('--output', required=True, help='new directory; parent must exist')
    args = parser.parse_args()
    try:
        manifest = package(args)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f'Package rejected: {error}', file=sys.stderr)
        return 1
    print(json.dumps(manifest['archive'], sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
