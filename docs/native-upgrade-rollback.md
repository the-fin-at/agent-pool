# Actual-programme upgrade and rollback acceptance

On 29 October 2026, the opt-in harness at implementation commit
`4368c158a467c30de1b5d4cb2a725201e5240b7b` completed an isolated round trip on
Linux x86_64. The [normalized evidence](native-upgrade-rollback-validation.json)
binds the source hash and actual executable hashes. This closes the pending-work
binary-handover proof in the [1.0 plan](../wiki/release-1.0.md); it is not a claim
that every 1.0 platform or deployment gate has passed.

## What the probe observes

```text
actual old 0.4.2 backup
  -> completed + queued + quota-waiting + needs_review jobs
native 0.5, same private pool
  -> old results/IDs/pins/keys retained; queued work executes once
actual old 0.4.2, same private pool
  -> pending work retained; controlled quota reset permits remaining work
```

The harness uses public CLI and RPC v1 reads, not production database fixtures or
private store methods. It runs the **actual programme backed up during the
production cutover**, rather than rebuilding the current Python oracle (which
contains later fixes). Both versions use one newly created disposable pool.

The measured round trip passed 30 checks in 9.597 seconds:

- All five job IDs and idempotency keys survived. Completed results and attempts
  were retained; the native result remained readable through old RPC v1.
- Native and old workers each respected the other runtime's worker lease.
- The controlled timeout remained `needs_review`; neither runtime silently
  replayed it. Its descendant exited.
- Quota-waiting work consumed no execution until a controlled fixture observation
  was changed. A queued job crossed upgrade; another crossed rollback.
- Five controlled invocations were observed once each, including the quarantined
  timeout. Final state was four successes and one intentional `needs_review`.
- Attached fake auth directories retained their paths, inodes, modes and sentinel
  contents. No credentials or real provider accounts were read or copied.
- Rollback replaced **only the programme**. No database restore or truncation ran.
- Both owned idle workers ended with observed exit 130 after intentional SIGTERM.
  The harness accepts explicit signal-stop statuses; this does not turn arbitrary
  service failures into success or change systemd restart policy.

Invocation counts refer only to controlled processes. They do not promise
exactly-once external side effects from a real model or third-party service.

## Repeating on the selected Linux host

Provide actual old/new executables and their independently verified hashes. The
provider must be the compiled `controlled-native-provider-0.5` acceptance fixture,
not an installed Codex or Claude CLI. The scratch parent must already exist;
choose a **new** child with the required prefix. Do not select a production pool.

```sh
python3 scripts/test_native_upgrade_rollback.py \
  --old-executable "$OLD_PROGRAMME" --old-sha256 "$OLD_SHA256" \
  --new-executable "$NATIVE_PROGRAMME" --new-sha256 "$NATIVE_SHA256" \
  --provider-executable "$CONTROLLED_PROVIDER" \
  --scratch-root "$VALIDATION_ROOT/native-upgrade-rollback.$RUN_ID"
```

`--validate-only` checks paths, hashes, runtime versions and the controlled
provider identity without creating the scratch pool. The default expected
versions are 0.4.2 and 0.5.0; explicit `--old-version`/`--new-version` select a
future pair. Every programme call includes the isolated `--home`. The process
environment points HOME, CODEX_HOME and CLAUDE_CONFIG_DIR into the new scratch
area and removes ambient API billing configuration and PYTHONPATH.

The harness rejects reused scratch paths, an ancestor containing `queue.sqlite3`
or `worker.lock` (the lease filename used by both runtimes), binary-hash/version
mismatch, and an ordinary provider CLI.
Source executables are read, not replaced; private active copies are switched
atomically. Known controlled processes are stopped; pool data, logs and
`report.json` remain for inspection. Remove only that explicitly selected test
folder after retaining the evidence you need.

Run the lightweight safety boundary tests separately:

```sh
python3 tests/real-host/test_native_upgrade_rollback.py
python3 -m py_compile scripts/test_native_upgrade_rollback.py
```

The seven safety cases use version-only executable fixtures. They prove the
harness's rejection/no-write behavior, not binary compatibility. The actual
Linux integration run supplies that separate evidence. The first safety case was
red against the initial preflight-only scaffold and green after path isolation
was implemented. Review found that a lease-only pool ancestor was incorrectly
accepted because the guard used a different filename. A public CLI regression
test reproduced that failure with the actual `worker.lock` contract, then passed
after the guard was corrected; the lease contents, inode, modification time and
directory inventory remain unchanged.

## Boundaries

This probe does not stop or change a systemd unit and does not use the live pool.
It covers pending-work handover with owned idle workers. It does not transition
an actively executing job between programmes. A later [active-execution probe](native-upgrade-rollback-active.md) covers two explicitly bounded edges separately.
The production cutover's service, backup and original-account/job verification
are separate operational evidence. This Linux result does not establish native
Windows installation, timeout/descendant behavior or GUI acceptance, and it does
not replace the native responsiveness, packaging or hosted CI gates. Those
limits remain in the [release plan](../wiki/release-1.0.md).

### Later CI decision — 29 October 2026

The user's subsequent instruction disabled all GitHub CI workflows. The earlier
reference above to a hosted CI gate is superseded by that explicit decision;
manual/native acceptance and independent reviews remain required. See the
[dated decision](../wiki/entscheidungen.md) and
[normalized GitHub evidence](release-operations-2026-10-29-validation.json).
