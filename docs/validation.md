# Validation

Run checks from the repository root. Tests use disposable homes and controlled providers unless a command explicitly opts into a named host. A successful controlled test does not prove a user's real login, a desktop installer or another operating system.

## Every source file and folder

```sh
python3 -m unittest tests.test_portability tests.test_packaging_reference -v
python3 scripts/check_portability.py --report test-results/portability.json
```

The inventory accounts for every distributable path, checks text and local documentation links, and requires an exact reviewed hash/purpose for binary assets. [Policy and review process](portability.md).

## Core and legacy compatibility

```sh
python3 -m unittest discover -s tests -v
cargo fmt --all -- --check
cargo test -p fleet-core -p fleet-cli --locked
cargo clippy -p fleet-core -p fleet-cli --all-targets --locked -- -D warnings
cargo build -p fleet-cli --examples --locked
cargo build -p fleet-cli --locked
python3 scripts/test_rust_compatibility.py
python3 -m unittest discover -s tests/real-host -p test_native_package.py -v
python3 scripts/build_zipapp.py
python3 dist/agent-fleet.pyz --version
```

The compatibility harness defaults to the newly built debug CLI. Set `FLEET_RUST_BIN` to another explicitly selected artifact to test that artifact. Tk tests require an available Tk installation; skipped GUI tests are not native Tauri acceptance.

## Frontend and desktop

```sh
cd desktop
npm ci
npm test
npm run build
npm run tauri build
```

The last command requires the platform's native Tauri prerequisites. Browser/React tests do not prove macOS WKWebView, Windows WebView2, signing or installer behavior. `scripts/test_native_desktop.py` is an opt-in macOS native-window harness using controlled providers and an explicit output directory.

## SSH integration

`python3 scripts/test_remote_ssh.py` creates its own Docker/OpenSSH fixture, disposable key, loopback-bound port and synthetic accounts; no existing SSH alias is required. Docker must be available. It writes its report under ignored `test-results/`.

Tests against an operator's actual host require explicit connection/profile inputs. Follow [remote validation](remote-validation.md). Live host checks and real provider inference are separate gates.

## Distribution status

Build the current Rust/Tauri source for the current native version. Older published 0.2/0.3 downloads contain the Python/Tk application. Native Windows installation and runtime acceptance, and public macOS signing/notarization, remain open. A CI compilation or a local macOS test must not be relabeled as a successful Windows installer test. Packaging and handover tests require explicitly supplied candidate programs and trusted hashes; see [native distribution](native-distribution.md).

Per-run logs and screenshots are machine-specific evidence and remain outside tracked product documentation. Record the exact source commit, command, platform, result and skips in your own test report.
