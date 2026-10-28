# Agent Fleet 0.5: Rust and Tauri

Requested by Johannes on 28 October 2026. Baseline: `f712523` (Python 0.4.1). Existing THE-FIN account overview, native login and real-host behavior are the compatibility contract.

Final integration base: `ddbc859` includes the native-lock nonstarvation fix (PR21), Claude unified/nested quota fixes, automatic same-provider account selection and project-scoped execution targets. See `docs/agent-routing-contract.md`; the Rust runtime must prove the same behavior.

## Required outcome

- Native Rust CLI, queue/worker, provider adapters, account and quota read model, SSH/RPC and native login-session implementation. No Python interpreter required by the new runtime.
- Tauri 2 desktop with the existing warm THE-FIN palette, original compass and upright bundled Albert Sans. Provider filters, search, remaining 5-hour circles, weekly/model limits, account details, native login and local/remote switching remain functional. Existing job submission and reports remain usable through CLI/skills. Desktop remains overview/native-login with optional read-only job history; it adds no task composer.
- Existing platform-specific AgentPool directories, `queue.sqlite3` schema, profiles, attached `auth_home`, jobs, reports, statuses, idempotency keys and remotes.json remain compatible. No credential copies, data reset or implicit replay.
- Rust and existing Python workers use the same OS leases and database transitions. Existing 0.4.1 remote server remains supported by RPC v1. Network and provider work never blocks the webview event loop.
- New native logins require provider confirmation, including Claude subscription method and exact configDirectory. Codes stay out of process command lines and logs. Stale UI responses cannot replace a newer server/login context.
- Child process groups are reaped on timeout/interruption; uncertain executions become needs_review. All applicable quota windows and unknown-reset holds remain enforced.

## Acceptance

1. Cargo format/check/clippy/tests and frontend typecheck/build/unit tests pass. Existing Python regression suite stays green.
2. Cross-language fixtures prove an old database remains usable in both implementations without changing profile/job identities; identical idempotent retries create one job, content changes are rejected, completed reports and needs_review states survive.
3. Native provider fixtures exercise read-only and editing task arguments, success/failure/quota/timeout, environment isolation, native-lock and worker-lock interoperability, login start/input/cancel and confirmation. No fixture contacts a provider.
4. Real local account metadata and existing jobs remain accessible without migration. No production queue is drained during acceptance. Real SSH cache/status and isolated job transport are verified independently, according to ADR-0001.
5. Browser user-flow checks and a native macOS Tauri window demonstrate the retained design and working controls. Source, native and controlled-provider evidence are distinguished. Windows/Linux checks are reported only if actually executed.
6. Review exact commit, push PR, merge only after local gates. Existing known GitHub billing failures are documented independently from code failures. Preserve other work and active native logins.
