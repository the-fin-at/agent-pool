//! Normalize provider observations. Never invent subscription token budgets.
use anyhow::{bail, Result};
use serde_json::{json, Map, Value};

/// ISO 8601 with an explicit timezone, as accepted by `quota set --reset-at`.
pub fn timestamp(value: &str) -> Result<f64> {
    let text = value.trim().replace(['Z', 'z'], "+00:00");
    if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(&text) {
        return Ok(dt.timestamp_micros() as f64 / 1e6);
    }
    for format in [
        "%Y-%m-%dT%H:%M:%S%.f%:z",
        "%Y-%m-%d %H:%M:%S%.f%:z",
        "%Y-%m-%dT%H:%M%:z",
        "%Y-%m-%d %H:%M%:z",
        "%Y-%m-%dT%H:%M:%S%.f%z",
        "%Y-%m-%dT%H:%M%z",
    ] {
        if let Ok(dt) = chrono::DateTime::parse_from_str(&text, format) {
            return Ok(dt.timestamp_micros() as f64 / 1e6);
        }
    }
    for format in [
        "%Y-%m-%dT%H:%M:%S%.f",
        "%Y-%m-%d %H:%M:%S%.f",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
    ] {
        if chrono::NaiveDateTime::parse_from_str(&text, format).is_ok() {
            bail!("Reset time needs a timezone, e.g. 2026-10-29T08:00:00+01:00");
        }
    }
    if chrono::NaiveDate::parse_from_str(&text, "%Y-%m-%d").is_ok() {
        bail!("Reset time needs a timezone, e.g. 2026-10-29T08:00:00+01:00");
    }
    bail!("Invalid isoformat string: '{value}'")
}

fn obj(v: &Value) -> Option<&Map<String, Value>> {
    v.as_object().filter(|m| !m.is_empty())
}

pub fn codex(payload: &Value) -> Vec<Value> {
    let mut buckets: Vec<(String, Value)> = match obj(&payload["rateLimitsByLimitId"]) {
        Some(m) => m.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
        None => vec![],
    };
    if buckets.is_empty() {
        if let Some(b) = obj(&payload["rateLimits"]) {
            let id = b
                .get("limitId")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .unwrap_or("codex");
            buckets.push((id.to_string(), Value::Object(b.clone())));
        }
    }
    let mut result = vec![];
    for (key, bucket) in buckets {
        for slot in ["primary", "secondary"] {
            let Some(w) = obj(&bucket[slot]) else {
                continue;
            };
            let field = |k: &str| w.get(k).cloned().unwrap_or(Value::Null);
            result.push(json!({"key": format!("{key}:{slot}"), "bucket": key,
                "minutes": field("windowDurationMins"), "used": field("usedPercent"),
                "reset": field("resetsAt"), "model": null}));
        }
    }
    result
}

/// The general Codex snapshot explains an account restriction. A model bucket's
/// reason must never be promoted to a restriction on the entire account.
pub fn codex_reached_type(payload: &Value) -> Option<&str> {
    let bucket = if let Some(buckets) = obj(&payload["rateLimitsByLimitId"]) {
        buckets.get("codex").and_then(obj)?
    } else {
        obj(&payload["rateLimits"])?
    };
    if bucket
        .get("limitId")
        .and_then(Value::as_str)
        .is_some_and(|id| !id.is_empty() && id != "codex")
    {
        return None;
    }
    bucket
        .get("rateLimitReachedType")
        .and_then(Value::as_str)
        .filter(|reason| !reason.is_empty())
}

fn info_of(event: &Value) -> Map<String, Value> {
    obj(&event["rate_limit_info"])
        .or_else(|| obj(&event["rateLimitInfo"]))
        .cloned()
        .unwrap_or_default()
}

/// One native rate-limit observation; overage is never a subscription window.
pub fn claude(event: &Value) -> Option<Value> {
    let info = info_of(event);
    let kind = match info
        .get("rateLimitType")
        .or_else(|| info.get("rate_limit_type"))
    {
        Some(Value::String(s)) => s.clone(),
        Some(_) => return None,
        None => "unknown".into(),
    };
    if kind == "overage" {
        return None;
    }
    let mut used = info
        .get("utilization")
        .and_then(Value::as_f64)
        .map(|u| json!(u * 100.0))
        .unwrap_or(Value::Null);
    if info.get("status").is_some_and(|s| s == "rejected") {
        used = json!(100);
    }
    let minutes = if kind == "five_hour" {
        json!(300)
    } else if kind.starts_with("seven_day") {
        json!(10080)
    } else {
        Value::Null
    };
    let reset = info
        .get("resetsAt")
        .or_else(|| info.get("resets_at"))
        .cloned()
        .unwrap_or(Value::Null);
    let model = kind
        .strip_prefix("seven_day_")
        .map(|m| json!(m))
        .unwrap_or(Value::Null);
    Some(
        json!({"key": kind, "bucket": "claude", "minutes": minutes, "used": used, "reset": reset, "model": model}),
    )
}

/// Prefer each native unified observation; preserve legacy limiting-window events.
pub fn claude_windows(event: &Value) -> Vec<Value> {
    let info = info_of(event);
    let unified = info
        .get("unifiedWindows")
        .and_then(obj)
        .or_else(|| info.get("unified_windows").and_then(obj));
    let active = info
        .get("rateLimitType")
        .or_else(|| info.get("rate_limit_type"))
        .cloned();
    let mut result: Vec<Value> = vec![];
    if let Some(unified) = unified {
        for (kind, observation) in unified {
            let Some(observation) = observation.as_object() else {
                continue;
            };
            let mut merged = Map::new();
            // A root rejection applies to its limiting window, not every other window.
            if active.as_ref().and_then(Value::as_str) == Some(kind.as_str()) {
                for k in ["utilization", "status", "resetsAt", "resets_at"] {
                    if let Some(v) = info.get(k) {
                        merged.insert(k.into(), v.clone());
                    }
                }
            }
            if observation.contains_key("resetsAt") || observation.contains_key("resets_at") {
                merged.remove("resetsAt");
                merged.remove("resets_at");
            }
            for (k, v) in observation {
                merged.insert(k.clone(), v.clone());
            }
            merged.insert("rateLimitType".into(), json!(kind));
            if let Some(w) = claude(&json!({"rate_limit_info": merged})) {
                result.push(w);
            }
        }
    }
    if let Some(legacy) = claude(event) {
        let known = result.iter().any(|w| w["key"] == legacy["key"]);
        let active_set = active
            .as_ref()
            .is_some_and(|a| !a.is_null() && a != "" && a != false);
        if !known && (active_set || result.is_empty()) {
            result.push(legacy);
        }
    }
    result
}

#[derive(Debug, Clone, PartialEq)]
pub struct Availability {
    pub ready: bool,
    pub ready_at: Option<f64>,
    /// `None` means no weekly window (infinitely far).
    pub weekly_reset: Option<f64>,
    pub reason: &'static str,
}

impl Availability {
    pub fn to_json(&self) -> Value {
        json!({"ready": self.ready, "ready_at": self.ready_at, "weekly_reset": self.weekly_reset, "reason": self.reason})
    }
}

fn truthy_number(v: &Value) -> Option<f64> {
    v.as_f64().filter(|n| *n != 0.0)
}

/// All applicable windows must allow work; the latest exhausted reset wins.
pub fn availability(
    windows: &[Value],
    now: f64,
    model: Option<&str>,
    bucket: Option<&str>,
) -> Availability {
    let mut blocked: Vec<f64> = vec![];
    let mut unknown = false;
    let mut weekly: Vec<f64> = vec![];
    let model = model.filter(|m| !m.is_empty()).map(str::to_lowercase);
    let bucket = bucket.filter(|b| !b.is_empty());
    for w in windows {
        if let Some(b) = bucket {
            if w["bucket"].as_str() != Some(b) {
                continue;
            }
        }
        if let Some(wm) = w["model"].as_str().filter(|s| !s.is_empty()) {
            // Without an explicit model, conservatively enforce all model windows.
            if let Some(m) = &model {
                if !m.contains(wm) {
                    continue;
                }
            }
        }
        let reset = w["reset"].as_f64();
        if reset.is_some_and(|r| r <= now) {
            continue;
        }
        if w["minutes"].as_f64() == Some(10080.0) {
            if let Some(r) = truthy_number(&w["reset"]) {
                weekly.push(r);
            }
        }
        if w["used"].as_f64().is_some_and(|u| u >= 100.0) {
            match reset {
                Some(r) => blocked.push(r),
                None => unknown = true,
            }
        }
    }
    Availability {
        ready: blocked.is_empty() && !unknown,
        ready_at: if unknown {
            None
        } else {
            Some(blocked.iter().copied().fold(now, f64::max))
        },
        weekly_reset: weekly.into_iter().reduce(f64::min),
        reason: if unknown {
            "reset_unknown"
        } else if blocked.is_empty() {
            "available"
        } else {
            "quota"
        },
    }
}
