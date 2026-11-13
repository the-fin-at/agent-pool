# Rust runtime and legacy compatibility

The current runtime uses Rust for the CLI, queue, providers and SSH/RPC surface, with a Tauri/React desktop. Python remains a regression reference and a supported source for older deployments; it is not required to run the native programs.

## Existing data

The historical `AgentPool` directory name and `agent-pool` compatibility command are product compatibility identifiers. They do not refer to a particular user's machine.

| Platform | Default pool |
| --- | --- |
| macOS | `~/Library/Application Support/AgentPool` |
| Windows | `%LOCALAPPDATA%\AgentPool` |
| Linux | `~/.local/share/agent-pool` |

`--home` or `AGENT_POOL_HOME` selects a different pool explicitly. Preserve profile identities, native auth directories, `queue.sqlite3`, completed reports, queued tasks and connection configuration when upgrading. Stop only the worker you own after accounting for active jobs. Do not restore an old database over newer work or copy credentials between machines.

## Build and upgrade

Follow [quick start](quickstart.md) and [desktop setup](desktop.md). A first install refuses existing targets. The native installers replace programs only with `--replace` on macOS/Linux or `-Replace` on Windows and preserve a program backup. They do not reset the pool.

Client and server can be upgraded separately while the documented RPC contract remains compatible. The [upgrade runbook](native-upgrade-rollback.md) covers disposable compatibility trials. For a downgrade involving a normal Claude login reference, read [native-default compatibility](native-claude-default.md).

## Validation

Run Rust tests, the public CLI compatibility harness and the legacy Python suite. These use controlled providers and disposable state. Keep native GUI, real provider, remote-host and Windows acceptance distinct from those tests. See [the validation matrix](validation.md).
