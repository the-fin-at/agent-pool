//! SSH transports only versioned JSON; credentials and SQLite stay on the server.
use crate::db::private_dir;
use crate::provider::{capture, plain_command};
use anyhow::{anyhow, bail, ensure, Result};
use regex::Regex;
use serde_json::{json, Map, Value};
use std::io::Write;
use std::path::{Path, PathBuf};

pub const PROTOCOL: i64 = 1;
pub const MAX_REQUEST: usize = 2 * 1024 * 1024;
pub const MAX_RESPONSE: usize = 10 * 1024 * 1024;

pub struct RemoteConfig {
    pub home: PathBuf,
    pub path: PathBuf,
}

impl RemoteConfig {
    pub fn new(home: &Path) -> Self {
        Self {
            home: home.to_owned(),
            path: home.join("remotes.json"),
        }
    }

    pub fn all(&self) -> Result<Map<String, Value>> {
        if !self.path.exists() {
            return Ok(Map::new());
        }
        let data: Value = serde_json::from_str(&std::fs::read_to_string(&self.path)?)
            .map_err(|_| anyhow!("Invalid remotes.json"))?;
        match data {
            Value::Object(m) => Ok(m),
            _ => bail!("Invalid remotes.json"),
        }
    }

    pub fn get(&self, name: &str) -> Result<Value> {
        let data = self.all()?;
        let value = data
            .get(name)
            .ok_or_else(|| anyhow!("Unknown SSH remote: {name}"))?;
        validate(value)
    }

    pub fn add(&self, name: &str, host: &str, command: &str, home: &str) -> Result<()> {
        ensure!(
            !name.trim().is_empty()
                && name == name.trim()
                && name.chars().count() <= 64
                && !name.chars().any(|c| (c as u32) < 32),
            "Verbindungsname: 1 bis 64 sichtbare Zeichen"
        );
        let folded = name.to_lowercase();
        ensure!(
            folded != "lokal" && folded != "local",
            "Dieser Name ist für den lokalen Rechner reserviert"
        );
        let value = validate(&json!({"host": host, "command": command, "home": home}))?;
        let mut data = self.all()?;
        ensure!(
            !data.contains_key(name),
            "Remote already exists; remove it explicitly before replacing"
        );
        data.insert(name.into(), value);
        self.save(&data)
    }

    pub fn remove(&self, name: &str) -> Result<()> {
        let mut data = self.all()?;
        ensure!(data.remove(name).is_some(), "Unknown SSH remote: {name}");
        self.save(&data)
    }

    fn save(&self, data: &Map<String, Value>) -> Result<()> {
        private_dir(&self.home)?;
        let mut tmp = tempfile::Builder::new()
            .prefix(".remotes-")
            .tempfile_in(&self.home)?;
        tmp.write_all(serde_json::to_string_pretty(data)?.as_bytes())?;
        tmp.as_file().sync_all()?;
        crate::db::private_file(tmp.path())?;
        tmp.persist(&self.path).map_err(|e| e.error)?;
        Ok(())
    }
}

pub fn validate(config: &Value) -> Result<Value> {
    let map = config
        .as_object()
        .ok_or_else(|| anyhow!("Invalid remote configuration"))?;
    let mut keys: Vec<&str> = map.keys().map(String::as_str).collect();
    keys.sort_unstable();
    ensure!(
        keys == ["command", "home", "host"],
        "Invalid remote configuration"
    );
    let host_ok = map["host"].as_str().is_some_and(|h| {
        Regex::new(r"^[A-Za-z0-9_][A-Za-z0-9_.@:\[\]-]{0,254}$")
            .unwrap()
            .is_match(h)
    });
    ensure!(
        host_ok,
        "Use an SSH config alias or user@host, without options or spaces"
    );
    let command = map["command"].as_str().filter(|c| !c.is_empty());
    let command = command.ok_or_else(|| anyhow!("Remote executable must be a nonempty string"))?;
    let home = map["home"].as_str().filter(|h| h.starts_with('/'));
    let home = home.ok_or_else(|| {
        anyhow!("Specify --server-home with the absolute state directory used by the worker")
    })?;
    for value in [command, home] {
        ensure!(
            !value.chars().any(|c| (c as u32) < 32),
            "Invalid remote executable or state path"
        );
    }
    ensure!(
        !command.starts_with('-'),
        "Remote state path must be absolute; executable cannot be an option"
    );
    Ok(json!({"host": map["host"], "command": command, "home": home}))
}

/// Python `shlex.quote` semantics for the remote POSIX shell.
pub fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".into();
    }
    let safe = value
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || "_@%+=:,./-".contains(c));
    if safe {
        value.into()
    } else {
        format!("'{}'", value.replace('\'', "'\"'\"'"))
    }
}

const SSH_OPTIONS: [&str; 6] = [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ForwardAgent=no",
];

/// Fixed probe; never interpolates user data into the remote shell.
pub fn discover(host: &str, timeout: f64) -> Result<Value> {
    validate(&json!({"host": host, "command": "agent-fleet", "home": "/"}))?;
    let script = "if command -v agent-fleet >/dev/null 2>&1; then exec agent-fleet connection-info; \
elif [ -x \"$HOME/.local/bin/agent-fleet\" ]; then exec \"$HOME/.local/bin/agent-fleet\" connection-info; \
elif command -v agent-pool >/dev/null 2>&1; then exec agent-pool connection-info; \
else echo \"Agent Fleet is not installed on this server\" >&2; exit 127; fi";
    let mut cmd = plain_command(Path::new("ssh"));
    cmd.arg("-T")
        .args(SSH_OPTIONS)
        .args(["-o", "ConnectTimeout=10", host, script]);
    let done = capture(cmd, None, timeout, MAX_RESPONSE as u64)?;
    ensure!(
        !done.timed_out,
        "Der Server antwortet nicht. Prüfe Adresse und SSH-Zugang."
    );
    if done.code != 0 {
        let err = done.err.trim();
        let tail: String = err
            .chars()
            .rev()
            .take(400)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        bail!("Verbindung nicht möglich. Agent Fleet und SSH-Schlüsselzugang müssen auf dem Server eingerichtet sein. {tail}");
    }
    let parsed = (|| -> Result<Value> {
        let data: Value = serde_json::from_str(&done.out)?;
        let config =
            validate(&json!({"host": host, "command": data["command"], "home": data["home"]}))?;
        let has = data["features"]
            .as_array()
            .is_some_and(|f| f.iter().any(|x| x == "native-login-sessions"));
        ensure!(has, "Bitte Agent Fleet auf dem Server aktualisieren");
        Ok(config)
    })();
    parsed.map_err(|_| {
        anyhow!("Server benötigt die aktuelle Agent-Fleet-Version. Bei eingeschränkten SSH-Schlüsseln die erweiterten Einstellungen verwenden.")
    })
}

pub struct RemoteClient {
    pub config: Value,
}

#[derive(Debug)]
pub struct RemoteReply {
    pub code: i32,
    pub output: String,
}

impl RemoteClient {
    pub fn new(config: &Value) -> Result<Self> {
        Ok(Self {
            config: validate(config)?,
        })
    }

    /// Only validated configuration tokens enter the remote shell; prompts travel on stdin.
    pub fn argv(&self, action: &str, interactive: bool, extra: &[String]) -> Vec<String> {
        let mut remote = vec![
            self.config["command"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            "--home".into(),
            self.config["home"].as_str().unwrap_or_default().to_string(),
            action.into(),
        ];
        remote.extend(extra.iter().cloned());
        let joined = remote
            .iter()
            .map(|s| shell_quote(s))
            .collect::<Vec<_>>()
            .join(" ");
        let mut argv: Vec<String> =
            vec!["ssh".into(), if interactive { "-tt" } else { "-T" }.into()];
        argv.extend(SSH_OPTIONS.iter().map(|s| s.to_string()));
        argv.extend(
            [
                "-o",
                "ConnectTimeout=10",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=2",
            ]
            .iter()
            .map(|s| s.to_string()),
        );
        argv.push(self.config["host"].as_str().unwrap_or_default().into());
        argv.push(joined);
        argv
    }

    pub fn request(&self, argv: &[String]) -> Result<RemoteReply> {
        self.request_timeout(argv, 120.0)
    }

    pub fn request_timeout(&self, argv: &[String], timeout: f64) -> Result<RemoteReply> {
        let payload = serde_json::to_string(&json!({"version": PROTOCOL, "argv": argv}))?;
        ensure!(payload.len() <= MAX_REQUEST, "Remote request exceeds 2 MiB");
        let ssh = self.argv("rpc", false, &[]);
        let mut cmd = plain_command(Path::new(&ssh[0]));
        cmd.args(&ssh[1..]);
        let done = capture(
            cmd,
            Some(payload.as_bytes()),
            timeout,
            MAX_RESPONSE as u64 + 1,
        )?;
        ensure!(
            !done.timed_out,
            "SSH timed out. Submission outcome may be unknown; repeat the identical --key or list jobs. Never retry with a new key."
        );
        if done.code != 0 {
            let err = done.err.trim();
            let tail: String = err
                .chars()
                .rev()
                .take(1200)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect();
            bail!(
                "SSH/RPC exited {}. Submission may have reached the server; inspect jobs or reuse the identical --key. {tail}",
                done.code
            );
        }
        ensure!(
            !done.overflow && done.out.len() <= MAX_RESPONSE,
            "Remote response exceeds 10 MiB"
        );
        parse_reply(&done.out)
    }

    /// Decoded output; code 1 becomes an error carrying the server message.
    pub fn data(&self, argv: &[String]) -> Result<Value> {
        let reply = self.request(argv)?;
        let data: Value = serde_json::from_str(&reply.output)
            .map_err(|_| anyhow!("Invalid remote command response"))?;
        if reply.code == 1 {
            let mut error = data["error"]
                .as_str()
                .unwrap_or("Remote operation failed")
                .to_string();
            if argv.first().is_some_and(|a| a == "auth") && error == "RPC operation not allowed" {
                error = "Bitte Agent Fleet auf dem Server aktualisieren, um Accounts direkt in der App anzumelden.".into();
            }
            bail!(error);
        }
        Ok(data)
    }
}

pub fn parse_reply(stdout: &str) -> Result<RemoteReply> {
    let result: Value = serde_json::from_str(stdout.trim()).map_err(|_| {
        anyhow!("Invalid remote JSON; verify agent-pool installation and a quiet SSH shell")
    })?;
    let ok = result.is_object()
        && result.get("version").and_then(Value::as_i64) == Some(PROTOCOL)
        && result.get("version").is_some_and(Value::is_i64)
        && result
            .get("code")
            .and_then(Value::as_i64)
            .is_some_and(|c| (0..=2).contains(&c))
        && result.get("output").is_some_and(Value::is_string);
    ensure!(ok, "Incompatible remote protocol");
    Ok(RemoteReply {
        code: result["code"].as_i64().unwrap_or(1) as i32,
        output: result["output"].as_str().unwrap_or_default().to_string(),
    })
}
