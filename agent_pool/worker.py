"""One local worker per queue; submitters may run concurrently."""
import time

from .providers import read_codex_quota, run_native
from .quota import availability


def refresh(store, profile, probe=read_codex_quota):
    if profile["provider"] != "codex":
        return False
    try:
        windows = probe(profile, store.authdir(profile["name"]))
        store.set_windows(profile["name"], windows, replace=True)
        if profile.get("hold_reason") == "quota_reset_unknown":
            store.update_profile(profile["name"], hold_until=None, hold_reason=None)
        return True
    except (ValueError, OSError) as exc:
        store.update_profile(profile["name"], quota_error=str(exc), checked_at=time.time())
        return False


def choose(store, job, now):
    candidates = []
    reasons = []
    for p in store.profiles():
        if p["provider"] != job["provider"] or (job["profile"] and p["name"] != job["profile"]):
            continue
        if not p["enabled"]:
            reasons.append(p["name"] + ":disabled_or_not_logged_in")
            continue
        if p["hold_reason"] and (p["hold_until"] is None or p["hold_until"] > now):
            reasons.append(p["name"] + ":" + p["hold_reason"])
            continue
        state = availability(store.windows(p["name"]), now, model=job["model"],
                             bucket=(job["bucket"] or "codex") if p["provider"] == "codex" else None)
        if not state["ready"]:
            reasons.append(p["name"] + ":" + state["reason"])
            continue
        candidates.append((state["weekly_reset"], p["last_used"], p["name"], p))
    if not candidates:
        return None, "; ".join(reasons) or "No matching profile; add a profile and log in"
    return min(candidates, key=lambda x: x[:3])[3], None


def tick(store, runner=run_native, probe=read_codex_quota, now=None):
    """Caller holds worker_lock. Executes at most one job per tick."""
    now = time.time() if now is None else now
    jobs = store.jobs(pending=True)
    if not jobs:
        return False
    providers = {j["provider"] for j in jobs}
    for p in store.profiles():
        # Probing is per-profile and metadata-only, with a 60-second cache.
        if p["enabled"] and p["provider"] in providers and p["provider"] == "codex":
            if p["checked_at"] is None or now - p["checked_at"] >= 60:
                refresh(store, p, probe)
    for job in jobs:
        if job["attempts"] >= job["max_attempts"]:
            store.update_job(job["id"], status="failed", error="Maximum attempts reached")
            continue
        profile, reason = choose(store, job, now)
        if profile is None:
            store.update_job(job["id"], status="waiting", error=reason)
            continue
        name = profile["name"]
        store.update_job(job["id"], status="running", chosen_profile=name,
                         attempts=job["attempts"] + 1, error=None)
        store.update_profile(name, last_used=now)
        try:
            result = runner(profile, job, store.authdir(name))
        except (OSError, ValueError) as exc:
            store.update_job(job["id"], status="needs_review", error=str(exc))
            return True
        except BaseException:
            store.update_job(job["id"], status="needs_review", error="Worker interrupted; inspect workspace before retry")
            raise
        if result.windows:
            store.set_windows(name, result.windows)
        if result.kind == "success":
            store.update_job(job["id"], status="succeeded", result=result.result, error=None)
        elif result.kind == "quota":
            if profile["provider"] == "codex":
                refresh(store, profile, probe)
            state = availability(store.windows(name), now, model=job["model"],
                                 bucket=(job["bucket"] or "codex") if profile["provider"] == "codex" else None)
            until = state["ready_at"] if not state["ready"] else None
            store.update_profile(name, hold_until=until, hold_reason="quota" if until else "quota_reset_unknown")
            store.update_job(job["id"], status="needs_review" if job["allow_edits"] else "waiting", error=result.error)
        else:
            store.update_job(job["id"], status="needs_review" if job["allow_edits"] or result.kind == "uncertain" else "failed", error=result.error)
        return True
    return False
