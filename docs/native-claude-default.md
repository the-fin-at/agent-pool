# Reuse an existing native Claude CLI login

The local overview can recognize a confirmed normal Claude CLI subscription login. It registers a reference with `auth_mode=native_default`, retaining the native home/keychain context and leaving `CLAUDE_CONFIG_DIR` unset. It creates no managed credential directory and copies no tokens. Missing or unconfirmed native logins are not imported as connected accounts.

Additional accounts use separate managed login directories. Profiles with the same confirmed identity share the most restrictive known quota/hold limits and a busy boundary within the pool. Automatic selection prefers the enabled normal context for that identity; an explicit `--profile NAME` still uses the selected profile's own context. External provider processes do not participate in the pool's locks.

The normal provider CLI owns login, account changes and logout. Disable the reference to stop assigning it work without deleting credentials. Refresh recognizes confirmed logout/identity changes, while unknown metadata and busy responses are not treated as logout. A local login is never transferred to an SSH server.

## Downgrade compatibility

Before using a version that does not understand `native_default`, inspect `agent-fleet profile list` and disable only the relevant reference with `agent-fleet profile disable NAME` using the newer CLI. Names can have collision suffixes; discover the actual profile instead of assuming one. Replace only the programs and retain the current queue and credential directories. Re-enable that reference explicitly if desired after returning to a compatible version.

## Tests

Native-default discovery, identity confirmation, shared holds, explicit pins and logout transitions are exercised by the Rust tests and `scripts/test_rust_compatibility.py`. Controlled fixtures do not establish that a particular user's real subscription login works. See [validation](validation.md).
