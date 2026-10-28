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

## Delivered proof

Reviewed source: `003ccfd`, against main `50e4297`. Standards: 0 open findings; Spec: 0 open findings. The read-only forward review covered full5h/free alternative, all blocked with an existing job, explicit pin, required Opus vs free Sonnet, unknown utilization, and an authorized provider switch with cancellation confirmation.

The complete Mac/Tk suite passes **141 tests**. The seven isolated routing cases also pass on the real Linux host. A real Codex submission resolved its target from the owner's machine-local policy, omitted `--profile` and used the normal six-attempt budget. Job `07d24f30aad04f9486286554f0de992e` had `profile: null`, was automatically assigned to `server-codex`, succeeded in one attempt and returned the verified result `{"routing_check":"OK","sum":42}`.

The real pool had usable capacity, so the live job proves unpinned routing, not an actually exhausted account. Exhaustion and failover were proved in isolated tests; real account limits were not falsified or deliberately consumed. Updated Codex/Claude skill files are installed on Mac and server with previous owned versions backed up. No service restart or executable update was necessary.

[Normalized evidence](agent-routing-validation.json). Hosted CI is a separate gate; the known billing block is not a passing matrix run. Personal policy files stay on their respective machines.
