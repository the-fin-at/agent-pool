# Claude code-rejection recovery in 0.5.1

Recorded on 29 October 2026 for [issue #35](https://github.com/the-fin-at/agent-pool/issues/35). The implementation is `the-fin-at/agent-pool@e551a463bfd4bc035db55c547d0f142e106a7ec2`, based on `2093fc17131629f6c5cd21b045c69ce5f896618d`. [Normalized validation and artifact reference](claude-login-retry-validation.json).

## Resulting behavior

Claude Code 2.1.312 can reject an authorization-code line while continuing to wait for another line, without repeating its paste prompt. Fleet 0.5.0 stayed in `verifying`, hid the code field and refused another input until cancellation or the 900-second expiry.

The patch recognizes that verified native diagnostic, returns a fixed safe instruction and restores `awaiting_code`. The user can submit a corrected code to the same session, profile and native process. The profile remains unconfirmed and disabled until the native CLI exits successfully and verifies the exact configuration directory, `loggedIn` and the `claude.ai` subscription method. Cancellation, expiry and credential storage retain their existing behavior.

Raw provider diagnostics, codes and secret-bearing return URLs are not copied into the new feedback. This change adds no credential import, default-Claude discovery or background-login navigation policy.

## Verification checkpoint

- The public CLI regression failed before the fix because the state remained `verifying`; it then passed with rejection, safe feedback, corrected input and verified success. Cancellation after rejection also passed. The original diagnostic probe accepted a second input with the fixed candidate.
- macOS: 86 Rust core tests, two bridge tests, 23 React tests, 25 native compatibility cases including 100 controlled jobs, and seven upgrade guards passed. Format, Clippy, typechecking, workspace checks and builds passed. Python discovered 145 tests: 115 passed and 30 Tk tests were skipped because this Python lacks `_tkinter`.
- The actual macOS WKWebView/Rust IPC harness passed 28 checks in an isolated pool. It observed the safe rejection message, restored masked editable input, no premature activation/success, and a subsequent provider-confirmed login. This is a controlled-provider native UI check, not a new real OAuth consent or an installed-release UI replay.
- The exact macOS release CLI artifact separately passed the three focused Claude cases (happy path, corrected retry and cancellation) with the existing native controlled fixture. Native 0.5.1 CLI and `.app` builds completed; both bundle versions match. Deep/strict verification of the local ad-hoc signature passed. The artifact hashes are in the normalized reference. This checkpoint does not claim notarization, publication or installation.

The independent Linux validator built the exact implementation with a digest-pinned Rust image, locked/offline dependencies and networking disabled. The artifact was then executed on the actual isolated Linux x86_64 host: three focused Claude tests, all 25 compatibility cases and 86 prebuilt Rust core tests passed, with no skips. All 245 transferred source files and artifact hashes matched; all 11 host commands exited zero and cleanup found no owned native processes or temporary test pools. The immutable image digest, ELF hash and separate actual-host proof binding are recorded in the normalized reference. This is not a container-only execution claim.

## Re-run the public boundaries

From an isolated checkout with the native fixture built:

```sh
cargo build -p fleet-cli --examples --locked
cargo build -p fleet-cli --locked
python3 scripts/test_rust_compatibility.py \
  RustCompatibility.test_native_claude_rejected_code_can_be_corrected_in_same_session \
  RustCompatibility.test_native_claude_rejected_code_remains_cancellable
```

For the real macOS UI, first build the frontend and the debug desktop with `custom-protocol`, then run `python3 scripts/test_native_desktop.py --output <new-private-output-directory>`. The harness requires an unlocked console, uses only owned fixture accounts/processes, and inhibits display/idle sleep only while its app runs. It does not simulate user activity.

## Boundaries retained

The [earlier incident record](../wiki/claude-login-2026-10-29.md) distinguishes an unproven original failure from a later successful real login. The recovered rejection path does not establish that the reporter's historical code was invalid. Patch validation starts no real provider login, inference job or production migration. Deployment is a later, separately verified operation.

The historical [0.5.0 manifest](rust-tauri-validation.json), private draft assets and the release packager's explicit 0.5.0 allowlist remain unchanged. Windows-native acceptance, distribution/signing and final 1.0 decisions remain open; GitHub CI remains deliberately disabled.
