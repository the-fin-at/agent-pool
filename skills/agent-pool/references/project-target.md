# Project execution target

Resolve project identity and target together. An explicit user target for the current task overrides the project's established target. Otherwise use the Chief-of-Staff project handoff or a clearly established target for this same project. A connection configured on the client describes availability; it does not choose where a project runs. A machine-wide `skill-policy.json` target is not an input to this decision.

A project handoff conveys:

- Project identity (repository or another unambiguous project identifier).
- Execution on the local machine or a remote pool.
- For remote execution, the named client connection and the registered server workspace plus its server path, or enough server path information to resolve and confirm that workspace before submission.
- For local execution, the working directory for this project.

These are routing data. Apply the task's own file ownership, allowed edits and acceptance checks; a handoff does not authorize additional execution, merge, deployment or messages.

Before submitting, validate the chosen remote name with `remote list` and the workspace/path on that target. A missing connection, workspace or target requires clarification; preserve the intended target while continuing independent work. Confirm a local project's working directory before using `--cwd`. Never substitute a client path for a server workspace.

## Forward scenarios

| Context | Next action |
| --- | --- |
| Project A explicitly uses remote `build-server`; the next request is project B with no target | Ask for B's target before submitting. A's choice does not carry over. |
| Project B explicitly requests local execution; a remote connection is configured | Use B's local directory. The configured remote does not override the task. |
| Chief of Staff hands off project C with remote `build-server`, workspace `project-c`, path `/srv/projects/c` | Validate that connection and workspace/path, then submit C with `--remote build-server --workspace project-c`. |
| A same-project follow-up has a clearly established remote and workspace | Reuse them for that project, unless the current task changes the target. |
| Project identity is unclear, two handoffs disagree, or remote target lacks a resolvable workspace/path | Ask for the missing decision before submission; continue independent work. |

Once the project's target is resolved, account selection stays automatic within the requested provider. Ordinary jobs omit `--profile`; the broker still enforces windows, model/bucket, holds, explicit pins and bounded same-job retries. See [quota-routing.md](quota-routing.md).
