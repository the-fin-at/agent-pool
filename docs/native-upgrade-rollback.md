# Upgrade and rollback acceptance

A program upgrade must preserve the current pool. A rollback replaces programs; restoring an old database would discard newer work and is not the rollback strategy.

## Prepare a disposable trial

Build or obtain two explicitly selected program versions for the same native platform. Review their hashes and test the controlled provider from `crates/fleet-cli/examples/controlled_provider.rs`. The harness accepts every program path, expected version and SHA-256 from the operator; it assumes no installed worker or server name.

```sh
python3 scripts/test_native_upgrade_rollback.py --help
```

Supply `--old-executable`, `--new-executable`, `--provider-executable`, `--old-sha256`, `--new-sha256`, `--old-version`, `--new-version` and `--scratch-root`. The scratch root must be a new absolute directory with the `native-upgrade-rollback.` prefix outside every existing pool. Use `--validate-only` to verify inputs before creating trial state.

`--scenario pending` checks queued-work preservation across program swaps. `--scenario active` covers controlled active handover and interruption. The temporary pool and provider are isolated; the fixtures do not use production subscriptions. Record actual checks and cleanup in the scratch report.

## Upgrade an existing installation

Account for active tasks first. Retain pool/credential directories and the independent worker's exact configuration. Use the native installer's explicit replace option to keep a program backup; restart only the worker you own. Compare versions, queue entries, completed results and heartbeat after replacement. Inspect any `needs_review` execution before retrying it.

Before downgrading across `native_default` support, follow [Claude login compatibility](native-claude-default.md). Test results on one pair of programs do not establish acceptance for every later pair or operating system.
