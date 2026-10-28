"""Normalize provider observations. Never invent subscription token budgets."""
import math
from datetime import datetime, timezone


def timestamp(value):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Reset time needs a timezone, e.g. 2026-10-29T08:00:00+01:00")
        return dt.timestamp()
    raise ValueError("Invalid reset timestamp")


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def codex_windows(payload):
    buckets = payload.get("rateLimitsByLimitId") or {}
    if not buckets and payload.get("rateLimits"):
        bucket = payload["rateLimits"]
        buckets = {bucket.get("limitId") or "codex": bucket}
    result = []
    for key, bucket in buckets.items():
        for slot in ("primary", "secondary"):
            window = bucket.get(slot)
            if not window:
                continue
            result.append({"key": f"{key}:{slot}", "bucket": key,
                           "minutes": window.get("windowDurationMins"),
                           "used": window.get("usedPercent"),
                           "reset": window.get("resetsAt"), "model": None})
    return result


def claude_window(event):
    info = event.get("rate_limit_info") or event.get("rateLimitInfo") or {}
    kind = info.get("rateLimitType", info.get("rate_limit_type", "unknown"))
    if kind == "overage":
        return None
    used = info.get("utilization")
    used = used * 100 if isinstance(used, (int, float)) else None
    if info.get("status") == "rejected":
        used = 100
    return {"key": kind, "bucket": "claude", "minutes": 300 if kind == "five_hour"
            else 10080 if kind.startswith("seven_day") else None,
            "used": used, "reset": info.get("resetsAt", info.get("resets_at")),
            "model": kind.removeprefix("seven_day_") if kind.startswith("seven_day_") else None}


def claude_windows(event):
    """Prefer each native unified observation; preserve legacy limiting-window events."""
    info = event.get("rate_limit_info") or event.get("rateLimitInfo") or {}
    unified = info.get("unifiedWindows") or info.get("unified_windows") or {}
    active = info.get("rateLimitType", info.get("rate_limit_type"))
    result = []
    if isinstance(unified, dict):
        for kind, observation in unified.items():
            if not isinstance(kind, str) or not isinstance(observation, dict):
                continue
            # A root rejection applies to its limiting window, not every other window.
            inherited = {k: info[k] for k in ("utilization", "status", "resetsAt", "resets_at") if k in info} if kind == active else {}
            if "resetsAt" in observation or "resets_at" in observation:
                inherited.pop("resetsAt", None)
                inherited.pop("resets_at", None)
            window = claude_window({"rate_limit_info": {**inherited, **observation, "rateLimitType": kind}})
            if window:
                result.append(window)
    legacy = claude_window(event)
    if legacy and legacy["key"] not in {w["key"] for w in result} and (active or not result):
        result.append(legacy)
    return result


def availability(windows, now, reserve=0, model=None, bucket=None):
    """All applicable windows must allow work; the latest exhausted reset wins."""
    blocked = []
    unknown = False
    weekly = []
    for w in windows:
        if bucket and w.get("bucket") != bucket:
            continue
        if w.get("model") and (not model or w["model"] not in model.lower()):
            # Without an explicit model, conservatively enforce all model windows.
            if model:
                continue
        reset, used = w.get("reset"), w.get("used")
        if reset is not None and reset <= now:
            continue
        if w.get("minutes") == 10080 and reset:
            weekly.append(reset)
        if used is not None and used >= 100 - reserve:
            if reset is None:
                unknown = True
            else:
                blocked.append(reset)
    return {"ready": not blocked and not unknown,
            "ready_at": None if unknown else max(blocked, default=now),
            "weekly_reset": min(weekly, default=float("inf")),
            "reason": "reset_unknown" if unknown else "quota" if blocked else "available"}
