"""Local-only durable queue; SQLite state must not be stored on network/sync drives."""
import json
import math
import os
import re
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def default_home():
    if os.environ.get("AGENT_POOL_HOME"):
        return Path(os.environ["AGENT_POOL_HOME"]).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "AgentPool"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/AgentPool"
    return Path.home() / ".local/share/agent-pool"


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


class WorkerBusy(ValueError):
    pass


class Store:
    def __init__(self, home):
        self.home = Path(home).expanduser().resolve()
        private_dir(self.home)
        self.db = sqlite3.connect(self.home / "queue.sqlite3", timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS profiles (
          name TEXT PRIMARY KEY, provider TEXT NOT NULL, binary TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0, last_used REAL NOT NULL DEFAULT 0,
          hold_until REAL, hold_reason TEXT, observed_at REAL, checked_at REAL, quota_error TEXT);
        CREATE TABLE IF NOT EXISTS windows (
          profile TEXT NOT NULL, key TEXT NOT NULL, data TEXT NOT NULL,
          PRIMARY KEY(profile,key));
        CREATE TABLE IF NOT EXISTS monitor_cache (
          source TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, prompt TEXT NOT NULL,
          cwd TEXT NOT NULL, provider TEXT NOT NULL, profile TEXT, model TEXT,
          bucket TEXT, allow_edits INTEGER NOT NULL, status TEXT NOT NULL,
          created REAL NOT NULL, updated REAL NOT NULL, chosen_profile TEXT,
          attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
          timeout REAL NOT NULL, result TEXT, error TEXT);
        ''')
        self.db.commit()
        if os.name != "nt":
            (self.home / "queue.sqlite3").chmod(0o600)

    def close(self):
        self.db.close()

    def profiles(self):
        return [dict(x) for x in self.db.execute("SELECT * FROM profiles ORDER BY name")]

    def profile(self, name):
        row = self.db.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown profile: {name}")
        return dict(row)

    def authdir(self, name):
        self.profile(name)
        path = self.home / "profiles" / name
        private_dir(path)
        return path

    def add_profile(self, name, provider, binary):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name):
            raise ValueError("Profile name: lowercase letters, digits and hyphens; start with a letter")
        if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}:
            raise ValueError("Reserved Windows profile name")
        if provider not in {"codex", "claude"}:
            raise ValueError("Provider must be codex or claude")
        with self.db:
            self.db.execute("INSERT INTO profiles(name,provider,binary) VALUES(?,?,?)",
                            (name, provider, binary))
        self.authdir(name)

    def update_profile(self, name, **values):
        self.profile(name)
        allowed = {"enabled", "last_used", "hold_until", "hold_reason", "observed_at", "checked_at", "quota_error"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid profile update")
        with self.db:
            self.db.execute("UPDATE profiles SET " + ",".join(f"{k}=?" for k in values) + " WHERE name=?",
                            (*values.values(), name))

    def windows(self, name):
        return [json.loads(x[0]) for x in self.db.execute("SELECT data FROM windows WHERE profile=?", (name,))]

    def set_windows(self, name, windows, replace=False):
        self.profile(name)
        with self.db:
            if replace:
                self.db.execute("DELETE FROM windows WHERE profile=?", (name,))
            for w in windows:
                used, reset = w.get("used"), w.get("reset")
                if used is not None and (not isinstance(used, (int, float)) or not 0 <= used <= 100):
                    raise ValueError("Quota used must be a percentage from 0 to 100")
                if reset is not None and (not isinstance(reset, (int, float)) or not 0 < reset < 1e12):
                    raise ValueError("Reset must be a Unix timestamp in seconds")
                self.db.execute("INSERT OR REPLACE INTO windows VALUES(?,?,?)", (name, w["key"], json.dumps(w)))
            self.db.execute("UPDATE profiles SET observed_at=?,checked_at=?,quota_error=NULL WHERE name=?", (time.time(), time.time(), name))

    def cached_monitor(self, source):
        row = self.db.execute("SELECT data FROM monitor_cache WHERE source=?", (source,)).fetchone()
        return json.loads(row[0]) if row else {}

    def cache_monitor(self, source, data):
        # Only normalized public account metadata and quota observations enter this cache.
        allowed = {"connected", "email", "plan", "account_type", "windows", "error", "observed_at", "checked_at"}
        if set(data) - allowed:
            raise ValueError("Unexpected monitor metadata")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO monitor_cache VALUES(?,?)", (source, json.dumps(data)))

    def submit(self, prompt, cwd, provider, profile=None, model=None, bucket=None,
               allow_edits=False, key=None, timeout=1800, max_attempts=6):
        path = Path(cwd).expanduser().resolve()
        if not path.is_dir() or not prompt.strip():
            raise ValueError("Task needs a nonempty prompt and an existing working directory")
        if not math.isfinite(timeout) or timeout <= 0 or max_attempts < 1:
            raise ValueError("Timeout and max attempts must be positive")
        if profile and self.profile(profile)["provider"] != provider:
            raise ValueError("Profile belongs to a different provider")
        spec = (prompt, str(path), provider, profile, model, bucket, int(allow_edits), timeout, max_attempts)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if key:
                old = self.db.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
                if old:
                    existing = tuple(old[k] for k in ("prompt", "cwd", "provider", "profile", "model", "bucket", "allow_edits", "timeout", "max_attempts"))
                    if spec != existing:
                        raise ValueError("Idempotency key already belongs to a different task")
                    return dict(old)
            ident, now = uuid.uuid4().hex, time.time()
            self.db.execute('''INSERT INTO jobs
              (id,idempotency_key,prompt,cwd,provider,profile,model,bucket,allow_edits,timeout,max_attempts,status,created,updated)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?,?)''', (ident, key, *spec, now, now))
        return self.job(ident)

    def job(self, ident):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown job: {ident}")
        return dict(row)

    def jobs(self, pending=False):
        where = "WHERE status IN ('queued','waiting')" if pending else ""
        return [dict(x) for x in self.db.execute(f"SELECT * FROM jobs {where} ORDER BY created")]

    def update_job(self, ident, **values):
        allowed = {"status", "chosen_profile", "attempts", "result", "error"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid job update")
        with self.db:
            self.db.execute("UPDATE jobs SET " + ",".join(f"{k}=?" for k in values) + ",updated=? WHERE id=?",
                            (*values.values(), time.time(), ident))

    def recover(self):
        with self.db:
            count = self.db.execute("UPDATE jobs SET status='needs_review', error='Worker stopped during execution; inspect workspace before retry',updated=? WHERE status='running'", (time.time(),)).rowcount
        return count

    @contextmanager
    def worker_lock(self):
        """OS lock survives neither process exit nor reboot; lock file contents are irrelevant."""
        path = self.home / "worker.lock"
        with open(path, "a+b") as stream:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise WorkerBusy("Another worker or profile operation is active") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise WorkerBusy("Another worker or profile operation is active") from exc
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)
