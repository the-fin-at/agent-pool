mod common;
use common::*;
use fleet_core::monitor::{collect_with, read_source, snapshot, sources};
use serde_json::{json, Value};
use std::path::Path;

fn window(used: f64) -> Value {
    json!({"key": "codex:primary", "bucket": "codex", "used": used, "reset": 9999999999.0, "minutes": 300})
}

fn setup() -> (Pool, Value) {
    let pool = Pool::new();
    let mut db = pool.db();
    db.add_profile("test-codex", "codex", "codex", None)
        .unwrap();
    db.update_profile("test-codex", json!({"enabled": true}))
        .unwrap();
    let source = sources(&db, false).unwrap().remove(0);
    (pool, source)
}

fn identity(
    email: &'static str,
    windows: Value,
) -> impl Fn(&Value, &Path) -> anyhow::Result<Value> {
    move |_, _| {
        Ok(
            json!({"connected": true, "email": email, "plan": "team", "windows": windows, "error": null}),
        )
    }
}

#[test]
fn live_metadata_updates_quota_without_enabling() {
    let (pool, source) = setup();
    pool.db()
        .update_profile("test-codex", json!({"enabled": false}))
        .unwrap();
    let data = read_source(
        &pool.home,
        &source,
        &identity("one@example.com", json!([window(25.0)])),
    )
    .unwrap();
    assert_eq!(data["email"], "one@example.com");
    assert_eq!(pool.db().windows("test-codex").unwrap()[0]["used"], 25.0);
    assert_eq!(pool.db().profile("test-codex").unwrap()["enabled"], 0);
}

#[test]
fn refresh_failure_keeps_last_observation_with_error() {
    let (pool, source) = setup();
    read_source(
        &pool.home,
        &source,
        &identity("one@example.com", json!([window(25.0)])),
    )
    .unwrap();
    let failing = |_: &Value, _: &Path| -> anyhow::Result<Value> { anyhow::bail!("Offline") };
    let result = read_source(&pool.home, &source, &failing).unwrap();
    assert_eq!(result["windows"][0]["used"], 25.0);
    assert_eq!(result["error"], "Offline");
}

#[test]
fn changed_or_logged_out_identity_never_inherits_quota() {
    let (pool, source) = setup();
    read_source(
        &pool.home,
        &source,
        &identity("one@example.com", json!([window(25.0)])),
    )
    .unwrap();
    read_source(
        &pool.home,
        &source,
        &identity("two@example.com", Value::Null),
    )
    .unwrap();
    let account = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(account["email"], "two@example.com");
    assert_eq!(account["windows"], json!([]));
    let out = |_: &Value, _: &Path| -> anyhow::Result<Value> {
        Ok(json!({"connected": false, "email": null, "windows": null, "error": null}))
    };
    read_source(&pool.home, &source, &out).unwrap();
    assert_eq!(
        snapshot(&pool.home, false).unwrap()[0]["windows"],
        json!([])
    );
}

#[test]
fn worker_quota_newer_than_cache_is_displayed() {
    let (pool, source) = setup();
    read_source(
        &pool.home,
        &source,
        &identity("one@example.com", json!([window(25.0)])),
    )
    .unwrap();
    std::thread::sleep(std::time::Duration::from_millis(20));
    pool.db()
        .set_windows("test-codex", &[window(75.0)], false)
        .unwrap();
    assert_eq!(
        snapshot(&pool.home, false).unwrap()[0]["windows"][0]["used"],
        75.0
    );
}

#[test]
fn claude_uses_saved_windows_and_never_probes() {
    let (pool, _) = setup();
    let mut db = pool.db();
    db.add_profile("test-claude", "claude", "claude", None)
        .unwrap();
    db.update_profile("test-claude", json!({"enabled": true}))
        .unwrap();
    db.set_windows("test-claude", &[json!({"key": "five_hour", "bucket": "claude", "used": 25, "reset": 9999999999.0, "minutes": 300})], false)
        .unwrap();
    let source = sources(&db, false)
        .unwrap()
        .into_iter()
        .find(|s| s["provider"] == "claude")
        .unwrap();
    let never = |_: &Value, _: &Path| -> anyhow::Result<Value> { panic!("private Claude read") };
    read_source(&pool.home, &source, &never).unwrap();
    let account = snapshot(&pool.home, false)
        .unwrap()
        .into_iter()
        .find(|a| a["provider"] == "claude")
        .unwrap();
    assert_eq!(account["connected"], true);
    assert_eq!(account["windows"][0]["used"], 25);
}

#[test]
fn cache_rejects_secret_fields() {
    let (pool, _) = setup();
    assert!(pool
        .db()
        .cache("test-codex", &json!({"access_token": "never stored"}))
        .is_err());
}

#[test]
fn missing_attached_account_reported_and_restored_claude_clears_only_its_error() {
    let pool = Pool::new();
    let native = pool.root().join("native");
    std::fs::create_dir(&native).unwrap();
    let mut db = pool.db();
    db.add_profile("claude", "claude", "claude", Some(native.to_str().unwrap()))
        .unwrap();
    db.cache("claude", &json!({"connected": true, "windows": []}))
        .unwrap();
    let probe = |_: &Value, _: &Path| -> anyhow::Result<Value> { anyhow::bail!("unused") };
    std::fs::rename(&native, pool.root().join("away")).unwrap();
    let accounts = collect_with(&pool.home, false, &probe).unwrap();
    assert!(accounts[0]["error"].as_str().unwrap().contains("missing"));
    std::fs::rename(pool.root().join("away"), &native).unwrap();
    let account = collect_with(&pool.home, false, &probe).unwrap().remove(0);
    assert!(account["error"].is_null());
    assert_eq!(account["connected"], true);
    db.cache(
        "claude",
        &json!({"connected": false, "windows": [], "error": "An unrelated provider error"}),
    )
    .unwrap();
    assert_eq!(
        collect_with(&pool.home, false, &probe).unwrap()[0]["error"],
        "An unrelated provider error"
    );
}

#[test]
fn default_codex_source_is_monitor_only_and_excluded_from_status() {
    let pool = Pool::new();
    let default = pool.root().join("native-codex");
    std::fs::create_dir(&default).unwrap();
    std::env::set_var("CODEX_HOME", &default);
    let db = pool.db();
    let items = sources(&db, true).unwrap();
    let main = items
        .iter()
        .find(|x| x["name"] == fleet_core::monitor::DEFAULT_SOURCE)
        .unwrap();
    assert_eq!(main["managed"], false);
    assert_eq!(main["enabled"], false);
    assert!(sources(&db, false).unwrap().is_empty());
    let (code, status) = pool.json(&["status"]);
    assert_eq!(code, 0);
    assert!(status["accounts"].as_array().unwrap().is_empty());
    let (code, overview) = pool.json(&["overview"]);
    assert_eq!(code, 0);
    assert_eq!(
        overview["accounts"][0]["name"],
        fleet_core::monitor::DEFAULT_SOURCE
    );
    assert!(db.profiles().unwrap().is_empty());
}
