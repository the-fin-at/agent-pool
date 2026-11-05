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

#[cfg(unix)]
fn codex_metadata_fixture() -> (Pool, Value) {
    let pool = Pool::new();
    let binary = script(
        &pool.root(),
        "codex-metadata",
        r#"
while IFS= read -r line; do
  case "$line" in *'"initialized"'*) continue;; esac
  id=$(printf '%s' "$line" | sed 's/^{"id":\([0-9]*\).*/\1/')
  case "$line" in
    *account/read*) result=$(cat "$CODEX_HOME/fixture-account.json");;
    *rateLimits*)
      if [ -f "$CODEX_HOME/fixture-quota-error" ]; then
        printf '{"id":%s,"error":{"message":"Controlled quota unavailable"}}\n' "$id"
        continue
      fi
      result=$(cat "$CODEX_HOME/fixture-rates.json");;
    *) result='{}';;
  esac
  printf '{"id":%s,"result":%s}\n' "$id" "$result"
done
"#,
    );
    let mut db = pool.db();
    db.add_profile("test-codex", "codex", binary.to_str().unwrap(), None)
        .unwrap();
    db.update_profile("test-codex", json!({"enabled": true}))
        .unwrap();
    let dir = db.authdir("test-codex").unwrap();
    std::fs::write(
        dir.join("fixture-account.json"),
        json!({"account":{"type":"chatgpt","email":"fixture@example.invalid","planType":"team","workspaceName":"Fixture workspace"}}).to_string(),
    ).unwrap();
    let source = sources(&db, false).unwrap().remove(0);
    (pool, source)
}

#[cfg(unix)]
fn write_codex_rates(pool: &Pool, payload: Value) {
    std::fs::write(
        pool.db()
            .authdir("test-codex")
            .unwrap()
            .join("fixture-rates.json"),
        payload.to_string(),
    )
    .unwrap();
}

#[cfg(unix)]
fn general_codex_rates(reason: Value) -> Value {
    json!({"rateLimitsByLimitId":{"codex":{
        "primary":{"usedPercent":100,"windowDurationMins":300,"resetsAt":9999999999.0},
        "secondary":{"usedPercent":16,"windowDurationMins":10080,"resetsAt":9999999999.0},
        "rateLimitReachedType":reason,"spendControlReached":false,
        "credits":{"hasCredits":false,"unlimited":false},"individualLimit":null
    }}})
}

#[test]
#[cfg(unix)]
fn codex_native_reason_and_workspace_survive_refresh_cache_and_public_views() {
    let (pool, source) = codex_metadata_fixture();
    write_codex_rates(
        &pool,
        general_codex_rates(json!("workspace_member_credits_depleted")),
    );
    let fresh = read_source(&pool.home, &source, &*fleet_core::monitor::native_probe()).unwrap();
    assert_eq!(
        fresh["rate_limit_reached_type"],
        "workspace_member_credits_depleted"
    );
    assert_eq!(fresh["workspace_name"], "Fixture workspace");
    let cached = pool.db().cached("test-codex").unwrap();
    assert_eq!(
        cached["rate_limit_reached_type"],
        fresh["rate_limit_reached_type"]
    );
    assert_eq!(cached["workspace_name"], fresh["workspace_name"]);
    for command in ["status", "overview"] {
        let (code, response) = pool.json(&[command]);
        assert_eq!(code, 0);
        let account = response["accounts"]
            .as_array()
            .unwrap()
            .iter()
            .find(|a| a["name"] == "test-codex")
            .unwrap();
        assert_eq!(
            account["rate_limit_reached_type"],
            "workspace_member_credits_depleted"
        );
        assert_eq!(account["workspace_name"], "Fixture workspace");
        assert_eq!(account["windows"][0]["used"], 100);
    }
}

#[test]
#[cfg(unix)]
fn codex_reason_is_refreshed_and_never_reused_after_missing_data_failure_or_logout() {
    let (pool, source) = codex_metadata_fixture();
    let probe = fleet_core::monitor::native_probe();
    for reason in [
        json!("workspace_member_credits_depleted"),
        json!("rate_limit_reached"),
        json!("future_provider_reason"),
        Value::Null,
    ] {
        write_codex_rates(&pool, general_codex_rates(reason.clone()));
        read_source(&pool.home, &source, &*probe).unwrap();
        assert_eq!(
            snapshot(&pool.home, false).unwrap()[0]["rate_limit_reached_type"],
            reason
        );
    }
    write_codex_rates(
        &pool,
        general_codex_rates(json!("workspace_member_credits_depleted")),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    write_codex_rates(
        &pool,
        json!({"rateLimits":{"primary":{"usedPercent":5,"windowDurationMins":300,"resetsAt":9999999999.0}}}),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    assert!(snapshot(&pool.home, false).unwrap()[0]["rate_limit_reached_type"].is_null());

    write_codex_rates(
        &pool,
        general_codex_rates(json!("workspace_member_credits_depleted")),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    let dir = pool.db().authdir("test-codex").unwrap();
    std::fs::write(dir.join("fixture-quota-error"), "controlled").unwrap();
    let failed = read_source(&pool.home, &source, &*probe).unwrap();
    assert!(failed["rate_limit_reached_type"].is_null());
    assert!(failed["error"].is_string());
    std::fs::remove_file(dir.join("fixture-quota-error")).unwrap();

    read_source(&pool.home, &source, &*probe).unwrap();
    let failed = read_source(&pool.home, &source, &|_, _| {
        anyhow::bail!("Controlled account unavailable")
    })
    .unwrap();
    assert!(failed["rate_limit_reached_type"].is_null());
    std::fs::write(dir.join("fixture-account.json"), r#"{"account":null}"#).unwrap();
    read_source(&pool.home, &source, &*probe).unwrap();
    let logged_out = snapshot(&pool.home, false).unwrap().remove(0);
    assert!(logged_out["rate_limit_reached_type"].is_null());
    assert!(logged_out["workspace_name"].is_null());
}

#[test]
#[cfg(unix)]
fn codex_reason_does_not_outlive_identity_or_newer_worker_observations() {
    let (pool, source) = codex_metadata_fixture();
    let probe = fleet_core::monitor::native_probe();
    // Older native CLIs only return the single general snapshot.
    write_codex_rates(
        &pool,
        json!({"rateLimits":{
            "limitId":"codex","rateLimitReachedType":"workspace_member_credits_depleted",
            "primary":{"usedPercent":100,"windowDurationMins":300,"resetsAt":9999999999.0}
        }}),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    assert_eq!(
        snapshot(&pool.home, false).unwrap()[0]["rate_limit_reached_type"],
        "workspace_member_credits_depleted"
    );
    std::thread::sleep(std::time::Duration::from_millis(20));
    pool.db()
        .set_windows("test-codex", &[window(5.0)], false)
        .unwrap();
    let newer = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(newer["windows"][0]["used"], 5.0);
    assert!(newer["rate_limit_reached_type"].is_null());

    let dir = pool.db().authdir("test-codex").unwrap();
    std::fs::write(
        dir.join("fixture-account.json"),
        json!({"account":{"type":"chatgpt","email":"other@example.invalid","planType":"team","workspaceName":"Another workspace"}}).to_string(),
    ).unwrap();
    write_codex_rates(&pool, general_codex_rates(Value::Null));
    read_source(&pool.home, &source, &*probe).unwrap();
    let changed = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(changed["email"], "other@example.invalid");
    assert_eq!(changed["workspace_name"], "Another workspace");
    assert!(changed["rate_limit_reached_type"].is_null());
}

#[test]
#[cfg(unix)]
fn codex_same_email_workspace_switch_never_relabels_old_windows_after_quota_failure() {
    let (pool, source) = codex_metadata_fixture();
    let probe = fleet_core::monitor::native_probe();
    write_codex_rates(
        &pool,
        general_codex_rates(json!("workspace_member_credits_depleted")),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    let before = snapshot(&pool.home, false).unwrap().remove(0);
    let dir = pool.db().authdir("test-codex").unwrap();
    std::fs::write(dir.join("fixture-quota-error"), "controlled").unwrap();

    // A failure in the same workspace may still display its explicitly stale data.
    read_source(&pool.home, &source, &*probe).unwrap();
    let same = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(same["windows"], before["windows"]);
    assert_eq!(same["observed_at"], before["observed_at"]);
    assert!(same["error"].is_string());
    assert!(same["rate_limit_reached_type"].is_null());

    // The email stays the same while the provider workspace changes.
    std::fs::write(
        dir.join("fixture-account.json"),
        json!({"account":{"type":"chatgpt","email":"fixture@example.invalid","planType":"team","workspaceName":"Another workspace"}}).to_string(),
    ).unwrap();
    read_source(&pool.home, &source, &*probe).unwrap();
    let changed = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(changed["email"], before["email"]);
    assert_eq!(changed["workspace_name"], "Another workspace");
    assert_eq!(changed["windows"], json!([]));
    assert!(changed["observed_at"].is_null());
    assert!(changed["rate_limit_reached_type"].is_null());
    assert!(changed["error"].is_string());

    // Once that workspace supplies its own observation, its quota appears normally.
    std::fs::remove_file(dir.join("fixture-quota-error")).unwrap();
    write_codex_rates(
        &pool,
        json!({"rateLimits":{"primary":{"usedPercent":5,"windowDurationMins":300,"resetsAt":9999999999.0}}}),
    );
    read_source(&pool.home, &source, &*probe).unwrap();
    let refreshed = snapshot(&pool.home, false).unwrap().remove(0);
    assert_eq!(refreshed["workspace_name"], "Another workspace");
    assert_eq!(refreshed["windows"][0]["used"], 5);
    assert!(refreshed["error"].is_null());
}

#[test]
#[cfg(unix)]
fn codex_workspace_metadata_appearance_or_loss_is_conservative_but_legacy_missing_is_compatible() {
    for (before, after, keep_old) in [
        (Some("Fixture workspace"), None, false),
        (None, Some("Fixture workspace"), false),
        (None, None, true),
    ] {
        let (pool, source) = codex_metadata_fixture();
        let dir = pool.db().authdir("test-codex").unwrap();
        let account = |workspace: Option<&str>| {
            let mut account =
                json!({"type":"chatgpt","email":"fixture@example.invalid","planType":"team"});
            if let Some(workspace) = workspace {
                account["workspaceName"] = json!(workspace);
            }
            json!({"account":account})
        };
        std::fs::write(
            dir.join("fixture-account.json"),
            account(before).to_string(),
        )
        .unwrap();
        write_codex_rates(&pool, general_codex_rates(Value::Null));
        let probe = fleet_core::monitor::native_probe();
        read_source(&pool.home, &source, &*probe).unwrap();
        let initial = snapshot(&pool.home, false).unwrap().remove(0);
        std::fs::write(dir.join("fixture-account.json"), account(after).to_string()).unwrap();
        std::fs::write(dir.join("fixture-quota-error"), "controlled").unwrap();
        read_source(&pool.home, &source, &*probe).unwrap();
        let changed = snapshot(&pool.home, false).unwrap().remove(0);
        assert_eq!(changed["workspace_name"], json!(after));
        assert_eq!(
            changed["windows"],
            if keep_old {
                initial["windows"].clone()
            } else {
                json!([])
            }
        );
        assert_eq!(changed["observed_at"].is_null(), !keep_old);
    }
}

#[test]
#[cfg(unix)]
fn codex_model_bucket_reason_does_not_become_a_general_account_reason() {
    let (pool, source) = codex_metadata_fixture();
    let probe = fleet_core::monitor::native_probe();
    let cases = [
        json!({"rateLimits":{"limitId":"codex_other","rateLimitReachedType":"workspace_member_credits_depleted","primary":{"usedPercent":100,"windowDurationMins":300}}}),
        json!({"rateLimits":{"rateLimitReachedType":"workspace_member_credits_depleted"},"rateLimitsByLimitId":{"codex_other":{"rateLimitReachedType":"workspace_member_credits_depleted","primary":{"usedPercent":100,"windowDurationMins":300}}}}),
        json!({"rateLimits":{"rateLimitReachedType":"workspace_member_credits_depleted"},"rateLimitsByLimitId":{"codex":{"rateLimitReachedType":null,"primary":{"usedPercent":5,"windowDurationMins":300}},"codex_other":{"rateLimitReachedType":"workspace_member_credits_depleted","primary":{"usedPercent":100,"windowDurationMins":300}}}}),
    ];
    for payload in cases {
        write_codex_rates(&pool, payload);
        read_source(&pool.home, &source, &*probe).unwrap();
        assert!(snapshot(&pool.home, false).unwrap()[0]["rate_limit_reached_type"].is_null());
    }
}
