//! Port of tests/test_pool_routing.py: the public queue/worker routing contract.
mod common;
use common::*;
use fleet_core::db::{now, Db, Spec};
use fleet_core::provider::Outcome;
use fleet_core::worker::tick;
use serde_json::{json, Value};
use std::cell::RefCell;
use std::path::Path;

struct Routing {
    pool: Pool,
    db: Db,
    now: f64,
    chosen: RefCell<Vec<(String, Value)>>,
}

fn empty_probe(_: &Value, _: &Path) -> anyhow::Result<Vec<Value>> {
    Ok(vec![])
}

fn unavailable(_: &Value, _: &Path) -> anyhow::Result<Vec<Value>> {
    anyhow::bail!("No reset observation")
}

impl Routing {
    fn new() -> Self {
        let pool = Pool::new();
        let mut db = pool.db();
        let t = now();
        for name in ["a", "b"] {
            db.add_profile(name, "codex", "codex", None).unwrap();
            db.update_profile(name, json!({"enabled": true, "checked_at": t}))
                .unwrap();
        }
        Self {
            pool,
            db,
            now: t,
            chosen: RefCell::new(vec![]),
        }
    }

    fn windows(&mut self, name: &str, five: f64, week: f64, five_reset: f64, week_reset: f64) {
        let t = self.now;
        self.db
            .set_windows(name, &[
                json!({"key": "codex:primary", "bucket": "codex", "minutes": 300, "used": five, "reset": t + five_reset}),
                json!({"key": "codex:secondary", "bucket": "codex", "minutes": 10080, "used": week, "reset": t + week_reset}),
            ], false)
            .unwrap();
    }

    fn submit(
        &mut self,
        provider: &str,
        key: &str,
        profile: Option<&str>,
        model: Option<&str>,
        edits: bool,
    ) -> String {
        let spec = Spec {
            prompt: "Read-only task".into(),
            cwd: self.pool.cwd.to_string_lossy().into(),
            provider: provider.into(),
            profile: profile.map(String::from),
            model: model.map(String::from),
            allow_edits: edits,
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

    fn tick_with(
        &mut self,
        at: f64,
        outcome: &dyn Fn(&str) -> Outcome,
        probe: fleet_core::worker::QuotaProbe,
    ) -> bool {
        let chosen = &self.chosen;
        let runner = |p: &Value, j: &Value, _: &Path| {
            let name = p["name"].as_str().unwrap().to_string();
            chosen.borrow_mut().push((name.clone(), j["model"].clone()));
            Ok(outcome(&name))
        };
        let _lease = self.db.worker_lock().unwrap();
        tick(&mut self.db, &runner, probe, Some(at)).unwrap()
    }

    fn tick(&mut self) -> bool {
        let at = self.now;
        self.tick_with(at, &|_| Outcome::new("success", "done", ""), &empty_probe)
    }

    fn names(&self) -> Vec<String> {
        self.chosen.borrow().iter().map(|c| c.0.clone()).collect()
    }

    fn job(&self, id: &str) -> Value {
        self.db.job(id).unwrap()
    }
}

#[test]
fn full_five_hour_profile_is_skipped_for_free_profile() {
    let mut r = Routing::new();
    r.windows("a", 100.0, 10.0, 30.0, 300.0);
    r.windows("b", 10.0, 10.0, 30.0, 600.0);
    let id = r.submit("codex", "one-job", None, None, false);
    r.tick();
    assert_eq!(r.names(), ["b"]);
    assert_eq!(r.job(&id)["status"], "succeeded");
    assert_eq!(r.job(&id)["attempts"], 1);
}

#[test]
fn full_week_is_skipped_even_with_free_five_hour_balance() {
    let mut r = Routing::new();
    r.windows("a", 0.0, 100.0, 30.0, 600.0);
    r.windows("b", 10.0, 10.0, 30.0, 600.0);
    let id = r.submit("codex", "one-job", None, None, false);
    r.tick();
    assert_eq!(r.names(), ["b"]);
    assert_eq!(r.job(&id)["chosen_profile"], "b");
}

#[test]
fn runtime_quota_keeps_same_job_and_uses_another_profile_next_tick() {
    let mut r = Routing::new();
    r.windows("a", 10.0, 10.0, 30.0, 300.0);
    r.windows("b", 10.0, 10.0, 30.0, 600.0);
    let id = r.submit("codex", "one-job", None, None, false);
    let outcome = |name: &str| {
        if name == "a" {
            Outcome::new("quota", "", "usage_limit_reached")
        } else {
            Outcome::new("success", "done", "")
        }
    };
    let at = r.now;
    r.tick_with(at, &outcome, &unavailable);
    assert_eq!(r.job(&id)["status"], "waiting");
    assert_eq!(
        r.db.profile("a").unwrap()["hold_reason"],
        "quota_reset_unknown"
    );
    r.tick_with(at, &outcome, &unavailable);
    assert_eq!(r.names(), ["a", "b"]);
    assert_eq!(r.job(&id)["status"], "succeeded");
    assert_eq!(r.job(&id)["attempts"], 2);
    assert_eq!(r.db.jobs(false).unwrap().len(), 1);
}

#[test]
fn waits_for_earliest_profile_that_clears_all_its_windows() {
    let mut r = Routing::new();
    r.windows("a", 100.0, 100.0, 10.0, 100.0);
    r.windows("b", 100.0, 10.0, 20.0, 600.0);
    let id = r.submit("codex", "one-job", None, None, false);
    let ok = |_: &str| Outcome::new("success", "done", "");
    let t = r.now;
    assert!(!r.tick_with(t, &ok, &empty_probe));
    assert!(!r.tick_with(t + 11.0, &ok, &empty_probe));
    assert!(r.names().is_empty());
    assert_eq!(r.job(&id)["attempts"], 0);
    assert!(r.job(&id)["error"].as_str().unwrap().contains("a:quota"));
    r.tick_with(t + 21.0, &ok, &empty_probe);
    assert_eq!(r.names(), ["b"]);
    assert_eq!(r.job(&id)["status"], "succeeded");
}

#[test]
fn waiting_codex_job_does_not_block_independent_claude_job() {
    let mut r = Routing::new();
    r.windows("a", 100.0, 10.0, 30.0, 600.0);
    r.windows("b", 100.0, 10.0, 30.0, 600.0);
    let first = r.submit("codex", "one-job", None, None, false);
    r.db.add_profile("claude", "claude", "claude", None)
        .unwrap();
    r.db.update_profile("claude", json!({"enabled": true}))
        .unwrap();
    let second = r.submit("claude", "second-job", None, None, false);
    r.tick();
    assert_eq!(r.names(), ["claude"]);
    assert_eq!(r.job(&first)["status"], "waiting");
    assert_eq!(r.job(&first)["attempts"], 0);
    assert_eq!(r.job(&second)["status"], "succeeded");
}

#[test]
fn explicit_pin_to_full_profile_waits_despite_other_free_account() {
    let mut r = Routing::new();
    r.windows("a", 100.0, 10.0, 30.0, 600.0);
    r.windows("b", 10.0, 10.0, 30.0, 600.0);
    let id = r.submit("codex", "one-job", Some("a"), None, false);
    assert!(!r.tick());
    assert!(r.names().is_empty());
    assert_eq!(r.job(&id)["status"], "waiting");
    assert_eq!(r.job(&id)["attempts"], 0);
}

#[test]
fn model_specific_limit_blocks_only_requested_family_without_provider_change() {
    let mut r = Routing::new();
    let t = r.now;
    r.db.add_profile("claude", "claude", "claude", None)
        .unwrap();
    r.db.update_profile("claude", json!({"enabled": true}))
        .unwrap();
    r.db
        .set_windows("claude", &[
            json!({"key": "five_hour", "bucket": "claude", "minutes": 300, "used": 10, "reset": t + 300.0}),
            json!({"key": "seven_day_opus", "bucket": "claude", "minutes": 10080, "used": 100, "reset": t + 600.0, "model": "opus"}),
        ], false)
        .unwrap();
    let sonnet = r.submit("claude", "sonnet", None, Some("sonnet"), false);
    let opus = r.submit("claude", "opus", None, Some("opus"), false);
    r.tick();
    r.tick();
    let chosen = r.chosen.borrow().clone();
    assert_eq!(chosen, vec![("claude".to_string(), json!("sonnet"))]);
    assert_eq!(r.job(&sonnet)["status"], "succeeded");
    assert_eq!(r.job(&opus)["status"], "waiting");
    assert_eq!(r.job(&opus)["provider"], "claude");
}

#[test]
fn editing_uncertainty_and_restart_never_replay() {
    let mut r = Routing::new();
    r.windows("a", 10.0, 10.0, 30.0, 600.0);
    r.windows("b", 10.0, 10.0, 30.0, 600.0);
    let edit = r.submit("codex", "edit-job", None, None, true);
    let at = r.now;
    r.tick_with(
        at,
        &|_| Outcome::new("quota", "", "usage limit"),
        &empty_probe,
    );
    assert_eq!(r.job(&edit)["status"], "needs_review");
    // A needs_review job is never picked again automatically, even with a free account.
    assert!(!r.tick());
    assert_eq!(r.names().len(), 1);

    let crashed = r.submit("codex", "crash-job", Some("b"), None, false);
    r.db.update_job(
        &crashed,
        json!({"status": "running", "attempts": 1, "chosen_profile": "b"}),
    )
    .unwrap();
    assert_eq!(r.db.recover().unwrap(), 1);
    assert!(!r.tick());
    assert_eq!(r.job(&crashed)["status"], "needs_review");
    assert_eq!(r.job(&crashed)["attempts"], 1);
    assert_eq!(r.names().len(), 1);
}
