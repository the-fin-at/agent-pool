# Native and SSH performance checks

Use `scripts/test_native_performance.py` with an explicitly configured `--remote`, an installed `--cli`, and a new `--output` directory. The SSH-only mode reads cached status and measures at least 20 samples. Native UI mode additionally requires a macOS debug desktop with the test hook and an unlocked console session.

```sh
python3 scripts/test_native_performance.py --remote pool --cli "$HOME/.local/bin/agent-fleet" --ssh-only --output test-results/performance
```

Supply your own optional `--reference` JSON to compare artifact hashes. Without one, the result records observed versions/hashes and makes no claim about matching a previously reviewed release. There is no dependency on a historical machine-specific report.

Native mode adds `--desktop PATH` and omits `--ssh-only`. It injects delays in disposable remote state, checks the real WKWebView/Rust IPC boundary and captures session availability. An unavailable or locked console is a missing gate, not a pass. Existing production account data and services are outside fault injection. See [remote validation](remote-validation.md) for the full three-loop procedure.
