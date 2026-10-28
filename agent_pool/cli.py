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
from .store import Store, WorkerBusy, default_home, file_lock
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
    place = p.add_mutually_exclusive_group()
    place.add_argument("--cwd", help="Local working directory")
    place.add_argument("--workspace", help="Registered workspace on the executing server")
    text = p.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", help="UTF-8 file, or - for stdin")
    p.add_argument("--allow-edits", action="store_true", help="Allow native file editing in cwd")
    p.add_argument("--key", help="Idempotency key, reusable only for the identical task")
    p.add_argument("--timeout", type=float, default=1800, help="Per-attempt CLI timeout in seconds")
    p.add_argument("--max-attempts", type=int, default=6)


def parser():
    p = argparse.ArgumentParser(prog="agent-fleet", description="Local durable job broker for native Codex and Claude Code")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--home", type=Path, default=default_home(), help="Local state directory; keep it off shared/sync drives")
    p.add_argument("--remote", help="Execute against a configured SSH remote")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("init", help="Create three disabled Codex profiles and one disabled Claude profile")
    sub.add_parser("rpc", help="Internal versioned SSH endpoint")
    auth = sub.add_parser("auth", help="Native browser login sessions without a terminal").add_subparsers(dest="operation", required=True)
    ast = auth.add_parser("start")
    ast.add_argument("name")
    ast.add_argument("--provider", choices=["codex", "claude"], required=True)
    ast.add_argument("--key", required=True, help="Stable UUID hex for this login attempt")
    for op in ("get", "cancel"):
        auth.add_parser(op).add_argument("id")
    ain = auth.add_parser("input")
    ain.add_argument("id")
    code = ain.add_mutually_exclusive_group(required=True)
    code.add_argument("--code")
    code.add_argument("--code-file", help="UTF-8 file or - for stdin; keeps code off the command line")
    status = sub.add_parser("status", help="Worker heartbeat and account snapshot")
    status.add_argument("--refresh", action="store_true")
    monitor = sub.add_parser("monitor", help="Read account metadata without inference")
    monitor.add_argument("--refresh", action="store_true")
    workspace = sub.add_parser("workspace").add_subparsers(dest="operation", required=True)
    workspace.add_parser("list")
    wa = workspace.add_parser("add")
    wa.add_argument("name")
    wa.add_argument("--path", required=True)
    wd = workspace.add_parser("remove")
    wd.add_argument("name")
    service = sub.add_parser("service", help="Generate a Linux systemd user unit; does not install it")
    service.add_argument("--exec", dest="exec_path", required=True, help="Absolute installed agent-fleet executable")
    remote = sub.add_parser("remote").add_subparsers(dest="operation", required=True)
    remote.add_parser("list")
    ra = remote.add_parser("add")
    ra.add_argument("name")
    ra.add_argument("--host", required=True, help="SSH alias or user@host")
    ra.add_argument("--command", default="agent-fleet", help="Installed executable on Linux")
    ra.add_argument("--server-home", required=True, help="Absolute state directory on Linux")
    for op in ("remove", "test"):
        remote.add_parser(op).add_argument("name")
    sub.add_parser("connection-info", help="Discover the installed executable and server state")
    sub.add_parser("doctor", help="Check installed native CLI executables; no inference requests")
    sub.add_parser("desktop", help="Open the native account and quota monitor")
    profiles = sub.add_parser("profile").add_subparsers(dest="operation", required=True)
    add = profiles.add_parser("add")
    add.add_argument("name")
    add.add_argument("--provider", choices=["codex", "claude"], required=True)
    add.add_argument("--binary", help="Native CLI executable or absolute path")
    add.add_argument("--auth-home", help="Attach an existing native account directory on this machine; no credential copy")
    profiles.add_parser("list")
    for op in ["enable", "disable", "release"]:
        profiles.add_parser(op).add_argument("name")
    login = sub.add_parser("login", help="Run the provider's own interactive browser sign-in in an isolated profile")
    login.add_argument("name")
    login.add_argument("--device-auth", action="store_true", help="Codex headless device sign-in")
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
        operation = jobs.add_parser(op)
        operation.add_argument("id")
        if op == "retry":
            operation.add_argument("--acknowledge-review", action="store_true", help="Confirm that a needs_review workspace was inspected")
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
    cwd = store.workspace(args.workspace) if args.workspace else (args.cwd or os.getcwd())
    return store.submit(prompt, cwd, args.provider, args.profile, args.model, args.bucket,
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


def launch_desktop(home, remote=None):
    args = ["--home", str(home)]
    if remote:
        args += ["--remote", remote]
    installed = next((candidate for candidate in [
        Path.home() / "Applications/Agent Fleet.app",
        Path.home() / "Applications/Agent Pool.app",
    ] if candidate.is_dir()), None)
    if sys.platform == "darwin" and installed is not None:
        subprocess.Popen(["open", "-n", str(installed), "--args", *args])
        emit({"desktop": "opened", "home": str(home), "remote": remote})
        return 0
    try:
        from .desktop import main as desktop_main
    except ImportError as exc:
        raise ValueError("Desktop needs Python with Tk, or the packaged Agent Fleet desktop app") from exc
    return desktop_main(args)


def dispatch(store, args):
    if args.action == "connection-info":
        launch = str(Path(sys.executable).resolve()) if getattr(sys, "frozen", False) else str(Path(sys.argv[0]).resolve())
        emit({"version": __version__, "command": launch, "home": str(store.home), "features": ["native-login-sessions", "cached-status"]})
    elif args.action == "auth":
        from . import login_sessions
        if args.operation == "start":
            emit(login_sessions.start(store.home, args.name, args.provider, args.key))
        elif args.operation == "get":
            emit(login_sessions.status(store.home, args.id))
        elif args.operation == "cancel":
            emit(login_sessions.cancel(store.home, args.id))
        else:
            code = args.code
            if args.code_file:
                code = sys.stdin.read() if args.code_file == "-" else Path(args.code_file).read_text(encoding="utf-8")
            emit(login_sessions.provide_code(store.home, args.id, code))
    elif args.action == "status":
        from .monitor import collect, snapshot
        from .runtime import worker_state
        accounts = collect(store.home, include_default=False) if args.refresh else snapshot(store.home, include_default=False)
        count = store.db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','waiting','running')").fetchone()[0]
        emit({"worker": worker_state(store.home), "accounts": accounts, "pending_jobs": count,
              "features": ["native-login-sessions", "cached-status"], "version": __version__})
    elif args.action == "monitor":
        from .monitor import collect, snapshot
        emit(collect(store.home, include_default=False) if args.refresh else snapshot(store.home, include_default=False))
    elif args.action == "workspace":
        if args.operation == "add":
            store.add_workspace(args.name, args.path)
        elif args.operation == "remove":
            with store.db:
                store.db.execute("DELETE FROM workspaces WHERE name=?", (args.name,))
        emit(store.workspaces())
    elif args.action == "service":
        from .service import unit
        print(unit(args.exec_path, store.home))
    elif args.action == "remote":
        from .remote import RemoteConfig, RemoteClient
        config = RemoteConfig(store.home)
        if args.operation == "add":
            config.add(args.name, args.host, args.command, args.server_home)
        elif args.operation == "remove":
            config.remove(args.name)
        elif args.operation == "test":
            result = RemoteClient(config.get(args.name)).request(["doctor"])
            print(result["output"], end="")
            return result["code"]
        emit(config.all())
    elif args.action == "desktop":
        return launch_desktop(store.home)
    elif args.action == "init":
        existing = {p["name"] for p in store.profiles()}
        for provider, names in [("codex", ["codex-1", "codex-2", "codex-3"]), ("claude", ["claude-1"])]:
            for name in names:
                if name not in existing:
                    store.add_profile(name, provider, provider)
        emit({"home": str(store.home), "profiles": store.profiles(), "next": "agent-fleet login codex-1"})
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
            store.add_profile(args.name, args.provider, args.binary or args.provider, auth_home=args.auth_home)
        elif args.operation in {"enable", "disable", "release"}:
            if args.operation == "release":
                store.update_profile(args.name, hold_until=None, hold_reason=None)
            else:
                store.update_profile(args.name, enabled=args.operation == "enable")
        emit(store.profiles())
    elif args.action == "login":
        with file_lock(store.authdir(args.name) / ".native.lock"):
            profile = store.profile(args.name)
            native = executable(profile["binary"])
            command = [native, "login"] if profile["provider"] == "codex" else [native, "auth", "login", "--claudeai"]
            if args.device_auth:
                if profile["provider"] != "codex":
                    raise ValueError("--device-auth is supported by Codex only")
                command.append("--device-auth")
            code = subprocess.call(command, env=environment(profile["provider"], store.authdir(args.name)))
            if code:
                raise ValueError(f"Native login failed (exit {code}); profile was not enabled")
            store.update_profile(args.name, enabled=True, hold_until=None, hold_reason=None, observed_at=None, checked_at=None)
        emit({"profile": args.name, "enabled": True})
    elif args.action == "quota":
        if args.operation == "refresh":
            profiles = [store.profile(args.name)] if args.name else store.profiles()
            for profile in profiles:
                if profile["provider"] == "codex":
                    refresh(store, profile)
        elif args.operation == "set":
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
            job = store.job(args.id)
            if job["status"] == "running":
                raise ValueError("Job is running; inspect its status. Only the server administrator should recover a stopped worker")
            if args.operation == "retry":
                if job["status"] not in {"failed", "needs_review", "cancelled"}:
                    raise ValueError("Only a stopped terminal job can be retried")
                if not store.transition_job(args.id, ("failed", "needs_review", "cancelled"), status="queued", attempts=0, result=None, error=None):
                    raise ValueError("Job changed before retry; reload it")
            else:
                if job["status"] not in {"queued", "waiting"}:
                    raise ValueError("Only queued or waiting jobs can be cancelled")
                if not store.transition_job(args.id, ("queued", "waiting"), status="cancelled", error="Cancelled by user"):
                    raise ValueError("Job already started; running tasks cannot be cancelled")
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
            from .runtime import heartbeat
            resources.enter_context(heartbeat(store.home))
            next_monitor = 0
            recovered = store.recover()
            if recovered:
                print(f"Recovered {recovered} interrupted job(s) as needs_review", file=sys.stderr)
            while True:
                if job:
                    current = store.job(job["id"])
                    if current["status"] in TERMINAL or time.monotonic() >= deadline:
                        emit({**summary(current), "result": current["result"]})
                        return 0 if current["status"] == "succeeded" else 1 if current["status"] in TERMINAL else 2
                if args.action == "work" and time.monotonic() >= next_monitor:
                    from .monitor import collect
                    collect(store.home, include_default=False)
                    next_monitor = time.monotonic() + 60
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
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "--login-cancel":
        if len(raw) != 4:return 1
        from .login_sessions import run_cancel
        return run_cancel(Path(raw[1]), raw[2], raw[3])
    if raw and raw[0] == "--login-worker":
        if len(raw) != 3:
            return 1
        from .login_sessions import run_worker
        return run_worker(Path(raw[1]), raw[2])
    args = parser().parse_args(raw)
    store = None
    previous_term = None
    if args.action in {"work", "run"}:
        import signal, threading
        if threading.current_thread() is threading.main_thread():
            previous_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.action == "rpc":
            from .rpc import serve
            return serve(args.home)
        if args.remote:
            from .remote import dispatch_remote
            return dispatch_remote(args)
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
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
