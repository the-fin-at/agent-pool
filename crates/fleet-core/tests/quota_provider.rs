use fleet_core::provider::{environment, native_argv, parse, redact};
use fleet_core::quota::{availability, claude, claude_windows, codex, timestamp};
use serde_json::{json, Value};
use std::path::Path;

fn window(used: Value, reset: Value, minutes: i64, extra: Value) -> Value {
    let mut w = json!({"key": "test", "used": used, "reset": reset, "minutes": minutes});
    for (k, v) in extra.as_object().unwrap() {
        w[k] = v.clone();
    }
    w
}

#[test]
fn waits_for_latest_of_all_exhausted_windows() {
    let s = availability(
        &[
            window(json!(100), json!(200), 300, json!({})),
            window(json!(100), json!(800), 10080, json!({})),
        ],
        100.0,
        None,
        None,
    );
    assert!(!s.ready);
    assert_eq!(s.ready_at, Some(800.0));
    assert_eq!(s.weekly_reset, Some(800.0));
}

#[test]
fn expired_window_and_unknown_reset() {
    assert!(
        availability(
            &[window(json!(100), json!(99), 300, json!({}))],
            100.0,
            None,
            None
        )
        .ready
    );
    let s = availability(
        &[window(json!(100), Value::Null, 300, json!({}))],
        100.0,
        None,
        None,
    );
    assert!(!s.ready);
    assert_eq!(s.ready_at, None);
    assert_eq!(s.reason, "reset_unknown");
}

#[test]
fn bucket_and_model_windows() {
    let other = window(
        json!(100),
        json!(200),
        300,
        json!({"bucket": "codex_other"}),
    );
    assert!(availability(&[other], 100.0, None, Some("codex")).ready);
    let opus = window(json!(100), json!(200), 10080, json!({"model": "opus"}));
    assert!(availability(std::slice::from_ref(&opus), 100.0, Some("sonnet"), None).ready);
    assert!(
        !availability(
            std::slice::from_ref(&opus),
            100.0,
            Some("claude-Opus-4"),
            None
        )
        .ready
    );
    // Without an explicit model all model windows are enforced conservatively.
    assert!(!availability(&[opus], 100.0, None, None).ready);
}

#[test]
fn five_hour_and_weekly_both_enforced() {
    let windows = [
        window(json!(10), json!(500), 300, json!({"bucket": "claude"})),
        window(json!(100), json!(9000), 10080, json!({"bucket": "claude"})),
    ];
    let s = availability(&windows, 100.0, None, None);
    assert!(!s.ready);
    assert_eq!(s.ready_at, Some(9000.0));
}

#[test]
fn codex_payloads() {
    let parsed = codex(
        &json!({"rateLimits": {"primary": {"usedPercent": 42, "windowDurationMins": 15, "resetsAt": 123}}}),
    );
    assert_eq!(parsed[0]["minutes"], 15);
    assert_eq!(parsed[0]["key"], "codex:primary");
    let parsed = codex(
        &json!({"rateLimits": {"primary": {"usedPercent": 100}}, "rateLimitsByLimitId": {
        "codex": {"primary": {"usedPercent": 10, "windowDurationMins": 300, "resetsAt": 999}}}}),
    );
    assert_eq!(parsed.len(), 1);
    assert_eq!(parsed[0]["used"], 10);
}

#[test]
fn claude_legacy_event_fraction_and_rejection() {
    let w = claude(
        &json!({"rate_limit_info": {"rateLimitType": "seven_day_opus", "status": "allowed_warning",
        "utilization": 0.92, "resetsAt": 123}}),
    )
    .unwrap();
    assert!((w["used"].as_f64().unwrap() - 92.0).abs() < 1e-9);
    assert_eq!(w["model"], "opus");
    assert_eq!(
        claude(&json!({"rate_limit_info": {"status": "rejected"}})).unwrap()["used"],
        100
    );
    assert!(claude(&json!({"rate_limit_info": {"rateLimitType": "overage"}})).is_none());
}

fn summary(windows: &[Value]) -> Vec<(String, Option<i64>, f64, Option<f64>)> {
    windows
        .iter()
        .map(|w| {
            (
                w["key"].as_str().unwrap().into(),
                w["minutes"].as_i64(),
                w["used"].as_f64().unwrap(),
                w["reset"].as_f64(),
            )
        })
        .collect()
}

#[test]
fn unified_fixture_from_native_cli() {
    let event: Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/claude-unified-limits.json"
    ))
    .unwrap();
    let ok = json!({"type": "result", "subtype": "success", "is_error": false, "result": "OK"});
    let out = parse("claude", &format!("{event}\n{ok}"), "", 0, "");
    assert_eq!(out.kind, "success");
    let got = summary(&out.windows);
    assert_eq!(got.len(), 2);
    assert_eq!(
        (got[0].0.as_str(), got[0].1, got[0].3),
        ("five_hour", Some(300), Some(1793221200.0))
    );
    assert_eq!(got[0].2, 0.0);
    assert_eq!(
        (got[1].0.as_str(), got[1].1, got[1].3),
        ("seven_day", Some(10080), Some(1793757600.0))
    );
    assert!((got[1].2 - 2.0).abs() < 1e-9);
}

#[test]
fn rejected_limiting_window_does_not_exhaust_others() {
    let ws = claude_windows(
        &json!({"rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour", "unifiedWindows": {
        "five_hour": {"status": "rejected", "resetsAt": 1000},
        "seven_day": {"status": "allowed", "utilization": 0.02, "resetsAt": 2000},
        "seven_day_opus": {"status": "allowed", "utilization": 0.25, "resetsAt": 2000},
        "overage": {"status": "rejected"}}}}),
    );
    let keys: Vec<(&str, f64, Value)> = ws
        .iter()
        .map(|w| {
            (
                w["key"].as_str().unwrap(),
                w["used"].as_f64().unwrap().round(),
                w["model"].clone(),
            )
        })
        .collect();
    assert_eq!(
        keys,
        vec![
            ("five_hour", 100.0, Value::Null),
            ("seven_day", 2.0, Value::Null),
            ("seven_day_opus", 25.0, json!("opus"))
        ]
    );
}

#[test]
fn legacy_partial_and_nested_reset_alias() {
    let legacy = claude_windows(
        &json!({"rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour",
        "utilization": 0.5, "resetsAt": 1000}}),
    );
    assert_eq!(
        summary(&legacy),
        vec![("five_hour".into(), Some(300), 50.0, Some(1000.0))]
    );
    let partial = claude_windows(
        &json!({"rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour",
        "utilization": 0.5, "resetsAt": 1000, "unifiedWindows": {"seven_day": {"utilization": 0.02, "resetsAt": 2000}}}}),
    );
    let keys: Vec<&str> = partial.iter().map(|w| w["key"].as_str().unwrap()).collect();
    assert_eq!(keys, vec!["seven_day", "five_hour"]);
    let nested = claude_windows(
        &json!({"rate_limit_info": {"rateLimitType": "five_hour", "resetsAt": 1000,
        "unified_windows": {"five_hour": {"utilization": 0.2, "resets_at": 2000}}}}),
    );
    assert_eq!(nested[0]["reset"], 2000);
    assert_eq!(nested.len(), 1);
}

#[test]
fn manual_reset_requires_timezone() {
    assert!(timestamp("2026-10-29T08:00:00").is_err());
    assert_eq!(timestamp("1970-01-01T01:00:01+01:00").unwrap(), 1.0);
    assert_eq!(timestamp("1970-01-01T00:00:02Z").unwrap(), 2.0);
}

#[test]
fn parse_semantics() {
    let prose = json!({"type": "result", "subtype": "success", "result": "The bug is a rate limit", "is_error": false});
    assert_eq!(
        parse("claude", &prose.to_string(), "", 0, "").kind,
        "success"
    );
    assert_eq!(parse("codex", "", "", 0, "Partial answer").kind, "failed");
    let quota = json!({"type": "result", "subtype": "error_during_execution", "is_error": true, "errors": ["rate_limit"]});
    assert_eq!(parse("claude", &quota.to_string(), "", 0, "").kind, "quota");
    let secret = json!({"type": "error", "message": "Bearer abc.secret"});
    assert!(!parse("codex", &secret.to_string(), "", 1, "")
        .error
        .contains("abc.secret"));
    let usage = json!({"type": "turn.failed", "error": {"message": "usage_limit_reached"}});
    assert_eq!(parse("codex", &usage.to_string(), "", 1, "").kind, "quota");
    let done = "{\"type\":\"turn.completed\"}";
    assert_eq!(parse("codex", done, "", 0, "Final").result, "Final");
}

#[test]
fn redaction() {
    let text = redact("token sk-ant-abcdefghijklmnop and Bearer xyz and eyJa.eyJb.sig");
    assert!(!text.contains("abcdefghijklmnop") && !text.contains("xyz") && !text.contains("eyJb"));
}

#[test]
fn environment_isolated_and_ambient_credentials_removed() {
    std::env::set_var("OPENAI_API_KEY", "secret");
    std::env::set_var("CLAUDE_CONFIG_DIR", "/wrong");
    let env = environment("codex", Path::new("/isolated"));
    let get = |k: &str| env.iter().find(|(key, _)| key == k).map(|(_, v)| v.clone());
    assert_eq!(get("CODEX_HOME").as_deref(), Some("/isolated"));
    assert!(get("OPENAI_API_KEY").is_none());
    assert!(get("CLAUDE_CONFIG_DIR").is_none());
    assert_eq!(env.iter().filter(|(k, _)| k == "CODEX_HOME").count(), 1);
}

#[test]
fn native_argv_uses_stdin_marker_and_read_only_sandbox() {
    let argv = native_argv(
        &json!({"provider": "codex"}),
        &json!({"allow_edits": 0, "model": null}),
        Path::new("out"),
    );
    assert_eq!(argv.last().unwrap(), "-");
    assert!(argv.contains(&"read-only".to_string()));
    assert!(!argv.iter().any(|a| a.contains("danger")));
    let argv = native_argv(
        &json!({"provider": "claude"}),
        &json!({"allow_edits": 1, "model": "opus"}),
        Path::new("x"),
    );
    assert!(argv.contains(&"Read,Glob,Grep,Edit,Write".to_string()));
    assert_eq!(&argv[argv.len() - 2..], ["--model", "opus"]);
}
