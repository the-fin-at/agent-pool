# Opt-in remote validation

Choose a connection and workspace explicitly. The names below are examples: replace them with your own registered connection, connected profile and disposable paths. Read [remote setup](remote.md) first. Preserve provider credentials, existing workers and production data.

## Loop 1: baseline

```sh
agent-fleet remote list
agent-fleet remote test pool
agent-fleet --remote pool status
agent-fleet --remote pool workspace list
```

Confirm the selected target, program version, worker heartbeat, actual workspace path and connected profiles. A successful metadata read does not prove model execution. Keep full account metadata in private reports.

## Loop 2: faults in disposable state

```sh
python3 scripts/test_real_host_transport.py --remote pool --output test-results/transport.json
python3 scripts/test_native_performance.py --remote pool --cli "$HOME/.local/bin/agent-fleet" --ssh-only --output test-results/performance
```

The transport test creates a private sibling scratch area, interrupts an acknowledgement after commit and verifies one job for an identical retry. It does not start provider inference. The performance test reads cached status. Native macOS UI performance additionally requires `--desktop` pointing to a debug build with the test hook; any injected delay uses disposable state. An optional `--reference` binds measurements to your own reviewed artifact hashes, not a checked-in workstation report.

The legacy Tk UI harness requires `--profile` for an existing connected Codex profile and `--login-profile` for a new disposable name. It starts and cancels a provider login session. Run it only with explicit authorization for that test account. `--client-home` can select an isolated client configuration; no particular account name is required.

## Loop 3: re-verification

Repeat baseline commands. Verify only the scratch state created by your tests was removed, existing jobs/credentials/services remain intact, and the original failure no longer reproduces. A bounded real model request is a separate opt-in action with its own result check and usage budget.

Store reports and screenshots under ignored `test-results/` or outside the checkout. A report from one host is evidence for that host and artifact only; it is not a project default or cross-platform acceptance.
