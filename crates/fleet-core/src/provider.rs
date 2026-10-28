//! Native CLI adapters: no OAuth-token parsing or direct subscription HTTP calls.
use crate::db::{truth, Lease};
use crate::quota;
use anyhow::{anyhow, bail, ensure, Context, Result};
use regex::Regex;
use serde_json::{json, Value};
use std::fs;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Once, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

/// Set by SIGINT/SIGTERM while a worker runs; native children are then stopped.
pub static STOP: AtomicBool = AtomicBool::new(false);
static SIGNALS: Once = Once::new();

pub fn install_signal_handler() {
    SIGNALS.call_once(|| {
        let _ = ctrlc::set_handler(|| STOP.store(true, Ordering::SeqCst));
    });
}

pub fn stopping() -> bool {
    STOP.load(Ordering::SeqCst)
}

/// Ambient keys/base URLs must not silently change the selected subscription or bill an API key.
pub const AUTH_ENV: &[&str] = &[
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "CODEX_SQLITE_HOME",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_MODEL",
    "CLAUDECODE",
    "CODEX_THREAD_ID",
    "SSH_AUTH_SOCK",
    "SSH_CONNECTION",
    "SSH_CLIENT",
];

/// Child environment: inherited minus billing/auth overrides, with exactly one isolated config dir.
pub fn environment(provider: &str, authdir: &Path) -> Vec<(String, String)> {
    let mut env: Vec<(String, String)> = std::env::vars_os()
        .filter_map(|(k, v)| Some((k.into_string().ok()?, v.into_string().ok()?)))
        .filter(|(k, _)| {
            !AUTH_ENV.contains(&k.as_str()) && k != "CODEX_HOME" && k != "CLAUDE_CONFIG_DIR"
        })
        .collect();
    let key = if provider == "codex" {
        "CODEX_HOME"
    } else {
        "CLAUDE_CONFIG_DIR"
    };
    env.push((key.into(), authdir.to_string_lossy().into_owned()));
    env
}

fn search_path() -> Vec<PathBuf> {
    let home = dirs::home_dir().unwrap_or_default();
    let mut paths: Vec<PathBuf> =
        std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()).collect();
    paths.push(home.join(".local/bin"));
    if cfg!(windows) {
        let local = std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData/Local"));
        paths.extend([
            local.join("Programs/OpenAI/Codex/bin"),
            local.join("Microsoft/WinGet/Links"),
        ]);
    } else {
        paths.extend([
            home.join(".npm-global/bin"),
            home.join(".npm/bin"),
            PathBuf::from("/opt/homebrew/bin"),
            PathBuf::from("/usr/local/bin"),
        ]);
    }
    paths
}

fn runnable(path: &Path) -> bool {
    let Ok(meta) = fs::metadata(path) else {
        return false;
    };
    if !meta.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        meta.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

/// Finder and Windows GUI launches have a smaller PATH than a login shell.
pub fn executable(binary: &str) -> Result<PathBuf> {
    ensure!(
        !binary.is_empty() && !binary.contains('\0'),
        "Native CLI not found: {binary}; install it or set profile --binary"
    );
    let path = Path::new(binary);
    let candidates: Vec<PathBuf> = if path.components().count() > 1 || path.is_absolute() {
        let mut c = vec![path.to_owned()];
        if cfg!(windows) {
            c.extend(["exe", "cmd", "bat"].iter().map(|x| path.with_extension(x)));
        }
        c
    } else {
        search_path()
            .into_iter()
            .filter(|d| !d.as_os_str().is_empty())
            .flat_map(|d| {
                let mut c = vec![d.join(binary)];
                if cfg!(windows) {
                    c.extend(
                        ["exe", "cmd", "bat"]
                            .iter()
                            .map(|x| d.join(format!("{binary}.{x}"))),
                    );
                }
                c
            })
            .collect()
    };
    let found = candidates
        .into_iter()
        .find(|p| runnable(p))
        .ok_or_else(|| {
            anyhow!("Native CLI not found: {binary}; install it or set profile --binary")
        })?;
    let ext = found
        .extension()
        .map(|x| x.to_string_lossy().to_ascii_lowercase());
    ensure!(
        !matches!(ext.as_deref(), Some("cmd" | "bat")),
        "Use the native .exe CLI on Windows, or run the whole broker in WSL; shell shims are unsupported"
    );
    Ok(found)
}

/// Native subprocess in its own process group (never through a shell).
pub fn plain_command(binary: &Path) -> Command {
    let mut c = Command::new(binary);
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        c.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        c.creation_flags(0x0800_0200);
    }
    c
}

pub fn auth_command(provider: &str, binary: &str, dir: &Path) -> Result<Command> {
    let mut c = plain_command(&executable(binary)?);
    c.env_clear();
    c.envs(environment(provider, dir));
    Ok(c)
}

pub fn profile_command(profile: &Value, dir: &Path) -> Result<Command> {
    let provider = profile["provider"].as_str().context("Missing provider")?;
    let binary = profile["binary"].as_str().unwrap_or(provider);
    auth_command(provider, binary, dir)
}

/// Kills the whole process group, then reaps the leader.
pub fn kill_tree(child: &mut Child) {
    #[cfg(unix)]
    unsafe {
        libc::kill(-(child.id() as i32), libc::SIGKILL);
    }
    #[cfg(windows)]
    {
        let _ = plain_command(Path::new("taskkill"))
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

pub fn redact(text: &str) -> String {
    static BEARER: OnceLock<Regex> = OnceLock::new();
    static TOKEN: OnceLock<Regex> = OnceLock::new();
    let bearer = BEARER.get_or_init(|| Regex::new(r#"(?i)Bearer\s+[^\s"']+"#).unwrap());
    let token = TOKEN.get_or_init(|| {
        Regex::new(r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)").unwrap()
    });
    let a = bearer.replace_all(text, "Bearer [REDACTED]");
    token.replace_all(&a, "[REDACTED]").into_owned()
}

pub struct Captured {
    pub code: i32,
    pub out: String,
    pub err: String,
    pub timed_out: bool,
    /// Worker shutdown requested via signal.
    pub stopped: bool,
    /// Stdout exceeded `limit` bytes; the process was killed.
    pub overflow: bool,
}

fn tail_bytes(file: &mut fs::File, max: u64) -> Result<String> {
    let len = file.seek(SeekFrom::End(0))?;
    file.seek(SeekFrom::Start(len.saturating_sub(max)))?;
    let mut raw = vec![];
    file.read_to_end(&mut raw)?;
    Ok(String::from_utf8_lossy(&raw).into_owned())
}

/// Runs a prepared native command with file-backed output, a deadline and group cleanup.
pub fn capture(
    mut cmd: Command,
    input: Option<&[u8]>,
    timeout: f64,
    limit: u64,
) -> Result<Captured> {
    let mut out = tempfile::tempfile()?;
    let mut err = tempfile::tempfile()?;
    cmd.stdout(out.try_clone()?).stderr(err.try_clone()?);
    cmd.stdin(if input.is_some() {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    let mut child = cmd.spawn().context("Native process could not be started")?;
    let writer = match (input, child.stdin.take()) {
        (Some(data), Some(mut pipe)) => {
            let data = data.to_vec();
            Some(thread::spawn(move || {
                let _ = pipe.write_all(&data);
            }))
        }
        _ => None,
    };
    let deadline = Instant::now() + Duration::from_secs_f64(timeout.clamp(0.001, 1e7));
    let (mut timed_out, mut stopped, mut overflow) = (false, false, false);
    let code = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status.code().unwrap_or(1),
            Ok(None) => {}
            Err(e) => {
                kill_tree(&mut child);
                return Err(e.into());
            }
        }
        if stopping() {
            stopped = true;
        } else if Instant::now() >= deadline {
            timed_out = true;
        } else if out.metadata()?.len() > limit {
            overflow = true;
        }
        if stopped || timed_out || overflow {
            kill_tree(&mut child);
            break 1;
        }
        thread::sleep(Duration::from_millis(20));
    };
    // A surviving grandchild may hold stdin open; the writer must never block the caller.
    drop(writer);
    let len = out.seek(SeekFrom::End(0))?;
    overflow |= len > limit;
    out.seek(SeekFrom::Start(0))?;
    let mut raw = vec![];
    (&mut out).take(limit).read_to_end(&mut raw)?;
    Ok(Captured {
        code,
        out: String::from_utf8_lossy(&raw).into_owned(),
        err: tail_bytes(&mut err, 8192)?,
        timed_out,
        stopped,
        overflow,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct Outcome {
    pub kind: &'static str,
    pub result: String,
    pub error: String,
    pub windows: Vec<Value>,
}

impl Outcome {
    pub fn new(kind: &'static str, result: &str, error: &str) -> Self {
        Self {
            kind,
            result: result.into(),
            error: error.into(),
            windows: vec![],
        }
    }
}

pub fn native_argv(profile: &Value, job: &Value, final_path: &Path) -> Vec<String> {
    let edits = truth(&job["allow_edits"]);
    let model: Vec<String> = match job["model"].as_str().filter(|m| !m.is_empty()) {
        Some(m) => vec!["--model".into(), m.into()],
        None => vec![],
    };
    let mut argv: Vec<String>;
    if profile["provider"] == "codex" {
        argv = [
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
        ]
        .map(String::from)
        .to_vec();
        argv.push(
            if edits {
                "workspace-write"
            } else {
                "read-only"
            }
            .into(),
        );
        argv.push("--output-last-message".into());
        argv.push(final_path.to_string_lossy().into_owned());
        argv.extend(model);
        argv.push("-".into());
    } else {
        let tools = if edits {
            "Read,Glob,Grep,Edit,Write"
        } else {
            "Read,Glob,Grep"
        };
        argv = [
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--restricted",
            "--strict-mcp-config",
            "--tools",
            tools,
            "--allowedTools",
            tools,
        ]
        .map(String::from)
        .to_vec();
        argv.extend(model);
    }
    argv
}

fn python_dumps_list(errors: &[Value]) -> String {
    // json.dumps(..., ensure_ascii=False) separators: ", " and ": ".
    fn render(v: &Value) -> String {
        match v {
            Value::Array(a) => format!("[{}]", a.iter().map(render).collect::<Vec<_>>().join(", ")),
            Value::Object(m) => format!(
                "{{{}}}",
                m.iter()
                    .map(|(k, v)| format!("{}: {}", Value::String(k.clone()), render(v)))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            other => other.to_string(),
        }
    }
    render(&Value::Array(errors.to_vec()))
}

fn last_chars(text: &str, n: usize) -> String {
    let count = text.chars().count();
    text.chars().skip(count.saturating_sub(n)).collect()
}

pub fn parse(provider: &str, stdout: &str, stderr: &str, code: i32, final_text: &str) -> Outcome {
    let mut windows = vec![];
    let mut errors: Vec<Value> = vec![];
    let mut completed = false;
    let mut result = final_text.to_string();
    for line in stdout.lines() {
        let Ok(e) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if !e.is_object() {
            continue;
        }
        let kind = e["type"].as_str().unwrap_or("");
        if provider == "codex" {
            if kind == "turn.completed" {
                completed = true;
            }
            if kind == "error" || kind == "turn.failed" {
                errors.push(
                    e.get("error")
                        .or(e.get("message"))
                        .cloned()
                        .unwrap_or(json!("Codex turn failed")),
                );
            }
            if kind == "item.completed"
                && e["item"]["type"] == "agent_message"
                && final_text.is_empty()
            {
                result = e["item"]["text"].as_str().unwrap_or("").into();
            }
        } else {
            if kind == "rate_limit_event" {
                windows.extend(quota::claude_windows(&e));
            }
            if kind == "result" {
                completed = e["subtype"] == "success" && !truth(&e["is_error"]);
                result = e["result"].as_str().unwrap_or("").into();
                if !completed {
                    match e["errors"].as_array().filter(|a| !a.is_empty()) {
                        Some(list) => errors.extend(list.iter().cloned()),
                        None => errors.push(
                            e.get("result")
                                .filter(|r| truth_str(r))
                                .or(e.get("subtype"))
                                .cloned()
                                .unwrap_or(json!("Claude failed")),
                        ),
                    }
                }
            }
            if kind == "assistant" && truth_str(&e["error"]) {
                errors.push(e["error"].clone());
            }
        }
    }
    if completed && code == 0 && errors.is_empty() {
        return Outcome {
            kind: "success",
            result: redact(&result),
            error: String::new(),
            windows,
        };
    }
    // Match provider error fields only, never a successful model's prose.
    let detail = if !errors.is_empty() {
        python_dumps_list(&errors)
    } else if code != 0 {
        last_chars(stderr, 4000)
    } else {
        "Missing successful completion event".into()
    };
    let lowered = detail.to_lowercase();
    let quota_hit = [
        "usage_limit_reached",
        "rate_limit",
        "rate limit",
        "usage limit",
        "hit your limit",
    ]
    .iter()
    .any(|s| lowered.contains(s));
    Outcome {
        kind: if quota_hit { "quota" } else { "failed" },
        result: String::new(),
        error: redact(&detail),
        windows,
    }
}

fn truth_str(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(m) => !m.is_empty(),
        Value::Number(n) => n.as_f64() != Some(0.0),
    }
}

const MAX_RUN_OUTPUT: u64 = 32 * 1024 * 1024;

/// Executes one job under the account lock; a held lock is `busy`, never an attempt.
pub fn run_native(profile: &Value, job: &Value, dir: &Path) -> Result<Outcome> {
    let _lease = match Lease::acquire(&dir.join(".native.lock")) {
        Ok(l) => l,
        Err(_) => {
            return Ok(Outcome::new(
                "busy",
                "",
                "Account metadata or login session is active; waiting",
            ))
        }
    };
    let folder = tempfile::Builder::new()
        .prefix("agent-pool-run-")
        .tempdir()?;
    let final_path = folder.path().join("final.txt");
    let mut cmd = profile_command(profile, dir)?;
    cmd.args(native_argv(profile, job, &final_path));
    cmd.current_dir(job["cwd"].as_str().context("Missing cwd")?);
    let prompt = job["prompt"].as_str().unwrap_or_default();
    let timeout = job["timeout"].as_f64().unwrap_or(1800.0);
    let r = capture(cmd, Some(prompt.as_bytes()), timeout, MAX_RUN_OUTPUT)?;
    if r.stopped {
        bail!(Interrupted);
    }
    if r.timed_out {
        return Ok(Outcome::new(
            "uncertain",
            "",
            "Native CLI timed out; inspect workspace before retry",
        ));
    }
    if r.overflow {
        return Ok(Outcome::new(
            "uncertain",
            "",
            "Output exceeded 32 MiB; inspect workspace before retry",
        ));
    }
    let final_text = fs::read_to_string(&final_path).unwrap_or_default();
    Ok(parse(
        profile["provider"].as_str().unwrap_or(""),
        &r.out,
        &r.err,
        r.code,
        &final_text,
    ))
}

/// Signal-driven worker stop while a native child ran.
#[derive(Debug)]
pub struct Interrupted;
impl std::fmt::Display for Interrupted {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Worker interrupted; inspect workspace before retry")
    }
}
impl std::error::Error for Interrupted {}

/// Documented JSONL metadata session; no model turn is started.
pub struct CodexSession {
    child: Child,
    lines: mpsc::Receiver<Value>,
    deadline: Instant,
    next_id: i64,
}

impl CodexSession {
    pub fn open(profile: &Value, dir: &Path, timeout: f64) -> Result<Self> {
        let mut cmd = auth_command("codex", profile["binary"].as_str().unwrap_or("codex"), dir)?;
        cmd.arg("app-server")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut child = cmd.spawn()?;
        let stdout = child.stdout.take().context("Missing native stdout")?;
        let (tx, rx) = mpsc::sync_channel(256);
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut bytes = vec![];
                match (&mut reader)
                    .take(4 * 1024 * 1024)
                    .read_until(b'\n', &mut bytes)
                {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {
                        if let Ok(v) = serde_json::from_slice::<Value>(&bytes) {
                            if tx.send(v).is_err() {
                                break;
                            }
                        }
                    }
                }
            }
        });
        let mut session = Self {
            child,
            lines: rx,
            deadline: Instant::now() + Duration::from_secs_f64(timeout),
            next_id: 0,
        };
        session.request(
            "initialize",
            json!({"clientInfo": {"name": "local_agent_pool", "title": "Local Agent Pool", "version": crate::VERSION}}),
        )?;
        session.send(&json!({"method": "initialized", "params": {}}))?;
        Ok(session)
    }

    fn send(&mut self, message: &Value) -> Result<()> {
        let pipe = self.child.stdin.as_mut().context("Missing native stdin")?;
        writeln!(pipe, "{message}")?;
        pipe.flush()?;
        Ok(())
    }

    pub fn request(&mut self, method: &str, params: Value) -> Result<Value> {
        self.next_id += 1;
        let id = self.next_id;
        self.send(&json!({"id": id, "method": method, "params": params}))?;
        loop {
            let remaining = self.deadline.saturating_duration_since(Instant::now());
            ensure!(!remaining.is_zero(), "Codex quota read timed out");
            let msg = match self.lines.recv_timeout(remaining) {
                Ok(m) => m,
                Err(mpsc::RecvTimeoutError::Timeout) => bail!("Codex quota read timed out"),
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    bail!("Codex app-server exited before its quota response")
                }
            };
            if msg.get("id") != Some(&json!(id)) {
                continue;
            }
            if let Some(error) = msg.get("error") {
                bail!("Codex quota unavailable: {}", redact(&error.to_string()));
            }
            return Ok(msg.get("result").cloned().unwrap_or(json!({})));
        }
    }
}

impl Drop for CodexSession {
    fn drop(&mut self) {
        kill_tree(&mut self.child);
    }
}

pub fn read_codex_quota(profile: &Value, dir: &Path) -> Result<Vec<Value>> {
    let _lease = Lease::acquire(&dir.join(".native.lock"))?;
    let mut session = CodexSession::open(profile, dir, 20.0)?;
    let windows = quota::codex(&session.request("account/rateLimits/read", json!({}))?);
    ensure!(
        !windows.is_empty(),
        "Codex returned no subscription quota windows"
    );
    Ok(windows)
}

/// Allowlisted account identity plus real quota observations.
pub fn codex_status(profile: &Value, dir: &Path) -> Result<Value> {
    let _lease = Lease::acquire(&dir.join(".native.lock"))?;
    codex_status_unlocked(profile, dir)
}

/// Caller already holds the account's `.native.lock`.
pub fn codex_status_unlocked(profile: &Value, dir: &Path) -> Result<Value> {
    let mut session = CodexSession::open(profile, dir, 20.0)?;
    let account =
        session.request("account/read", json!({"refreshToken": false}))?["account"].clone();
    if !truth_str(&account) {
        return Ok(
            json!({"connected": false, "email": null, "plan": null, "windows": null, "error": null}),
        );
    }
    let mut result = json!({"connected": true, "email": account["email"], "plan": account["planType"],
        "account_type": account["type"]});
    match session
        .request("account/rateLimits/read", json!({}))
        .map(|v| quota::codex(&v))
    {
        Ok(w) if !w.is_empty() => {
            result["windows"] = json!(w);
            result["error"] = Value::Null;
        }
        Ok(_) => {
            result["windows"] = Value::Null;
            result["error"] = json!("Keine Kontingent-Fenster vom Anbieter gemeldet");
        }
        Err(e) => {
            result["windows"] = Value::Null;
            result["error"] = json!(redact(&e.to_string()));
        }
    }
    Ok(result)
}
