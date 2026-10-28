//! Account read model. Cached observations stay explicit when a refresh fails.
use crate::db::{now, truth, Db, ATTACHED_PROFILE_UNAVAILABLE};
use crate::provider::{codex_status, redact};
use anyhow::Result;
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

pub const DEFAULT_SOURCE: &str = "@codex-default";

pub type Probe = dyn Fn(&Value, &Path) -> Result<Value> + Send + Sync;

fn default_codex_home() -> PathBuf {
    match std::env::var_os("CODEX_HOME") {
        Some(v) => crate::db::expand(Path::new(&v)),
        None => dirs::home_dir().unwrap_or_default().join(".codex"),
    }
}

fn canonical(path: &Path) -> PathBuf {
    crate::db::resolve(path)
}

/// Managed profiles plus, optionally, the monitor-only default Codex account.
pub fn sources(db: &Db, include_default: bool) -> Result<Vec<Value>> {
    let mut result = Vec::new();
    for p in db.profiles()? {
        let name = p["name"].as_str().unwrap_or_default().to_string();
        let authdir = match p["auth_home"].as_str() {
            Some(a) => PathBuf::from(a),
            None => db.home.join("profiles").join(&name),
        };
        let mut item = p.clone();
        item["authdir"] = json!(authdir.to_string_lossy());
        item["managed"] = json!(true);
        result.push(item);
    }
    if include_default {
        let default = canonical(&default_codex_home());
        let managed: Vec<PathBuf> = result
            .iter()
            .map(|p| canonical(Path::new(p["authdir"].as_str().unwrap_or_default())))
            .collect();
        if default.is_dir() && !managed.contains(&default) {
            result.insert(
                0,
                json!({"name": DEFAULT_SOURCE, "provider": "codex", "binary": "codex",
                       "enabled": false, "managed": false, "authdir": default.to_string_lossy()}),
            );
        }
    }
    Ok(result)
}

fn get<'a>(v: &'a Value, k: &str) -> &'a Value {
    v.get(k).unwrap_or(&Value::Null)
}

pub fn read_source(home: &Path, source: &Value, probe: &Probe) -> Result<Value> {
    let mut db = Db::open(home)?;
    let name = source["name"].as_str().unwrap_or_default().to_string();
    let managed = truth(&source["managed"]);
    let mut old = db.cached(&name)?;
    let checked = now();
    let attempt = (|| -> Result<Value> {
        let authdir = if managed {
            db.authdir(&name)?
        } else {
            PathBuf::from(source["authdir"].as_str().unwrap_or_default())
        };
        if source["provider"] == "claude" {
            // A restored directory retires only its own registration error.
            if old["error"] == ATTACHED_PROFILE_UNAVAILABLE {
                old["error"] = Value::Null;
                db.cache(&name, &old)?;
            }
            return Ok(old.clone());
        }
        let data = probe(source, &authdir)?;
        let mut fresh = Map::new();
        for k in ["connected", "email", "plan", "account_type", "error"] {
            fresh.insert(k.into(), get(&data, k).clone());
        }
        fresh.insert("checked_at".into(), json!(checked));
        let windows = get(&data, "windows");
        if let Some(list) = windows.as_array() {
            fresh.insert("windows".into(), windows.clone());
            fresh.insert("observed_at".into(), json!(checked));
            if managed {
                db.set_windows(&name, list, true)?;
                if db.profile(&name)?["hold_reason"] == "quota_reset_unknown" {
                    db.update_profile(&name, json!({"hold_until": null, "hold_reason": null}))?;
                }
            }
        } else if truth(&fresh["connected"]) {
            let same = old.get("email") == fresh.get("email") && truth(get(&old, "connected"));
            fresh.insert(
                "windows".into(),
                if same {
                    old.get("windows").cloned().unwrap_or(json!([]))
                } else {
                    json!([])
                },
            );
            fresh.insert(
                "observed_at".into(),
                if same {
                    get(&old, "observed_at").clone()
                } else {
                    Value::Null
                },
            );
        } else {
            fresh.insert("windows".into(), json!([]));
            fresh.insert("observed_at".into(), Value::Null);
        }
        let fresh = Value::Object(fresh);
        db.cache(&name, &fresh)?;
        Ok(fresh)
    })();
    match attempt {
        Ok(v) => Ok(v),
        Err(e) => {
            let mut stale = if old.as_object().is_some_and(|m| !m.is_empty()) {
                old
            } else {
                json!({"connected": truth(&source["enabled"]),
                       "windows": if managed { json!(db.windows(&name).unwrap_or_default()) } else { json!([]) },
                       "observed_at": source["observed_at"]})
            };
            stale["error"] = json!(redact(&e.to_string()));
            stale["checked_at"] = json!(checked);
            db.cache(&name, &stale)?;
            Ok(stale)
        }
    }
}

pub fn native_probe() -> Box<Probe> {
    Box::new(|source: &Value, dir: &Path| codex_status(source, dir))
}

/// Refreshes all sources with at most three concurrent metadata reads.
pub fn collect_with(home: &Path, include_default: bool, probe: &Probe) -> Result<Vec<Value>> {
    let items = {
        let db = Db::open(home)?;
        sources(&db, include_default)?
    };
    let queue = Arc::new(Mutex::new(items));
    std::thread::scope(|scope| {
        for _ in 0..3 {
            let queue = Arc::clone(&queue);
            scope.spawn(move || loop {
                let next = queue.lock().ok().and_then(|mut q| q.pop());
                let Some(source) = next else { break };
                let _ = read_source(home, &source, probe);
            });
        }
    });
    snapshot(home, include_default)
}

pub fn collect(home: &Path, include_default: bool) -> Result<Vec<Value>> {
    collect_with(home, include_default, &*native_probe())
}

pub fn snapshot(home: &Path, include_default: bool) -> Result<Vec<Value>> {
    let db = Db::open(home)?;
    let mut result = Vec::new();
    for source in sources(&db, include_default)? {
        let name = source["name"].as_str().unwrap_or_default();
        let managed = truth(&source["managed"]);
        let cached = db.cached(name)?;
        let empty = cached.as_object().is_none_or(|m| m.is_empty());
        let mut windows = cached.get("windows").cloned().unwrap_or(json!([]));
        let mut observed = get(&cached, "observed_at").clone();
        // A worker observation after the metadata check belongs to the current CLI profile.
        let worker_observed = source["observed_at"].as_f64().unwrap_or(0.0);
        if managed && (empty || worker_observed > cached["checked_at"].as_f64().unwrap_or(0.0)) {
            windows = json!(db.windows(name)?);
            observed = source["observed_at"].clone();
        }
        if cached.get("connected") == Some(&Value::Bool(false)) {
            windows = json!([]);
            observed = Value::Null;
        }
        let connected = cached
            .get("connected")
            .cloned()
            .unwrap_or_else(|| json!(truth(&source["enabled"])));
        result.push(json!({
            "name": name, "provider": source["provider"], "managed": managed,
            "enabled": truth(&source["enabled"]), "connected": connected,
            "email": get(&cached, "email"), "plan": get(&cached, "plan"),
            "windows": windows, "observed_at": observed,
            "checked_at": get(&cached, "checked_at"), "error": get(&cached, "error"),
            "hold_reason": source["hold_reason"], "hold_until": source["hold_until"],
        }));
    }
    Ok(result)
}
