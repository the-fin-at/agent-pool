# Two active-execution handover edges

The [pending-work acceptance](native-upgrade-rollback.md) remains a separate,
previously accepted proof. On 29 October 2026, the opt-in `--scenario active` probe
at implementation commit `a31bcdd8a99fb7469349158dcfbe536516a15ba9` passed 30 checks
on Linux x86_64 in 12.775 seconds. The [normalized evidence](native-upgrade-rollback-active-validation.json)
binds the script, controlled example source, compiled fixture and actual
programme hashes to that run. This addresses issue #31.

| Direction | Controlled operation | Observed outcome |
| --- | --- | --- |
| Actual old 0.4.2 → native 0.5 | WAIT for held execution to finish, then stop idle worker | Ordinary result and one attempt survive; independent work progresses once after profile restoration |
| Native 0.5 → actual old 0.4.2 | INTERRUPT editable execution with an observed descendant and partial effect | Exit 130; `needs_review`, one attempt and partial effect survive rollback; uncertain work is not replayed |

## What actually ran

Both edges use the actual old programme archive created during the production
cutover and the independently verified native 0.5 executable. The old programme
was not rebuilt from the current Python reference. Only the controlled provider
example was rebuilt, offline in the existing local Linux/amd64 Rust container
and caches. No compiler or packages were installed on the SSH host, and the
installed native executable was unchanged.

Every programme command uses the same newly created private pool through an
explicit `--home`. HOME, CODEX_HOME and CLAUDE_CONFIG_DIR point to owned scratch
paths. The provider reads fake account markers, records its real invocation/PID,
and holds execution until a fixture release file appears (bounded to 30 seconds).
The interrupt mode requires the actual `workspace-write` sandbox argument,
writes a known partial workspace effect, starts a controlled descendant, then
publishes readiness atomically. Assertions combine public CLI/RPC job states,
real `/proc` process identity/state, invocation records and workspace effects.

For WAIT, the old worker first exposes `running`/attempts 1 while its provider is
held. A ready job and a quota-waiting job remain at attempts 0. The probe disables
every eligible fixture profile through public CLI, releases the active provider,
and observes its ordinary completed result. The old worker observes the disabled
profiles without claiming later work. After that idle worker stops, native
successfully acquires the lease and restores the exact original profile enabled
map. Ready work succeeds once; quota-waiting work stays unstarted until a
controlled quota observation/reset permits it.

For INTERRUPT, native exposes another `running`/attempts 1 job with `allow_edits`,
a live controlled parent/descendant and a known partial effect. The probe gates
eligible profiles again and sends SIGTERM only to its owned native worker.
Native exits 130, leaves `needs_review`/attempts 1 and terminates both controlled
processes. After programme-only rollback, actual old 0.4.2 reads the unchanged job
through RPC, returns the same ID for an identical retry, acquires the released
lease and completes independent pending work after exact profile restoration.
The interrupted job, invocation count and partial effect remain unchanged.
Interrupted stdout is not promised as a saved result.

All five durable IDs survived. Four jobs succeeded with their known results and
one attempt each; the interrupted job remained `needs_review`. Exactly five
controlled invocations were counted. Attached fake auth paths, directory inodes,
modes and sentinel hashes remained intact, including an initially disabled
profile. No database restore or truncation ran. Every owned worker stopped with
observed exit 130; the native active stop is explicitly required to return 130.
The final read-only cleanup check found no active controlled provider processes.

## Repeating the probe

Use the explicit executable/hash/provider/scratch arguments in the
[pending-work runbook](native-upgrade-rollback.md#repeating-on-the-selected-linux-host),
adding `--scenario active` and selecting the controlled fixture built from the
matching example source. Keep the default `--scenario pending` for the original
30-check regression. The same preflight path/hash/version/provider protections
apply; seven public CLI safety tests remain green.

TDD used the same agreed public worker/provider boundaries. Before adding WAIT,
the original compiled provider completed instead of holding the execution and
the probe failed. After WAIT was added, its 12-check tracer passed. Before adding
INTERRUPT, the WAIT-only provider again completed without its requested barrier;
the next probe failed. The final compiled provider passed both active edges.
The full existing pending scenario also passed with the new fixture. Syntax,
Rust formatting and diff checks passed.

## Limits and remaining gates

This is an **exclusive controlled fixture workflow**. Profile disable/enable is
a per-profile administrative seam; it is not an atomic pool-wide pause or
stop-after-current API. No concurrent administrator changes the profile map in
this probe. The worker's public job behavior supplies the evidence that later
work remains unclaimed while those fixture profiles are disabled.

These two edges do not establish symmetric coverage: native→old WAIT and
old→native INTERRUPT are still unproven here. The test does not model a systemd
cutover, unexpected host/power loss, real provider inference, credential changes,
Windows execution or GUI behavior. It makes no exactly-once external side-effect
promise and does not describe interruption as graceful completion. Production
service verification and the other 1.0 gates remain separate evidence.
