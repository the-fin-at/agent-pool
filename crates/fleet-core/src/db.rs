//! Local-only durable queue; the SQLite schema is shared byte-for-byte with Python 0.4.x.
use anyhow::{anyhow, bail, ensure, Context, Result};
use fs2::FileExt;
use regex::Regex;
use rusqlite::types::{Value as SqlValue, ValueRef};
use rusqlite::{params, Connection, OptionalExtension, Row, TransactionBehavior};
use serde_json::{json, Map, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const ATTACHED_PROFILE_UNAVAILABLE: &str =
    "Attached native profile is missing or changed; restore its original directory";

pub fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

pub fn default_home() -> PathBuf {
    if let Some(v) = std::env::var_os("AGENT_POOL_HOME").filter(|v| !v.is_empty()) {
        return resolve(&expand(Path::new(&v)));
    }
    let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    if cfg!(windows) {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData/Local"))
            .join("AgentPool")
    } else if cfg!(target_os = "macos") {
        home.join("Library/Application Support/AgentPool")
    } else {
        home.join(".local/share/agent-pool")
    }
}

/// `~` expansion plus absolutization (Python `expanduser()` then relative to cwd).
pub fn expand(path: &Path) -> PathBuf {
    let s = path.to_string_lossy();
    let home = || dirs::home_dir().unwrap_or_default();
    let path = if s == "~" {
        home()
    } else if let Some(tail) = s.strip_prefix("~/") {
        home().join(tail)
    } else {
        path.to_owned()
    };
    if path.is_absolute() {
        path
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    }
}

/// Canonical path in the form Python stores: plain `C:\...` on Windows, never `\\?\C:\...`.
pub fn canonical(path: &Path) -> std::io::Result<PathBuf> {
    dunce::canonicalize(path)
}

/// Python `Path.resolve()` (non-strict): canonicalize the longest existing prefix.
pub fn resolve(path: &Path) -> PathBuf {
    let path = expand(path);
    if let Ok(p) = canonical(&path) {
        return p;
    }
    let mut tail = vec![];
    let mut current = path.as_path();
    while let Some(parent) = current.parent() {
        if let Some(name) = current.file_name() {
            tail.push(name.to_owned());
        }
        if let Ok(base) = canonical(parent) {
            let mut out = base;
            for part in tail.iter().rev() {
                out.push(part);
            }
            return out;
        }
        current = parent;
    }
    path
}

pub fn private_dir(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

pub fn private_file(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    }
    let _ = path;
    Ok(())
}

/// Another process holds the worker lease or a native account lock.
#[derive(Debug)]
pub struct WorkerBusy;
impl std::fmt::Display for WorkerBusy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Another worker or native account session is active")
    }
}
impl std::error::Error for WorkerBusy {}

/// Nonblocking OS lock, interoperable with Python `fcntl.flock` / `msvcrt.locking`.
pub struct Lease(fs::File);

impl Lease {
    pub fn acquire(path: &Path) -> Result<Self> {
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .read(true)
            .open(path)?;
        private_file(path)?;
        if cfg!(windows) && file.metadata()?.len() == 0 {
            file.write_all(b"0")?;
            file.flush()?;
        }
        if let Err(error) = file.try_lock_exclusive() {
            let contended = error
                .raw_os_error()
                .is_some_and(|code| Some(code) == fs2::lock_contended_error().raw_os_error());
            if contended || error.kind() == std::io::ErrorKind::WouldBlock {
                return Err(anyhow!(WorkerBusy));
            }
            return Err(error.into());
        }
        Ok(Self(file))
    }
}

impl Drop for Lease {
    fn drop(&mut self) {
        let _ = FileExt::unlock(&self.0);
    }
}

pub fn is_busy(error: &anyhow::Error) -> bool {
    error.downcast_ref::<WorkerBusy>().is_some()
}

/// Private JSON written atomically next to its final path.
pub fn atomic_json(path: &Path, data: &Value, prefix: &str) -> Result<()> {
    let parent = path.parent().context("Missing parent directory")?;
    let mut tmp = tempfile::Builder::new()
        .prefix(prefix)
        .tempfile_in(parent)?;
    tmp.write_all(serde_json::to_string(data)?.as_bytes())?;
    tmp.as_file().sync_all()?;
    private_file(tmp.path())?;
    tmp.persist(path).map_err(|e| e.error)?;
    Ok(())
}

pub fn row_json(row: &Row<'_>) -> rusqlite::Result<Value> {
    let mut out = Map::new();
    let names: Vec<String> = row.as_ref().column_names().map(|s| s.to_string()).collect();
    for (i, name) in names.into_iter().enumerate() {
        let v = match row.get_ref(i)? {
            ValueRef::Null => Value::Null,
            ValueRef::Integer(v) => json!(v),
            ValueRef::Real(v) => json!(v),
            ValueRef::Text(v) => json!(String::from_utf8_lossy(v)),
            ValueRef::Blob(_) => Value::Null,
        };
        out.insert(name, v);
    }
    Ok(Value::Object(out))
}

fn sql(v: &Value) -> SqlValue {
    match v {
        Value::Null => SqlValue::Null,
        Value::Bool(v) => SqlValue::Integer(i64::from(*v)),
        Value::Number(n) => match n.as_i64() {
            Some(i) => SqlValue::Integer(i),
            None => SqlValue::Real(n.as_f64().unwrap_or_default()),
        },
        Value::String(v) => SqlValue::Text(v.clone()),
        _ => SqlValue::Text(v.to_string()),
    }
}

pub fn truth(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|x| x != 0.0),
        Value::String(s) => !s.is_empty(),
        _ => false,
    }
}

pub fn terminal(v: &Value) -> bool {
    matches!(
        v["status"].as_str(),
        Some("succeeded" | "failed" | "needs_review" | "cancelled")
    )
}

pub fn job_code(v: &Value) -> i32 {
    if v["status"] == "succeeded" {
        0
    } else if terminal(v) {
        1
    } else {
        2
    }
}

pub fn summary(v: &Value) -> Value {
    let mut v = v.clone();
    if let Some(m) = v.as_object_mut() {
        m.remove("prompt");
        m.remove("result");
    }
    v
}

fn name_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[a-z][a-z0-9-]{0,47}$").unwrap())
}

pub fn valid_profile_name(name: &str) -> Result<()> {
    ensure!(
        name_re().is_match(name),
        "Profile name: lowercase letters, digits and hyphens; start with a letter"
    );
    let upper = name.to_uppercase();
    let base = upper.split('.').next().unwrap_or_default();
    let reserved = ["CON", "PRN", "AUX", "NUL"].contains(&base)
        || (1..=9).any(|i| base == format!("COM{i}") || base == format!("LPT{i}"));
    ensure!(!reserved, "Reserved Windows profile name");
    Ok(())
}

/// Task specification as accepted by `job submit` / `run`.
#[derive(Debug, Clone, Default)]
pub struct Spec {
    pub prompt: String,
    pub cwd: String,
    pub provider: String,
    pub profile: Option<String>,
    pub model: Option<String>,
    pub bucket: Option<String>,
    pub allow_edits: bool,
    pub key: Option<String>,
    pub timeout: f64,
    pub max_attempts: i64,
}

const PROFILE_FIELDS: &[&str] = &[
    "enabled",
    "last_used",
    "hold_until",
    "hold_reason",
    "observed_at",
    "checked_at",
    "quota_error",
];
const JOB_FIELDS: &[&str] = &["status", "chosen_profile", "attempts", "result", "error"];

pub struct Db {
    pub home: PathBuf,
    pub conn: Connection,
}

impl Db {
    pub fn open(home: &Path) -> Result<Self> {
        let home = resolve(home);
        private_dir(&home)?;
        let path = home.join("queue.sqlite3");
        let conn = Connection::open(&path)?;
        conn.busy_timeout(Duration::from_secs(20))?;
        conn.query_row("PRAGMA journal_mode=WAL", [], |_| Ok(()))?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS workspaces (name TEXT PRIMARY KEY, path TEXT NOT NULL);
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
          timeout REAL NOT NULL, result TEXT, error TEXT);",
        )?;
        let mut db = Self { home, conn };
        {
            let tx = db
                .conn
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let columns: Vec<String> = {
                let mut s = tx.prepare("PRAGMA table_info(profiles)")?;
                let rows = s.query_map([], |r| r.get(1))?;
                rows.collect::<rusqlite::Result<_>>()?
            };
            if !columns.iter().any(|c| c == "auth_home") {
                tx.execute("ALTER TABLE profiles ADD COLUMN auth_home TEXT", [])?;
            }
            tx.commit()?;
        }
        private_file(&path)?;
        Ok(db)
    }

    pub fn query(&self, query: &str, args: &[&dyn rusqlite::ToSql]) -> Result<Vec<Value>> {
        let mut stmt = self.conn.prepare(query)?;
        let rows = stmt.query_map(args, row_json)?;
        Ok(rows.collect::<rusqlite::Result<_>>()?)
    }

    pub fn workspaces(&self) -> Result<Vec<Value>> {
        self.query("SELECT * FROM workspaces ORDER BY name", &[])
    }

    pub fn add_workspace(&self, name: &str, path: &str) -> Result<Value> {
        ensure!(
            name_re().is_match(name),
            "Workspace name: lowercase letters, digits and hyphens"
        );
        let path = resolve(Path::new(path));
        ensure!(
            path.is_dir(),
            "Workspace must be an existing directory on this server"
        );
        let text = path.to_string_lossy().into_owned();
        self.conn
            .execute("INSERT INTO workspaces VALUES(?,?)", params![name, text])?;
        Ok(json!({"name": name, "path": text}))
    }

    pub fn remove_workspace(&self, name: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM workspaces WHERE name=?", [name])?;
        Ok(())
    }

    pub fn workspace(&self, name: &str) -> Result<String> {
        let path: Option<String> = self
            .conn
            .query_row("SELECT path FROM workspaces WHERE name=?", [name], |r| {
                r.get(0)
            })
            .optional()?;
        let path = path.ok_or_else(|| anyhow!("Unknown server workspace: {name}"))?;
        let p = Path::new(&path);
        ensure!(
            p.is_dir() && resolve(p).to_string_lossy() == path,
            "Workspace is missing or its symlink target changed; register it again"
        );
        Ok(path)
    }

    pub fn profiles(&self) -> Result<Vec<Value>> {
        self.query("SELECT * FROM profiles ORDER BY name", &[])
    }

    pub fn profile(&self, name: &str) -> Result<Value> {
        self.conn
            .query_row("SELECT * FROM profiles WHERE name=?", [name], row_json)
            .optional()?
            .ok_or_else(|| anyhow!("Unknown profile: {name}"))
    }

    pub fn authdir(&self, name: &str) -> Result<PathBuf> {
        let profile = self.profile(name)?;
        if let Some(raw) = profile["auth_home"].as_str().filter(|s| !s.is_empty()) {
            let path = PathBuf::from(raw);
            ensure!(
                path.is_dir() && resolve(&path).to_string_lossy() == raw,
                ATTACHED_PROFILE_UNAVAILABLE
            );
            return Ok(path);
        }
        let path = self.home.join("profiles").join(name);
        private_dir(&path)?;
        Ok(path)
    }

    pub fn add_profile(
        &mut self,
        name: &str,
        provider: &str,
        binary: &str,
        auth_home: Option<&str>,
    ) -> Result<()> {
        valid_profile_name(name)?;
        ensure!(
            provider == "codex" || provider == "claude",
            "Provider must be codex or claude"
        );
        ensure!(
            !binary.is_empty(),
            "Native binary must be a nonempty name or path"
        );
        let auth = match auth_home {
            None => None,
            Some(raw) => {
                let path = resolve(Path::new(raw));
                ensure!(
                    path.is_dir(),
                    "Native auth home must be an existing directory on this machine"
                );
                #[cfg(unix)]
                {
                    use std::os::unix::fs::MetadataExt;
                    ensure!(
                        path.metadata()?.uid() == unsafe { libc::getuid() },
                        "Native auth home must belong to the current user"
                    );
                }
                Some(path.to_string_lossy().into_owned())
            }
        };
        let home = self.home.clone();
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let target = resolve(
            &auth
                .as_ref()
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join("profiles").join(name)),
        );
        let existing: Vec<Value> = {
            let mut stmt = tx.prepare("SELECT * FROM profiles ORDER BY name")?;
            let rows = stmt.query_map([], row_json)?;
            rows.collect::<rusqlite::Result<_>>()?
        };
        for p in &existing {
            let dir = match p["auth_home"].as_str().filter(|s| !s.is_empty()) {
                Some(a) => PathBuf::from(a),
                None => home
                    .join("profiles")
                    .join(p["name"].as_str().unwrap_or_default()),
            };
            ensure!(
                resolve(&dir) != target,
                "This native account directory is already registered"
            );
        }
        tx.execute(
            "INSERT INTO profiles(name,provider,binary,auth_home) VALUES(?,?,?,?)",
            params![name, provider, binary, auth],
        )?;
        tx.commit()?;
        self.authdir(name)?;
        Ok(())
    }

    pub fn update_profile(&self, name: &str, values: Value) -> Result<()> {
        self.profile(name)?;
        self.update("profiles", "name", name, &values, PROFILE_FIELDS, None)?;
        Ok(())
    }

    fn update(
        &self,
        table: &str,
        key: &str,
        id: &str,
        values: &Value,
        allowed: &[&str],
        expected: Option<&[&str]>,
    ) -> Result<bool> {
        let map = values
            .as_object()
            .ok_or_else(|| anyhow!("Invalid {table} update"))?;
        ensure!(
            !map.is_empty() && map.keys().all(|k| allowed.contains(&k.as_str())),
            "Invalid {table} update"
        );
        let mut assigns: Vec<String> = map.keys().map(|k| format!("{k}=?")).collect();
        let mut args: Vec<SqlValue> = map.values().map(sql).collect();
        if table == "jobs" {
            assigns.push("updated=?".into());
            args.push(SqlValue::Real(now()));
        }
        args.push(SqlValue::Text(id.into()));
        let mut query = format!("UPDATE {table} SET {} WHERE {key}=?", assigns.join(","));
        if let Some(states) = expected {
            ensure!(!states.is_empty(), "Invalid job transition");
            query += &format!(" AND status IN ({})", vec!["?"; states.len()].join(","));
            args.extend(states.iter().map(|s| SqlValue::Text((*s).into())));
        }
        Ok(self
            .conn
            .execute(&query, rusqlite::params_from_iter(args))?
            > 0)
    }

    pub fn windows(&self, name: &str) -> Result<Vec<Value>> {
        let mut s = self
            .conn
            .prepare("SELECT data FROM windows WHERE profile=?")?;
        let rows = s.query_map([name], |r| r.get::<_, String>(0))?;
        let mut out = vec![];
        for raw in rows {
            out.push(serde_json::from_str(&raw?)?);
        }
        Ok(out)
    }

    pub fn set_windows(&mut self, name: &str, windows: &[Value], replace: bool) -> Result<()> {
        self.profile(name)?;
        let tx = self.conn.transaction()?;
        if replace {
            tx.execute("DELETE FROM windows WHERE profile=?", [name])?;
        }
        for w in windows {
            let used = &w["used"];
            ensure!(
                used.is_null() || used.as_f64().is_some_and(|v| (0.0..=100.0).contains(&v)),
                "Quota used must be a percentage from 0 to 100"
            );
            let reset = &w["reset"];
            ensure!(
                reset.is_null() || reset.as_f64().is_some_and(|v| v > 0.0 && v < 1e12),
                "Reset must be a Unix timestamp in seconds"
            );
            let key = w["key"]
                .as_str()
                .ok_or_else(|| anyhow!("Quota window needs a key"))?;
            tx.execute(
                "INSERT OR REPLACE INTO windows VALUES(?,?,?)",
                params![name, key, w.to_string()],
            )?;
        }
        tx.execute(
            "UPDATE profiles SET observed_at=?,checked_at=?,quota_error=NULL WHERE name=?",
            params![now(), now(), name],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn cached(&self, source: &str) -> Result<Value> {
        let raw: Option<String> = self
            .conn
            .query_row(
                "SELECT data FROM monitor_cache WHERE source=?",
                [source],
                |r| r.get(0),
            )
            .optional()?;
        Ok(match raw {
            Some(s) => serde_json::from_str(&s)?,
            None => json!({}),
        })
    }

    /// Only normalized public account metadata and quota observations enter this cache.
    pub fn cache(&self, source: &str, data: &Value) -> Result<()> {
        let allowed = [
            "connected",
            "email",
            "plan",
            "account_type",
            "windows",
            "error",
            "observed_at",
            "checked_at",
        ];
        let ok = data
            .as_object()
            .is_some_and(|m| m.keys().all(|k| allowed.contains(&k.as_str())));
        ensure!(ok, "Unexpected monitor metadata");
        self.conn.execute(
            "INSERT OR REPLACE INTO monitor_cache VALUES(?,?)",
            params![source, data.to_string()],
        )?;
        Ok(())
    }

    pub fn submit(&mut self, spec: &Spec) -> Result<Value> {
        for value in [
            Some(&spec.prompt),
            spec.model.as_ref(),
            spec.bucket.as_ref(),
            spec.key.as_ref(),
        ]
        .into_iter()
        .flatten()
        {
            ensure!(!value.contains('\0'), "Task contains NUL characters");
        }
        static SAFE: OnceLock<Regex> = OnceLock::new();
        let safe = SAFE.get_or_init(|| Regex::new(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$").unwrap());
        for value in [spec.model.as_ref(), spec.bucket.as_ref()]
            .into_iter()
            .flatten()
        {
            ensure!(safe.is_match(value), "Invalid model or quota bucket");
        }
        ensure!(
            !(spec.timeout > 14400.0 || spec.max_attempts > 100),
            "Task limit: timeout <= 4 hours, max attempts <= 100"
        );
        ensure!(
            spec.provider == "codex" || spec.provider == "claude",
            "Provider must be codex or claude"
        );
        let path = resolve(Path::new(&spec.cwd));
        ensure!(
            path.is_dir() && !spec.prompt.trim().is_empty(),
            "Task needs a nonempty prompt and an existing working directory"
        );
        ensure!(
            spec.timeout.is_finite() && spec.timeout > 0.0 && spec.max_attempts >= 1,
            "Timeout and max attempts must be positive"
        );
        if let Some(p) = spec.profile.as_deref().filter(|p| !p.is_empty()) {
            ensure!(
                self.profile(p)?["provider"] == spec.provider.as_str(),
                "Profile belongs to a different provider"
            );
        }
        let cwd = path.to_string_lossy().into_owned();
        let edits = i64::from(spec.allow_edits);
        let key = spec.key.as_deref().filter(|k| !k.is_empty());
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        if let Some(key) = key {
            let old = tx
                .query_row(
                    "SELECT * FROM jobs WHERE idempotency_key=?",
                    [key],
                    row_json,
                )
                .optional()?;
            if let Some(old) = old {
                let opt =
                    |v: &Option<String>| v.as_deref().map(|s| json!(s)).unwrap_or(Value::Null);
                let same = old["prompt"] == spec.prompt.as_str()
                    && old["cwd"] == cwd.as_str()
                    && old["provider"] == spec.provider.as_str()
                    && old["profile"] == opt(&spec.profile)
                    && old["model"] == opt(&spec.model)
                    && old["bucket"] == opt(&spec.bucket)
                    && old["allow_edits"].as_i64() == Some(edits)
                    && old["timeout"].as_f64() == Some(spec.timeout)
                    && old["max_attempts"].as_i64() == Some(spec.max_attempts);
                ensure!(same, "Idempotency key already belongs to a different task");
                return Ok(old);
            }
        }
        let id = uuid::Uuid::new_v4().simple().to_string();
        let t = now();
        tx.execute(
            "INSERT INTO jobs
              (id,idempotency_key,prompt,cwd,provider,profile,model,bucket,allow_edits,timeout,max_attempts,status,created,updated)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?,?)",
            params![id, key, spec.prompt, cwd, spec.provider, spec.profile, spec.model, spec.bucket, edits,
                spec.timeout, spec.max_attempts, t, t],
        )?;
        tx.commit()?;
        self.job(&id)
    }

    pub fn job(&self, id: &str) -> Result<Value> {
        self.conn
            .query_row("SELECT * FROM jobs WHERE id=?", [id], row_json)
            .optional()?
            .ok_or_else(|| anyhow!("Unknown job: {id}"))
    }

    pub fn jobs(&self, pending: bool) -> Result<Vec<Value>> {
        self.query(
            if pending {
                "SELECT * FROM jobs WHERE status IN ('queued','waiting') ORDER BY created"
            } else {
                "SELECT * FROM jobs ORDER BY created"
            },
            &[],
        )
    }

    pub fn pending_count(&self) -> Result<i64> {
        Ok(self.conn.query_row(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','waiting','running')",
            [],
            |r| r.get(0),
        )?)
    }

    pub fn update_job(&self, id: &str, values: Value) -> Result<()> {
        self.update("jobs", "id", id, &values, JOB_FIELDS, None)?;
        Ok(())
    }

    /// Compare-and-set on status; false when another process changed the job first.
    pub fn transition(&self, id: &str, expected: &[&str], values: Value) -> Result<bool> {
        if expected.is_empty() {
            bail!("Invalid job transition");
        }
        self.update("jobs", "id", id, &values, JOB_FIELDS, Some(expected))
    }

    pub fn claim(&mut self, id: &str, name: &str) -> Result<bool> {
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let enabled: Option<i64> = tx
            .query_row("SELECT enabled FROM profiles WHERE name=?", [name], |r| {
                r.get(0)
            })
            .optional()?;
        let enabled = enabled.ok_or_else(|| anyhow!("Unknown profile: {name}"))?;
        if enabled == 0 {
            return Ok(false);
        }
        let changed = tx.execute(
            "UPDATE jobs SET status='running',chosen_profile=?,attempts=attempts+1,error=NULL,updated=? WHERE id=? AND status IN ('queued','waiting')",
            params![name, now(), id],
        )?;
        tx.commit()?;
        Ok(changed > 0)
    }

    pub fn recover(&self) -> Result<usize> {
        Ok(self.conn.execute(
            "UPDATE jobs SET status='needs_review', error='Worker stopped during execution; inspect workspace before retry',updated=? WHERE status='running'",
            [now()],
        )?)
    }

    /// Only the executor owns this lease; queue administration remains available.
    pub fn worker_lock(&self) -> Result<Lease> {
        Lease::acquire(&self.home.join("worker.lock"))
    }
}
