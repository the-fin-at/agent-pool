//! A held native account lock (`.native.lock`) excludes that account for one tick only.
mod common;
use common::*;
use fleet_core::db::{now, Db, Lease, Spec};
use fleet_core::provider::Outcome;
use fleet_core::worker::{tick, tick_with};
use serde_json::{json, Value};
use std::cell::RefCell;
use std::path::Path;

fn no_probe(_: &Value, _: &Path) -> anyhow::Result<Vec<Value>> {
    Ok(vec![])
}

struct Fixture {
    pool: Pool,
    db: Db,
    now: f64,
}

impl Fixture {
    /// Codex accounts `a` and `b`; `a` is preferred (weekly reset sooner).
    fn new() -> Self {
        let pool = Pool::new();
        let mut db = pool.db();
        let t = now();
        for (name, week_reset) in [("a", 300.0), ("b", 600.0)] {
            db.add_profile(name, "codex", "codex", None).unwrap();
            db.set_windows(
                name,
                &[
                    json!({"key": "codex:secondary", "bucket": "codex", "minutes": 10080,
                "used": 10, "reset": t + week_reset}),
                ],
                false,
            )
            .unwrap();
            db.update_profile(name, json!({"enabled": true, "checked_at": t}))
                .unwrap();
        }
        Self { pool, db, now: t }
    }

    fn submit(
        &mut self,
        provider: &str,
        key: &str,
        profile: Option<&str>,
        model: Option<&str>,
    ) -> String {
        let spec = Spec {
            prompt: "Read-only task".into(),
            cwd: self.pool.cwd.to_string_lossy().into(),
            provider: provider.into(),
            profile: profile.map(String::from),
            model: model.map(String::from),
            key: Some(key.into()),
            timeout: 1800.0,
            max_attempts: 6,
            ..Spec::default()
        };
        self.db.submit(&spec).unwrap()["id"]
            .as_str()
            .unwrap()
            .to_string()
    }

    /// Holds the real OS lock exactly as a login or metadata session would.
    fn hold(&self, name: &str) -> Lease {
        Lease::acquire(&self.db.authdir(name).unwrap().join(".native.lock")).unwrap()
    }

    fn job(&self, id: &str) -> Value {
        self.db.job(id).unwrap()
    }
}

fn recorder(
    log: &RefCell<Vec<String>>,
) -> impl Fn(&Value, &Value, &Path) -> anyhow::Result<Outcome> + '_ {
    move |p, _, _| {
        log.borrow_mut()
            .push(p["name"].as_str().unwrap().to_string());
        Ok(Outcome::new("success", "done", ""))
    }
}

#[test]
fn unpinned_job_uses_ready_account_when_preferred_account_is_locked() {
    let mut f = Fixture::new();
    let id = f.submit("codex", "same-key", None, Some("gpt-5"));
    let before = f.job(&id);
    let log = RefCell::new(vec![]);
    {
        let _held = f.hold("a");
        let at = f.now;
        assert!(tick(&mut f.db, &recorder(&log), &no_probe, Some(at)).unwrap());
    }
    assert_eq!(*log.borrow(), ["b"]);
    let after = f.job(&id);
    assert_eq!(after["status"], "succeeded");
    assert_eq!(after["attempts"], 1);
    assert_eq!(after["chosen_profile"], "b");
    for field in [
        "id",
        "idempotency_key",
        "profile",
        "model",
        "provider",
        "prompt",
    ] {
        assert_eq!(after[field], before[field], "{field}");
    }
    // Busy is never persisted: no hold, still enabled, last_used untouched.
    let a = f.db.profile("a").unwrap();
    assert_eq!(a["enabled"], 1);
    assert!(a["hold_reason"].is_null() && a["hold_until"].is_null());
    assert_eq!(a["last_used"], 0.0);
    // Next tick without the lock, the preferred account is eligible again.
    let next = f.submit("codex", "next-key", None, None);
    let at = f.now;
    tick(&mut f.db, &recorder(&log), &no_probe, Some(at)).unwrap();
    assert_eq!(*log.borrow(), ["b", "a"]);
    assert_eq!(f.job(&next)["chosen_profile"], "a");
}

#[test]
fn pinned_job_to_locked_account_waits_and_later_independent_job_runs_same_tick() {
    let mut f = Fixture::new();
    let pinned = f.submit("codex", "pinned", Some("a"), None);
    f.db.add_profile("claude", "claude", "claude", None)
        .unwrap();
    f.db.update_profile("claude", json!({"enabled": true}))
        .unwrap();
    let independent = f.submit("claude", "independent", None, None);
    let log = RefCell::new(vec![]);
    {
        let _held = f.hold("a");
        let at = f.now;
        assert!(tick(&mut f.db, &recorder(&log), &no_probe, Some(at)).unwrap());
    }
    assert_eq!(*log.borrow(), ["claude"]);
    let job = f.job(&pinned);
    assert_eq!(job["status"], "waiting");
    assert_eq!(job["attempts"], 0);
    assert_eq!(job["profile"], "a");
    assert!(job["error"].as_str().unwrap().contains("a:busy"));
    assert_eq!(f.job(&independent)["status"], "succeeded");
    assert!(f.db.profile("a").unwrap()["hold_reason"].is_null());
    // Released lock: the pinned job runs on its own account, never on `b`.
    let at = f.now;
    tick(&mut f.db, &recorder(&log), &no_probe, Some(at)).unwrap();
    assert_eq!(*log.borrow(), ["claude", "a"]);
    assert_eq!(f.job(&pinned)["attempts"], 1);
}

#[test]
fn lost_lock_race_inside_runner_falls_back_without_counting_an_attempt() {
    let mut f = Fixture::new();
    let id = f.submit("codex", "race", None, None);
    let log = RefCell::new(vec![]);
    let runner = |p: &Value, _: &Value, _: &Path| {
        let name = p["name"].as_str().unwrap().to_string();
        log.borrow_mut().push(name.clone());
        Ok(if name == "a" {
            Outcome::new(
                "busy",
                "",
                "Account metadata or login session is active; waiting",
            )
        } else {
            Outcome::new("success", "done", "")
        })
    };
    let at = f.now;
    assert!(tick(&mut f.db, &runner, &no_probe, Some(at)).unwrap());
    assert_eq!(*log.borrow(), ["a", "b"]);
    let job = f.job(&id);
    assert_eq!(job["attempts"], 1);
    assert_eq!(job["chosen_profile"], "b");
    assert_eq!(f.db.profile("a").unwrap()["last_used"], 0.0);
}

#[test]
fn chooser_repeating_a_busy_account_is_bounded() {
    let mut f = Fixture::new();
    let id = f.submit("codex", "stuck", None, None);
    let a = f.db.profile("a").unwrap();
    let chooser =
        move |_: &Db, _: &Value, _: f64| -> anyhow::Result<(Option<Value>, Option<String>)> {
            Ok((Some(a.clone()), None))
        };
    let never = |_: &Value, _: &Value, _: &Path| -> anyhow::Result<Outcome> {
        panic!("locked account executed")
    };
    let _held = f.hold("a");
    let at = f.now;
    assert!(!tick_with(&mut f.db, &never, &no_probe, Some(at), &chooser).unwrap());
    let job = f.job(&id);
    assert_eq!(job["status"], "waiting");
    assert_eq!(job["attempts"], 0);
    assert!(job["error"].as_str().unwrap().contains("a:busy"));
}

#[test]
fn all_accounts_locked_is_an_idle_tick() {
    let mut f = Fixture::new();
    let id = f.submit("codex", "idle", None, None);
    let never = |_: &Value, _: &Value, _: &Path| -> anyhow::Result<Outcome> {
        panic!("locked account executed")
    };
    let (_a, _b) = (f.hold("a"), f.hold("b"));
    let at = f.now;
    assert!(!tick(&mut f.db, &never, &no_probe, Some(at)).unwrap());
    let job = f.job(&id);
    assert_eq!(
        (job["status"].as_str(), job["attempts"].as_i64()),
        (Some("waiting"), Some(0))
    );
    for name in ["a", "b"] {
        let p = f.db.profile(name).unwrap();
        assert!(p["hold_reason"].is_null());
        assert_eq!(p["enabled"], 1);
    }
}

#[cfg(unix)]
#[test]
fn native_runner_with_real_lock_uses_other_fixture_account() {
    let mut f = Fixture::new();
    let binary = script(&f.pool.root(), "native-cli", FAKE_NATIVE);
    f.db.conn
        .execute(
            "UPDATE profiles SET binary=? WHERE name IN ('a','b')",
            [binary.to_str().unwrap()],
        )
        .unwrap();
    let id = f.submit("codex", "native", None, None);
    {
        let _held = f.hold("a");
        let at = f.now;
        assert!(tick(
            &mut f.db,
            &fleet_core::worker::native_runner,
            &no_probe,
            Some(at)
        )
        .unwrap());
    }
    let job = f.job(&id);
    assert_eq!(job["status"], "succeeded", "{job}");
    assert_eq!(job["chosen_profile"], "b");
    assert_eq!(job["result"], "Worker report: Read-only task");
}
