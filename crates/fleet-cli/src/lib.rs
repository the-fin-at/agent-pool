use serde_json::{json, Value};
use std::{
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
const MAX_REQUEST: u64 = 2 * 1024 * 1024;
fn error(message: impl std::fmt::Display) -> i32 {
    println!(
        "{}",
        json!({"error":fleet_core::provider::redact(&message.to_string())})
    );
    1
}
pub fn main_entry() -> i32 {
    run(std::env::args().skip(1).collect())
}
pub fn run(mut argv: Vec<String>) -> i32 {
    if argv.first().map(String::as_str) == Some("--login-worker") {
        if argv.len() != 3 {
            return error("Invalid login worker arguments");
        }
        return match fleet_core::login_worker(Path::new(&argv[1]), &argv[2]) {
            Ok(()) => 0,
            Err(e) => error(e),
        };
    }
    if argv.first().map(String::as_str) == Some("--login-cancel") {
        if argv.len() != 4 {
            return error("Invalid login cancellation arguments");
        }
        let mut cmd = vec![];
        if argv[2] != "-" {
            cmd.extend(["--remote".into(), argv[2].clone()]);
        }
        cmd.extend(["auth".into(), "cancel".into(), argv[3].clone()]);
        return match fleet_core::execute(Path::new(&argv[1]), &cmd) {
            Ok(r) => r.code,
            Err(_) => 1,
        };
    }
    let mut home = fleet_core::default_home();
    let mut remote = None;
    while let Some(first) = argv.first().cloned() {
        if first == "--version" || first == "-V" {
            println!("{}", fleet_core::VERSION);
            return 0;
        }
        if first == "--home" || first == "--remote" {
            if argv.len() < 2 {
                return error(format!("Missing value for {first}"));
            }
            let value = argv.remove(1);
            argv.remove(0);
            if first == "--home" {
                home = PathBuf::from(value);
            } else {
                remote = Some(value);
            }
            continue;
        }
        if let Some(value) = first.strip_prefix("--home=") {
            home = PathBuf::from(value);
            argv.remove(0);
            continue;
        }
        if let Some(value) = first.strip_prefix("--remote=") {
            remote = Some(value.into());
            argv.remove(0);
            continue;
        }
        break;
    }
    if argv.is_empty() || matches!(argv[0].as_str(), "--help" | "-h") {
        println!("Agent Fleet {}\nNative Rust task broker and Tauri desktop.\n\nUsage: agent-fleet [--home PATH] [--remote NAME] COMMAND\n\nCommands: desktop, init, doctor, connection-info, overview, status, monitor,\n          remote, profile, login, auth, workspace, quota, job, work, run, service\n\nExisting AgentPool state directories and RPC v1 remain compatible.\nUse COMMAND --help for command details.",fleet_core::VERSION);
        return 0;
    }
    if argv[0] == "rpc" {
        if argv.len() != 1 || remote.is_some() {
            return error("Invalid RPC invocation");
        }
        let mut raw = vec![];
        if let Err(e) = std::io::stdin().take(MAX_REQUEST + 1).read_to_end(&mut raw) {
            return error(e);
        }
        let request = if raw.len() as u64 > MAX_REQUEST {
            Err("Remote request exceeds 2 MiB".to_string())
        } else {
            serde_json::from_slice::<Value>(&raw).map_err(|_| "Invalid request JSON".into())
        };
        let reply = match request {
            Ok(v) => fleet_core::rpc(&home, v),
            Err(e) => json!({"version":1,"code":1,"output":json!({"error":e}).to_string()}),
        };
        println!("{reply}");
        return 0;
    }
    if argv[0] == "desktop" {
        if argv.len() != 1 {
            return error("Unexpected desktop arguments");
        }
        return match launch_desktop(&home, remote.as_deref()) {
            Ok(()) => {
                println!(
                    "{}",
                    json!({"desktop":"opened","home":home,"remote":remote})
                );
                0
            }
            Err(e) => error(e),
        };
    }
    if let Some(remote) = remote {
        argv.splice(0..0, ["--remote".into(), remote]);
    }
    match fleet_core::execute(&home, &argv) {
        Ok(reply) => {
            print!("{}", reply.output);
            if !reply.output.ends_with('\n') {
                println!();
            }
            let _ = std::io::stdout().flush();
            reply.code
        }
        Err(e) => error(e),
    }
}
fn launch_desktop(home: &Path, remote: Option<&str>) -> Result<(), String> {
    let mut args = vec!["--home".to_string(), home.to_string_lossy().into_owned()];
    if let Some(r) = remote {
        args.extend(["--remote".into(), r.into()]);
    }
    if let Some(path) = std::env::var_os("AGENT_FLEET_DESKTOP_BIN") {
        let path = PathBuf::from(path);
        if !path.is_file() {
            return Err(
                "AGENT_FLEET_DESKTOP_BIN must point to the installed native desktop executable"
                    .into(),
            );
        }
        return spawn_desktop(&path, &args);
    }
    if cfg!(target_os = "macos") {
        for app in [
            dirs_home().join("Applications/Agent Fleet.app"),
            PathBuf::from("/Applications/Agent Fleet.app"),
        ] {
            if app.is_dir() {
                Command::new("open")
                    .arg("-n")
                    .arg(app)
                    .arg("--args")
                    .args(&args)
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()
                    .map_err(|e| e.to_string())?;
                return Ok(());
            }
        }
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let name = if cfg!(windows) {
        "agent-fleet-desktop.exe"
    } else {
        "agent-fleet-desktop"
    };
    let mut candidates = vec![exe
        .parent()
        .ok_or("Missing executable directory")?
        .join(name)];
    if cfg!(windows) {
        // Tauri NSIS currentUser installs under LOCALAPPDATA/productName, separate from the CLI.
        for key in ["LOCALAPPDATA", "ProgramFiles", "ProgramW6432"] {
            if let Some(base) = std::env::var_os(key) {
                candidates.push(PathBuf::from(base).join("Agent Fleet").join(name));
            }
        }
    }
    let desktop = candidates.into_iter().find(|p| p.is_file()).ok_or(
        "Install the native Agent Fleet desktop app, or set AGENT_FLEET_DESKTOP_BIN to a custom installation path"
    )?;
    spawn_desktop(&desktop, &args)
}
fn spawn_desktop(desktop: &Path, args: &[String]) -> Result<(), String> {
    Command::new(desktop)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn dirs_home() -> PathBuf {
    if cfg!(windows) {
        std::env::var_os("USERPROFILE")
    } else {
        std::env::var_os("HOME")
    }
    .map(PathBuf::from)
    .unwrap_or_default()
}
