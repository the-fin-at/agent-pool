# Native performance acceptance

Requested in [issue #25](https://github.com/the-fin-at/agent-pool/issues/25) on 29 October 2026. This is the performance gate from [the 1.0 plan](../wiki/release-1.0.md), not an inference-speed benchmark.

## Public boundaries and budgets

- Twenty sequential native CLI `status` calls through an explicitly selected, real SSH connection. Every call reads the server cache without `--refresh`. Nearest-rank p95 must be below **3,000 ms**. The cold first call remains in the samples.
- The actual macOS WKWebView calls `fleet_request` in the actual Rust bridge. An owned wrapper executes the real native server's RPC and delays its response for at least **2,000 ms**. During three such requests, a 20 ms timer measures scheduling lag, `requestAnimationFrame` measures frame intervals, and a visible React provider filter must change before the reply arrives.
- Timer lag p95 must be below **100 ms**, maximum below **500 ms**. Frame intervals use the same budgets. At least 50 timer and frame samples must exist during each delayed request. Filter response must remain below 500 ms.
- Before those requests, the **same native instrument** observes an intentional 700 ms main-thread block. It must reject this control under the normal p95/maximum budgets. Otherwise the harness refuses a pass.

The timer window starts immediately before invoking the task and includes the first scheduled callbacks after completion. This trailing observation is necessary: a synchronous block could otherwise finish before its delayed callback is collected. Startup and a documented settling period are excluded. Quantiles use the sorted sample at index `ceil(p * n) - 1`; no interpolated or hand-selected samples are substituted. Raw timing arrays remain in the JSON evidence.

This proves native IPC/event-loop responsiveness and a visible filter interaction under transport delay. It does not measure every connection-navigation journey, card-render throughput, model inference or native Windows performance. Existing Tk and `fakeTransport` tests are not used as evidence here.

## Run

Requirements are the installed native CLI, an existing explicit SSH connection, Python 3, and a built debug Tauri application with `custom-protocol`. The release application deliberately has no injection/reporting hook. Native UI acceptance requires an unlocked macOS console session; a failed preflight exits 77 without starting an app. The selected SSH configuration and existing trust remain unchanged.

```sh
python3 scripts/test_native_performance.py \
  --remote <project-connection> \
  --desktop <candidate-worktree>/target/debug/agent-fleet-desktop \
  --output <new-private-output-directory>
```

The harness uses the public `remote list`/`remote add` CLI to create its private client fixture. It does not change the user's connection preferences. The configured server binary must be native and compatible with the selected desktop. Its hash/version and the desktop/CLI hashes are recorded; known 0.5 artifacts are additionally compared with [the migration manifest](rust-tauri-validation.json). A caller must bind an unfamiliar future build to its candidate commit rather than infer build provenance from a version string.

The SSH-only gate can be run without a graphical console:

```sh
python3 scripts/test_native_performance.py \
  --remote <project-connection> --ssh-only \
  --output <new-private-output-directory>
```

SSH-only success means `requested_gates_passed: true` while `all_gates_passed: false`; `native_ui.not_requested` remains explicit. Sample counts outside 20–100 and configured delays outside 2–5 seconds are rejected before any SSH or GUI work. Thresholds are not configurable. A locked session is unavailable, not a green UI result; unlock is never automated. A bounded display/idle sleep assertion lasts only for the owned app process and does not simulate user input or change security settings.

## Isolation and evidence

Production receives cached status reads only. Outputs are parsed in memory and reduced to timings, response size, version and nonidentifying counts. Emails, prompts, results, native authentication directories and credential contents are not logged or copied.

The delayed endpoint uses a uniquely generated private directory next to the selected pool, a new empty pool, and isolated `HOME`, `CODEX_HOME` and `CLAUDE_CONFIG_DIR`. It executes the configured native binary over real SSH. No worker, provider inference or login is started. After the run, the wrapper's observed delay timings are retrieved and its generated directory removed. Cleanup never targets a supplied production home. The native app and temporary client pool are also owned by the invocation.

`performance.json` includes raw samples, hard budgets, negative control, interaction results, remote delay observations, platform/architecture, executable hashes, reviewed application reference and harness content hashes. The latter identify an uncommitted test implementation without falsely claiming that it already existed in the recorded Git base. Native failures retain a report when possible; timeouts and unavailable sessions cannot be presented as passes.

## Evidence recorded on 29 October 2026

The initial actual SSH run against the newly upgraded native 0.5 production server passed at p95 **537.9 ms**. A rerun using public CLI fixture configuration passed at p95 **560.4 ms** (20 samples, maximum 602.6 ms). These are historical intermediate measurements. The final SSH-only run of the hardened harness passed at p95 **652.8 ms**, maximum **686.2 ms**; all 20 responses reported native 0.5.0. Its raw samples and nonidentifying load context are in [native-performance-validation.json](native-performance-validation.json).

The first UI preflight reported `screen_locked: true`, `console_session: true`, using the corrected `kCGSSessionOnConsoleKey`. It exited 77 before any app or provider started. That was a genuine locked screen, separate from the earlier corrected console-key typo. At that historical checkpoint, the native gate remained open; SSH success alone did not satisfy it.

After the user confirmed that the Mac was unlocked on 29 October 2026, the unchanged harness at `the-fin-at/agent-pool@c6be2d9b0904685bbdfe0b11b7063ecf93bb337d` completed the actual native run. Both console checks observed `screen_locked: false`, `console_session: true`. The reviewed 0.5 debug WKWebView/bridge, installed CLI and remote Rust binary matched the migration manifest hashes.

The same native instrument rejected its deliberate main-thread block: timer maximum **700 ms**, frame maximum **712 ms**. During the three real delayed SSH requests, combined timer lag p95/maximum was **5/5 ms** across 335 samples, and frame interval p95/maximum was **18/54 ms** across 478 samples. Each visible React filter interaction completed in **31 ms** before its pending request returned. The remote wrapper independently recorded three successful native RPCs with delays of **2,000.126**, **2,000.203** and **2,000.244 ms**. All per-request and combined budgets passed without changing thresholds or source.

The same full run's twenty cache-only production status reads passed at p95 **643.06 ms**, maximum **797.67 ms**. No provider inference, worker change or production queue mutation occurred. The owned app exited, its temporary local pool was removed, and a subsequent read-only check found zero generated remote performance directories. [The normalized evidence](native-performance-validation.json) retains raw timing arrays, the negative control, executable/source bindings and raw-report hashes. This later full pass supersedes the earlier locked-console performance gap; it does not establish Windows performance, every navigation journey, installed-release GUI behavior or a complete 1.0 release.
