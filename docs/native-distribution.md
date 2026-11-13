# Native distribution

Package explicitly reviewed binaries built from the current source version. The packaging helper checks the version in `Cargo.toml`; it is not pinned to an earlier workstation build. CLI and desktop programs still require native platform acceptance, and macOS signing/notarization are separate from packaging.

## Trusted artifact reference

Create an operator-reviewed JSON file outside tracked product documentation. It identifies:

- `version`: the current workspace package version from `Cargo.toml`.
- `reviewed_implementation_commit`: the full reviewed Git commit hash.
- `release.mac_cli_sha256` or `release.linux_cli_sha256`: the verified native CLI hash for the chosen platform.
- For macOS, `release.app_executable_sha256`: the verified desktop executable hash. The bundle metadata must match the CLI version and pass deep/strict codesign verification.

These are operator inputs, not an authenticity service. Compute hashes from the artifacts actually tested; never reuse values from somebody else's machine. An optional `native_gui.debug_binary_sha256` can bind a debug UI artifact for performance comparisons.

## Build and package

Build with the locked toolchain/dependencies and validate the exact binaries first. The helper currently supports macOS arm64 (CLI plus app) and Linux x86_64 (CLI); it must run on the matching native platform.

```sh
python3 scripts/package_native_release.py --help
```

Pass `--platform`, `--reference`, `--cli`, `--output`, and `--app` on macOS. All paths are explicit. Output must be a new directory under an existing parent. No provider, pool, GUI or installation process is started by packaging.

The helper checks hashes and executable headers before execution, verifies the bundle allowlist, stages the native installer, and round-trips the archive into a new directory. It emits an archive, member manifest and SHA256SUMS. Repeat packaging from identical reviewed inputs to test archive repeatability. This is separate from an independent clean compiler rebuild.

The archive contains native programs and `scripts/install_native.sh`, not account state, local configuration or development-run reports. Windows packaging is not supplied by this helper; build and validate its Tauri installer on Windows. Older Python/Tk downloads are a separate legacy distribution.

## Guards

```sh
python3 -m unittest tests.test_packaging_reference -v
python3 -m unittest discover -s tests/real-host -p test_native_package.py -v
```

Successful native roundtrips require `FLEET_PACKAGE_INPUTS` pointing to your own explicit input JSON with `reference`, `platform`, `cli`, `cli_sha256` and optionally `app`. Artifact-dependent tests skip when those inputs are unavailable; a skip is not a shipping approval. Store your reports under ignored `test-results/`.
