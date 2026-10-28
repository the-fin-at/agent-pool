"""CLI contract: JSON on stdout, native interactive login only in `login`."""
import argparse
import math
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from contextlib import ExitStack

from . import __version__
from .providers import environment, executable, redact
from .quota import availability, timestamp
from .store import Store, WorkerBusy, default_home
from .worker import refresh, tick

TERMINAL = {"succeeded", "failed", "needs_review", "cancelled"}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False))


def summary(job):
    return {k: v for k, v in job.items() if k not in {"prompt", "result"}}


def task_args(p):
    p.add_argument("--provider", choices=["codex", "claude"], required=True)
    p.add_argument("--profile", help="Pin this job to one account; omit to choose among this provider's profiles")
    p.add_argument("--model", help="Provider-native model name; omit for its configured default")
    p.add_argument("--bucket", help="Codex rate-limit bucket id; default codex")
    p.add_argument("--cwd", default=os.getcwd())
    text = p.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", help="UTF-8 file, or - for stdin")
    p.add_argument("--allow-edits", action="store_true", help="Allow native file editing in cwd")
    p.add_argument("--key", help="Idempotency key, reusable only for the identical task")
    p.add_argument("--timeout", type=float, default=1800, help="Per-attempt CLI timeout in seconds")
    p.add_argument("--max-attempts", type=int, default=6)


def parser():
    p = argparse.ArgumentParser(prog="agent-pool", description="Local durable job broker for native Codex and Claude Code")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--home", type=Path, default=default_home(), help="Local state directory; keep it off shared/sync drives")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("init", help="Create three disabled Codex profiles and one disabled Claude profile")
    sub.add_parser("doctor", help="Check installed native CLI executables; no inference requests")
    sub.add_parser("desktop", help="Open the native account and quota monitor")
    profiles = sub.add_parser("profile").add_subparsers(dest="operation", required=True)
    add = profiles.add_parser("add")
    add.add_argument("name")
    add.add_argument("--provider", choices=["codex", "claude"], required=True)
    add.add_argument("--binary", help="Native CLI executable or absolute path")
    profiles.add_parser("list")
    for op in ["enable", "disable", "release"]:
        profiles.add_parser(op).add_argument("name")
    login = sub.add_parser("login", help="Run the provider's own interactive browser sign-in in an isolated profile")
    login.add_argument("name")
    quota = sub.add_parser("quota").add_subparsers(dest="operation", required=True)
    show = quota.add_parser("show")
    show.add_argument("name", nargs="?")
    sync = quota.add_parser("refresh", help="Read documented Codex app-server quotas")
    sync.add_argument("name", nargs="?")
    manual = quota.add_parser("set", help="Record an observed quota window, e.g. from native /usage")
    manual.add_argument("name")
    manual.add_argument("--window", choices=["five-hour", "weekly"], required=True)
    manual.add_argument("--used", type=float, required=True)
    manual.add_argument("--reset-at", required=True, help="ISO 8601 timestamp including timezone")
    manual.add_argument("--model", help="Optional Claude model family, e.g. opus")
    manual.add_argument("--bucket", default="codex")
    jobs = sub.add_parser("job").add_subparsers(dest="operation", required=True)
    task_args(jobs.add_parser("submit"))
    jobs.add_parser("list")
    get = jobs.add_parser("get")
    get.add_argument("id")
    get.add_argument("--result-only", action="store_true")
    wait = jobs.add_parser("wait", help="Wait for another worker; does not execute jobs")
    wait.add_argument("id")
    wait.add_argument("--seconds", type=float, default=60)
    for op in ["retry", "cancel"]:
        jobs.add_parser(op).add_argument("id")
    work = sub.add_parser("work", help="Keep processing the queue; Ctrl-C stops this worker")
    work.add_argument("--once", action="store_true")
    work.add_argument("--drain", action="store_true", help="Exit when no task is runnable")
    work.add_argument("--poll", type=float, default=5, help="Idle polling seconds (1..30)")
    run = sub.add_parser("run", help="Submit and run; returns the persisted job if wait time expires")
    task_args(run)
    run.add_argument("--wait-seconds", type=float, default=60)
    return p


def submit(store, args):
    prompt = args.prompt
    if args.prompt_file:
        prompt = sys.stdin.read() if args.prompt_file == "-" else Path(args.prompt_file).read_text(encoding="utf-8")
    return store.submit(prompt, args.cwd, args.provider, args.profile, args.model, args.bucket,
                        args.allow_edits, args.key, args.timeout, args.max_attempts)


def quotas(store, name=None):
    result = []
    now = time.time()
    for p in store.profiles():
        if name and p["name"] != name:
            continue
        windows = store.windows(p["name"])
        state = availability(windows, now, bucket="codex" if p["provider"] == "codex" else None)
        state["weekly_reset"] = None if state["weekly_reset"] == float("inf") else state["weekly_reset"]
        result.append({**p, "windows": windows, "availability": state,
                       "quota_known": bool(windows)})
    if name:
        store.profile(name)
    return result


def dispatch(store, args):
    if args.action == "desktop":
        installed = Path.home() / "Applications/Agent Pool.app"
        if sys.platform == "darwin" and installed.is_dir():
            subprocess.Popen(["open", str(installed), "--args", "--home", str(store.home)])
            emit({"desktop": "opened", "home": str(store.home)})
            return 0
        try:
            from .desktop import main as desktop_main
        except ImportError as exc:
            raise ValueError("Desktop needs Python with Tk, or the packaged Agent Pool desktop app") from exc
        return desktop_main(["--home", str(store.home)])
    elif args.action == "init":
        existing = {p["name"] for p in store.profiles()}
        for provider, names in [("codex", ["codex-1", "codex-2", "codex-3"]), ("claude", ["claude-1"])]:
            for name in names:
                if name not in existing:
                    store.add_profile(name, provider, provider)
        emit({"home": str(store.home), "profiles": store.profiles(), "next": "agent-pool login codex-1"})
    elif args.action == "doctor":
        checks = []
        for provider in ("codex", "claude"):
            names = {p["binary"] for p in store.profiles() if p["provider"] == provider} or {provider}
            for binary in sorted(names):
                try:
                    path = executable(binary)
                    result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
                    checks.append({"provider": provider, "path": path, "version": result.stdout.strip(), "ok": result.returncode == 0})
                except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                    checks.append({"provider": provider, "ok": False, "error": str(exc)})
        emit({"python": sys.version.split()[0], "platform": sys.platform, "home": str(store.home), "checks": checks})
    elif args.action == "profile":
        if args.operation == "add":
            store.add_profile(args.name, args.provider, args.binary or args.provider)
        elif args.operation in {"enable", "disable", "release"}:
            with store.worker_lock():
                if args.operation == "release":
                    store.update_profile(args.name, hold_until=None, hold_reason=None)
                else:
                    store.update_profile(args.name, enabled=args.operation == "enable")
        emit(store.profiles())
    elif args.action == "login":
        with store.worker_lock():
            profile = store.profile(args.name)
            native = executable(profile["binary"])
            command = [native, "login"] if profile["provider"] == "codex" else [native, "auth", "login", "--claudeai"]
            code = subprocess.call(command, env=environment(profile["provider"], store.authdir(args.name)))
            if code:
                raise ValueError(f"Native login failed (exit {code}); profile was not enabled")
            store.update_profile(args.name, enabled=True, hold_until=None, hold_reason=None, observed_at=None, checked_at=None)
        emit({"profile": args.name, "enabled": True})
    elif args.action == "quota":
        if args.operation == "refresh":
            with store.worker_lock():
                profiles = [store.profile(args.name)] if args.name else store.profiles()
                for profile in profiles:
                    if profile["provider"] == "codex":
                        refresh(store, profile)
        elif args.operation == "set":
            with store.worker_lock():
                p = store.profile(args.name)
                reset = timestamp(args.reset_at)
                if reset <= time.time():
                    raise ValueError("Manual reset must be in the future")
                minutes = 300 if args.window == "five-hour" else 10080
                bucket = args.bucket if p["provider"] == "codex" else "claude"
                key = f"{bucket}:primary" if minutes == 300 else f"{bucket}:secondary"
                if p["provider"] == "claude":
                    key = "five_hour" if minutes == 300 else "seven_day" + ("_" + args.model if args.model else "")
                store.set_windows(args.name, [{"key": key, "bucket": bucket, "minutes": minutes,
                                              "used": args.used, "reset": reset, "model": args.model}])
                # A user observation makes a formerly unknown reset known.
                if p["hold_reason"] == "quota_reset_unknown":
                    store.update_profile(args.name, hold_until=None, hold_reason=None)
        emit(quotas(store, getattr(args, "name", None)))
    elif args.action == "job":
        if args.operation == "submit":
            emit(summary(submit(store, args)))
        elif args.operation == "list":
            emit([summary(j) for j in store.jobs()])
        elif args.operation in {"get", "wait"}:
            deadline = time.monotonic() + max(0, getattr(args, "seconds", 0))
            job = store.job(args.id)
            while args.operation == "wait" and job["status"] not in TERMINAL and time.monotonic() < deadline:
                time.sleep(min(1, max(0, deadline - time.monotonic())))
                job = store.job(args.id)
            if getattr(args, "result_only", False):
                if job["status"] != "succeeded":
                    raise ValueError("Job has not succeeded: " + job["status"])
                print(job["result"])
            else:
                emit({**summary(job), "result": job["result"]})
            return 0 if job["status"] == "succeeded" else 1 if job["status"] in TERMINAL else 2
        else:
            with store.worker_lock():
                job = store.job(args.id)
                if job["status"] == "running":
                    raise ValueError("Recover the stopped worker first with `work --once`")
                if args.operation == "retry":
                    if job["status"] not in {"failed", "needs_review", "cancelled"}:
                        raise ValueError("Only a stopped terminal job can be retried")
                    store.update_job(args.id, status="queued", attempts=0, result=None, error=None)
                else:
                    if job["status"] not in {"queued", "waiting"}:
                        raise ValueError("Only queued or waiting jobs can be cancelled")
                    store.update_job(args.id, status="cancelled", error="Cancelled by user")
            emit(summary(store.job(args.id)))
    elif args.action in {"work", "run"}:
        if args.action == "run" and (not math.isfinite(args.wait_seconds) or args.wait_seconds < 0):
            raise ValueError("Wait time cannot be negative")
        job = submit(store, args) if args.action == "run" else None
        deadline = time.monotonic() + args.wait_seconds if job else None
        with ExitStack() as resources:
            try:
                resources.enter_context(store.worker_lock())
            except WorkerBusy:
                if not job:
                    raise
                current = store.job(job["id"])
                while current["status"] not in TERMINAL and time.monotonic() < deadline:
                    time.sleep(min(1, max(0, deadline - time.monotonic())))
                    current = store.job(job["id"])
                emit({**summary(current), "result": current["result"]})
                return 0 if current["status"] == "succeeded" else 1 if current["status"] in TERMINAL else 2
            recovered = store.recover()
            if recovered:
                print(f"Recovered {recovered} interrupted job(s) as needs_review", file=sys.stderr)
            while True:
                if job:
                    current = store.job(job["id"])
                    if current["status"] in TERMINAL or time.monotonic() >= deadline:
                        emit({**summary(current), "result": current["result"]})
                        return 0 if current["status"] == "succeeded" else 1 if current["status"] in TERMINAL else 2
                did_work = tick(store)
                if args.action == "work":
                    if args.once or (args.drain and not did_work):
                        emit({"processed": did_work, "jobs": [summary(j) for j in store.jobs()]})
                        return 0
                if not did_work:
                    pause = min(30, max(1, getattr(args, "poll", 2)))
                    if deadline:
                        pause = min(pause, max(0, deadline - time.monotonic()))
                    time.sleep(pause)
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    store = None
    try:
        store = Store(args.home)
        return dispatch(store, args)
    except (ValueError, OSError, sqlite3.Error) as exc:
        emit({"error": redact(str(exc))})
        return 1
    except KeyboardInterrupt:
        print("Worker stopped; queued jobs remain persisted.", file=sys.stderr)
        return 130
    finally:
        if store:
            store.close()
