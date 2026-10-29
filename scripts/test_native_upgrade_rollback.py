#!/usr/bin/env python3
"""Opt-in pending-work programme handover acceptance in one newly created private pool."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("old-executable", "new-executable", "provider-executable", "scratch-root", "old-sha256", "new-sha256"):
        result.add_argument("--" + name, required=True)
    result.add_argument("--old-version", default="0.4.2")
    result.add_argument("--new-version", default="0.5.0")
    result.add_argument("--validate-only", action="store_true", help="Check inputs/versions without creating the scratch pool")
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def isolated_environment(root):
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "AGENT_POOL_HOME", "PYTHONPATH"):
        env.pop(name, None)
    env.update(PYTHONNOUSERSITE="1", HOME=str(root / "user"), CODEX_HOME=str(root / "user/.codex"),
               CLAUDE_CONFIG_DIR=str(root / "user/.claude"), XDG_CONFIG_HOME=str(root / "user/.config"))
    return env


def validate(args):
    raw_root = Path(args.scratch_root)
    require(raw_root.is_absolute(), "Scratch root must be absolute")
    require(raw_root.name.startswith("native-upgrade-rollback."), "Scratch root must use the native-upgrade-rollback. prefix")
    require(not raw_root.exists() and not raw_root.is_symlink(), "Scratch root must not already exist")
    parent = raw_root.parent.resolve(strict=True)
    require(parent.is_dir(), "Scratch parent must be an existing directory")
    root = parent / raw_root.name
    # A new directory inside an existing pool is still the wrong place for faults.
    for ancestor in (parent, *parent.parents):
        require(not (ancestor / "queue.sqlite3").exists() and not (ancestor / "worker.lock").exists(),
                "Scratch root must not be inside an existing pool")
    programs = {}
    for role in ("old", "new", "provider"):
        path = Path(getattr(args, role + "_executable"))
        require(path.is_absolute(), role + " executable must be absolute")
        path = path.resolve(strict=True)
        require(path.is_file() and os.access(path, os.X_OK), role + " executable must be an executable file")
        programs[role] = path
    require(programs["old"] != programs["new"], "Old and new executables must be distinct")
    for role in ("old", "new"):
        expected = getattr(args, role + "_sha256").lower()
        require(re.fullmatch(r"[0-9a-f]{64}", expected), role + " SHA-256 must have 64 hex digits")
        require(digest(programs[role]) == expected, role + " executable SHA-256 mismatch")
    require(args.old_sha256.lower() != args.new_sha256.lower(), "Old and new executable hashes must differ")
    hashes = {"old": args.old_sha256.lower(), "new": args.new_sha256.lower(),
              "provider": digest(programs["provider"])}
    versions = {}
    for role in ("old", "new"):
        done = subprocess.run([str(programs[role]), "--home", str(root / "pool"), "--version"],
                              env=isolated_environment(root), text=True, capture_output=True, timeout=10)
        expected = getattr(args, role + "_version")
        require(done.returncode == 0 and done.stdout.strip() == expected,
                role + " executable did not report expected version " + expected)
        versions[role] = expected
    fixture = subprocess.run([str(programs["provider"]), "--version"], env=isolated_environment(root),
                             text=True, capture_output=True, timeout=10)
    require(fixture.returncode == 0 and fixture.stdout.strip() == "controlled-native-provider-0.5",
            "Provider must be the compiled controlled-native-provider-0.5 fixture")
    return root, programs, versions, hashes


class Handover:
    def __init__(self, root, programs, versions, hashes):
        # mkdir is deliberately non-recursive/exclusive after validation; no reuse.
        root.mkdir(mode=0o700)
        self.root = root
        self.pool = root / "pool"
        self.workspace = root / "work"
        self.workspace.mkdir(mode=0o700)
        (root / "user").mkdir(mode=0o700)
        self.env = isolated_environment(root)
        self.active = root / "active-programme"
        self.programs = dict(programs)
        provider = root / "controlled-provider"
        shutil.copy2(programs["provider"], provider)
        provider.chmod(0o700)
        require(digest(provider) == hashes["provider"], "Controlled provider changed after validation")
        self.programs["provider"] = provider
        self.versions = versions
        self.children = []
        self.logs = []
        self.checks = []
        self.jobs = {}
        self.report = {
            "schema_version": 1, "passed": False,
            "scope": "isolated pending-work controlled-provider CLI handover; no active-job transition, production state or real inference",
            "versions": versions, "programme_sha256": hashes,
            "checks": self.checks, "worker_stops": [], "phases": [],
        }

    def check(self, condition, name):
        require(condition, name)
        self.checks.append(name)

    def switch(self, role):
        require(not any(child.poll() is None for child in self.children), "Cannot switch while an owned worker is running")
        staged = self.root / "programme.staged"
        shutil.copy2(self.programs[role], staged)
        staged.chmod(0o700)
        require(digest(staged) == self.report["programme_sha256"][role], "Staged programme hash changed")
        os.replace(staged, self.active)
        value = self.raw("--version")
        require(value.stdout.strip() == self.versions[role], "Active programme version mismatch")
        self.report["phases"].append({"programme": role, "version": self.versions[role], "sha256": digest(self.active)})

    def raw(self, *argv, codes=(0,), timeout=30, input=None):
        command = [str(self.active), "--home", str(self.pool), *argv]
        child = subprocess.Popen(command, env=self.env, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
        self.children.append(child)
        try:
            stdout, stderr = child.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate(timeout=3)
            raise
        done = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        require(done.returncode in codes, "CLI command failed: " + " ".join(argv[:2]) + " (exit " + str(done.returncode) + ") " + done.stderr[-600:])
        return done

    def call(self, *argv, codes=(0,), timeout=30):
        done = self.raw(*argv, codes=codes, timeout=timeout)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def job(self, ident):
        return self.call("job", "get", ident, codes=(0, 1, 2))

    def inventory(self):
        rows = self.call("job", "list")
        return {row["id"]: self.job(row["id"]) for row in rows}

    def rpc_job(self, ident):
        done = self.raw("rpc", input=json.dumps({"version": 1, "argv": ["job", "get", ident]}))
        envelope = json.loads(done.stdout)
        require(envelope["code"] in (0, 1, 2), "RPC job read failed")
        return json.loads(envelope["output"])

    def identities(self):
        return [{key: row.get(key) for key in ("name", "provider", "binary", "enabled", "auth_home")}
                for row in self.call("profile", "list")]

    def auth_inventory(self):
        result = {}
        for name in ("runner", "blocked"):
            directory = self.root / "auth" / name
            info = directory.stat()
            result[name] = {"inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode),
                            "sentinel_sha256": digest(directory / "sentinel")}
        return result

    def submit(self, label, profile="runner", prompt=None, timeout=15):
        prompt = label if prompt is None else prompt
        argv = ["job", "submit", "--provider", "codex", "--profile", profile, "--workspace", "fixture",
                "--prompt", prompt, "--key", label, "--timeout", str(timeout), "--max-attempts", "3"]
        reply = self.call(*argv)
        self.jobs[label] = {"id": reply["id"], "argv": argv, "prompt": prompt}
        return reply["id"]

    def windows(self, blocked):
        reset = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        # Both the public observation and controlled native probe see the same state.
        info = {"rateLimits": {"primary": {"usedPercent": 10, "windowDurationMins": 300,
                                           "resetsAt": time.time() + 1800},
                               "secondary": {"usedPercent": 100 if blocked else 10,
                                             "windowDurationMins": 10080, "resetsAt": time.time() + 86400}}}
        (self.root / "auth/blocked/fixture-ratelimits.json").write_text(json.dumps(info))
        self.call("quota", "set", "blocked", "--window", "weekly", "--used", "100" if blocked else "10", "--reset-at", reset)

    def start_worker(self, label):
        log = (self.root / (label + ".log")).open("w")
        self.logs.append(log)
        child = subprocess.Popen([str(self.active), "--home", str(self.pool), "work", "--poll", "1"],
                                 env=self.env, stdout=log, stderr=log, start_new_session=True)
        self.children.append(child)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            require(child.poll() is None, "Owned worker exited before heartbeat")
            state = self.call("status")["worker"]
            if state.get("online") and state.get("pid") == child.pid:
                return child
            time.sleep(.05)
        raise ValueError("Owned worker did not publish a fresh heartbeat")

    def stop_worker(self, child, role):
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)
        try:
            code = child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            # Only our process group, never a service or another user's worker.
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
            raise ValueError("Owned worker did not stop gracefully")
        self.check(code in (0, 130, -signal.SIGTERM, 128 + signal.SIGTERM), role + " worker stopped with an expected signal status")
        self.report["worker_stops"].append({"programme": role, "exit_code": code})

    def check_lease(self, contender, label):
        # A live owner may refresh waiting-row timestamps; durable work must not change.
        before = self.lease_inventory()
        done = subprocess.run([str(self.programs[contender]), "--home", str(self.pool), "work", "--once"],
                              env=self.env, text=True, capture_output=True, timeout=10)
        self.check(done.returncode == 1 and "worker" in (done.stderr + done.stdout).lower(), label + " rejects a second worker")
        self.check(self.lease_inventory() == before, label + " retains jobs while another runtime owns the lease")

    def lease_inventory(self):
        return {ident: {key: value for key, value in job.items() if key != "updated"}
                for ident, job in self.inventory().items()}

    def check_timeout_child(self):
        child_file = self.root / "auth/runner/fixture-child.pid"
        require(child_file.is_file(), "Controlled timeout did not create its descendant marker")
        pid = int(child_file.read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            done = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], text=True, capture_output=True, timeout=3)
            if not done.stdout.strip() or done.stdout.strip().startswith("Z"):
                self.check(True, "Old worker timeout reaped its controlled descendant")
                return
            time.sleep(.05)
        raise ValueError("Controlled timeout descendant remains active")

    def run(self):
        self.switch("old")
        self.call("workspace", "add", "fixture", "--path", str(self.workspace))
        for name in ("runner", "blocked"):
            auth = self.root / "auth" / name
            auth.mkdir(mode=0o700, parents=True)
            (auth / "sentinel").write_text("controlled attached account; not a credential")
            (auth / "fixture-accepted").write_text("controlled fixture only")
            self.call("profile", "add", name, "--provider", "codex", "--binary", str(self.programs["provider"]), "--auth-home", str(auth))
            self.call("profile", "enable", name)
        self.windows(blocked=True)
        self.submit("completed-before-upgrade")
        self.call("work", "--once")
        self.submit("uncertain-before-upgrade", prompt="__timeout__", timeout=.4)
        self.call("work", "--once")
        self.check_timeout_child()
        self.submit("waiting-across-upgrade", profile="blocked")
        self.call("work", "--once")
        self.submit("queued-across-upgrade")
        baseline = self.inventory()
        wanted = {"completed-before-upgrade": "succeeded", "uncertain-before-upgrade": "needs_review",
                  "waiting-across-upgrade": "waiting", "queued-across-upgrade": "queued"}
        self.check(all(baseline[self.jobs[label]["id"]]["status"] == status for label, status in wanted.items()),
                   "Old programme created all four required durable states")
        profiles = self.identities()
        auth = self.auth_inventory()
        completed = self.jobs["completed-before-upgrade"]["id"]
        self.check(self.rpc_job(completed) == baseline[completed], "Old RPC v1 exposes the completed result before upgrade")
        self.switch("new")
        self.check(self.inventory() == baseline, "Native programme reads every old job field/result unchanged")
        self.check(self.rpc_job(completed) == baseline[completed], "Native RPC v1 retains the old completed job/result")
        self.check(self.identities() == profiles and self.auth_inventory() == auth, "Native programme retains attached profile identities and directory sentinels")
        queued = self.jobs["queued-across-upgrade"]
        self.check(self.call(*queued["argv"])["id"] == queued["id"], "Native identical retry retains the old job ID")
        self.call("work", "--drain")
        after_native = self.inventory()
        self.check(after_native[queued["id"]]["status"] == "succeeded" and after_native[queued["id"]]["attempts"] == 1,
                   "Native worker executes queued old work exactly once")
        for label in ("completed-before-upgrade", "uncertain-before-upgrade"):
            ident = self.jobs[label]["id"]
            self.check(after_native[ident] == baseline[ident], "Native worker preserves " + label)
        waiting = self.jobs["waiting-across-upgrade"]["id"]
        self.check(after_native[waiting]["status"] == "waiting" and after_native[waiting]["attempts"] == 0,
                   "Native worker retains quota-waiting work without an execution")
        new_worker = self.start_worker("native-idle")
        self.check_lease("old", "Native lease")
        self.stop_worker(new_worker, "native")
        self.submit("queued-across-rollback")
        before_rollback = self.inventory()
        self.switch("old")
        self.check(self.inventory() == before_rollback, "Programme-only rollback retains every pending job/result without DB restore")
        self.check(self.rpc_job(queued["id"]) == before_rollback[queued["id"]], "Old RPC v1 reads the result written by the native worker")
        self.check(self.identities() == profiles and self.auth_inventory() == auth, "Rollback retains attached profile mappings and sentinels without re-login")
        self.check(self.call(*queued["argv"])["id"] == queued["id"], "Old identical retry retains the native-completed job ID")
        # Keep ready work behind the old worker lease check by disabling only the fixture profile.
        self.call("profile", "disable", "runner")
        old_worker = self.start_worker("old-idle")
        deadline = time.monotonic() + 10
        queued_rollback = self.jobs["queued-across-rollback"]["id"]
        while self.job(queued_rollback)["status"] == "queued" and time.monotonic() < deadline:
            time.sleep(.05)
        self.check(self.job(queued_rollback)["status"] == "waiting", "Old idle worker observes the disabled fixture before lease comparison")
        self.check_lease("new", "Old lease")
        self.stop_worker(old_worker, "old")
        self.call("profile", "enable", "runner")
        self.windows(blocked=False)
        self.call("work", "--drain")
        final = self.inventory()
        review = self.jobs["uncertain-before-upgrade"]["id"]
        self.check(final[review] == baseline[review], "Rollback never replays needs_review work")
        self.check(set(final) == {value["id"] for value in self.jobs.values()}, "All five durable IDs survive upgrade and rollback")
        for label, item in self.jobs.items():
            if label != "uncertain-before-upgrade":
                job = final[item["id"]]
                self.check(job["status"] == "succeeded" and job["attempts"] == 1 and job["result"] == "read-only: " + item["prompt"],
                           "Final result and one attempt retained for " + label)
        trace = []
        for name in ("runner", "blocked"):
            path = self.root / "auth" / name / "fixture-executions.jsonl"
            if path.exists():
                trace.extend(json.loads(line)["prompt"] for line in path.read_text().splitlines())
        self.check(Counter(trace) == Counter(value["prompt"] for value in self.jobs.values()),
                   "Controlled invocation inventory contains each job once including the quarantined timeout")
        self.check(self.identities() == profiles and self.auth_inventory() == auth, "Final profile identities/auth sentinels remain intact")
        self.report.update(passed=True, job_count=len(final), invocation_count=len(trace),
                           terminal_counts=dict(Counter(job["status"] for job in final.values())),
                           identities_preserved=True, uncertain_replayed=False, database_restored=False)
        return self.report

    def close(self):
        for child in self.children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=3)
        # Only known controlled-fixture children in our workspace may be reaped.
        for marker in (self.root / "auth").glob("*/fixture-*.pid"):
            try:
                pid = int(marker.read_text())
                proc = Path("/proc") / str(pid)
                if ((proc / "exe").resolve(strict=True) == self.programs["provider"]
                        and (proc / "cwd").resolve(strict=True) == self.workspace):
                    os.kill(pid, signal.SIGTERM)
            except (ValueError, FileNotFoundError, ProcessLookupError, PermissionError):
                pass
        for log in self.logs:
            log.close()


def main():
    args = parser().parse_args()
    handover = None
    try:
        root, programs, versions, hashes = validate(args)
        if args.validate_only:
            print(json.dumps({"mode": "preflight", "versions": versions, "programme_sha256": hashes}))
            return 0
        handover = Handover(root, programs, versions, hashes)
        try:
            report = handover.run()
        finally:
            handover.close()
            (root / "report.json").write_text(json.dumps(handover.report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        if handover is not None:
            handover.report["error"] = str(exc)
            (handover.root / "report.json").write_text(json.dumps(handover.report, indent=2, sort_keys=True) + "\n")
        print("Upgrade/rollback acceptance failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
