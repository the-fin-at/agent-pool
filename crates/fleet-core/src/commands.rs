//! Command contract: JSON on stdout-equivalent `Reply.output`; codes 0 success, 1 failure, 2 unfinished.
use crate::args::{parse, py_float_str, Args};
use crate::db::{job_code, now, summary, terminal, Db, Lease, Spec};
use crate::provider::{self, executable, plain_command, redact, STOP};
use crate::quota::{availability, timestamp};
use crate::remote::{self, RemoteClient, RemoteConfig, MAX_REQUEST, MAX_RESPONSE, PROTOCOL};
use crate::{login, monitor, service, worker, Reply, VERSION};
use anyhow::{anyhow, bail, ensure, Result};
use serde_json::{json, Value};
use std::io::Read;
use std::path::Path;
use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};

pub const FEATURES: &[&str] = &["native-login-sessions", "cached-status"];
const RPC_ACTIONS: &[&str] = &[
    "doctor",
    "connection-info",
    "status",
    "monitor",
    "workspace",
    "profile",
    "quota",
    "job",
    "auth",
];

pub fn emit(value: &Value) -> String {
    format!("{value}\n")
}

fn ok(value: Value) -> Result<Reply> {
    Ok(Reply {
        code: 0,
        output: emit(&value),
    })
}

/// Errors become `{"error": ...}` with code 1, exactly like the Python CLI and RPC.
pub fn error_reply(error: &anyhow::Error) -> Reply {
    Reply {
        code: 1,
        output: emit(&json!({"error": redact(&error.to_string())})),
    }
}

fn read_text_source(path: &str) -> Result<String> {
    if path == "-" {
        let mut s = String::new();
        std::io::stdin().read_to_string(&mut s)?;
        Ok(s)
    } else {
        Ok(std::fs::read_to_string(path)?)
    }
}

fn prompt_of(args: &Args) -> Result<String> {
    match args.opt("--prompt-file") {
        Some(path) => read_text_source(path),
        None => Ok(args.opt("--prompt").unwrap_or_default().to_string()),
    }
}

pub fn execute(home: &Path, argv: &[String]) -> Result<Reply> {
    let args = match parse(argv) {
        Ok(a) => a,
        // Help is plain text with code 0 locally; `rpc` maps every parse failure to an error.
        Err(e) => match e.downcast::<crate::args::Help>() {
            Ok(help) => {
                return Ok(Reply {
                    code: 0,
                    output: help.0,
                })
            }
            Err(e) => return Err(e),
        },
    };
    if args.version {
        return Ok(Reply {
            code: 0,
            output: format!("{VERSION}\n"),
        });
    }
    match args.action.as_str() {
        "rpc" => {
            bail!("The rpc endpoint reads one JSON request from stdin; route it to fleet_core::rpc")
        }
        "desktop" => {
            bail!("The desktop is opened by the Agent Fleet application, not the core library")
        }
        _ => {}
    }
    if let Some(name) = args.remote.clone() {
        return dispatch_remote(home, &name, &args);
    }
    dispatch(home, &args, false)
}

fn submit(db: &mut Db, args: &Args) -> Result<Value> {
    let prompt = prompt_of(args)?;
    let cwd = match (args.opt("--workspace"), args.opt("--cwd")) {
        (Some(ws), _) => db.workspace(ws)?,
        (None, Some(cwd)) => cwd.to_string(),
        (None, None) => std::env::current_dir()?.to_string_lossy().into_owned(),
    };
    let spec = Spec {
        prompt,
        cwd,
        provider: args.opt("--provider").unwrap_or_default().into(),
        profile: args.opt("--profile").map(String::from),
        model: args.opt("--model").map(String::from),
        bucket: args.opt("--bucket").map(String::from),
        allow_edits: args.flag("--allow-edits"),
        key: args.opt("--key").map(String::from),
        timeout: args.float("--timeout", 1800.0)?,
        max_attempts: args.int("--max-attempts", 6)?,
    };
    db.submit(&spec)
}

fn quotas(db: &Db, name: Option<&str>) -> Result<Value> {
    let mut result = vec![];
    let t = now();
    for p in db.profiles()? {
        let pname = p["name"].as_str().unwrap_or_default();
        if name.is_some_and(|n| n != pname) {
            continue;
        }
        let windows = db.windows(pname)?;
        let bucket = if p["provider"] == "codex" {
            Some("codex")
        } else {
            None
        };
        let state = availability(&windows, t, None, bucket).to_json();
        let mut item = p.clone();
        item["quota_known"] = json!(!windows.is_empty());
        item["windows"] = json!(windows);
        item["availability"] = state;
        result.push(item);
    }
    if let Some(n) = name {
        db.profile(n)?;
    }
    Ok(json!(result))
}

fn job_with_result(job: &Value) -> Value {
    let mut v = summary(job);
    v["result"] = job["result"].clone();
    v
}

fn job_reply(job: &Value) -> Reply {
    Reply {
        code: job_code(job),
        output: emit(&job_with_result(job)),
    }
}

fn wait_for(db: &Db, id: &str, deadline: Instant) -> Result<Value> {
    let mut job = db.job(id)?;
    while !terminal(&job) && Instant::now() < deadline {
        std::thread::sleep(
            deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_secs(1)),
        );
        job = db.job(id)?;
    }
    Ok(job)
}

fn sys_platform() -> &'static str {
    match std::env::consts::OS {
        "macos" => "darwin",
        "windows" => "win32",
        other => other,
    }
}

fn doctor(db: &Db) -> Result<Value> {
    let mut checks = vec![];
    let profiles = db.profiles()?;
    for provider in ["codex", "claude"] {
        let mut names: Vec<String> = profiles
            .iter()
            .filter(|p| p["provider"] == provider)
            .filter_map(|p| p["binary"].as_str().map(String::from))
            .collect();
        if names.is_empty() {
            names.push(provider.into());
        }
        names.sort();
        names.dedup();
        for binary in names {
            let check = (|| -> Result<Value> {
                let path = executable(&binary)?;
                let mut c = plain_command(&path);
                c.arg("--version");
                let done = provider::capture(c, None, 10.0, 1024 * 1024)?;
                ensure!(
                    !done.timed_out,
                    "Command '{} --version' timed out after 10 seconds",
                    path.display()
                );
                Ok(
                    json!({"provider": provider, "path": path.to_string_lossy(), "version": done.out.trim(),
                    "ok": done.code == 0}),
                )
            })();
            checks.push(check.unwrap_or_else(
                |e| json!({"provider": provider, "ok": false, "error": e.to_string()}),
            ));
        }
    }
    Ok(
        json!({"runtime": "rust", "version": VERSION, "platform": sys_platform(),
        "home": db.home.to_string_lossy(), "checks": checks}),
    )
}

fn interactive_login(db: &mut Db, name: &str, device_auth: bool) -> Result<Value> {
    ensure!(!crate::monitor::native_default(&db.profile(name)?), "Diese Anmeldung wird von deiner normalen Claude-CLI verwaltet. Bitte dort mit claude auth login anmelden und hier aktualisieren.");
    let dir = db.authdir(name)?;
    let _lock = Lease::acquire(&dir.join(".native.lock"))?;
    let profile = db.profile(name)?;
    let codex = profile["provider"] == "codex";
    if device_auth && !codex {
        bail!("--device-auth is supported by Codex only");
    }
    if !codex {
        login::check_claude_directory(&profile, &dir)?;
    }
    let mut cmd = provider::profile_command(&profile, &dir)?;
    if codex {
        cmd.arg("login");
        if device_auth {
            cmd.arg("--device-auth");
        }
    } else {
        cmd.args(["auth", "login", "--claudeai"]);
    }
    let status = cmd.status()?;
    if !status.success() {
        bail!(
            "Native login failed (exit {}); profile was not enabled",
            status.code().unwrap_or(1)
        );
    }
    if let Some(cached) =
        login::verify(&profile, &dir).map_err(|e| anyhow!("{e}; profile was not enabled"))?
    {
        db.cache(name, &cached)?;
    }
    db.update_profile(
        name,
        json!({"enabled": true, "hold_until": null, "hold_reason": null, "observed_at": null, "checked_at": null}),
    )?;
    Ok(json!({"profile": name, "enabled": true}))
}

fn status_value(db: &Db, accounts: Vec<Value>) -> Result<Value> {
    Ok(
        json!({"worker": worker::worker_state(&db.home), "accounts": accounts, "pending_jobs": db.pending_count()?,
        "features": FEATURES, "version": VERSION}),
    )
}

/// Local dispatch. `rpc` restricts nothing here; `rpc()` validates before calling.
pub fn dispatch(home: &Path, args: &Args, rpc: bool) -> Result<Reply> {
    let mut db = Db::open(home)?;
    let home = db.home.clone();
    match (args.action.as_str(), args.op()) {
        ("connection-info", _) => {
            let exe = std::env::current_exe()?;
            let exe = crate::db::canonical(&exe).unwrap_or(exe);
            ok(
                json!({"version": VERSION, "command": exe.to_string_lossy(), "home": home.to_string_lossy(),
                "features": FEATURES}),
            )
        }
        ("auth", "start") => ok(login::start(
            &home,
            args.need("name")?,
            args.opt("--provider").unwrap_or_default(),
            args.opt("--key").unwrap_or_default(),
        )?),
        ("auth", "get") => ok(login::status(&home, args.need("id")?)?),
        ("auth", "cancel") => ok(login::cancel(&home, args.need("id")?)?),
        ("auth", "input") => {
            let code = match args.opt("--code-file") {
                Some(path) => read_text_source(path)?,
                None => args.opt("--code").unwrap_or_default().to_string(),
            };
            ok(login::provide_code(&home, args.need("id")?, &code)?)
        }
        ("status", _) => {
            drop(db);
            let accounts = if args.flag("--refresh") {
                monitor::collect(&home, false)?
            } else {
                monitor::snapshot(&home, false)?
            };
            ok(status_value(&Db::open(&home)?, accounts)?)
        }
        ("overview", _) => {
            // Local desktop read model only; includes the monitor-only default Codex account.
            ensure!(!rpc, "RPC operation not allowed");
            drop(db);
            let accounts = if args.flag("--refresh") {
                monitor::collect(&home, true)?
            } else {
                monitor::snapshot(&home, true)?
            };
            ok(status_value(&Db::open(&home)?, accounts)?)
        }
        ("monitor", _) => {
            drop(db);
            let accounts = if args.flag("--refresh") {
                monitor::collect(&home, false)?
            } else {
                monitor::snapshot(&home, false)?
            };
            ok(Value::Array(accounts))
        }
        ("workspace", op) => {
            match op {
                "add" => {
                    db.add_workspace(args.need("name")?, args.opt("--path").unwrap_or_default())?;
                }
                "remove" => db.remove_workspace(args.need("name")?)?,
                _ => {}
            }
            ok(json!(db.workspaces()?))
        }
        ("service", _) => Ok(Reply {
            code: 0,
            output: service::unit(
                args.opt("--exec").unwrap_or_default(),
                &home.to_string_lossy(),
            )? + "\n",
        }),
        ("remote", op) => {
            let config = RemoteConfig::new(&home);
            match op {
                "add" => config.add(
                    args.need("name")?,
                    args.opt("--host").unwrap_or_default(),
                    args.opt("--command").unwrap_or("agent-fleet"),
                    args.opt("--server-home").unwrap_or_default(),
                )?,
                "remove" => config.remove(args.need("name")?)?,
                "test" => {
                    let reply = RemoteClient::new(&config.get(args.need("name")?)?)?
                        .request(&["doctor".into()])?;
                    return Ok(Reply {
                        code: reply.code,
                        output: reply.output,
                    });
                }
                "discover" => return ok(remote::discover(args.need("host")?, 20.0)?),
                _ => {}
            }
            ok(Value::Object(config.all()?))
        }
        ("init", _) => {
            let existing: Vec<String> = db
                .profiles()?
                .iter()
                .filter_map(|p| p["name"].as_str().map(String::from))
                .collect();
            for (provider, names) in [
                ("codex", vec!["codex-1", "codex-2", "codex-3"]),
                ("claude", vec!["claude-1"]),
            ] {
                for name in names {
                    if !existing.iter().any(|e| e == name) {
                        db.add_profile(name, provider, provider, None)?;
                    }
                }
            }
            ok(
                json!({"home": home.to_string_lossy(), "profiles": db.profiles()?, "next": "agent-fleet login codex-1"}),
            )
        }
        ("doctor", _) => ok(doctor(&db)?),
        ("profile", op) => {
            match op {
                "add" => {
                    let provider = args.opt("--provider").unwrap_or_default();
                    db.add_profile(
                        args.need("name")?,
                        provider,
                        args.opt("--binary").unwrap_or(provider),
                        args.opt("--auth-home"),
                    )?;
                }
                "release" => db.update_profile(
                    args.need("name")?,
                    json!({"hold_until": null, "hold_reason": null}),
                )?,
                "enable" | "disable" => {
                    db.update_profile(args.need("name")?, json!({"enabled": op == "enable"}))?
                }
                _ => {}
            }
            ok(json!(db.profiles()?))
        }
        ("login", _) => ok(interactive_login(
            &mut db,
            args.need("name")?,
            args.flag("--device-auth"),
        )?),
        ("quota", op) => {
            let name = args.pos("name");
            match op {
                "refresh" => {
                    let profiles = match name {
                        Some(n) => vec![db.profile(n)?],
                        None => db.profiles()?,
                    };
                    for p in profiles.iter().filter(|p| p["provider"] == "codex") {
                        worker::refresh(&mut db, p, &worker::native_probe);
                    }
                }
                "set" => {
                    let n = args.need("name")?;
                    let p = db.profile(n)?;
                    let reset = timestamp(args.opt("--reset-at").unwrap_or_default())?;
                    ensure!(reset > now(), "Manual reset must be in the future");
                    let used = args.float("--used", f64::NAN)?;
                    let five = args.opt("--window") == Some("five-hour");
                    let minutes = if five { 300 } else { 10080 };
                    let model = args.opt("--model");
                    let claude = p["provider"] == "claude";
                    let bucket = if claude {
                        "claude".to_string()
                    } else {
                        args.opt("--bucket").unwrap_or("codex").to_string()
                    };
                    let key = if claude {
                        if five {
                            "five_hour".to_string()
                        } else {
                            format!(
                                "seven_day{}",
                                model.map(|m| format!("_{m}")).unwrap_or_default()
                            )
                        }
                    } else if five {
                        format!("{bucket}:primary")
                    } else {
                        format!("{bucket}:secondary")
                    };
                    ensure!(
                        used.is_finite() && (0.0..=100.0).contains(&used),
                        "Quota used must be a percentage from 0 to 100"
                    );
                    db.set_windows(
                        n,
                        &[
                            json!({"key": key, "bucket": bucket, "minutes": minutes, "used": used,
                        "reset": reset, "model": model}),
                        ],
                        false,
                    )?;
                    // A user observation makes a formerly unknown reset known.
                    if p["hold_reason"] == "quota_reset_unknown" {
                        db.update_profile(n, json!({"hold_until": null, "hold_reason": null}))?;
                    }
                }
                _ => {}
            }
            ok(quotas(&db, name)?)
        }
        ("job", "submit") => ok(summary(&submit(&mut db, args)?)),
        ("job", "list") => ok(json!(db
            .jobs(false)?
            .iter()
            .map(summary)
            .collect::<Vec<_>>())),
        ("job", op @ ("get" | "wait")) => {
            let id = args.need("id")?;
            let seconds = if op == "wait" {
                args.float("--seconds", 60.0)?
            } else {
                0.0
            };
            let span = if seconds.is_finite() {
                seconds.clamp(0.0, 1e7)
            } else if seconds > 0.0 {
                1e7
            } else {
                0.0
            };
            let job = wait_for(&db, id, Instant::now() + Duration::from_secs_f64(span))?;
            if args.flag("--result-only") {
                ensure!(
                    job["status"] == "succeeded",
                    "Job has not succeeded: {}",
                    job["status"].as_str().unwrap_or("")
                );
                return Ok(Reply {
                    code: 0,
                    output: format!("{}\n", job["result"].as_str().unwrap_or("")),
                });
            }
            Ok(job_reply(&job))
        }
        ("job", op @ ("retry" | "cancel")) => {
            let id = args.need("id")?;
            let job = db.job(id)?;
            ensure!(
                job["status"] != "running",
                "Job is running; inspect its status. Only the server administrator should recover a stopped worker"
            );
            if op == "retry" {
                ensure!(
                    matches!(
                        job["status"].as_str(),
                        Some("failed" | "needs_review" | "cancelled")
                    ),
                    "Only a stopped terminal job can be retried"
                );
                if rpc {
                    ensure!(
                        job["status"] != "needs_review" || args.flag("--acknowledge-review"),
                        "Inspect the server workspace and surviving processes, then retry with --acknowledge-review"
                    );
                }
                let changed = db.transition(
                    id,
                    &["failed", "needs_review", "cancelled"],
                    json!({"status": "queued", "attempts": 0, "result": null, "error": null}),
                )?;
                ensure!(changed, "Job changed before retry; reload it");
            } else {
                ensure!(
                    matches!(job["status"].as_str(), Some("queued" | "waiting")),
                    "Only queued or waiting jobs can be cancelled"
                );
                let changed = db.transition(
                    id,
                    &["queued", "waiting"],
                    json!({"status": "cancelled", "error": "Cancelled by user"}),
                )?;
                ensure!(
                    changed,
                    "Job already started; running tasks cannot be cancelled"
                );
            }
            ok(summary(&db.job(id)?))
        }
        ("work" | "run", _) => {
            ensure!(!rpc, "RPC operation not allowed");
            work(db, args)
        }
        _ => bail!("Unsupported command"),
    }
}

fn interruptible_sleep(seconds: f64) {
    let until = Instant::now() + Duration::from_secs_f64(seconds.max(0.0));
    while Instant::now() < until && !provider::stopping() {
        std::thread::sleep(
            until
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(100)),
        );
    }
}

fn stopped_reply() -> Reply {
    eprintln!("Worker stopped; queued jobs remain persisted.");
    Reply {
        code: 130,
        output: String::new(),
    }
}

fn work(mut db: Db, args: &Args) -> Result<Reply> {
    let run = args.action == "run";
    let wait = args.float("--wait-seconds", 60.0)?;
    if run {
        ensure!(
            wait.is_finite() && wait >= 0.0,
            "Wait time cannot be negative"
        );
    }
    let poll = args.float("--poll", 5.0)?;
    let job = if run {
        Some(submit(&mut db, args)?)
    } else {
        None
    };
    let deadline = Instant::now() + Duration::from_secs_f64(if run { wait.min(1e7) } else { 0.0 });
    let _lease = match db.worker_lock() {
        Ok(l) => l,
        Err(e) if crate::db::is_busy(&e) && job.is_some() => {
            let id = job
                .as_ref()
                .and_then(|j| j["id"].as_str())
                .unwrap_or_default()
                .to_string();
            return Ok(job_reply(&wait_for(&db, &id, deadline)?));
        }
        Err(e) => return Err(e),
    };
    provider::install_signal_handler();
    STOP.store(false, Ordering::SeqCst);
    let _heartbeat = worker::Heartbeat::start(&db.home);
    let recovered = db.recover()?;
    if recovered > 0 {
        eprintln!("Recovered {recovered} interrupted job(s) as needs_review");
    }
    let mut next_monitor = Instant::now();
    loop {
        if provider::stopping() {
            return Ok(stopped_reply());
        }
        if let Some(j) = &job {
            let current = db.job(j["id"].as_str().unwrap_or_default())?;
            if terminal(&current) || Instant::now() >= deadline {
                return Ok(job_reply(&current));
            }
        }
        if !run && Instant::now() >= next_monitor {
            let _ = monitor::refresh_codex(&db.home);
            next_monitor = Instant::now() + Duration::from_secs(60);
        }
        let did_work =
            match worker::tick(&mut db, &worker::native_runner, &worker::native_probe, None) {
                Ok(v) => v,
                Err(e) if e.downcast_ref::<provider::Interrupted>().is_some() => {
                    return Ok(stopped_reply())
                }
                Err(e) => return Err(e),
            };
        if !run && (args.flag("--once") || (args.flag("--drain") && !did_work)) {
            let jobs: Vec<Value> = db.jobs(false)?.iter().map(summary).collect();
            return ok(json!({"processed": did_work, "jobs": jobs}));
        }
        if !did_work {
            let base = if run { 2.0 } else { poll };
            let mut pause = if base.is_nan() {
                1.0
            } else {
                base.clamp(1.0, 30.0)
            };
            if run {
                pause = pause.min(
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_secs_f64(),
                );
            }
            interruptible_sleep(pause);
        }
    }
}

fn task_argv(args: &Args) -> Result<Vec<String>> {
    ensure!(
        args.opt("--workspace").is_some() && args.opt("--cwd").is_none(),
        "Remote tasks require --workspace <server-name>; local --cwd is not transferred"
    );
    ensure!(
        args.opt("--key").is_some_and(|k| !k.is_empty()),
        "Remote tasks require a stable --key for safe retries after disconnection"
    );
    let prompt = prompt_of(args)?;
    let mut argv: Vec<String> = vec![
        "job".into(),
        "submit".into(),
        "--provider".into(),
        args.opt("--provider").unwrap_or_default().into(),
        "--workspace".into(),
        args.opt("--workspace").unwrap_or_default().into(),
        format!("--prompt={prompt}"),
        "--key".into(),
        args.opt("--key").unwrap_or_default().into(),
        "--timeout".into(),
        py_float_str(args.float("--timeout", 1800.0)?),
        "--max-attempts".into(),
        args.int("--max-attempts", 6)?.to_string(),
    ];
    for field in ["--profile", "--model", "--bucket"] {
        if let Some(v) = args.opt(field).filter(|v| !v.is_empty()) {
            argv.push(field.into());
            argv.push(v.into());
        }
    }
    if args.flag("--allow-edits") {
        argv.push("--allow-edits".into());
    }
    Ok(argv)
}

fn forward(client: &RemoteClient, argv: &[String]) -> Result<Reply> {
    let reply = client.request(argv)?;
    Ok(Reply {
        code: reply.code,
        output: reply.output,
    })
}

/// Client side of `--remote NAME`; compatible with Python 0.4.x servers.
pub fn dispatch_remote(home: &Path, name: &str, args: &Args) -> Result<Reply> {
    let client = RemoteClient::new(&RemoteConfig::new(home).get(name)?)?;
    let action = args.action.as_str();
    let op = args.op();
    let s = |v: &str| v.to_string();
    match action {
        "auth" => {
            let mut argv = vec![s("auth"), s(op)];
            if op == "start" {
                argv.extend([
                    s(args.need("name")?),
                    s("--provider"),
                    s(args.opt("--provider").unwrap_or_default()),
                    s("--key"),
                    s(args.opt("--key").unwrap_or_default()),
                ]);
            } else {
                argv.push(s(args.need("id")?));
            }
            if op == "input" {
                let code = match args.opt("--code-file") {
                    Some(path) => read_text_source(path)?,
                    None => s(args.opt("--code").unwrap_or_default()),
                };
                argv.push(format!("--code={}", code.trim()));
            }
            forward(&client, &argv)
        }
        "login" => {
            let mut extra = vec![s(args.need("name")?)];
            if args.flag("--device-auth") {
                extra.push(s("--device-auth"));
            }
            let ssh = client.argv("login", true, &extra);
            let status = std::process::Command::new(&ssh[0])
                .args(&ssh[1..])
                .status()?;
            Ok(Reply {
                code: status.code().unwrap_or(1),
                output: String::new(),
            })
        }
        "work" => bail!("Run work as a persistent service on Linux; use docs/remote.md"),
        "run" => {
            let wait = args.float("--wait-seconds", 60.0)?;
            ensure!(
                wait.is_finite() && (0.0..=60.0).contains(&wait),
                "Remote run --wait-seconds must be between 0 and 60; use job get for later results"
            );
            let reply = client.request(&task_argv(args)?)?;
            if reply.code != 0 {
                return Ok(Reply {
                    code: reply.code,
                    output: reply.output,
                });
            }
            let job: Value = serde_json::from_str(&reply.output)
                .map_err(|_| anyhow!("Invalid remote command response"))?;
            let id = job["id"]
                .as_str()
                .ok_or_else(|| anyhow!("Invalid remote command response"))?;
            forward(
                &client,
                &[
                    s("job"),
                    s("wait"),
                    s(id),
                    s("--seconds"),
                    py_float_str(wait),
                ],
            )
        }
        "job" if op == "submit" => forward(&client, &task_argv(args)?),
        "init" => {
            bail!("Perform initial setup and workspace/profile registration directly on the server")
        }
        "workspace" if op != "list" => {
            bail!("Perform initial setup and workspace/profile registration directly on the server")
        }
        "profile" if op == "add" => {
            bail!("Perform initial setup and workspace/profile registration directly on the server")
        }
        "doctor" => forward(&client, &[s("doctor")]),
        "monitor" | "status" | "overview" => {
            ensure!(
                !args.flag("--refresh"),
                "The persistent server worker refreshes metadata; read status without --refresh"
            );
            // Remote status is always the server's cache; the default local source never applies.
            forward(
                &client,
                &[s(if action == "monitor" {
                    "monitor"
                } else {
                    "status"
                })],
            )
        }
        "profile" | "workspace" => {
            let mut argv = vec![s(action), s(op)];
            if let Some(n) = args.pos("name") {
                argv.push(s(n));
            }
            forward(&client, &argv)
        }
        "quota" if op == "show" => {
            let mut argv = vec![s("quota"), s("show")];
            if let Some(n) = args.pos("name") {
                argv.push(s(n));
            }
            forward(&client, &argv)
        }
        "job" => {
            let mut argv = vec![s("job"), s(op)];
            if let Some(id) = args.pos("id") {
                argv.push(s(id));
            }
            if op == "wait" {
                argv.extend([s("--seconds"), py_float_str(args.float("--seconds", 60.0)?)]);
            }
            if args.flag("--acknowledge-review") {
                argv.push(s("--acknowledge-review"));
            }
            if args.flag("--result-only") {
                argv.push(s("--result-only"));
            }
            forward(&client, &argv)
        }
        _ => bail!("This operation must be performed directly on the server"),
    }
}

fn rpc_checks(args: &Args) -> Result<()> {
    // Root globals cannot follow subcommands. RPC never accepts a client home or nested remote.
    ensure!(
        args.remote.is_none() && !args.version,
        "Nested remotes are forbidden"
    );
    let (action, op) = (args.action.as_str(), args.op());
    if matches!(action, "monitor" | "status") && args.flag("--refresh") {
        bail!("The persistent worker refreshes metadata; RPC reads the cache only");
    }
    ensure!(
        !(action == "quota" && op != "show"),
        "Quota observations are maintained on the server"
    );
    ensure!(
        !(action == "workspace" && op != "list"),
        "Register workspaces directly on the server"
    );
    ensure!(
        !(action == "profile" && op == "add"),
        "Add native executables and profiles directly on the server"
    );
    ensure!(
        !(action == "auth" && op == "input" && args.opt("--code-file").is_some()),
        "RPC login codes are transferred directly, not read from server files"
    );
    if action == "job" && op == "submit" {
        let ok = args.opt("--workspace").is_some()
            && args.opt("--cwd").is_none()
            && args.opt("--prompt-file").is_none()
            && args.opt("--key").is_some_and(|k| !k.is_empty());
        ensure!(
            ok,
            "Remote submit requires --workspace, --prompt and a stable --key"
        );
    }
    if action == "job" && op == "wait" {
        let seconds = args.float("--seconds", 60.0)?;
        ensure!(
            seconds.is_finite() && (0.0..=60.0).contains(&seconds),
            "Remote waits must be between 0 and 60 seconds"
        );
    }
    Ok(())
}

fn rpc_handle(home: &Path, request: &Value) -> Result<Reply> {
    let map = request
        .as_object()
        .ok_or_else(|| anyhow!("Incompatible remote protocol"))?;
    let keys_ok = map.len() == 2 && map.contains_key("version") && map.contains_key("argv");
    let version_ok = map
        .get("version")
        .is_some_and(|v| (v.is_i64() || v.is_u64()) && v.as_i64() == Some(PROTOCOL));
    ensure!(keys_ok && version_ok, "Incompatible remote protocol");
    let argv = map["argv"]
        .as_array()
        .filter(|a| !a.is_empty() && a.iter().all(Value::is_string));
    let argv: Vec<String> = argv
        .ok_or_else(|| anyhow!("RPC argv must be a nonempty string array"))?
        .iter()
        .map(|v| v.as_str().unwrap_or_default().to_string())
        .collect();
    ensure!(
        !argv.iter().any(|t| t.contains('\0')),
        "NUL in RPC arguments"
    );
    ensure!(
        RPC_ACTIONS.contains(&argv[0].as_str()),
        "RPC operation not allowed"
    );
    let args = parse(&argv).map_err(|_| anyhow!("Invalid RPC arguments"))?;
    rpc_checks(&args)?;
    dispatch(home, &args, true)
}

fn envelope(reply: Reply) -> Value {
    let response = json!({"version": PROTOCOL, "code": reply.code, "output": reply.output});
    if response.to_string().len() > MAX_RESPONSE {
        return json!({"version": PROTOCOL, "code": 1,
            "output": json!({"error": "Response exceeds 10 MiB; retrieve individual jobs"}).to_string()});
    }
    response
}

/// Version-1 envelope for one decoded request; never panics on hostile input.
pub fn rpc(home: &Path, request: Value) -> Value {
    let reply = rpc_handle(home, &request).unwrap_or_else(|e| error_reply(&e));
    envelope(reply)
}

/// Raw stdin bytes of `agent-fleet rpc`: size limit, UTF-8, JSON nesting all enforced.
pub fn rpc_bytes(home: &Path, raw: &[u8]) -> Value {
    if raw.len() > MAX_REQUEST {
        return envelope(error_reply(&anyhow!("Remote request exceeds 2 MiB")));
    }
    let parsed = std::str::from_utf8(raw)
        .map_err(|e| anyhow!("{e}"))
        .and_then(|text| serde_json::from_str::<Value>(text).map_err(|e| anyhow!("{e}")));
    match parsed {
        Ok(request) => rpc(home, request),
        Err(e) => envelope(error_reply(&e)),
    }
}
