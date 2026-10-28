"""Desktop read model. Cached observations stay explicit when a refresh fails."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .providers import read_codex_status, redact
from .quota import availability
from .store import Store

DEFAULT_SOURCE = "@codex-default"


def sources(store, include_default=True):
    result = [{**p, "authdir": str(store.authdir(p["name"])), "managed": True} for p in store.profiles()]
    default = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    managed_paths = {Path(p["authdir"]).resolve() for p in result}
    if include_default and default.is_dir() and default not in managed_paths:
        result.insert(0, {"name": DEFAULT_SOURCE, "provider": "codex", "binary": "codex",
                          "enabled": False, "managed": False, "authdir": str(default)})
    return result


def read_source(home, source, probe=read_codex_status):
    store = Store(home)
    try:
        old = store.cached_monitor(source["name"])
        if source["provider"] == "claude":
            # No private usage endpoint or credential-file parsing for subscription accounts.
            return old
        now = time.time()
        try:
            data = probe(source, Path(source["authdir"]))
            windows = data.get("windows")
            fresh = {k: data.get(k) for k in ("connected", "email", "plan", "account_type", "error")}
            fresh["checked_at"] = now
            if windows is not None:
                fresh.update(windows=windows, observed_at=now)
                if source["managed"]:
                    store.set_windows(source["name"], windows, replace=True)
                    p = store.profile(source["name"])
                    if p["hold_reason"] == "quota_reset_unknown":
                        store.update_profile(source["name"], hold_until=None, hold_reason=None)
            elif fresh["connected"]:
                same_identity = old.get("email") == fresh.get("email") and old.get("connected")
                fresh.update(windows=old.get("windows", []) if same_identity else [],
                             observed_at=old.get("observed_at") if same_identity else None)
            else:
                fresh.update(windows=[], observed_at=None)
            store.cache_monitor(source["name"], fresh)
            return fresh
        except (ValueError, OSError, RuntimeError) as exc:
            fallback = {"connected": bool(source.get("enabled")),
                        "windows": store.windows(source["name"]) if source["managed"] else [],
                        "observed_at": source.get("observed_at")}
            stale = {**(old or fallback), "error": redact(str(exc)), "checked_at": now}
            store.cache_monitor(source["name"], stale)
            return stale
    finally:
        store.close()


def collect(home, include_default=True, probe=read_codex_status):
    store = Store(home)
    try:
        items = sources(store, include_default)
    finally:
        store.close()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda source: read_source(home, source, probe), items))
    return snapshot(home, include_default)


def snapshot(home, include_default=True):
    store = Store(home)
    try:
        result = []
        for source in sources(store, include_default):
            cached = store.cached_monitor(source["name"])
            windows = cached.get("windows", [])
            observed = cached.get("observed_at")
            # A worker observation after the metadata check belongs to the current CLI profile.
            worker_observed = source.get("observed_at") or 0
            if source["managed"] and (not cached or worker_observed > (cached.get("checked_at") or 0)):
                windows, observed = store.windows(source["name"]), source.get("observed_at")
            if cached.get("connected") is False:
                windows, observed = [], None
            connected = cached.get("connected", bool(source.get("enabled")))
            result.append({"name": source["name"], "provider": source["provider"],
                           "managed": source["managed"], "enabled": bool(source["enabled"]),
                           "connected": connected, "email": cached.get("email"), "plan": cached.get("plan"),
                           "windows": windows, "observed_at": observed,
                           "checked_at": cached.get("checked_at"), "error": cached.get("error"),
                           "hold_reason": source.get("hold_reason"), "hold_until": source.get("hold_until")})
        return result
    finally:
        store.close()


def relative_time(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "unter 1 Min."
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} Min."
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} Std." + (f" {minutes} Min." if minutes else "")
    days, hours = divmod(hours, 24)
    return f"{days} Tage" + (f" {hours} Std." if hours else "")


def window_view(window, now=None):
    now = time.time() if now is None else now
    minutes = window.get("minutes")
    title = "5 Stunden" if minutes == 300 else "Woche" if minutes == 10080 else f"{minutes} Minuten" if minutes else "Weiteres Limit"
    if window.get("model"):
        title += " · " + window["model"].title()
    if window.get("bucket") not in {None, "codex", "claude"}:
        title += " · " + window["bucket"]
    used, reset = window.get("used"), window.get("reset")
    expired = reset is not None and reset <= now
    valid = isinstance(used, (int, float)) and 0 <= used <= 100
    # Passing a predicted reset is not proof of a replenished balance.
    return {"title": title, "used": float(used) if valid and not expired else None,
            "remaining": 100 - used if valid and not expired else None,
            "reset_label": "Reset erreicht · Aktualisierung nötig" if expired else
                "Reset-Zeit unbekannt" if reset is None else "Reset in " + relative_time(reset - now),
            "reset_absolute": datetime.fromtimestamp(reset).astimezone().strftime("%d.%m.%Y, %H:%M %Z") if reset else "",
            "expired": expired}


def account_view(account, now=None):
    now = time.time() if now is None else now
    observed = account.get("observed_at")
    stale = bool(account.get("error")) or bool(observed and now - observed > 150)
    windows = [window_view(w, now) for w in account.get("windows", [])]
    stale = stale or any(w["expired"] for w in windows)
    state = availability(account.get("windows", []), now, bucket="codex" if account["provider"] == "codex" else None)
    held = account.get("hold_reason") and (account.get("hold_until") is None or account["hold_until"] > now)
    if not account.get("connected"):
        label, tone = ("Verbindung prüfen", "warning") if account.get("error") else ("Nicht verbunden", "muted")
    elif stale:
        label, tone = "Stand prüfen", "warning"
    elif held or not state["ready"]:
        label, tone = "Limit erreicht", "warning"
    elif not windows or all(w["used"] is None for w in windows):
        label, tone = "Quote unbekannt", "muted"
    else:
        label, tone = "Verbunden", "success"
    plan = {"team": "Business / Team", "prolite": "Pro", "pro": "Pro", "plus": "Plus",
            "enterprise": "Enterprise", "free": "Free"}.get(account.get("plan"), account.get("plan") or "Tarif unbekannt")
    return {**account, "windows_view": windows, "status_label": label, "tone": tone, "plan_label": plan,
            "stale": stale, "updated_label": "Noch keine Quotenabfrage" if not observed else
                "Stand " + datetime.fromtimestamp(observed).astimezone().strftime("%H:%M:%S"),
            "role_label": "Für Aufträge aktiv" if account.get("enabled") else
                "CLI-Hauptaccount · nur Anzeige" if not account.get("managed") else "Profil pausiert"}
