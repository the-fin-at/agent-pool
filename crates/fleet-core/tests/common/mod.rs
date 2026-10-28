#![allow(dead_code)]
use fleet_core::db::Db;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

pub struct Pool {
    pub tmp: tempfile::TempDir,
    pub home: PathBuf,
    pub cwd: PathBuf,
}

impl Pool {
    pub fn new() -> Self {
        let tmp = tempfile::tempdir().unwrap();
        let root = fleet_core::db::canonical(tmp.path()).unwrap();
        let home = root.join("state");
        let cwd = root.join("repo");
        std::fs::create_dir_all(&cwd).unwrap();
        Db::open(&home).unwrap();
        Self { tmp, home, cwd }
    }
    pub fn root(&self) -> PathBuf {
        self.home.parent().unwrap().to_owned()
    }
    pub fn db(&self) -> Db {
        Db::open(&self.home).unwrap()
    }
    pub fn run(&self, argv: &[&str]) -> (i32, String) {
        let argv: Vec<String> = argv.iter().map(|s| s.to_string()).collect();
        match fleet_core::execute(&self.home, &argv) {
            Ok(r) => (r.code, r.output),
            Err(e) => (1, fleet_core::commands::error_reply(&e).output),
        }
    }
    pub fn json(&self, argv: &[&str]) -> (i32, Value) {
        let (code, out) = self.run(argv);
        (code, serde_json::from_str(&out).unwrap_or(json!(out)))
    }
    pub fn rpc(&self, argv: &[&str]) -> (i64, Value) {
        let reply = fleet_core::rpc(&self.home, json!({"version": 1, "argv": argv}));
        let output = reply["output"].as_str().unwrap();
        (
            reply["code"].as_i64().unwrap(),
            serde_json::from_str(output).unwrap_or(json!(output)),
        )
    }
}

/// Writes an executable POSIX shell fixture (never contacts a provider).
#[cfg(unix)]
pub fn script(dir: &Path, name: &str, body: &str) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;
    let path = dir.join(name);
    std::fs::write(&path, format!("#!/bin/sh\n{body}")).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
    path
}

pub fn wait_until(seconds: f64, mut f: impl FnMut() -> bool) -> bool {
    let until = Instant::now() + Duration::from_secs_f64(seconds);
    while Instant::now() < until {
        if f() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    f()
}

#[cfg(unix)]
pub fn alive(pid: i32) -> bool {
    unsafe { libc::kill(pid, 0) == 0 }
}

/// Controlled Codex/Claude fixture covering exec, app-server, login and status.
pub const FAKE_NATIVE: &str = r#"
home="${CODEX_HOME:-$CLAUDE_CONFIG_DIR}"
if [ -n "$CODEX_HOME" ]; then provider=codex; else provider=claude; fi
accepted="$home/fixture-accepted"
case "$1 $2" in
  "login status")
    [ -f "$accepted" ] || exit 1
    echo "Logged in using ChatGPT"; exit 0;;
  "auth status")
    if [ -f "$accepted" ]; then
      echo "{\"loggedIn\":true,\"authMethod\":\"claude.ai\",\"email\":\"fixture@example.invalid\",\"subscriptionType\":\"max\",\"configDirectory\":\"$home\"}"; exit 0
    fi
    echo "{\"loggedIn\":false,\"authMethod\":\"none\",\"configDirectory\":\"$home\"}"; exit 1;;
  "login --device-auth")
    echo $$ > "$home/fixture-native.pid"
    echo "Open https://auth.openai.com/codex/device"
    echo "Enter this code: ABCD-EFGHI"
    n=0
    while [ ! -f "$accepted" ]; do sleep 0.1; n=$((n+1)); [ $n -gt 300 ] && exit 1; done
    echo "Login successful"; exit 0;;
  "auth login")
    echo $$ > "$home/fixture-native.pid"
    printf 'Visit https://claude.com/oauth/authorize?state=fixture-only\nPaste code here if prompted > '
    read code
    [ "$code" = "fixture-authorized-code" ] || exit 1
    echo fixture-only > "$accepted"
    echo "Login successful"; exit 0;;
esac
if [ "$1" = "app-server" ]; then
  while IFS= read -r line; do
    case "$line" in *'"initialized"'*) continue;; esac
    id=$(printf '%s' "$line" | sed 's/^{"id":\([0-9]*\).*/\1/')
    case "$line" in
      *rateLimits*) echo "{\"id\":$id,\"result\":{\"rateLimits\":{\"primary\":{\"usedPercent\":25,\"windowDurationMins\":300,\"resetsAt\":9999999999}}}}";;
      *account/read*)
        if [ -f "$accepted" ]; then
          echo "{\"id\":$id,\"result\":{\"account\":{\"type\":\"chatgpt\",\"email\":\"fixture@example.invalid\",\"planType\":\"team\"}}}"
        else echo "{\"id\":$id,\"result\":{\"account\":null}}"; fi;;
      *) echo "{\"id\":$id,\"result\":{}}";;
    esac
  done
  exit 0
fi
if [ "$1" = "exec" ]; then
  prompt=$(cat)
  case "$prompt" in
    sleep*) sleep 60 & echo $! > "$PWD/child.pid"; echo $$ > "$PWD/native.pid"; wait; exit 0;;
  esac
  echo "{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"Worker report: $prompt\"}}"
  echo '{"type":"turn.completed","usage":{"input_tokens":1}}'
  exit 0
fi
if [ "$1" = "--print" ]; then
  prompt=$(cat)
  echo '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","utilization":0.2,"rateLimitType":"five_hour","resetsAt":9999999999}}'
  echo "{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"result\":\"Worker report: $prompt\"}"
  exit 0
fi
if [ "$1" = "--version" ]; then echo "fixture 1.0"; exit 0; fi
exit 3
"#;
