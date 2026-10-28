---
name: agent-pool
description: Compatibility name for agent-fleet. Dispatch bounded work through Agent Fleet with quota-aware automatic account selection, inspect quota waits and retrieve reports. Use when assigning work to local or SSH-hosted Codex/Claude profiles or using the available account pool.
---

# Agent Pool / Agent Fleet nutzen

`agent-pool` is the compatibility alias; prefer the canonical `agent-fleet` executable and portable archive.

Use the installed `agent-fleet` command, version 0.4.2+. On Windows use `py -3 <installed-agent-fleet.pyz>`. Default to **automatic account selection**: ordinary jobs omit `--profile`. A full account must not pin the whole task to its five-hour reset. Honor an account explicitly required by the user; a pinned job deliberately cannot switch accounts.

## Target and live capacity

1. Resolve the execution target **for the current project** before submission. The user's explicit target for this task wins. Otherwise use the Chief-of-Staff handoff for this project, or the target clearly established for this same project. Reuse a target only within that project. If the project identity or target is missing, conflicting or ambiguous, ask the user for the target before submitting; continue independent work while waiting. Machine-wide preferences, available accounts and a sole configured remote do not establish a project's target; there is no implicit local fallback. For handoff details and project-boundary scenarios read [references/project-target.md](references/project-target.md). For remote execution validate the named connection with `remote list`, confirm the server workspace/path belongs to this project, and append `--remote <name>` before every remote action.
2. Read `status` and `quota show` on that target. Check enabled/connected profiles, holds, window durations, model/bucket, timestamps and worker heartbeat. Do not hardcode an account's percentage, reset, email or subscription capacity in this skill or task. For quota decisions and waits read [references/quota-routing.md](references/quota-routing.md). Remote status reads the server cache; remote `--refresh`, `init` and `work` are not supported. The server worker handles refresh and execution.
3. Keep the requested provider and native model. Supply `--model` when the user specified one. Set `--bucket` only from a known matching native bucket, not an invented model-name mapping. Use all eligible profiles of that provider; do not pick the first profile or add a pin merely because one snapshot looked best. The scheduler enforces the actual job's model/bucket and concurrent state. Cross-provider or model fallback requires permission in the task; it is a new task, not a silent rewrite of an existing idempotency key.

## Submit once, keep the job

Write a bounded UTF-8 task file with objective, working directory, file ownership, acceptance checks and report format. For edits include: “You are not alone in the codebase. Preserve other people's changes and adapt your edits to them.” File changes require task authorization and `--allow-edits`; ordinary work stays read-only. Claude's shell tools are disabled; Codex uses its native sandbox.

For a remote pool, use a registered **server** workspace and a stable key:

```sh
agent-fleet --remote <name> job submit --provider codex --workspace <server-workspace> --prompt-file <task-file> --key <unique-key>
agent-fleet --remote <name> job wait <job-id> --seconds 30
```

The ordinary command has **no `--profile`**. Add it only for a deliberate user account constraint or an account-specific test. Locally use `--cwd <local-directory>` instead of `--workspace` if appropriate. The client reads the prompt file; project files must already exist on the server. Do not copy the `--max-attempts 1` setting from single-account acceptance tests into pooled work; normal quota failover needs the broker's bounded retry budget (default 6).

Save the returned job ID and key. After an uncertain SSH response, list/get jobs or resend the identical submission with the **same key**. A different prompt, profile, model, bucket or timeout is a different specification and cannot reuse that key. `run` on a remote only submits and waits for the independent worker.

## Progress and completion

- Ensure the worker is online. A local `work` process needs a durable terminal/supervisor. `work --once` and `work --drain` do not keep waiting through exhausted windows.
- For read-only work, a native quota rejection holds that profile and leaves the same unpinned job available for another eligible profile on a following worker tick, within its retry budget. Do not resubmit under new keys or force `profile release`/`quota set` to claim capacity.
- If all matching profiles are exhausted, retain the queued/waiting job. The persistent worker resumes when a matching profile becomes eligible. Use bounded `job wait`/`job get`; continue independent runnable work instead of blocking the client in one five-hour sleep. Waiting is unfinished, not success. If heartbeat is offline or a reset is unknown, report that condition rather than promising a restart time.
- A quota failure during edits, timeout or interruption may mean partial changes and `needs_review`. Inspect the actual server workspace/processes before retry or a continuation. Remote retry needs `--acknowledge-review`. Do not blindly replay edits on another account.
- Finish only when `status` is `succeeded` and the actual result/changes meet acceptance. Report job ID, actual `chosen_profile`, provider/model, result and checks. For `job get`/`job wait`, exit codes are 0 success, 1 failure/review/cancelled, 2 pending; a successful submission only confirms queuing. A worker report supplies evidence, not authorization to merge, deploy or message others.

For missing binaries, connections or logins use `setup-agents-fleet`. The dashboard is an overview. A display-only native Codex default account is not a managed execution profile; an existing account can be explicitly attached on its own machine by the administrator. Browser consent belongs to the owner and credentials remain on that machine. Separate accounts keep their separate provider limits.
