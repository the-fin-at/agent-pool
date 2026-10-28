mod common;
use common::*;
use fleet_core::db::{now, Db, Lease, Spec};
use fleet_core::provider::Outcome;
use fleet_core::worker::{choose, tick, tick_with};
use serde_json::{json, Value};
use std::path::Path;

fn setup() -> (Pool, Db) {
    let pool = Pool::new();
    let mut db = pool.db();
    db.add_profile("one", "codex", "codex", None).unwrap();
    db.update_profile("one", json!({"enabled": true, "checked_at": now()}))
        .unwrap();
    (pool, db)
}

fn spec(pool: &Pool) -> Spec {
    Spec {
        prompt: "Inspect this project".into(),
        cwd: pool.cwd.to_string_lossy().into(),
        provider: "codex".into(),
        timeout: 1800.0,
        max_attempts: 6,
        ..Spec::default()
    }
}

fn no_probe(_: &Value, _: &Path) -> anyhow::Result<Vec<Value>> {
    Ok(vec![])
}

fn failing_probe(_: &Value, _: &Path) -> anyhow::Result<Vec<Value>> {
    anyhow::bail!("No metadata")
}

fn runner(o: Outcome) -> impl Fn(&Value, &Value, &Path) -> anyhow::Result<Outcome> {
    move |_, _, _| Ok(o.clone())
}

fn never(_: &Value, _: &Value, _: &Path) -> anyhow::Result<Outcome> {
    panic!("must not run")
}

#[test]
fn submit_persists_and_key_is_idempotent() {
    let (pool, mut db) = setup();
    let mut s = spec(&pool);
    s.key = Some("unique".into());
    let a = db.submit(&s).unwrap();
    assert_eq!(
        pool.db().job(a["id"].as_str().unwrap()).unwrap()["prompt"],
        "Inspect this project"
    );
    assert_eq!(db.submit(&s).unwrap()["id"], a["id"]);
    s.prompt = "Different".into();
    assert!(db.submit(&s).is_err());
    assert_eq!(a["id"].as_str().unwrap().len(), 32);
}

#[test]
fn simultaneous_submitters_share_one_task() {
    let (pool, _db) = setup();
    let ids: Vec<String> = std::thread::scope(|scope| {
        let handles: Vec<_> = (0..12)
            .map(|_| {
                let pool = &pool;
                scope.spawn(move || {
                    let mut db = pool.db();
                    let mut s = spec(pool);
                    s.prompt = "same".into();
                    s.key = Some("concurrent".into());
                    db.submit(&s).unwrap()["id"].as_str().unwrap().to_string()
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    assert!(ids.iter().all(|i| *i == ids[0]));
}

#[test]
fn rejects_invalid_task_limits() {
    let (pool, mut db) = setup();
    let changes: [fn(&mut Spec); 6] = [
        |s: &mut Spec| s.timeout = f64::NAN,
        |s: &mut Spec| s.timeout = 99999.0,
        |s: &mut Spec| s.max_attempts = 101,
        |s: &mut Spec| s.model = Some("--bad".into()),
        |s: &mut Spec| s.prompt = "x\0y".into(),
        |s: &mut Spec| s.prompt = "   ".into(),
    ];
    for change in changes {
        let mut s = spec(&pool);
        change(&mut s);
        assert!(db.submit(&s).is_err());
    }
    assert!(db.jobs(false).unwrap().is_empty());
}

#[test]
fn routes_to_weekly_allowance_expiring_soonest_and_respects_pins() {
    let (pool, mut db) = setup();
    let t = now();
    db.add_profile("two", "codex", "codex", None).unwrap();
    db.update_profile("two", json!({"enabled": true})).unwrap();
    for (name, reset) in [("one", t + 200.0), ("two", t + 100.0)] {
        db.set_windows(name, &[json!({"key": "weekly", "bucket": "codex", "minutes": 10080, "used": 20, "reset": reset})], false)
            .unwrap();
    }
    let job = db.submit(&spec(&pool)).unwrap();
    assert_eq!(choose(&db, &job, t).unwrap().0.unwrap()["name"], "two");
    db.update_profile("one", json!({"enabled": false})).unwrap();
    let mut pinned = spec(&pool);
    pinned.profile = Some("one".into());
    let job = db.submit(&pinned).unwrap();
    let (selected, reason) = choose(&db, &job, t).unwrap();
    assert!(selected.is_none());
    assert!(reason.unwrap().contains("one:disabled"));
}

#[test]
fn exhausted_account_fails_over_within_provider_only() {
    let (pool, mut db) = setup();
    let t = now();
    db.add_profile("two", "codex", "codex", None).unwrap();
    db.update_profile("two", json!({"enabled": true})).unwrap();
    db.add_profile("claude-test", "claude", "claude", None)
        .unwrap();
    db.update_profile("claude-test", json!({"enabled": true}))
        .unwrap();
    db.set_windows("one", &[json!({"key": "codex:primary", "bucket": "codex", "minutes": 300, "used": 100, "reset": t + 100.0})], false)
        .unwrap();
    let job = db.submit(&spec(&pool)).unwrap();
    assert_eq!(choose(&db, &job, t).unwrap().0.unwrap()["name"], "two");
    db.update_profile("two", json!({"enabled": false})).unwrap();
    assert!(choose(&db, &job, t).unwrap().0.is_none());
}

#[test]
fn success_returns_report() {
    let (pool, mut db) = setup();
    let job = db.submit(&spec(&pool)).unwrap();
    let _lease = db.worker_lock().unwrap();
    assert!(tick(
        &mut db,
        &runner(Outcome::new("success", "Found three modules", "")),
        &no_probe,
        None
    )
    .unwrap());
    let stored = db.job(job["id"].as_str().unwrap()).unwrap();
    assert_eq!(stored["status"], "succeeded");
    assert_eq!(stored["result"], "Found three modules");
    assert_eq!(stored["attempts"], 1);
}

#[test]
fn exhausted_job_waits_without_consuming_attempt() {
    let (pool, mut db) = setup();
    let t = now();
    let job = db.submit(&spec(&pool)).unwrap();
    let id = job["id"].as_str().unwrap();
    db.set_windows("one", &[json!({"key": "limit", "bucket": "codex", "minutes": 300, "used": 100, "reset": t + 100.0})], false)
        .unwrap();
    assert!(!tick(&mut db, &never, &no_probe, Some(t)).unwrap());
    assert_eq!(db.job(id).unwrap()["attempts"], 0);
    assert_eq!(db.job(id).unwrap()["status"], "waiting");
    tick(
        &mut db,
        &runner(Outcome::new("success", "After reset", "")),
        &no_probe,
        Some(t + 101.0),
    )
    .unwrap();
    assert_eq!(db.job(id).unwrap()["status"], "succeeded");
}

#[test]
fn unknown_quota_error_holds_account() {
    let (pool, mut db) = setup();
    let job = db.submit(&spec(&pool)).unwrap();
    tick(
        &mut db,
        &runner(Outcome::new("quota", "", "usage_limit_reached")),
        &failing_probe,
        None,
    )
    .unwrap();
    tick(&mut db, &never, &failing_probe, None).unwrap();
    assert_eq!(
        db.profile("one").unwrap()["hold_reason"],
        "quota_reset_unknown"
    );
    assert_eq!(db.job(job["id"].as_str().unwrap()).unwrap()["attempts"], 1);
}

#[test]
fn quota_during_edit_timeout_and_crash_require_review() {
    let (pool, mut db) = setup();
    let mut edit = spec(&pool);
    edit.allow_edits = true;
    let job = db.submit(&edit).unwrap();
    tick(
        &mut db,
        &runner(Outcome::new("quota", "", "usage limit")),
        &no_probe,
        None,
    )
    .unwrap();
    assert_eq!(
        db.job(job["id"].as_str().unwrap()).unwrap()["status"],
        "needs_review"
    );
    assert_eq!(
        db.profile("one").unwrap()["hold_reason"],
        "quota_reset_unknown"
    );
    db.update_profile("one", json!({"hold_until": null, "hold_reason": null}))
        .unwrap();

    let job = db.submit(&spec(&pool)).unwrap();
    tick(
        &mut db,
        &runner(Outcome::new("uncertain", "", "timeout")),
        &no_probe,
        None,
    )
    .unwrap();
    assert_eq!(
        db.job(job["id"].as_str().unwrap()).unwrap()["status"],
        "needs_review"
    );

    let job = db.submit(&spec(&pool)).unwrap();
    let id = job["id"].as_str().unwrap();
    db.update_job(id, json!({"status": "running", "attempts": 1}))
        .unwrap();
    assert_eq!(db.recover().unwrap(), 1);
    assert!(!tick(&mut db, &never, &no_probe, None).unwrap());
    assert_eq!(db.job(id).unwrap()["status"], "needs_review");
}

#[test]
fn busy_account_is_idle_tick_without_attempt() {
    let (pool, mut db) = setup();
    let job = db.submit(&spec(&pool)).unwrap();
    assert!(!tick(
        &mut db,
        &runner(Outcome::new("busy", "", "locked")),
        &no_probe,
        None
    )
    .unwrap());
    let current = db.job(job["id"].as_str().unwrap()).unwrap();
    assert_eq!(current["status"], "waiting");
    assert_eq!(current["attempts"], 0);
}

#[test]
fn cancel_between_selection_and_claim_never_runs() {
    let (pool, mut db) = setup();
    let job = db.submit(&spec(&pool)).unwrap();
    let id = job["id"].as_str().unwrap().to_string();
    let home = pool.home.clone();
    let chooser = move |db: &Db, job: &Value, at: f64| {
        let selected = choose(db, job, at);
        Db::open(&home)
            .unwrap()
            .transition(&id, &["queued", "waiting"], json!({"status": "cancelled"}))
            .unwrap();
        selected
    };
    assert!(!tick_with(&mut db, &never, &no_probe, None, &chooser).unwrap());
    assert_eq!(
        db.job(job["id"].as_str().unwrap()).unwrap()["status"],
        "cancelled"
    );
}

#[test]
fn disabled_profile_cannot_be_claimed_and_second_worker_is_rejected() {
    let (pool, mut db) = setup();
    db.add_profile("test", "codex", "codex", None).unwrap();
    let job = db.submit(&spec(&pool)).unwrap();
    assert!(!db.claim(job["id"].as_str().unwrap(), "test").unwrap());
    let _lease = db.worker_lock().unwrap();
    let err = pool.db().worker_lock().err().unwrap();
    assert!(fleet_core::db::is_busy(&err));
    assert!(err.to_string().contains("Another worker"));
}

#[test]
fn unsafe_profile_names_rejected() {
    let (_pool, mut db) = setup();
    for name in ["../escape", "a/b", "con", "aux", "Upper", ""] {
        assert!(
            db.add_profile(name, "codex", "codex", None).is_err(),
            "{name}"
        );
    }
    assert!(db.windows("one").unwrap().is_empty());
}

#[test]
fn attached_native_directory_registered_without_copy() {
    let (pool, mut db) = setup();
    let native = pool.root().join("native");
    std::fs::create_dir(&native).unwrap();
    std::fs::write(native.join("marker"), "existing state").unwrap();
    db.add_profile("server", "codex", "codex", Some(native.to_str().unwrap()))
        .unwrap();
    assert_eq!(db.authdir("server").unwrap(), native);
    assert!(!pool.home.join("profiles/server").exists());
    let dup = db
        .add_profile(
            "duplicate",
            "codex",
            "codex",
            Some(native.to_str().unwrap()),
        )
        .unwrap_err();
    assert!(dup.to_string().contains("already registered"));
    // Reverse direction: an attached directory inside the managed location blocks a later profile.
    let future = pool.home.join("profiles/later");
    std::fs::create_dir_all(&future).unwrap();
    db.add_profile("attached", "codex", "codex", Some(future.to_str().unwrap()))
        .unwrap();
    assert!(db
        .add_profile("later", "codex", "codex", None)
        .unwrap_err()
        .to_string()
        .contains("already registered"));
    std::fs::remove_dir_all(&native).unwrap();
    assert!(db
        .authdir("server")
        .unwrap_err()
        .to_string()
        .contains("missing"));
    assert!(!native.exists());
}

#[cfg(unix)]
#[test]
fn attached_directory_symlink_swap_rejected() {
    let (pool, mut db) = setup();
    let native = pool.root().join("native");
    let other = pool.root().join("other");
    std::fs::create_dir(&native).unwrap();
    std::fs::create_dir(&other).unwrap();
    db.add_profile("server", "codex", "codex", Some(native.to_str().unwrap()))
        .unwrap();
    std::fs::remove_dir(&native).unwrap();
    std::os::unix::fs::symlink(&other, &native).unwrap();
    assert!(db.authdir("server").is_err());
}

#[test]
fn legacy_database_is_extended_additively() {
    let pool = Pool::new();
    let home = pool.root().join("legacy");
    std::fs::create_dir_all(&home).unwrap();
    {
        let conn = rusqlite::Connection::open(home.join("queue.sqlite3")).unwrap();
        conn.execute_batch(
            "CREATE TABLE profiles (name TEXT PRIMARY KEY, provider TEXT NOT NULL, binary TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0, last_used REAL NOT NULL DEFAULT 0,
              hold_until REAL, hold_reason TEXT, observed_at REAL, checked_at REAL, quota_error TEXT);
             INSERT INTO profiles(name,provider,binary,enabled) VALUES('codex-1','codex','codex',1);
             CREATE TABLE jobs (id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, prompt TEXT NOT NULL,
              cwd TEXT NOT NULL, provider TEXT NOT NULL, profile TEXT, model TEXT,
              bucket TEXT, allow_edits INTEGER NOT NULL, status TEXT NOT NULL,
              created REAL NOT NULL, updated REAL NOT NULL, chosen_profile TEXT,
              attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
              timeout REAL NOT NULL, result TEXT, error TEXT);
             INSERT INTO jobs VALUES('abc','k','p','/tmp','codex',NULL,NULL,NULL,0,'succeeded',1.0,2.0,'codex-1',1,6,1800.0,'kept',NULL);",
        )
        .unwrap();
    }
    let db = Db::open(&home).unwrap();
    let p = db.profile("codex-1").unwrap();
    assert_eq!(p["enabled"], 1);
    assert!(p.as_object().unwrap().contains_key("auth_home"));
    assert_eq!(db.job("abc").unwrap()["result"], "kept");
    let tables: i64 = db
        .conn
        .query_row("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('workspaces','windows','monitor_cache')", [], |r| r.get(0))
        .unwrap();
    assert_eq!(tables, 3);
}

#[test]
fn native_lock_makes_job_busy() {
    let pool = Pool::new();
    let auth = pool.root().join("auth");
    std::fs::create_dir(&auth).unwrap();
    let _lock = Lease::acquire(&auth.join(".native.lock")).unwrap();
    let out = fleet_core::provider::run_native(
        &json!({"provider": "codex", "binary": "/nonexistent"}),
        &json!({}),
        &auth,
    )
    .unwrap();
    assert_eq!(out.kind, "busy");
}

#[cfg(unix)]
#[test]
fn native_process_round_trip_timeout_and_group_kill() {
    let (pool, mut db) = setup();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    db.add_profile("fixture", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    db.update_profile(
        "fixture",
        json!({"enabled": true, "checked_at": 9999999999.0}),
    )
    .unwrap();
    db.update_profile("one", json!({"enabled": false})).unwrap();
    let mut s = spec(&pool);
    s.prompt = "Examine the module".into();
    s.profile = Some("fixture".into());
    let job = db.submit(&s).unwrap();
    assert!(tick(&mut db, &fleet_core::worker::native_runner, &no_probe, None).unwrap());
    let done = db.job(job["id"].as_str().unwrap()).unwrap();
    assert_eq!(done["status"], "succeeded", "{done}");
    assert_eq!(done["result"], "Worker report: Examine the module");

    s.prompt = "sleep forever".into();
    s.timeout = 0.5;
    let job = db.submit(&s).unwrap();
    let started = std::time::Instant::now();
    tick(&mut db, &fleet_core::worker::native_runner, &no_probe, None).unwrap();
    assert!(started.elapsed().as_secs() < 10);
    let done = db.job(job["id"].as_str().unwrap()).unwrap();
    assert_eq!(done["status"], "needs_review");
    let child: i32 = std::fs::read_to_string(pool.cwd.join("child.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(
        wait_until(3.0, || !alive(child)),
        "background child survived timeout"
    );
}

#[cfg(unix)]
#[test]
fn quota_jsonrpc_handshake_uses_no_model_turn() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let dir = pool.root().join("codex-home");
    std::fs::create_dir(&dir).unwrap();
    let windows =
        fleet_core::provider::read_codex_quota(&json!({"binary": binary.to_str().unwrap()}), &dir)
            .unwrap();
    assert_eq!(windows[0]["used"], 25);
}

#[test]
fn unusable_native_lock_surfaces_error_instead_of_waiting_forever() {
    let (pool, mut db) = setup();
    let auth = db.authdir("one").unwrap();
    // A directory at the lock-file path is an actual non-contention OS error.
    std::fs::create_dir(auth.join(".native.lock")).unwrap();
    let error =
        match fleet_core::provider::run_native(&db.profile("one").unwrap(), &json!({}), &auth) {
            Err(error) => error,
            Ok(_) => panic!("A lock I/O error must not be reported as a busy account"),
        };
    assert!(!fleet_core::db::is_busy(&error));
    let mut s = spec(&pool);
    s.profile = Some("one".into());
    let job = db.submit(&s).unwrap();
    assert!(tick(&mut db, &fleet_core::worker::native_runner, &no_probe, None).unwrap());
    let failed = db.job(job["id"].as_str().unwrap()).unwrap();
    assert_eq!(failed["status"], "needs_review");
    assert!(failed["error"].as_str().is_some_and(|e| !e.is_empty()));
    assert!(!tick(&mut db, &fleet_core::worker::native_runner, &no_probe, None).unwrap());
    assert_eq!(db.job(job["id"].as_str().unwrap()).unwrap()["attempts"], 1);
}
