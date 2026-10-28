//! Bounded native login sessions; OAuth credentials remain entirely with provider CLIs.
//! File format, ids and locks are shared with Python `agent_pool.login_sessions`.
use crate::db::{atomic_json, is_busy, now, private_dir, resolve, Db, Lease, WorkerBusy};
use crate::provider::{capture, executable, kill_tree, profile_command, redact};
use anyhow::{anyhow, bail, ensure, Context, Result};
use regex::Regex;
use serde_json::{json, Value};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::OnceLock;
use std::thread;
use std::time::{Duration, Instant};

pub const TTL: f64 = 900.0;
pub const HEARTBEAT_STALE: f64 = 45.0;
pub const MAX_LIVE: usize = 4;
pub const ACTIVE: &[&str] = &["starting", "awaiting_browser", "awaiting_code", "verifying"];
pub const LOGIN_HOSTS: &[&str] = &[
    "auth.openai.com",
    "chatgpt.com",
    "claude.ai",
    "claude.com",
    "console.anthropic.com",
    "platform.claude.com",
];
const MAX_OUTPUT: usize = 128 * 1024;

pub fn active(state: &Value) -> bool {
    state.as_str().is_some_and(|s| ACTIVE.contains(&s))
}

/// Only official HTTPS provider pages may be opened by a client.
pub fn safe_url(value: &str) -> bool {
    let Ok(url) = url::Url::parse(value) else {
        return false;
    };
    // Python urlsplit keeps the literal port; `url` normalizes :443 away for https.
    let explicit_port = authority_port(value);
    url.scheme() == "https"
        && url.host_str().is_some_and(|h| LOGIN_HOSTS.contains(&h))
        && url.username().is_empty()
        && url.password().is_none()
        && matches!(explicit_port, Ok(None) | Ok(Some(443)))
}

fn authority_port(value: &str) -> Result<Option<u16>, ()> {
    let rest = value.split_once("://").map(|x| x.1).ok_or(())?;
    let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
    let hostport = authority.rsplit('@').next().unwrap_or_default();
    match hostport.rsplit_once(':') {
        None => Ok(None),
        Some((_, "")) => Ok(None),
        Some((_, p)) => p.parse::<u16>().map(Some).map_err(|_| ()),
    }
}

pub fn folder(home: &Path) -> Result<PathBuf> {
    let path = home.join("login-sessions");
    private_dir(&path)?;
    Ok(path)
}

fn id_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[a-f0-9]{32}$").unwrap())
}

pub struct SessionPaths {
    pub state: PathBuf,
    pub input: PathBuf,
    pub cancel: PathBuf,
    pub lock: PathBuf,
}

pub fn paths(home: &Path, id: &str) -> Result<SessionPaths> {
    ensure!(id_re().is_match(id), "Invalid login session");
    let root = folder(home)?;
    Ok(SessionPaths {
        state: root.join(format!("{id}.json")),
        input: root.join(format!("{id}.input")),
        cancel: root.join(format!("{id}.cancel")),
        lock: root.join(format!("{id}.lock")),
    })
}

fn write_private(path: &Path, data: &Value) -> Result<()> {
    atomic_json(path, data, ".login-")
}

fn remove(path: &Path) {
    let _ = fs::remove_file(path);
}

/// Current session state; a killed daemon cannot leave an eternally active login.
pub fn status(home: &Path, id: &str) -> Result<Value> {
    let p = paths(home, id)?;
    ensure!(p.state.exists(), "Unknown login session");
    let mut data: Value = serde_json::from_str(&fs::read_to_string(&p.state)?)?;
    ensure!(data.is_object(), "Unknown login session");
    let t = now();
    let expires = data["expires_at"]
        .as_f64()
        .ok_or_else(|| anyhow!("Invalid login session"))?;
    let updated = data["updated_at"]
        .as_f64()
        .or_else(|| data["created_at"].as_f64())
        .unwrap_or(0.0);
    if active(&data["state"]) && (t > expires || t - updated > HEARTBEAT_STALE) {
        data["state"] = json!("expired");
        data["url"] = Value::Null;
        data["device_code"] = Value::Null;
        data["message"] = json!("Die Anmeldung ist abgelaufen. Bitte neu starten.");
        write_private(&p.state, &data)?;
        remove(&p.input);
        remove(&p.cancel);
    }
    Ok(data)
}

/// Command that re-enters this executable as a detached login worker.
pub fn worker_command(home: &Path, id: &str) -> Result<Vec<String>> {
    let exe = std::env::current_exe().context("Cannot locate the running executable")?;
    Ok(vec![
        exe.to_string_lossy().into_owned(),
        "--login-worker".into(),
        resolve(home).to_string_lossy().into_owned(),
        id.into(),
    ])
}

fn detached(argv: &[String], cwd: &Path) -> Command {
    let mut c = Command::new(&argv[0]);
    c.args(&argv[1..])
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // Equivalent of Python start_new_session=True: independent of the client's terminal.
        unsafe {
            c.pre_exec(|| {
                libc::setsid();
                Ok(())
            });
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS
        c.creation_flags(0x0800_0200 | 0x0000_0008);
    }
    c
}

fn which(name: &str) -> Option<PathBuf> {
    std::env::split_paths(&std::env::var_os("PATH")?)
        .map(|d| d.join(name))
        .find(|p| p.is_file())
}

fn launch_worker(home: &Path, id: &str) -> Result<()> {
    let command = worker_command(home, id)?;
    // A transient user unit also survives logind session cleanup when available.
    if cfg!(target_os = "linux") {
        if let Some(systemd_run) = which("systemd-run") {
            let mut c = Command::new(systemd_run);
            c.args(["--user", "--collect", "--quiet"])
                .arg(format!("--unit=agent-fleet-login-{id}"))
                .arg(format!("--working-directory={}", home.display()))
                .arg(format!(
                    "--setenv=PATH={}",
                    std::env::var("PATH").unwrap_or_else(|_| "/usr/local/bin:/usr/bin:/bin".into())
                ))
                .args([
                    "--property=RuntimeMaxSec=960",
                    "--property=UMask=0077",
                    "--property=KillMode=control-group",
                    "--",
                ])
                .args(&command);
            if let Ok(done) = capture(c, None, 10.0, 64 * 1024) {
                if done.code == 0 && !done.timed_out {
                    return Ok(());
                }
            }
        }
    }
    let mut child = detached(&command, home).spawn()?;
    thread::Builder::new()
        .name("login-reaper".into())
        .spawn(move || {
            let _ = child.wait();
        })?;
    Ok(())
}

/// Atomic, idempotent start keyed by a client-chosen 32-hex id.
pub fn start(home: &Path, name: &str, provider: &str, key: &str) -> Result<Value> {
    start_with(home, name, provider, key, &launch_worker)
}

pub fn start_with(
    home: &Path,
    name: &str,
    provider: &str,
    key: &str,
    spawn: &dyn Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    ensure!(
        provider == "codex" || provider == "claude",
        "Choose Codex or Claude"
    );
    ensure!(
        id_re().is_match(key),
        "A stable 32-character login key is required"
    );
    let mut db = Db::open(home)?;
    let home = db.home.clone();
    let root = folder(&home)?;
    let _start = Lease::acquire(&root.join(".start.lock"))?;
    let p = paths(&home, key)?;
    if p.state.exists() {
        let old = status(&home, key)?;
        ensure!(
            old["profile"] == name && old["provider"] == provider,
            "Login key already belongs to another account"
        );
        return Ok(old);
    }
    let existing = db.profiles()?.into_iter().find(|p| p["name"] == name);
    if let Some(e) = &existing {
        ensure!(
            e["provider"] == provider,
            "This profile belongs to a different provider"
        );
    }
    // Resolve before modifying the profile registry.
    executable(
        existing
            .as_ref()
            .and_then(|e| e["binary"].as_str())
            .unwrap_or(provider),
    )?;
    let mut live = 0;
    for entry in fs::read_dir(&root)? {
        let path = entry?.path();
        if path.extension().and_then(|x| x.to_str()) != Some("json") {
            continue;
        }
        let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        let Ok(old) = status(&home, stem) else {
            continue;
        };
        if active(&old["state"]) {
            live += 1;
            ensure!(
                old["profile"] != name,
                "Anmeldung für dieses Profil läuft bereits"
            );
        }
    }
    ensure!(
        live < MAX_LIVE,
        "Es laufen bereits vier Anmeldungen. Schließe zuerst eine davon ab."
    );
    if existing.is_none() {
        db.add_profile(name, provider, provider, None)?;
    }
    let t = now();
    let mut data = json!({"id": key, "profile": name, "provider": provider, "state": "starting",
        "created_at": t, "updated_at": t, "expires_at": t + TTL,
        "url": null, "device_code": null, "message": "Anmeldung wird vorbereitet …"});
    if p.cancel.exists() {
        // Cancel may reach the server before an uncertain start request.
        data["state"] = json!("cancelled");
        data["message"] = json!("Anmeldung abgebrochen.");
        remove(&p.cancel);
        write_private(&p.state, &data)?;
        return Ok(data);
    }
    write_private(&p.state, &data)?;
    if let Err(e) = spawn(&home, key) {
        data["state"] = json!("failed");
        data["message"] = json!(format!(
            "Login-Prozess konnte nicht gestartet werden: {}",
            redact(&e.to_string())
        ));
        write_private(&p.state, &data)?;
    }
    Ok(data)
}

pub fn provide_code(home: &Path, id: &str, code: &str) -> Result<Value> {
    let trimmed = code.trim();
    ensure!(
        !trimmed.is_empty()
            && code.chars().count() <= 4096
            && !trimmed.chars().any(|c| (c as u32) < 32),
        "Please paste the complete authorization code"
    );
    let data = status(home, id)?;
    ensure!(
        data["provider"] == "claude"
            && (data["state"] == "awaiting_browser" || data["state"] == "awaiting_code"),
        "This login is not waiting for a Claude authorization code"
    );
    write_private(&paths(home, id)?.input, &json!({"code": trimmed}))?;
    Ok(json!({"accepted": true, "id": id}))
}

pub fn cancel(home: &Path, id: &str) -> Result<Value> {
    let p = paths(home, id)?;
    if !p.state.exists() {
        write_private(&p.cancel, &json!({"cancel": true}))?;
        return Ok(json!({"id": id, "cancel_requested": true}));
    }
    let data = status(home, id)?;
    let live = active(&data["state"]);
    if live {
        write_private(&p.cancel, &json!({"cancel": true}))?;
    }
    Ok(json!({"id": id, "cancel_requested": live}))
}

fn paste_prompt(text: &str) -> bool {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)paste.*code|code here").unwrap())
        .is_match(text)
}

/// Allowlist public login instructions; never persist raw CLI logs or tokens.
pub fn observe(provider: &str, raw: &str) -> serde_json::Map<String, Value> {
    static OSC: OnceLock<Regex> = OnceLock::new();
    static CSI: OnceLock<Regex> = OnceLock::new();
    static URL: OnceLock<Regex> = OnceLock::new();
    static CODE: OnceLock<Regex> = OnceLock::new();
    let raw = OSC
        .get_or_init(|| Regex::new(r"\x1b\][^\x07]*(?:\x07|\x1b\\)").unwrap())
        .replace_all(raw, "");
    let raw = CSI
        .get_or_init(|| Regex::new(r"\x1b\[[0-?]*[ -/]*[@-~]").unwrap())
        .replace_all(&raw, "")
        .into_owned();
    let urls: Vec<String> = URL
        .get_or_init(|| Regex::new(r#"https://[^\s\x1b<>"']+"#).unwrap())
        .find_iter(&raw)
        .map(|m| {
            m.as_str()
                .trim_end_matches(['.', ',', ')', ';'])
                .to_string()
        })
        .filter(|u| safe_url(u))
        .collect();
    let mut result = serde_json::Map::new();
    if let Some(url) = urls.last() {
        result.insert("url".into(), json!(url));
        result.insert("state".into(), json!("awaiting_browser"));
        result.insert(
            "message".into(),
            json!("Bestätige die Anmeldung im Browser."),
        );
    }
    if provider == "codex" {
        let code = CODE.get_or_init(|| Regex::new(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b").unwrap());
        if let Some(m) = code.find_iter(&raw).last() {
            result.insert("device_code".into(), json!(m.as_str()));
        }
    } else if (!urls.is_empty() || !raw.contains("https://")) && paste_prompt(&raw) {
        result.insert("state".into(), json!("awaiting_code"));
        result.insert(
            "message".into(),
            json!("Öffne die Anmeldeseite. Falls ein Code erscheint, füge ihn hier ein."),
        );
    }
    result
}

fn same_dir(reported: &str, dir: &Path) -> bool {
    resolve(Path::new(reported)) == resolve(dir)
}

fn native_status(profile: &Value, dir: &Path) -> Result<crate::provider::Captured> {
    let mut c = profile_command(profile, dir)?;
    if profile["provider"] == "codex" {
        c.args(["login", "status"]);
    } else {
        c.args(["auth", "status"]);
    }
    capture(c, None, 20.0, 1024 * 1024)
}

/// Older Claude CLIs ignore CLAUDE_CONFIG_DIR for status; refuse to log into the wrong directory.
pub fn check_claude_directory(profile: &Value, dir: &Path) -> Result<Value> {
    let done = native_status(profile, dir)?;
    let data: Value = serde_json::from_str(done.out.trim()).map_err(|_| {
        anyhow!("Bitte die native Claude-CLI aktualisieren; ihr Profilstatus konnte nicht geprüft werden.")
    })?;
    let ok = data["configDirectory"]
        .as_str()
        .filter(|s| !s.is_empty())
        .is_some_and(|r| same_dir(r, dir));
    ensure!(ok, "Die Claude-CLI bestätigt nicht das gewählte Profilverzeichnis. Bitte die CLI aktualisieren.");
    Ok(data)
}

/// Confirms a subscription login in exactly this directory; returns allowlisted Claude identity.
pub fn verify(profile: &Value, dir: &Path) -> Result<Option<Value>> {
    let done = native_status(profile, dir)?;
    ensure!(
        !done.timed_out && done.code == 0,
        "Der Anbieter hat die Anmeldung noch nicht bestätigt"
    );
    if profile["provider"] == "claude" {
        let data: Value = serde_json::from_str(done.out.trim())
            .map_err(|_| anyhow!("Die native CLI meldet keine Claude-Abonnement-Anmeldung"))?;
        let ok = data["configDirectory"]
            .as_str()
            .filter(|s| !s.is_empty())
            .is_some_and(|r| same_dir(r, dir));
        ensure!(
            ok,
            "Die Claude-CLI hat ein anderes Profilverzeichnis verwendet"
        );
        ensure!(
            data["loggedIn"] == true && data["authMethod"] == "claude.ai",
            "Die native CLI meldet keine Claude-Abonnement-Anmeldung"
        );
        return Ok(Some(
            json!({"connected": true, "email": data["email"], "plan": data["subscriptionType"],
            "account_type": "claude.ai", "windows": [], "error": null, "checked_at": now(), "observed_at": null}),
        ));
    }
    let text = format!("{}{}", done.out, done.err).to_lowercase();
    ensure!(
        text.contains("chatgpt"),
        "Die native CLI meldet keine ChatGPT-Abonnement-Anmeldung"
    );
    Ok(None)
}

enum Chunk {
    Data(Vec<u8>),
}

fn pump(mut source: impl Read + Send + 'static, tx: mpsc::SyncSender<Chunk>) {
    thread::spawn(move || {
        let mut buf = [0u8; 4096];
        loop {
            match source.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    if tx.send(Chunk::Data(buf[..n].to_vec())).is_err() {
                        break;
                    }
                }
            }
        }
    });
}

struct Session {
    path: PathBuf,
    data: Value,
}

impl Session {
    fn update(&mut self, values: Value) -> Result<()> {
        if let (Some(target), Some(src)) = (self.data.as_object_mut(), values.as_object()) {
            for (k, v) in src {
                target.insert(k.clone(), v.clone());
            }
            target.insert("updated_at".into(), json!(now()));
        }
        write_private(&self.path, &self.data)
    }
    fn state(&self) -> &str {
        self.data["state"].as_str().unwrap_or_default()
    }
}

/// Entry point for `--login-worker HOME ID`; owns one native login process.
pub fn login_worker(home: &Path, id: &str) -> Result<()> {
    let p = paths(home, id)?;
    let data = status(home, id)?;
    ensure!(data["state"] == "starting", "Login session is not starting");
    let mut db = Db::open(home)?;
    let mut session = Session {
        path: p.state.clone(),
        data,
    };
    let mut proc: Option<Child> = None;
    let mut completed = false;
    let mut owns = false;
    let mut profile = Value::Null;
    let mut authdir = PathBuf::new();
    let outcome = run_session(
        &mut db,
        &p,
        &mut session,
        &mut proc,
        &mut owns,
        &mut profile,
        &mut authdir,
    );
    match outcome {
        Ok(done) => completed = done,
        Err(e) if is_busy(&e) => {
            if !owns {
                if let Some(mut c) = proc.take() {
                    kill_tree(&mut c);
                }
                return Err(anyhow!(WorkerBusy));
            }
            let _ = session.update(json!({"state": "failed",
                "message": "Dieser Account wird gerade verwendet. Versuche die Anmeldung später erneut."}));
        }
        Err(e) => {
            let message: String = redact(&e.to_string()).chars().take(500).collect();
            let _ = session.update(json!({"state": "failed", "message": message}));
        }
    }
    if let Some(mut c) = proc.take() {
        kill_tree(&mut c);
    }
    remove(&p.input);
    remove(&p.cancel);
    if !active(&session.data["state"]) {
        let _ = session.update(json!({"url": null, "device_code": null}));
    }
    drop(db);
    if completed {
        // Refresh the same read model used by the UI; no inference turn.
        let mut source = profile.clone();
        source["enabled"] = json!(true);
        source["managed"] = json!(true);
        source["authdir"] = json!(authdir.to_string_lossy());
        let _ = crate::monitor::read_source(home, &source, &*crate::monitor::native_probe());
        session.update(json!({"state": "succeeded", "message": "Account verbunden.", "url": null, "device_code": null}))?;
        remove(&p.input);
        remove(&p.cancel);
        return Ok(());
    }
    bail!("Login session ended without success: {}", session.state())
}

fn run_session(
    db: &mut Db,
    p: &SessionPaths,
    session: &mut Session,
    proc: &mut Option<Child>,
    owns: &mut bool,
    profile_out: &mut Value,
    authdir_out: &mut PathBuf,
) -> Result<bool> {
    let name = session.data["profile"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let profile = db.profile(&name)?;
    let authdir = db.authdir(&name)?;
    *profile_out = profile.clone();
    *authdir_out = authdir.clone();
    let provider = profile["provider"].as_str().unwrap_or_default().to_string();
    // Only one daemon may own this session, even after an uncertain client retry.
    let _session_lock = Lease::acquire(&p.lock)?;
    *owns = true;
    let _account_lock = Lease::acquire(&authdir.join(".native.lock"))?;
    if provider == "codex" {
        let config = authdir.join("config.toml");
        if !config.exists() {
            let mut options = fs::OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut f = options.open(&config)?;
            f.write_all(b"cli_auth_credentials_store = \"file\"\n")?;
        }
    } else {
        check_claude_directory(&profile, &authdir)?;
    }
    let mut cmd = profile_command(&profile, &authdir)?;
    if provider == "codex" {
        cmd.args(["login", "--device-auth"]);
    } else {
        cmd.args(["auth", "login", "--claudeai"]);
    }
    cmd.envs([("BROWSER", "echo"), ("CI", "1"), ("TERM", "dumb")])
        .current_dir(&authdir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    let (tx, rx) = mpsc::sync_channel::<Chunk>(8192);
    pump(
        child.stdout.take().context("Missing native stdout")?,
        tx.clone(),
    );
    pump(child.stderr.take().context("Missing native stderr")?, tx);
    let mut stdin = child.stdin.take();
    *proc = Some(child);
    let mut raw: Vec<u8> = vec![];
    let mut last_write: Option<Instant> = None;
    loop {
        let running = proc
            .as_mut()
            .map(|c| matches!(c.try_wait(), Ok(None)))
            .unwrap_or(false);
        if running && p.cancel.exists() {
            session.update(json!({"state": "cancelled", "message": "Anmeldung abgebrochen."}))?;
            return Ok(false);
        }
        if running && now() > session.data["expires_at"].as_f64().unwrap_or(0.0) {
            session.update(
                json!({"state": "expired", "message": "Anmeldung abgelaufen. Bitte neu starten."}),
            )?;
            return Ok(false);
        }
        if let Ok(Chunk::Data(bytes)) = rx.recv_timeout(Duration::from_millis(100)) {
            raw.extend(bytes);
            while raw.len() <= MAX_OUTPUT {
                match rx.try_recv() {
                    Ok(Chunk::Data(more)) => raw.extend(more),
                    Err(_) => break,
                }
            }
            ensure!(
                raw.len() <= MAX_OUTPUT,
                "Unexpectedly large native login output"
            );
        }
        if last_write.is_none_or(|t| t.elapsed() > Duration::from_millis(300)) {
            let text = String::from_utf8_lossy(&raw).into_owned();
            let mut changes = observe(&provider, &text);
            if session.state() == "verifying" && !paste_prompt(&text) {
                changes.remove("state");
                changes.remove("message");
            }
            // Every write doubles as the heartbeat read by `status`.
            session.update(Value::Object(changes))?;
            last_write = Some(Instant::now());
        }
        if p.input.exists() {
            let incoming: Value = serde_json::from_str(&fs::read_to_string(&p.input)?)?;
            remove(&p.input);
            let code = incoming["code"]
                .as_str()
                .ok_or_else(|| anyhow!("Invalid login code"))?
                .to_string();
            raw.clear();
            if let Some(pipe) = stdin.as_mut() {
                pipe.write_all(format!("{code}\n").as_bytes())?;
                pipe.flush()?;
            }
            session
                .update(json!({"state": "verifying", "message": "Anmeldung wird bestätigt …"}))?;
        }
        let exit = proc.as_mut().and_then(|c| c.try_wait().ok().flatten());
        if let Some(status) = exit {
            if !status.success() {
                // Native diagnostics may contain secrets; use a safe actionable message.
                bail!("Anmeldung fehlgeschlagen. Prüfe, ob Device-Login erlaubt ist und der Anbieter erreichbar ist.");
            }
            drop(stdin.take());
            let cached = verify(&profile, &authdir)?;
            if let Some(cached) = cached {
                db.cache(&name, &cached)?;
            }
            db.update_profile(
                &name,
                json!({"enabled": true, "hold_until": null, "hold_reason": null, "checked_at": null, "observed_at": null}),
            )?;
            session.update(
                json!({"state": "verifying", "message": "Account-Daten werden abgerufen …"}),
            )?;
            return Ok(true);
        }
    }
}

/// `--login-cancel HOME TARGET ID`: cancel locally (`-`) or through a configured remote.
pub fn login_cancel(home: &Path, target: &str, id: &str) -> Result<()> {
    if target == "-" {
        cancel(home, id)?;
    } else {
        let config = crate::remote::RemoteConfig::new(home).get(target)?;
        crate::remote::RemoteClient::new(&config)?.data(&[
            "auth".into(),
            "cancel".into(),
            id.into(),
        ])?;
    }
    Ok(())
}
