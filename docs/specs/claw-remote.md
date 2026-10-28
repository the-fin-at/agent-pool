# Real remote setup and three verification loops

## Problem Statement

The account dashboard and SSH worker have been tested with containers, but the owner needs a working personal Linux connection and evidence that user flows, failures and performance hold on a real host.

## Solution

Install Agent Fleet on claw-remote, run a private persistent worker, connect the Mac dashboard, exercise real native account visibility and a bounded agent task where existing authentication permits it. Run three distinct loops and implement every reproducible application defect found.

## User Stories

1. As the owner, I want the existing SSH alias to work without entering a new address.
2. As the owner, I want the remote visible in the desktop connection list.
3. As the owner, I want remote and local account data separated.
4. As the owner, I want real server quotas instead of fixture values.
5. As the owner, I want the worker to survive closing the client.
6. As the owner, I want a small remote task to return an inspectable report.
7. As the owner, I want browser login and cancellation tested on the installed executable.
8. As the owner, I want unsupported native CLI versions explained instead of silent waiting.
9. As the owner, I want lost submission replies to preserve exactly one job.
10. As the owner, I want broken SSH to leave the GUI responsive and recoverable.
11. As the owner, I want changing targets to discard stale replies.
12. As the owner, I want cancellation, timeouts and worker restart tested safely.
13. As the owner, I want quota waits to enforce both short and weekly windows.
14. As the owner, I want malformed requests rejected without executing shell payloads.
15. As the owner, I want measurable status latency and GUI responsiveness under load.
16. As the owner, I want existing services and credentials preserved.
17. As the owner, I want repeatable tests and exact separation of real-provider and controlled-provider proof.
18. As the owner, I want the corrected app and server versions installed and the work reviewable in GitHub.

## Implementation Decisions

- Use the existing native Tk dashboard and OpenSSH JSON RPC, no new listening service.
- Use a user systemd worker with a private local state directory, registered dedicated test workspace, and logind linger if already available or authorized without extra credentials.
- Use the installed CLI/archive, not only source imports, for subprocess/login tests.
- Provide explicit administrator-only attachment of an existing native account directory, keeping credentials and directory permissions in place. Bind its resolved path, reject duplicate attachment, and fail clearly if the directory disappears or its symlink target changes. New profiles continue using private isolated directories.
- Reuse existing server-native authentication on that host only; keep newly requested consent explicit. Controlled providers are confined to isolated test pools.
- Keep ordinary application changes bounded to defects demonstrated by the three loops.
- Record host state without publishing private addresses, account emails, credentials, device codes or raw login URLs.

## Testing Decisions

Primary seams are public CLI/RPC and actual desktop user actions. Existing queue, SSH and native login fixtures are prior art. New regression tests reproduce observed defects before production changes.

1. User loop: installation discovery, GUI connection navigation, refresh, account/details, native login start/cancel, real task/report where logged in, client independence.
2. Adversarial loop: malformed input, literal shell strings, concurrent/duplicate requests, broken SSH, cancelled login, quota waits, worker termination/recovery; isolated pools only.
3. Performance loop: 20 warm remote status reads (p95 <3s), 100 synthetic jobs across bounded batches (no losses/duplicates), dashboard event-loop probe under delayed transport (p95 <100ms, no interval >500ms). Values are acceptance targets; fix or explicitly report misses.

All loops end with re-verification after fixes. Final gate: local full suite, real Linux suite/CLI checks, visual native GUI evidence, packaged macOS smoke, review against standards and spec. CI billing and native Windows acceptance remain separately reported.

## Out of Scope

New server purchase, credential replication, quota evasion, changes to unrelated services, human browser consent fabrication, destructive load on the production pool, native Windows proof from a Mac.

## Further Notes

Unattended execution was explicitly requested. Decisions normally confirmed by skill interviews are made from repository and host evidence. Three loops are separate user/failure/performance passes, not three repetitions of one test suite.
