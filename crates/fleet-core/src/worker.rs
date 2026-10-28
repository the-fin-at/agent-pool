//! One worker per queue (worker.lock); submitters and administrators may run concurrently.
use crate::db::{is_busy, now, resolve, truth, Db, Lease};
use crate::provider::{read_codex_quota, run_native, Interrupted, Outcome};
use crate::quota::availability;
use anyhow::Result;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

pub type Runner<'a> = &'a dyn Fn(&Value, &Value, &Path) -> Result<Outcome>;
pub type QuotaProbe<'a> = &'a dyn Fn(&Value, &Path) -> Result<Vec<Value>>;

pub fn native_runner(profile: &Value, job: &Value, dir: &Path) -> Result<Outcome> {
    run_native(profile, job, dir)
}

pub fn native_probe(profile: &Value, dir: &Path) -> Result<Vec<Value>> {
    read_codex_quota(profile, dir)
}

fn bucket_for(profile: &Value, job: &Value) -> Option<String> {
    if profile["provider"] == "codex" {
        Some(
            job["bucket"]
                .as_str()
                .filter(|b| !b.is_empty())
                .unwrap_or("codex")
                .to_string(),
        )
    } else {
        None
    }
}

/// Metadata-only quota read for Codex profiles; failures are recorded, never fabricated.
pub fn refresh(db: &mut Db, profile: &Value, probe: QuotaProbe) -> bool {
    if profile["provider"] != "codex" {
        return false;
    }
    let name = profile["name"].as_str().unwrap_or_default().to_string();
    let attempt = (|| -> Result<()> {
        let dir = db.authdir(&name)?;
        let windows = probe(profile, &dir)?;
        db.set_windows(&name, &windows, true)?;
        if profile["hold_reason"] == "quota_reset_unknown" {
            db.update_profile(&name, json!({"hold_until": null, "hold_reason": null}))?;
        }
        Ok(())
    })();
    match attempt {
        Ok(()) => true,
        Err(e) => {
            let _ = db.update_profile(
                &name,
                json!({"quota_error": e.to_string(), "checked_at": now()}),
            );
            false
        }
    }
}

/// Same-provider candidates only; pinned jobs never fail over to another account.
/// Preference: weekly allowance expiring soonest, then least recently used, then name.
pub fn choose(db: &Db, job: &Value, at: f64) -> Result<(Option<Value>, Option<String>)> {
    choose_except(db, job, at, &HashSet::new())
}

/// Like [`choose`], skipping accounts whose native lock is held during this tick only.
pub fn choose_except(
    db: &Db,
    job: &Value,
    at: f64,
    busy: &HashSet<String>,
) -> Result<(Option<Value>, Option<String>)> {
    let mut candidates: Vec<(f64, f64, String, Value)> = vec![];
    let mut reasons: Vec<String> = vec![];
    let pinned = job["profile"].as_str().filter(|p| !p.is_empty());
    for p in db.profiles()? {
        let name = p["name"].as_str().unwrap_or_default().to_string();
        if p["provider"] != job["provider"] || pinned.is_some_and(|x| x != name) {
            continue;
        }
        if busy.contains(&name) {
            reasons.push(format!("{name}:busy"));
            continue;
        }
        if !truth(&p["enabled"]) {
            reasons.push(format!("{name}:disabled_or_not_logged_in"));
            continue;
        }
        if let Some(reason) = p["hold_reason"].as_str().filter(|r| !r.is_empty()) {
            if p["hold_until"].as_f64().is_none_or(|u| u > at) {
                reasons.push(format!("{name}:{reason}"));
                continue;
            }
        }
        let state = availability(
            &db.windows(&name)?,
            at,
            job["model"].as_str(),
            bucket_for(&p, job).as_deref(),
        );
        if !state.ready {
            reasons.push(format!("{name}:{}", state.reason));
            continue;
        }
        let last = p["last_used"].as_f64().unwrap_or(0.0);
        candidates.push((state.weekly_reset.unwrap_or(f64::INFINITY), last, name, p));
    }
    candidates.sort_by(|a, b| {
        a.0.partial_cmp(&b.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
            .then(a.2.cmp(&b.2))
    });
    match candidates.into_iter().next() {
        Some(c) => Ok((Some(c.3), None)),
        None => Ok((
            None,
            Some(if reasons.is_empty() {
                "No matching profile; add a profile and log in".into()
            } else {
                reasons.join("; ")
            }),
        )),
    }
}

/// Caller holds the worker lease. Executes at most one job per tick; true when work happened.
/// An account whose `.native.lock` is held (login/metadata session) is skipped for this tick
/// only: unpinned jobs use another ready account and later jobs still run.
pub fn tick(db: &mut Db, runner: Runner, probe: QuotaProbe, at: Option<f64>) -> Result<bool> {
    tick_inner(db, runner, probe, at, &choose_except)
}

pub type Chooser<'a> = &'a dyn Fn(&Db, &Value, f64) -> Result<(Option<Value>, Option<String>)>;
type Selector<'a> =
    &'a dyn Fn(&Db, &Value, f64, &HashSet<String>) -> Result<(Option<Value>, Option<String>)>;

/// Custom chooser (tests/integration). A chooser that keeps returning a busy account is
/// bounded: the job waits for this tick and the next job is considered.
pub fn tick_with(
    db: &mut Db,
    runner: Runner,
    probe: QuotaProbe,
    at: Option<f64>,
    chooser: Chooser,
) -> Result<bool> {
    tick_inner(db, runner, probe, at, &|db, job, at, _busy| {
        chooser(db, job, at)
    })
}

/// Nonblocking probe of the account lock, released immediately; the runner re-acquires it.
fn account_busy(db: &Db, name: &str) -> bool {
    match db.authdir(name) {
        Ok(dir) => matches!(Lease::acquire(&dir.join(".native.lock")), Err(e) if is_busy(&e)),
        // Missing attached directories are reported by the normal execution path.
        Err(_) => false,
    }
}

fn tick_inner(
    db: &mut Db,
    runner: Runner,
    probe: QuotaProbe,
    at: Option<f64>,
    select: Selector,
) -> Result<bool> {
    let at = at.unwrap_or_else(now);
    let jobs = db.jobs(true)?;
    if jobs.is_empty() {
        return Ok(false);
    }
    let providers: Vec<&Value> = jobs.iter().map(|j| &j["provider"]).collect();
    for p in db.profiles()? {
        // Probing is per-profile and metadata-only, with a 60-second cache.
        if truth(&p["enabled"]) && p["provider"] == "codex" && providers.contains(&&p["provider"]) {
            let stale = p["checked_at"].as_f64().is_none_or(|c| at - c >= 60.0);
            if stale {
                refresh(db, &p, probe);
            }
        }
    }
    let mut busy: HashSet<String> = HashSet::new();
    let bound = db.profiles()?.len() + 1;
    'jobs: for job in jobs {
        let id = job["id"].as_str().unwrap_or_default().to_string();
        let cwd = job["cwd"].as_str().unwrap_or_default();
        let cwd_path = Path::new(cwd);
        if !cwd_path.is_dir() || resolve(cwd_path).to_string_lossy() != cwd {
            db.transition(
                &id,
                &["queued", "waiting"],
                json!({"status": "needs_review",
                "error": "Working directory disappeared or its symlink target changed"}),
            )?;
            continue;
        }
        if job["attempts"].as_i64().unwrap_or(0) >= job["max_attempts"].as_i64().unwrap_or(1) {
            db.transition(
                &id,
                &["queued", "waiting"],
                json!({"status": "failed", "error": "Maximum attempts reached"}),
            )?;
            continue;
        }
        let mut selections = 0;
        let (profile, name, result) = loop {
            selections += 1;
            let (profile, reason) = select(db, &job, at, &busy)?;
            let chosen = profile
                .as_ref()
                .and_then(|p| p["name"].as_str())
                .map(String::from);
            let repeat = chosen.as_ref().is_some_and(|n| busy.contains(n));
            let (Some(profile), Some(name), false) =
                (profile, chosen.clone(), repeat || selections > bound)
            else {
                let reason = match (&chosen, reason) {
                    (Some(n), _) if repeat => Some(format!("{n}:busy")),
                    (_, r) => r,
                };
                db.transition(
                    &id,
                    &["queued", "waiting"],
                    json!({"status": "waiting", "error": reason}),
                )?;
                continue 'jobs;
            };
            if account_busy(db, &name) {
                busy.insert(name);
                continue;
            }
            if !db.claim(&id, &name)? {
                continue 'jobs;
            }
            let result = db
                .authdir(&name)
                .and_then(|dir| runner(&profile, &job, &dir));
            if matches!(&result, Ok(r) if r.kind == "busy") {
                // Lost a race for the account lock: undo the claim, no attempt is counted.
                let error = result.map(|r| r.error).unwrap_or_default();
                db.transition(
                    &id,
                    &["running"],
                    json!({"status": "waiting", "attempts": job["attempts"],
                        "chosen_profile": job["chosen_profile"], "error": error}),
                )?;
                busy.insert(name);
                continue;
            }
            break (profile, name, result);
        };
        db.update_profile(&name, json!({"last_used": at}))?;
        let result = match result {
            Ok(r) => r,
            Err(e) if e.downcast_ref::<Interrupted>().is_some() => {
                db.update_job(
                    &id,
                    json!({"status": "needs_review",
                    "error": "Worker interrupted; inspect workspace before retry"}),
                )?;
                return Err(e);
            }
            Err(e) => {
                db.update_job(
                    &id,
                    json!({"status": "needs_review", "error": e.to_string()}),
                )?;
                return Ok(true);
            }
        };
        if !result.windows.is_empty() {
            // Observations are advisory; an invalid one must not lose the job outcome.
            let _ = db.set_windows(&name, &result.windows, false);
        }
        let edits = truth(&job["allow_edits"]);
        match result.kind {
            "success" => {
                db.update_job(
                    &id,
                    json!({"status": "succeeded", "result": result.result, "error": null}),
                )?;
            }
            "quota" => {
                if profile["provider"] == "codex" {
                    refresh(db, &profile, probe);
                }
                let state = availability(
                    &db.windows(&name)?,
                    at,
                    job["model"].as_str(),
                    bucket_for(&profile, &job).as_deref(),
                );
                let until = if state.ready { None } else { state.ready_at };
                db.update_profile(
                    &name,
                    json!({"hold_until": until,
                    "hold_reason": if until.is_some() { "quota" } else { "quota_reset_unknown" }}),
                )?;
                db.update_job(&id, json!({"status": if edits { "needs_review" } else { "waiting" }, "error": result.error}))?;
            }
            kind => {
                let status = if edits || kind == "uncertain" {
                    "needs_review"
                } else {
                    "failed"
                };
                db.update_job(&id, json!({"status": status, "error": result.error}))?;
            }
        }
        return Ok(true);
    }
    Ok(false)
}

/// Worker liveness from `worker-status.json` (never touches the executor lease).
pub fn worker_state(home: &Path) -> Value {
    let read = || -> Option<Value> {
        let data: Value =
            serde_json::from_str(&fs::read_to_string(home.join("worker-status.json")).ok()?)
                .ok()?;
        let updated = data.get("updated_at")?.as_f64()?;
        let age = (now() - updated).max(0.0);
        Some(
            json!({"online": truth(&data["running"]) && age < 35.0, "age_seconds": (age * 10.0).round() / 10.0,
            "pid": data["pid"], "started_at": data["started_at"], "home": data["home"]}),
        )
    };
    read().unwrap_or_else(|| json!({"online": false, "age_seconds": null}))
}

/// Writes a liveness record every 10 s; a failed write shows as stale, never as online.
pub struct Heartbeat {
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
    path: PathBuf,
    home: PathBuf,
    started: f64,
}

fn write_status(path: &Path, home: &Path, started: f64, running: bool) {
    let tmp = path.with_extension("tmp");
    let record = json!({"running": running, "pid": std::process::id(), "started_at": started,
        "home": resolve(home).to_string_lossy(), "updated_at": now()});
    let attempt = (|| -> std::io::Result<()> {
        let mut options = fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut f = options.open(&tmp)?;
        f.write_all(record.to_string().as_bytes())?;
        drop(f);
        fs::rename(&tmp, path)
    })();
    let _ = attempt;
}

impl Heartbeat {
    pub fn start(home: &Path) -> Self {
        let path = home.join("worker-status.json");
        let started = now();
        write_status(&path, home, started, true);
        let stop = Arc::new(AtomicBool::new(false));
        let (flag, p, h) = (Arc::clone(&stop), path.clone(), home.to_owned());
        let thread = thread::Builder::new()
            .name("worker-heartbeat".into())
            .spawn(move || {
                let mut ticks = 0;
                while !flag.load(Ordering::SeqCst) {
                    thread::sleep(Duration::from_millis(100));
                    ticks += 1;
                    if ticks >= 100 && !flag.load(Ordering::SeqCst) {
                        ticks = 0;
                        write_status(&p, &h, started, true);
                    }
                }
            })
            .ok();
        Self {
            stop,
            thread,
            path,
            home: home.to_owned(),
            started,
        }
    }
}

impl Drop for Heartbeat {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        write_status(&self.path, &self.home, self.started, false);
    }
}
