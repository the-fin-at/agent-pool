mod common;
use common::*;
use fleet_core::remote::{parse_reply, shell_quote, validate, RemoteClient, RemoteConfig};
use serde_json::json;

fn rpc_pool() -> Pool {
    let pool = Pool::new();
    let path = pool.root();
    assert_eq!(
        pool.run(&["workspace", "add", "demo", "--path", path.to_str().unwrap()])
            .0,
        0
    );
    pool
}

fn submit(pool: &Pool, prompt: &str, key: &str) -> (i64, serde_json::Value) {
    pool.rpc(&[
        "job",
        "submit",
        "--workspace",
        "demo",
        "--provider",
        "codex",
        "--prompt",
        prompt,
        "--key",
        key,
    ])
}

#[test]
fn disconnected_resubmission_keeps_one_job_and_rejects_conflict() {
    let pool = rpc_pool();
    submit(&pool, "prüfe äöü", "request-1");
    let (code, job) = submit(&pool, "prüfe äöü", "request-1");
    assert_eq!(code, 0);
    assert_eq!(pool.db().jobs(false).unwrap().len(), 1);
    assert!(job.get("prompt").is_none());
    assert_eq!(submit(&pool, "different", "request-1").0, 1);
}

#[test]
fn rpc_never_executes_or_allows_nested_remote() {
    let pool = rpc_pool();
    for argv in [
        vec!["work"],
        vec!["run"],
        vec!["login", "codex-1"],
        vec!["rpc"],
        vec!["--remote", "x", "doctor"],
        vec!["overview"],
        vec!["init"],
        vec!["service", "--exec", "/x"],
        vec!["remote", "list"],
    ] {
        assert_eq!(pool.rpc(&argv).0, 1, "{argv:?}");
    }
    assert!(pool.db().jobs(false).unwrap().is_empty());
}

#[test]
fn rpc_restrictions_match_reference() {
    let pool = rpc_pool();
    let root = pool.root();
    let r = root.to_str().unwrap();
    for argv in [
        vec!["status", "--refresh"],
        vec!["monitor", "--refresh"],
        vec!["quota", "refresh"],
        vec![
            "quota",
            "set",
            "x",
            "--window",
            "weekly",
            "--used",
            "1",
            "--reset-at",
            "2099-01-01T00:00:00Z",
        ],
        vec!["profile", "add", "x", "--provider", "codex"],
        vec!["workspace", "add", "x", "--path", r],
        vec!["workspace", "remove", "demo"],
        vec![
            "auth",
            "input",
            &"a".repeat(32),
            "--code-file",
            "/etc/passwd",
        ],
        vec![
            "job",
            "submit",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--cwd",
            r,
            "--key",
            "k",
        ],
        vec![
            "job",
            "submit",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--workspace",
            "demo",
        ],
        vec![
            "job",
            "submit",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--workspace",
            "absent",
            "--key",
            "k",
        ],
        vec!["job", "submit", "--help"],
        vec!["job", "list", "--bogus"],
        vec!["job", "frobnicate"],
    ] {
        assert_eq!(pool.rpc(&argv).0, 1, "{argv:?}");
    }
    assert_eq!(pool.rpc(&["status"]).0, 0);
    assert_eq!(pool.rpc(&["workspace", "list"]).1[0]["name"], "demo");
}

#[test]
fn envelope_validation() {
    let pool = rpc_pool();
    for request in [
        json!({"version": 2, "argv": ["doctor"]}),
        json!({"version": true, "argv": ["doctor"]}),
        json!({"version": 1.0, "argv": ["job", "list"]}),
        json!({"version": 1, "argv": ["doctor"], "home": "/tmp"}),
        json!({"version": 1, "argv": []}),
        json!({"version": 1, "argv": [1]}),
        json!([1]),
        json!({"version": 1, "argv": ["job", "get", "a\u{0}b"]}),
    ] {
        let reply = fleet_core::rpc(&pool.home, request.clone());
        assert_eq!(reply["code"], 1, "{request}");
        assert_eq!(reply["version"], 1);
        assert!(
            serde_json::from_str::<serde_json::Value>(reply["output"].as_str().unwrap()).unwrap()
                ["error"]
                .is_string()
        );
    }
    let big = vec![b'x'; 2 * 1024 * 1024 + 1];
    assert_eq!(fleet_core::rpc_bytes(&pool.home, &big)["code"], 1);
    assert_eq!(fleet_core::rpc_bytes(&pool.home, b"\xff")["code"], 1);
    let deep = format!("{}0{}", "[".repeat(2000), "]".repeat(2000));
    assert_eq!(
        fleet_core::rpc_bytes(&pool.home, deep.as_bytes())["code"],
        1
    );
    let ok = fleet_core::rpc_bytes(&pool.home, br#"{"version":1,"argv":["job","list"]}"#);
    assert_eq!(ok["code"], 0);
}

#[test]
fn invalid_values_and_wait_bounds_rejected() {
    let pool = rpc_pool();
    for (opt, value) in [
        ("--model", "--bad"),
        ("--timeout", "nan"),
        ("--timeout", "999999"),
        ("--max-attempts", "101"),
    ] {
        let argv = [
            "job",
            "submit",
            "--workspace",
            "demo",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--key",
            "x",
            opt,
            value,
        ];
        assert_eq!(pool.rpc(&argv).0, 1, "{opt} {value}");
    }
    let (_, job) = submit(&pool, "x", "k");
    let id = job["id"].as_str().unwrap();
    for seconds in ["nan", "inf", "61", "-1"] {
        assert_eq!(
            pool.rpc(&["job", "wait", id, "--seconds", seconds]).0,
            1,
            "{seconds}"
        );
    }
    assert_eq!(pool.rpc(&["job", "wait", id, "--seconds", "0"]).0, 2);
}

#[test]
fn prompt_is_literal_never_shell_executed() {
    let pool = rpc_pool();
    let target = pool.root().join("pwned");
    let t = target.to_str().unwrap();
    let prompt = format!("$(touch {t}); `touch {t}`; ' \"\nHallo");
    let (code, job) = submit(&pool, &prompt, "lit");
    assert_eq!(code, 0);
    assert_eq!(
        pool.db().job(job["id"].as_str().unwrap()).unwrap()["prompt"],
        prompt.as_str()
    );
    assert!(!target.exists());
}

#[cfg(unix)]
#[test]
fn workspace_symlink_swap_rejected() {
    let pool = rpc_pool();
    let original = pool.root().join("work");
    std::fs::create_dir(&original).unwrap();
    assert_eq!(
        pool.run(&[
            "workspace",
            "add",
            "work",
            "--path",
            original.to_str().unwrap()
        ])
        .0,
        0
    );
    std::fs::remove_dir(&original).unwrap();
    std::os::unix::fs::symlink(&pool.home, &original).unwrap();
    let argv = [
        "job",
        "submit",
        "--workspace",
        "work",
        "--provider",
        "codex",
        "--prompt",
        "x",
        "--key",
        "k",
    ];
    assert_eq!(pool.rpc(&argv).0, 1);
}

#[test]
fn administration_works_while_worker_lease_is_held_and_review_needs_ack() {
    let pool = rpc_pool();
    let mut db = pool.db();
    db.add_profile("test", "codex", "codex", None).unwrap();
    let (_, job) = submit(&pool, "x", "k");
    let id = job["id"].as_str().unwrap();
    {
        let _lease = db.worker_lock().unwrap();
        assert_eq!(pool.rpc(&["profile", "disable", "test"]).0, 0);
        assert_eq!(pool.rpc(&["job", "cancel", id]).0, 0);
        assert_eq!(pool.rpc(&["job", "retry", id]).0, 0);
    }
    assert_eq!(db.job(id).unwrap()["status"], "queued");
    db.update_job(id, json!({"status": "needs_review"}))
        .unwrap();
    assert_eq!(pool.rpc(&["job", "retry", id]).0, 1);
    assert_eq!(pool.rpc(&["job", "retry", id, "--acknowledge-review"]).0, 0);
    db.update_job(id, json!({"status": "succeeded", "result": "kept"}))
        .unwrap();
    assert_eq!(pool.rpc(&["job", "cancel", id]).0, 1);
    assert_eq!(db.job(id).unwrap()["status"], "succeeded");
}

#[test]
fn exit_codes_and_result_only() {
    let pool = Pool::new();
    assert_eq!(pool.run(&["init"]).0, 0);
    assert_eq!(pool.db().profiles().unwrap().len(), 4);
    assert_eq!(pool.run(&["job", "get", "does-not-exist"]).0, 1);
    let cwd = pool.cwd.to_str().unwrap().to_string();
    let (code, job) = pool.json(&[
        "job",
        "submit",
        "--provider",
        "codex",
        "--cwd",
        &cwd,
        "--prompt",
        "pending",
        "--key",
        "pending",
    ]);
    assert_eq!(code, 0);
    let id = job["id"].as_str().unwrap().to_string();
    assert_eq!(pool.run(&["job", "get", &id]).0, 2);
    assert_eq!(pool.run(&["job", "get", &id, "--result-only"]).0, 1);
    pool.db()
        .update_job(&id, json!({"status": "succeeded", "result": "plain text"}))
        .unwrap();
    assert_eq!(
        pool.run(&["job", "get", &id, "--result-only"]),
        (0, "plain text\n".into())
    );
    let (code, full) = pool.json(&["job", "get", &id]);
    assert_eq!((code, full["result"].as_str()), (0, Some("plain text")));
    pool.db()
        .update_job(&id, json!({"status": "failed"}))
        .unwrap();
    assert_eq!(pool.run(&["job", "wait", &id, "--seconds", "0"]).0, 1);
}

#[test]
fn strict_parser_rejects_unknown_input() {
    let pool = Pool::new();
    for argv in [
        vec!["frobnicate"],
        vec!["job"],
        vec!["job", "explode"],
        vec!["status", "--refreshh"],
        vec!["status", "extra"],
        vec![
            "quota",
            "set",
            "x",
            "--window",
            "monthly",
            "--used",
            "1",
            "--reset-at",
            "2099-01-01T00:00:00Z",
        ],
        vec!["job", "submit", "--provider", "gemini", "--prompt", "x"],
        vec!["job", "submit", "--provider", "codex"],
        vec![
            "job",
            "submit",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--prompt-file",
            "y",
        ],
        vec![
            "job",
            "submit",
            "--provider",
            "codex",
            "--prompt",
            "x",
            "--cwd",
            "/",
            "--workspace",
            "w",
        ],
        vec!["--home", "/tmp", "status"],
        vec!["profile", "enable"],
        vec!["work", "--once=yes"],
        vec!["desktop"],
        vec!["rpc"],
    ] {
        assert_eq!(pool.run(&argv).0, 1, "{argv:?}");
    }
    let parsed = fleet_core::args::parse(&[
        "job".into(),
        "wait".into(),
        "abc".into(),
        "--sec".into(),
        "-1".into(),
    ])
    .unwrap();
    assert_eq!(parsed.opt("--seconds"), Some("-1"));
    let parsed =
        fleet_core::args::parse(&["--remote".into(), "srv".into(), "status".into()]).unwrap();
    assert_eq!(parsed.remote.as_deref(), Some("srv"));
}

#[test]
fn quota_set_and_show() {
    let pool = Pool::new();
    pool.run(&["profile", "add", "c1", "--provider", "claude"]);
    pool.db()
        .update_profile("c1", json!({"hold_reason": "quota_reset_unknown"}))
        .unwrap();
    let (code, out) = pool.json(&[
        "quota",
        "set",
        "c1",
        "--window",
        "weekly",
        "--used",
        "100",
        "--reset-at",
        "2099-01-01T00:00:00+00:00",
        "--model",
        "opus",
    ]);
    assert_eq!(code, 0, "{out}");
    assert_eq!(out[0]["windows"][0]["key"], "seven_day_opus");
    assert_eq!(out[0]["availability"]["ready"], false);
    assert_eq!(out[0]["hold_reason"], serde_json::Value::Null);
    assert_eq!(
        pool.run(&[
            "quota",
            "set",
            "c1",
            "--window",
            "weekly",
            "--used",
            "5",
            "--reset-at",
            "2000-01-01T00:00:00Z"
        ])
        .0,
        1
    );
    assert_eq!(pool.run(&["quota", "show", "missing"]).0, 1);
}

#[test]
fn remote_config_validation_and_quoting() {
    let pool = Pool::new();
    let config = RemoteConfig::new(&pool.home);
    for host in [
        "-oProxyCommand=oops",
        "user@host;touch /tmp/x",
        "a\nb",
        "foo bar",
    ] {
        assert!(config.add("bad", host, "agent-fleet", "/srv").is_err());
    }
    assert!(config
        .add("local", "server", "agent-fleet", "/srv")
        .is_err());
    assert!(config
        .add("x", "server", "agent-fleet", "relative")
        .is_err());
    assert!(config.add("x", "server", "-oops", "/srv").is_err());
    config
        .add(
            "central",
            "user@server",
            "/opt/Agent Pool/agent-pool",
            "/srv/state",
        )
        .unwrap();
    assert!(config
        .add("central", "user@server", "agent-fleet", "/srv/state")
        .is_err());
    let client = RemoteClient::new(&config.get("central").unwrap()).unwrap();
    let argv = client.argv("rpc", false, &[]);
    assert!(argv.contains(&"BatchMode=yes".to_string()));
    assert!(argv.contains(&"StrictHostKeyChecking=yes".to_string()));
    assert!(argv.contains(&"ForwardAgent=no".to_string()));
    assert_eq!(
        argv.last().unwrap(),
        "'/opt/Agent Pool/agent-pool' --home /srv/state rpc"
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            std::fs::metadata(&config.path)
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }
    assert!(validate(&json!({"host": "server", "command": null, "home": "/srv"})).is_err());
    assert!(validate(&json!({"host": "server", "command": "agent-pool", "home": null})).is_err());
    assert_eq!(shell_quote("it's"), "'it'\"'\"'s'");
    assert_eq!(shell_quote(""), "''");
    let (code, out) = pool.json(&["remote", "list"]);
    assert_eq!(code, 0);
    assert_eq!(out["central"]["home"], "/srv/state");
    assert_eq!(pool.run(&["--remote", "central", "work"]).0, 1);
    assert_eq!(
        pool.run(&["--remote", "central", "status", "--refresh"]).0,
        1
    );
    assert_eq!(
        pool.run(&[
            "--remote",
            "central",
            "workspace",
            "add",
            "x",
            "--path",
            "/x"
        ])
        .0,
        1
    );
    assert_eq!(pool.run(&["--remote", "central", "quota", "refresh"]).0, 1);
    let cwd = pool.cwd.to_str().unwrap().to_string();
    assert_eq!(
        pool.run(&[
            "--remote",
            "central",
            "job",
            "submit",
            "--provider",
            "codex",
            "--cwd",
            &cwd,
            "--prompt",
            "x",
            "--key",
            "k"
        ])
        .0,
        1
    );
    assert_eq!(
        pool.run(&[
            "--remote",
            "central",
            "run",
            "--provider",
            "codex",
            "--workspace",
            "w",
            "--prompt",
            "x",
            "--key",
            "k",
            "--wait-seconds",
            "61"
        ])
        .0,
        1
    );
}

#[test]
fn reply_parsing_rejects_dirty_shell_and_wrong_protocol() {
    assert!(parse_reply("welcome\n{}")
        .unwrap_err()
        .to_string()
        .contains("quiet SSH shell"));
    assert!(parse_reply(r#"{"version":2,"code":0,"output":""}"#).is_err());
    assert!(parse_reply(r#"{"version":1,"code":3,"output":""}"#).is_err());
    assert!(parse_reply(r#"{"version":1,"code":0,"output":1}"#).is_err());
    let ok = parse_reply("{\"version\":1,\"code\":2,\"output\":\"{}\\n\"}\n").unwrap();
    assert_eq!(ok.code, 2);
}

#[test]
fn service_unit_escapes_paths() {
    let value =
        fleet_core::service::unit("/opt/Agent Pool/$x%/agent-pool", "/srv/agent-pool").unwrap();
    assert!(value.contains("KillMode=control-group"));
    assert!(value.contains("$$x%%"));
    assert!(value.contains("UMask=0077"));
    assert!(fleet_core::service::unit("relative", "/srv").is_err());
}

#[test]
fn heartbeat_reports_liveness() {
    let pool = Pool::new();
    assert_eq!(
        fleet_core::worker::worker_state(&pool.home)["online"],
        false
    );
    {
        let _hb = fleet_core::worker::Heartbeat::start(&pool.home);
        let state = fleet_core::worker::worker_state(&pool.home);
        assert_eq!(state["online"], true);
        assert_eq!(state["home"], pool.home.to_str().unwrap());
    }
    assert_eq!(
        fleet_core::worker::worker_state(&pool.home)["online"],
        false
    );
}

#[test]
fn run_attaches_to_existing_worker() {
    let pool = Pool::new();
    let _lease = pool.db().worker_lock().unwrap();
    let cwd = pool.cwd.to_str().unwrap().to_string();
    let (code, job) = pool.json(&[
        "run",
        "--provider",
        "codex",
        "--cwd",
        &cwd,
        "--prompt",
        "wait for the other worker",
        "--wait-seconds",
        "0",
    ]);
    assert_eq!(code, 2);
    assert_eq!(job["status"], "queued");
    assert_eq!(pool.run(&["work", "--once"]).0, 1);
}

#[cfg(unix)]
#[test]
fn work_once_executes_through_native_fixture() {
    let pool = Pool::new();
    let binary = script(&pool.root(), "native-cli", FAKE_NATIVE);
    let b = binary.to_str().unwrap().to_string();
    assert_eq!(
        pool.run(&[
            "profile",
            "add",
            "fx",
            "--provider",
            "claude",
            "--binary",
            &b
        ])
        .0,
        0
    );
    assert_eq!(pool.run(&["profile", "enable", "fx"]).0, 0);
    let cwd = pool.cwd.to_str().unwrap().to_string();
    let (_, job) = pool.json(&[
        "job",
        "submit",
        "--provider",
        "claude",
        "--cwd",
        &cwd,
        "--prompt",
        "read",
        "--key",
        "w1",
    ]);
    let (code, out) = pool.json(&["work", "--once"]);
    assert_eq!(code, 0, "{out}");
    assert_eq!(out["processed"], true);
    let (code, done) = pool.json(&["job", "get", job["id"].as_str().unwrap()]);
    assert_eq!(code, 0, "{done}");
    assert_eq!(done["result"], "Worker report: read");
    assert_eq!(
        pool.db().windows("fx").unwrap()[0]["used"]
            .as_f64()
            .map(f64::round),
        Some(20.0)
    );
    assert_eq!(
        fleet_core::worker::worker_state(&pool.home)["online"],
        false
    );
}
