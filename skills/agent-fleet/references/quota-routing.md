# Quota-aware dispatch

The broker owns profile choice. Preflight explains capacity; it does not reserve a profile. Use live `status` and `quota show` from the chosen target, then submit normal work **without `--profile`**.

| Observation on one profile | Action |
| --- | --- |
| Applicable five-hour window exhausted, another same-provider profile eligible | Submit unpinned; the worker skips the full profile. |
| Five-hour capacity free but an applicable weekly window exhausted | That profile remains blocked. Other eligible profiles may run. |
| Requested model's window/bucket exhausted | Respect that limit. Another model's capacity is not permission to change the model. |
| A provider account has only a weekly window | Treat it as weekly by `minutes=10080`; do not infer a five-hour budget from “primary”. |
| Missing/stale utilization or missing windows, without a known quota hold | Capacity is unknown, not 0% or 100%. A bounded native attempt may supply the observation. |
| Known quota rejection with unknown reset | The worker holds that profile; route other eligible profiles. Do not invent a reset or release the hold. |
| All matching profiles blocked | Leave the original job waiting for its persistent worker; continue unrelated work. |

Apply **all relevant windows on each profile**. Five hours is usually `minutes=300`, a week `10080`; retain other native durations. Codex requires the job's actual bucket (default `codex`). Claude also has generic and model-family windows. `quota show` is a conservative summary without a job-specific model; an Opus-only limit does not prove that a specifically requested Sonnet job cannot run. Let the scheduler evaluate the submitted model; never disable an entire provider from one summary.

The current scheduler first filters disabled profiles, active holds and applicable exhausted windows, then prioritizes the available weekly allowance with the earliest reset, followed by least-recently-used profile. An explicit pin narrows that candidate set to one profile. Therefore pinning a full profile intentionally waits even when another account is free; clarify that tradeoff when the account constraint is requested.

A profile becomes eligible only after **its latest applicable exhausted reset** (also respecting its hold). Across profiles the first eligible profile can resume work. Example: A has five-hour reset in 10minutes but its exhausted week resets in 60minutes; B's exhausted five-hour resets in 20minutes and its week is free. The first expected opportunity is B in 20minutes, not A in 10minutes. Unknown resets prevent a firm estimate. Passing a predicted reset is not proof of a replenished balance; native checks/rejection remain authoritative.

For an unpinned read-only job, runtime quota rejection leaves the same job waiting and marks/holds the rejected account. On later ticks other eligible accounts are considered. Attempts are bounded; a terminal `failed` due to exhausted attempt budget is not a waiting job. Diagnose before an explicit retry. Authentication errors, invalid models and unrelated native errors are not automatically quota failures.

A source-profile quota check is metadata, not an instruction to rewrite limits. Only record manual quota observations when actually supplied by the provider/owner. Never set fake percentages, clear a known hold or duplicate the same task under new keys to get it running.

Provider fallback is separate from account fallback. If the task expressly allows an alternative provider/model, inspect any partial work, formulate a distinct allowed continuation/subtask with its own specification/key, and report the change. Before dispatching the permitted alternative, cancel the original queued/waiting copy and confirm it is cancelled. That cancellation is part of the authorized switch. If it is already running or cancellation is uncertain, inspect its state first and do not start a parallel copy of the same objective. Record both job IDs.
