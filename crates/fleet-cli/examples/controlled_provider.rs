//! Native controlled-provider acceptance fixture. No network, credentials or inference.
use serde_json::{json, Value};
use std::{
    env, fs,
    io::{self, BufRead, Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs_f64()
}
fn main() {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args == ["--sleep-child"] {
        thread::sleep(Duration::from_secs(60));
        return;
    }
    if args == ["--version"] {
        println!("controlled-native-provider-0.5");
        return;
    }
    let codex = env::var_os("CODEX_HOME").is_some();
    let home = PathBuf::from(
        env::var_os(if codex {
            "CODEX_HOME"
        } else {
            "CLAUDE_CONFIG_DIR"
        })
        .unwrap_or_else(|| {
            PathBuf::from(env::var_os("HOME").expect("isolated fixture HOME"))
                .join(".claude")
                .into_os_string()
        }),
    );
    let config_override = env::var_os("CLAUDE_CONFIG_DIR").is_some();
    let accepted = home.join("fixture-accepted");
    let logged_in =
        accepted.exists() && !(config_override && home.join("fixture-default-only").exists());
    if args == ["app-server"] {
        if home.join("fixture-metadata-error").exists() {
            eprintln!("Controlled metadata unavailable");
            std::process::exit(1);
        }
        for line in io::stdin().lock().lines() {
            let Ok(line) = line else { break };
            let r: Value = serde_json::from_str(&line).unwrap();
            if r["method"] == "initialized" {
                continue;
            }
            let result = match r["method"].as_str().unwrap_or("") {
                "account/read" => {
                    json!({"account":if accepted.exists(){json!({"email":"rust-fixture@example.invalid","type":"chatgpt","planType":"team"})}else{Value::Null}})
                }
                "account/rateLimits/read" => {
                    if let Ok(raw) = fs::read_to_string(home.join("fixture-ratelimits.json")) {
                        serde_json::from_str(&raw).unwrap()
                    } else {
                        json!({"rateLimits":{"primary":{"usedPercent":25,"windowDurationMins":300,"resetsAt":now()+600.},"secondary":{"usedPercent":40,"windowDurationMins":10080,"resetsAt":now()+3600.}}})
                    }
                }
                _ => json!({}),
            };
            println!("{}", json!({"id":r["id"],"result":result}));
            io::stdout().flush().unwrap();
        }
        return;
    }
    if args == ["login", "status"] {
        if accepted.exists() {
            println!("Logged in using ChatGPT");
            return;
        }
        std::process::exit(1);
    }
    if args == ["auth", "status"] {
        if home.join("fixture-metadata-error").exists() {
            eprintln!("Controlled metadata unavailable");
            std::process::exit(2);
        }
        println!(
            "{}",
            json!({"loggedIn":logged_in,"authMethod":if logged_in{"claude.ai"}else{"none"},"email":fs::read_to_string(home.join("fixture-email")).unwrap_or_else(|_|"rust-fixture@example.invalid".into()).trim(),"subscriptionType":"max","configDirectory":fs::canonicalize(&home).unwrap()})
        );
        std::process::exit(if logged_in { 0 } else { 1 });
    }
    if args.first().is_some_and(|s| s == "login" || s == "auth") {
        fs::write(
            home.join("fixture-parent.pid"),
            std::process::id().to_string(),
        )
        .unwrap();
        if codex {
            println!("Open https://auth.openai.com/codex/device\nEnter this code: ABCD-EFGHI");
            io::stdout().flush().unwrap();
            let until = now() + 30.;
            while !accepted.exists() && now() < until {
                thread::sleep(Duration::from_millis(30));
            }
            if !accepted.exists() {
                std::process::exit(1);
            }
        } else {
            print!("Visit https://claude.com/oauth/authorize?state=fixture-only\nPaste code here if prompted > ");
            io::stdout().flush().unwrap();
            let mut input = io::stdin().lock();
            loop {
                let mut code = String::new();
                if input.read_line(&mut code).unwrap() == 0 {
                    std::process::exit(1);
                }
                if code.trim() == "fixture-authorized-code" {
                    break;
                }
                // Claude 2.1.312 waits for another line after rejecting a code,
                // without printing the original paste prompt again.
                eprintln!("Invalid code. Please make sure the full code was copied.");
                io::stderr().flush().unwrap();
            }
            fs::write(&accepted, "fixture-only").unwrap();
        }
        println!("Login successful");
        return;
    }
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
    ] {
        assert!(
            env::var_os(key).is_none(),
            "Ambient billing configuration leaked"
        );
    }
    let mut prompt = String::new();
    io::stdin().read_to_string(&mut prompt).unwrap();
    let mut trace = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(home.join("fixture-executions.jsonl"))
        .unwrap();
    writeln!(
        trace,
        "{}",
        json!({"prompt":prompt,"pid":std::process::id(),"config_override":config_override})
    )
    .unwrap();
    drop(trace);
    fs::write(
        home.join("fixture-parent.pid"),
        std::process::id().to_string(),
    )
    .unwrap();
    if prompt == "__barrier_wait__" || prompt == "__barrier_interrupt__" {
        let mode = if prompt == "__barrier_wait__" {
            "wait"
        } else {
            "interrupt"
        };
        let mut child = if mode == "interrupt" {
            assert!(args
                .windows(2)
                .any(|a| a == ["--sandbox", "workspace-write"]));
            fs::write(
                "fixture-interrupt-effect",
                "partial controlled edit before interruption",
            )
            .unwrap();
            let child = Command::new(env::current_exe().unwrap())
                .arg("--sleep-child")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            fs::write(home.join("fixture-child.pid"), child.id().to_string()).unwrap();
            Some(child)
        } else {
            None
        };
        let marker = home.join(format!("fixture-barrier-{mode}.ready"));
        let release = home.join(format!("fixture-barrier-{mode}.release"));
        fs::write(
            marker.with_extension("staged"),
            json!({"pid":std::process::id(),"child_pid":child.as_ref().map(|c|c.id())}).to_string(),
        )
        .unwrap();
        fs::rename(marker.with_extension("staged"), marker).unwrap();
        let until = now() + 30.;
        while !release.exists() && now() < until {
            thread::sleep(Duration::from_millis(20));
        }
        if let Some(child) = child.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }
        assert!(release.exists(), "Controlled barrier expired");
    }
    if prompt == "__timeout__" {
        let mut child = Command::new(env::current_exe().unwrap())
            .arg("--sleep-child")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        fs::write(home.join("fixture-child.pid"), child.id().to_string()).unwrap();
        thread::sleep(Duration::from_secs(60));
        let _ = child.wait();
        return;
    }
    if prompt == "__quota__" || home.join("fixture-quota-reject").exists() {
        fs::write(home.join("fixture-ratelimits.json"), json!({"rateLimits":{"primary":{"usedPercent":100,"windowDurationMins":300,"resetsAt":now()+600.}}}).to_string()).unwrap();
        if args
            .windows(2)
            .any(|a| a == ["--sandbox", "workspace-write"])
        {
            fs::write("fixture-edit-effect", "partial controlled edit").unwrap();
        }
        println!(
            "{}",
            json!({"type":"error","message":"usage_limit_reached"})
        );
        std::process::exit(1);
    }
    if codex {
        let at = args
            .iter()
            .position(|s| s == "--sandbox")
            .expect("sandbox argument");
        let result = format!("{}: {prompt}", args[at + 1]);
        if let Some(at) = args.iter().position(|s| s == "--output-last-message") {
            fs::write(&args[at + 1], &result).unwrap();
        }
        println!(
            "{}",
            json!({"type":"item.completed","item":{"type":"agent_message","text":result}})
        );
        println!("{}", json!({"type":"turn.completed"}));
    } else {
        println!(
            "{}",
            json!({"type":"rate_limit_event","rate_limit_info":{"status":"allowed","utilization":0.2,"rateLimitType":"five_hour","resetsAt":now()+600.,"unifiedWindows":{"five_hour":{"utilization":0.2,"resetsAt":now()+600.,"status":"allowed"},"seven_day":{"utilization":0.42,"resetsAt":now()+3600.,"status":"allowed"}}}})
        );
        println!(
            "{}",
            json!({"type":"result","subtype":"success","is_error":false,"result":format!("Claude: {prompt}")})
        );
    }
}
