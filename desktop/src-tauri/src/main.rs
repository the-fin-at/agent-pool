#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use serde::Serialize;
use serde_json::Value;
use std::{collections::HashMap, path::PathBuf, sync::Mutex};
use tauri::{Manager, State};

struct AppState {
    home: PathBuf,
    target: Option<String>,
    logins: Mutex<HashMap<String, Option<String>>>,
}
#[derive(Serialize)]
struct InitialConfig {
    home: String,
    target: Option<String>,
    version: &'static str,
}
#[tauri::command]
fn initial_config(state: State<'_, AppState>) -> InitialConfig {
    InitialConfig {
        home: state.home.to_string_lossy().into_owned(),
        target: state.target.clone(),
        version: fleet_core::VERSION,
    }
}
fn ui_allowed(argv: &[String]) -> bool {
    match argv.first().map(String::as_str) {
        Some("overview" | "status" | "monitor" | "doctor" | "connection-info") => true,
        Some("remote") => argv
            .get(1)
            .is_some_and(|s| ["list", "add", "remove", "test", "discover"].contains(&s.as_str())),
        Some("profile") => argv
            .get(1)
            .is_some_and(|s| ["list", "enable", "disable", "release"].contains(&s.as_str())),
        Some("workspace") => argv.get(1).is_some_and(|s| s == "list"),
        Some("quota") => argv.get(1).is_some_and(|s| s == "show"),
        Some("job") => argv
            .get(1)
            .is_some_and(|s| ["list", "get"].contains(&s.as_str())),
        Some("auth") => argv
            .get(1)
            .is_some_and(|s| ["start", "get", "input", "cancel"].contains(&s.as_str())),
        _ => false,
    }
}
#[tauri::command]
async fn fleet_request(
    state: State<'_, AppState>,
    target: Option<String>,
    argv: Vec<String>,
) -> Result<Value, String> {
    if !ui_allowed(&argv)
        || serde_json::to_vec(&argv).map_err(|e| e.to_string())?.len() > 2 * 1024 * 1024
    {
        return Err("Dieser Aufruf ist in der App nicht erlaubt".into());
    }
    let home = state.home.clone();
    let for_tracking = argv.clone();
    let selected = target.clone();
    if argv.first().map(String::as_str) == Some("auth")
        && argv.get(1).map(String::as_str) == Some("start")
    {
        if let Some(at) = argv.iter().position(|s| s == "--key") {
            if let Some(id) = argv.get(at + 1) {
                state
                    .logins
                    .lock()
                    .map_err(|_| "Anmeldestatus nicht verfügbar")?
                    .insert(id.clone(), target.clone());
            }
        }
    }
    let value = tauri::async_runtime::spawn_blocking(move || {
        let mut args = argv;
        if let Some(target) = target {
            args.splice(0..0, ["--remote".into(), target]);
        }
        let reply = fleet_core::execute(&home, &args)
            .map_err(|e| fleet_core::provider::redact(&e.to_string()))?;
        let value: Value = serde_json::from_str(&reply.output)
            .map_err(|_| "Ungültige Antwort der Auftragsverwaltung".to_string())?;
        if reply.code == 1 && value.get("status").is_none() {
            return Err(value["error"]
                .as_str()
                .unwrap_or("Aufruf fehlgeschlagen")
                .to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|e| e.to_string())?;
    if let Ok(data) = &value {
        let action = for_tracking.first().map(String::as_str);
        let op = for_tracking.get(1).map(String::as_str);
        if action == Some("auth")
            && (op == Some("cancel")
                || data["state"]
                    .as_str()
                    .is_some_and(|s| ["succeeded", "failed", "cancelled", "expired"].contains(&s)))
        {
            if let Some(id) = data["id"]
                .as_str()
                .or_else(|| for_tracking.get(2).map(String::as_str))
            {
                let mut l = state
                    .logins
                    .lock()
                    .map_err(|_| "Anmeldestatus nicht verfügbar")?;
                if l.get(id) == Some(&selected) {
                    l.remove(id);
                }
            }
        }
    }
    value
}
#[tauri::command]
fn open_login_url(url: String) -> Result<(), String> {
    validate_login_url(&url)?;
    let mut c = if cfg!(target_os = "macos") {
        std::process::Command::new("open")
    } else if cfg!(windows) {
        let mut c = std::process::Command::new("rundll32.exe");
        c.arg("url.dll,FileProtocolHandler");
        c
    } else {
        std::process::Command::new("xdg-open")
    };
    c.arg(url)
        .spawn()
        .map_err(|_| "Browser konnte nicht geöffnet werden")?;
    Ok(())
}
fn validate_login_url(url: &str) -> Result<(), String> {
    let u = url::Url::parse(url).map_err(|_| "Ungültige Anmeldeseite")?;
    if u.scheme() != "https"
        || !u.username().is_empty()
        || u.password().is_some()
        || u.port_or_known_default() != Some(443)
        || !u.host_str().is_some_and(|h| {
            [
                "auth.openai.com",
                "chatgpt.com",
                "claude.ai",
                "claude.com",
                "console.anthropic.com",
                "platform.claude.com",
            ]
            .contains(&h)
        })
    {
        return Err("Diese Anmeldeseite ist nicht freigegeben".into());
    }
    Ok(())
}

fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args
        .first()
        .is_some_and(|s| s == "--login-worker" || s == "--login-cancel")
    {
        std::process::exit(fleet_cli::run(args));
    }
    let mut home = fleet_core::default_home();
    let mut target = None;
    let mut at = 0;
    while at < args.len() {
        match args[at].as_str() {
            "--home" if at + 1 < args.len() => {
                home = PathBuf::from(&args[at + 1]);
                at += 2;
            }
            "--remote" if at + 1 < args.len() => {
                target = Some(args[at + 1].clone());
                at += 2;
            }
            _ => {
                at += 1;
            }
        }
    }
    let builder = tauri::Builder::default()
        .manage(AppState {
            home,
            target,
            logins: Mutex::new(HashMap::new()),
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let state = window.state::<AppState>();
                if let Ok(logins) = state.logins.lock() {
                    for (id, target) in logins.iter() {
                        if let Ok(exe) = std::env::current_exe() {
                            let mut c = std::process::Command::new(exe);
                            c.args([
                                "--login-cancel",
                                &state.home.to_string_lossy(),
                                target.as_deref().unwrap_or("-"),
                                id,
                            ]);
                            c.stdin(std::process::Stdio::null())
                                .stdout(std::process::Stdio::null())
                                .stderr(std::process::Stdio::null());
                            #[cfg(unix)]
                            {
                                use std::os::unix::process::CommandExt;
                                c.process_group(0);
                            }
                            let _ = c.spawn();
                        }
                    }
                };
            }
        });
    #[cfg(debug_assertions)]
    let builder = builder
        .invoke_handler(tauri::generate_handler![
            initial_config,
            fleet_request,
            open_login_url,
            test_report
        ])
        .on_page_load(|window, payload| {
            if payload.event() == tauri::webview::PageLoadEvent::Finished {
                if let Ok(path) = std::env::var("AGENT_FLEET_TEST_SCRIPT") {
                    if let Ok(script) = std::fs::read_to_string(path) {
                        let _ = window.eval(&script);
                    }
                };
            }
        });
    #[cfg(not(debug_assertions))]
    let builder = builder.invoke_handler(tauri::generate_handler![
        initial_config,
        fleet_request,
        open_login_url
    ]);
    builder
        .run(tauri::generate_context!())
        .expect("Agent Fleet konnte nicht gestartet werden");
}

// The native acceptance harness is absent from optimized release builds.
#[cfg(debug_assertions)]
#[tauri::command]
fn test_report(app: tauri::AppHandle, result: Value) -> Result<(), String> {
    let path =
        std::env::var("AGENT_FLEET_TEST_REPORT").map_err(|_| "No native test report configured")?;
    std::fs::write(
        path,
        serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    app.exit(if result["passed"] == true { 0 } else { 1 });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_official_https_login_origins_can_open_a_browser() {
        for good in [
            "https://auth.openai.com/codex/device",
            "https://claude.com/oauth/authorize?state=fixture",
            "https://platform.claude.com/",
        ] {
            assert!(validate_login_url(good).is_ok(), "{good}");
        }
        for bad in [
            "javascript:alert(1)",
            "file:///etc/passwd",
            "http://claude.com",
            "https://claude.com.attacker.invalid",
            "https://attacker@claude.com",
            "https://claude.com:444",
            "https://claude.com@attacker.invalid",
        ] {
            assert!(validate_login_url(bad).is_err(), "{bad}");
        }
    }
    #[test]
    fn webview_cannot_start_workers_or_register_native_executables() {
        for argv in [
            vec!["work"],
            vec!["profile", "add"],
            vec!["workspace", "add"],
            vec!["quota", "set"],
            vec!["rpc"],
            vec!["--remote", "x"],
        ] {
            assert!(!ui_allowed(
                &argv.into_iter().map(str::to_string).collect::<Vec<_>>()
            ));
        }
    }
}
