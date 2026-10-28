# Agent Fleet account-routing contract

Behavioral contract for the execution skill and scheduler, including backend migrations. The desktop remains overview/login; agents control jobs through CLI/skills. This change requires no scheduler-runtime modification: the existing scheduler already implements the selection behavior.

## Target and portability

Explicit user target overrides personal preference. The skill reads `<connection-info.home>/skill-policy.json`; version1, `default_target.kind` is `local` or `remote`, and remote additionally has `name`. This is an agent-side preference, not a new implicit CLI flag. Agents must still pass `--remote <name>`. The shared skill source contains no private hostname.

Configured on this owner's machines: Mac points to its existing `claw-remote` connection; Linux points to its own local pool. Neither personal JSON file is committed. Missing/invalid targets do not silently redirect execution to another machine. No default project/workspace is inferred or synchronized.

## Required scheduler behavior

1. Unpinned jobs use eligible enabled profiles of the requested provider. Known exhausted five-hour, weekly or relevant model/bucket windows and active holds exclude a profile.
2. A full five-hour window on A does not block eligible B. A free five-hour window does not override an exhausted weekly window. Window duration comes from metadata, not primary/secondary position.
3. Preserve explicit model/bucket and account pins. A pinned exhausted profile intentionally waits despite other free accounts. A model-specific limit applies to its family; a different provider is never an implicit substitute.
4. Unknown usage is not fabricated as free or exhausted. A bounded native attempt can supply missing observations. A known quota rejection with unknown reset holds only that profile.
5. Read-only runtime quota rejection retains the same job/key. Another eligible same-provider profile may execute on a following tick, within the bounded attempt budget. Rejection is not a reason to duplicate the job or mutate the original specification.
6. If every matching profile is blocked, status becomes `waiting`, with no inference attempt consumed merely by waiting. For each profile all applicable exhausted windows/holds must clear. The earliest profile meeting all conditions can resume.
7. Waiting Codex work does not starve independent ready Claude work (or vice versa). The original job's provider is unchanged.
8. Editing failures/timeouts/interruption may leave partial work; `needs_review` is not automatically replayed across accounts. Explicit inspection/acknowledgment rules remain.
9. The skill submits once, polls in bounded waits, retains job ID/key and keeps an independent worker alive. It does not sleep the client for an entire five-hour window or call `work --drain` as a persistent service.
10. Explicitly permitted provider fallback creates a distinct task specification; cancel/confirm a queued old copy before the alternative to avoid duplicate execution. Never fork a possibly-running objective blindly.

Current candidate preference after eligibility filtering: earliest available weekly reset, then least recently used, then stable profile name. That ordering is secondary to the safety/eligibility contract.

## Tests

`python -m unittest discover -s tests -p test_pool_routing.py -v` proves seven scenarios against the public Store/tick boundary: full5h skip, full-week skip, runtime same-job failover/unknown reset hold, earliest jointly eligible reset, other-provider queue progress, explicit full-profile pin, and model-family isolation without provider substitution. The test provider runner is controlled and isolated; real account quotas are never overwritten or deliberately exhausted.

Existing broker/quota tests additionally cover unknown utilization, model-specific applicability, provider/pin boundaries, edit-review semantics and earliest-weekly preference. These behaviors must remain equivalent when migrating from Python to another backend; a new implementation need not preserve module names, but should run equivalent public CLI/queue scenarios.
