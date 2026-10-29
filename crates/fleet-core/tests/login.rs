mod common;
use common::*;
use fleet_core::db::{now, Lease};
use fleet_core::login::{self, observe, paths, safe_url};
use serde_json::json;
use std::path::Path;

fn no_spawn(_: &Path, _: &str) -> anyhow::Result<()> {
    panic!("worker must not be launched")
}

fn key() -> String {
    uuid::Uuid::new_v4().simple().to_string()
}

#[test]
fn only_official_https_login_hosts_are_openable() {
    for url in [
        "https://auth.openai.com/codex/device",
        "https://claude.com/oauth/authorize?state=x",
        "https://claude.ai:443/x",
    ] {
        assert!(safe_url(url), "{url}");
    }
    for url in [
        "file:///etc/passwd",
        "http://claude.com",
        "https://claude.com.evil.test",
        "https://user@claude.com",
        "https://claude.com:8000",
        "https://claude.com:bad",
    ] {
        assert!(!safe_url(url), "{url}");
    }
}

#[test]
fn observer_extracts_only_public_instructions() {
    let data = observe(
        "codex",
        "\x1b[32mOpen https://auth.openai.com/codex/device\x1b[0m\nABCD-EFGHI\nBearer secret-token",
    );
    assert_eq!(data["device_code"], "ABCD-EFGHI");
    assert_eq!(data["url"], "https://auth.openai.com/codex/device");
    assert!(!serde_json::to_string(&data)
        .unwrap()
        .contains("secret-token"));
    assert!(observe(
        "claude",
        "Visit https://evil.example/steal\nPaste code here"
    )
    .is_empty());
    assert_eq!(
        observe(
            "claude",
            "Visit https://claude.com/oauth/authorize?state=x\nPaste code here"
        )["state"],
        "awaiting_code"
    );
}

#[test]
fn claude_rejection_is_retryable_without_persisting_native_diagnostics() {
    let data = observe(
        "claude",
        "\x1b[31mInvalid code. Please make sure the full code was copied.\x1b[0m\nBearer secret-token\nhttps://claude.ai/oauth/callback?code=secret-return-code",
    );
    assert_eq!(data["state"], "awaiting_code");
    assert_eq!(
        data["message"],
        "Claude hat den Code nicht akzeptiert. Kopiere den vollständigen Code aus dem Browser und versuche es erneut."
    );
    assert_eq!(data.len(), 2);
    let serialized = serde_json::to_string(&data).unwrap();
    assert!(!serialized.contains("secret-token") && !serialized.contains("secret-return-code"));
    assert!(observe(
        "codex",
        "Invalid code. Please make sure the full code was copied."
    )
    .is_empty());
}

#[test]
fn invalid_session_ids_rejected() {
    let pool = Pool::new();
    let values = [
        "../auth".to_string(),
        "/etc/passwd".into(),
        "x".repeat(32),
        "a".repeat(33),
        "A".repeat(32),
    ];
    for value in &values {
        assert!(paths(&pool.home, value).is_err(), "{value}");
    }
    assert!(pool.rpc(&["auth", "get", "invalid"]).0 == 1);
}

#[test]
fn stale_login_expires_without_exposing_url_or_code() {
    let pool = Pool::new();
    let id = "a".repeat(32);
    let p = paths(&pool.home, &id).unwrap();
    let t = now();
    // Written exactly as Python's write_private would (json.dump, ensure_ascii).
    std::fs::write(&p.state, json!({"id": id, "state": "awaiting_browser", "created_at": t - 100.0, "updated_at": t - 100.0,
        "expires_at": t + 20.0, "url": "https://auth.openai.com/codex/device", "device_code": "ABCD-EFGHI"}).to_string())
    .unwrap();
    let data = login::status(&pool.home, &id).unwrap();
    assert_eq!(data["state"], "expired");
    assert!(data["url"].is_null() && data["device_code"].is_null());
}

#[cfg(unix)]
#[test]
fn cancel_before_start_prevents_late_login_and_start_is_idempotent() {
    let pool = Pool::new();
    let k = key();
    assert_eq!(
        login::cancel(&pool.home, &k).unwrap()["cancel_requested"],
        true
    );
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    pool.db()
        .add_profile("test-codex", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    let first = login::start_with(&pool.home, "test-codex", "codex", &k, &no_spawn).unwrap();
    assert_eq!(first["state"], "cancelled");
    let again = login::start_with(&pool.home, "test-codex", "codex", &k, &no_spawn).unwrap();
    assert_eq!(again["state"], "cancelled");
    assert!(login::start_with(&pool.home, "other", "codex", &k, &no_spawn).is_err());
}

#[cfg(unix)]
#[test]
fn at_most_four_live_sessions_and_one_per_profile() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let b = binary.to_str().unwrap();
    let idle = |_: &Path, _: &str| -> anyhow::Result<()> { Ok(()) };
    for i in 0..5 {
        pool.db()
            .add_profile(&format!("p{i}"), "codex", b, None)
            .unwrap();
    }
    for i in 0..4 {
        assert_eq!(
            login::start_with(&pool.home, &format!("p{i}"), "codex", &key(), &idle).unwrap()
                ["state"],
            "starting"
        );
    }
    assert!(login::start_with(&pool.home, "p0", "codex", &key(), &idle).is_err());
    let err = login::start_with(&pool.home, "p4", "codex", &key(), &idle).unwrap_err();
    assert!(err.to_string().contains("vier"));
}

#[cfg(unix)]
fn in_process(home: &Path, id: &str) -> anyhow::Result<()> {
    let (home, id) = (home.to_owned(), id.to_owned());
    std::thread::spawn(move || {
        let _ = login::login_worker(&home, &id);
    });
    Ok(())
}

#[cfg(unix)]
fn wait_state(pool: &Pool, id: &str, states: &[&str]) -> serde_json::Value {
    let mut last = json!(null);
    let reached = wait_until(15.0, || {
        last = login::status(&pool.home, id).unwrap();
        states.contains(&last["state"].as_str().unwrap_or(""))
    });
    assert!(reached, "did not reach {states:?}: {last}");
    last
}

#[cfg(unix)]
#[test]
fn device_login_round_trip_enables_and_refreshes_read_model() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let mut db = pool.db();
    db.add_profile("test-codex", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    let k = key();
    login::start_with(&pool.home, "test-codex", "codex", &k, &in_process).unwrap();
    let data = wait_state(&pool, &k, &["awaiting_browser"]);
    assert_eq!(data["device_code"], "ABCD-EFGHI");
    assert!(!db.profile("test-codex").unwrap()["enabled"]
        .as_i64()
        .map(|v| v != 0)
        .unwrap_or(false));
    let dir = db.authdir("test-codex").unwrap();
    assert!(std::fs::read_to_string(dir.join("config.toml"))
        .unwrap()
        .contains("cli_auth_credentials_store"));
    std::fs::write(dir.join("fixture-accepted"), "fixture-only").unwrap();
    let done = wait_state(&pool, &k, &["succeeded"]);
    assert!(done["url"].is_null() && done["device_code"].is_null());
    assert_eq!(db.profile("test-codex").unwrap()["enabled"], 1);
    assert_eq!(
        db.cached("test-codex").unwrap()["email"],
        "fixture@example.invalid"
    );
    assert_eq!(
        login::start_with(&pool.home, "test-codex", "codex", &k, &no_spawn).unwrap()["state"],
        "succeeded"
    );
    let raw = std::fs::read_to_string(paths(&pool.home, &k).unwrap().state).unwrap();
    assert!(!raw.contains("Login successful"));
}

#[cfg(unix)]
#[test]
fn claude_code_round_trip_verifies_config_directory() {
    use std::os::unix::fs::PermissionsExt;
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let db = {
        let mut db = pool.db();
        db.add_profile("test-claude", "claude", binary.to_str().unwrap(), None)
            .unwrap();
        db
    };
    let k = key();
    login::start_with(&pool.home, "test-claude", "claude", &k, &in_process).unwrap();
    wait_state(&pool, &k, &["awaiting_code"]);
    assert!(login::provide_code(&pool.home, &k, "bad\u{1}code").is_err());
    login::provide_code(&pool.home, &k, "fixture-authorized-code").unwrap();
    wait_state(&pool, &k, &["succeeded"]);
    assert_eq!(
        db.cached("test-claude").unwrap()["email"],
        "fixture@example.invalid"
    );
    assert_eq!(db.profile("test-claude").unwrap()["enabled"], 1);
    let p = paths(&pool.home, &k).unwrap();
    assert!(!p.input.exists());
    assert!(!std::fs::read_to_string(&p.state)
        .unwrap()
        .contains("fixture-authorized-code"));
    assert_eq!(
        std::fs::metadata(&p.state).unwrap().permissions().mode() & 0o777,
        0o600
    );
}

#[cfg(unix)]
#[test]
fn cancel_kills_native_process_and_keeps_existing_enabled_state() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let mut db = pool.db();
    db.add_profile("test-codex", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    db.update_profile("test-codex", json!({"enabled": true}))
        .unwrap();
    let k = key();
    login::start_with(&pool.home, "test-codex", "codex", &k, &in_process).unwrap();
    wait_state(&pool, &k, &["awaiting_browser"]);
    assert_eq!(db.profile("test-codex").unwrap()["enabled"], 1);
    let dir = db.authdir("test-codex").unwrap();
    let pid: i32 = std::fs::read_to_string(dir.join("fixture-native.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    db.update_profile("test-codex", json!({"enabled": false}))
        .unwrap();
    assert_eq!(
        login::cancel(&pool.home, &k).unwrap()["cancel_requested"],
        true
    );
    wait_state(&pool, &k, &["cancelled"]);
    assert!(
        wait_until(3.0, || !alive(pid)),
        "native login survived cancellation"
    );
    assert_eq!(db.profile("test-codex").unwrap()["enabled"], 0);
}

#[cfg(unix)]
#[test]
fn busy_account_fails_without_starting_native_login() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let mut db = pool.db();
    db.add_profile("test-codex", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    let dir = db.authdir("test-codex").unwrap();
    let _lock = Lease::acquire(&dir.join(".native.lock")).unwrap();
    let k = key();
    login::start_with(&pool.home, "test-codex", "codex", &k, &in_process).unwrap();
    let data = wait_state(&pool, &k, &["failed"]);
    assert!(data["message"].as_str().unwrap().contains("verwendet"));
    assert!(!dir.join("fixture-native.pid").exists());
}

#[cfg(unix)]
#[test]
fn api_key_login_is_not_a_subscription() {
    let pool = Pool::new();
    let binary = script(
        &pool.root(),
        "api-key-cli",
        "echo 'Logged in using API key'\nexit 0\n",
    );
    let dir = pool.root().join("codex");
    std::fs::create_dir(&dir).unwrap();
    assert!(login::verify(
        &json!({"provider": "codex", "binary": binary.to_str().unwrap()}),
        &dir
    )
    .is_err());
}

#[cfg(windows)]
#[test]
fn windows_paths_match_python_resolve_form() {
    let pool = Pool::new();
    let p = fleet_core::db::resolve(&pool.home);
    assert!(!p.to_string_lossy().starts_with(r"\\?\"));
    let ws = pool.root().join("ws");
    std::fs::create_dir(&ws).unwrap();
    let (code, out) = pool.json(&["workspace", "add", "ws", "--path", ws.to_str().unwrap()]);
    assert_eq!(code, 0, "{out}");
    assert!(!out[0]["path"].as_str().unwrap().starts_with(r"\\?\"));
    assert!(pool.db().workspace("ws").is_ok());
}

#[test]
fn local_help_is_success_but_rpc_help_is_rejected() {
    let pool = Pool::new();
    for argv in [
        vec!["--help"],
        vec!["job", "--help"],
        vec!["job", "submit", "--help"],
        vec!["status", "-h"],
    ] {
        let (code, out) = pool.run(&argv);
        assert_eq!(code, 0, "{argv:?}");
        assert!(out.starts_with("usage:"), "{out}");
    }
    assert!(pool.run(&["--help"]).1.contains("job {submit"));
    assert_eq!(pool.rpc(&["job", "--help"]).0, 1);
    assert_eq!(pool.rpc(&["status", "--help"]).0, 1);
}
