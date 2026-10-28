//! Strict argument grammar mirroring the Python argparse contract in `agent_pool/cli.py`.
//! Unknown commands, operations, options, extra positionals and conflicting groups are rejected.
use anyhow::{anyhow, bail, Result};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy)]
struct Opt {
    name: &'static str,
    value: bool,
    choices: &'static [&'static str],
    required: bool,
    /// Options sharing a nonzero group are mutually exclusive.
    group: u8,
}

const fn flag(name: &'static str) -> Opt {
    Opt {
        name,
        value: false,
        choices: &[],
        required: false,
        group: 0,
    }
}
const fn val(name: &'static str) -> Opt {
    Opt {
        name,
        value: true,
        choices: &[],
        required: false,
        group: 0,
    }
}
const fn req(name: &'static str) -> Opt {
    Opt {
        name,
        value: true,
        choices: &[],
        required: true,
        group: 0,
    }
}
const fn grouped(name: &'static str, group: u8) -> Opt {
    Opt {
        name,
        value: true,
        choices: &[],
        required: false,
        group,
    }
}
const PROVIDERS: &[&str] = &["codex", "claude"];
const fn provider_opt() -> Opt {
    Opt {
        name: "--provider",
        value: true,
        choices: PROVIDERS,
        required: true,
        group: 0,
    }
}

struct Cmd {
    positionals: Vec<(&'static str, bool)>,
    opts: Vec<Opt>,
    /// Groups where exactly one member is required.
    required_groups: Vec<u8>,
}

impl Cmd {
    fn new(positionals: &[(&'static str, bool)], opts: &[Opt]) -> Self {
        Self {
            positionals: positionals.to_vec(),
            opts: opts.to_vec(),
            required_groups: vec![],
        }
    }
    fn requiring(mut self, groups: &[u8]) -> Self {
        self.required_groups = groups.to_vec();
        self
    }
}

const PLACE: u8 = 1;
const TEXT: u8 = 2;
const CODE: u8 = 3;

fn task_opts() -> Vec<Opt> {
    vec![
        provider_opt(),
        val("--profile"),
        val("--model"),
        val("--bucket"),
        grouped("--cwd", PLACE),
        grouped("--workspace", PLACE),
        grouped("--prompt", TEXT),
        grouped("--prompt-file", TEXT),
        flag("--allow-edits"),
        val("--key"),
        val("--timeout"),
        val("--max-attempts"),
    ]
}

/// Commands that take an operation word.
pub fn operations(action: &str) -> Option<&'static [&'static str]> {
    Some(match action {
        "auth" => &["start", "get", "input", "cancel"],
        "workspace" => &["list", "add", "remove"],
        "remote" => &["list", "add", "remove", "test", "discover"],
        "profile" => &["add", "list", "enable", "disable", "release"],
        "quota" => &["show", "refresh", "set"],
        "job" => &["submit", "list", "get", "wait", "retry", "cancel"],
        _ => return None,
    })
}

pub const ACTIONS: &[&str] = &[
    "init",
    "rpc",
    "auth",
    "status",
    "overview",
    "monitor",
    "workspace",
    "service",
    "remote",
    "connection-info",
    "doctor",
    "desktop",
    "profile",
    "login",
    "quota",
    "job",
    "work",
    "run",
];

fn spec(action: &str, op: Option<&str>) -> Option<Cmd> {
    let name = [("name", false)];
    let id = [("id", false)];
    Some(match (action, op) {
        ("init" | "rpc" | "connection-info" | "doctor" | "desktop", None) => Cmd::new(&[], &[]),
        ("status" | "monitor" | "overview", None) => Cmd::new(&[], &[flag("--refresh")]),
        ("service", None) => Cmd::new(&[], &[req("--exec")]),
        ("login", None) => Cmd::new(&name, &[flag("--device-auth")]),
        ("work", None) => Cmd::new(&[], &[flag("--once"), flag("--drain"), val("--poll")]),
        ("run", None) => {
            let mut opts = task_opts();
            opts.push(val("--wait-seconds"));
            Cmd::new(&[], &opts).requiring(&[TEXT])
        }
        ("auth", Some("start")) => Cmd::new(&name, &[provider_opt(), req("--key")]),
        ("auth", Some("get" | "cancel")) => Cmd::new(&id, &[]),
        ("auth", Some("input")) => Cmd::new(
            &id,
            &[grouped("--code", CODE), grouped("--code-file", CODE)],
        )
        .requiring(&[CODE]),
        ("workspace", Some("list"))
        | ("remote", Some("list"))
        | ("profile", Some("list"))
        | ("job", Some("list")) => Cmd::new(&[], &[]),
        ("workspace", Some("add")) => Cmd::new(&name, &[req("--path")]),
        ("workspace", Some("remove")) => Cmd::new(&name, &[]),
        ("remote", Some("add")) => Cmd::new(
            &name,
            &[req("--host"), val("--command"), req("--server-home")],
        ),
        ("remote", Some("remove" | "test")) => Cmd::new(&name, &[]),
        ("remote", Some("discover")) => Cmd::new(&[("host", false)], &[]),
        ("profile", Some("add")) => Cmd::new(
            &name,
            &[provider_opt(), val("--binary"), val("--auth-home")],
        ),
        ("profile", Some("enable" | "disable" | "release")) => Cmd::new(&name, &[]),
        ("quota", Some("show" | "refresh")) => Cmd::new(&[("name", true)], &[]),
        ("quota", Some("set")) => Cmd::new(
            &name,
            &[
                Opt {
                    name: "--window",
                    value: true,
                    choices: &["five-hour", "weekly"],
                    required: true,
                    group: 0,
                },
                req("--used"),
                req("--reset-at"),
                val("--model"),
                val("--bucket"),
            ],
        ),
        ("job", Some("submit")) => Cmd::new(&[], &task_opts()).requiring(&[TEXT]),
        ("job", Some("get")) => Cmd::new(&id, &[flag("--result-only")]),
        ("job", Some("wait")) => Cmd::new(&id, &[val("--seconds")]),
        ("job", Some("retry")) => Cmd::new(&id, &[flag("--acknowledge-review")]),
        ("job", Some("cancel")) => Cmd::new(&id, &[]),
        _ => return None,
    })
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Args {
    pub remote: Option<String>,
    pub version: bool,
    pub action: String,
    pub op: Option<String>,
    pub pos: BTreeMap<String, String>,
    pub opts: BTreeMap<String, String>,
    pub flags: BTreeSet<String>,
}

impl Args {
    pub fn op(&self) -> &str {
        self.op.as_deref().unwrap_or("")
    }
    pub fn pos(&self, name: &str) -> Option<&str> {
        self.pos.get(name).map(String::as_str)
    }
    pub fn need(&self, name: &str) -> Result<&str> {
        self.pos(name)
            .ok_or_else(|| anyhow!("Missing argument: {name}"))
    }
    pub fn opt(&self, name: &str) -> Option<&str> {
        self.opts.get(name).map(String::as_str)
    }
    pub fn flag(&self, name: &str) -> bool {
        self.flags.contains(name)
    }
    pub fn float(&self, name: &str, default: f64) -> Result<f64> {
        match self.opt(name) {
            None => Ok(default),
            Some(v) => {
                py_float(v).ok_or_else(|| anyhow!("argument {name}: invalid float value: '{v}'"))
            }
        }
    }
    pub fn int(&self, name: &str, default: i64) -> Result<i64> {
        match self.opt(name) {
            None => Ok(default),
            Some(v) => {
                let t = v.trim().replace('_', "");
                t.parse::<i64>()
                    .map_err(|_| anyhow!("argument {name}: invalid int value: '{v}'"))
            }
        }
    }
}

pub fn py_float(value: &str) -> Option<f64> {
    let t = value.trim();
    let lower = t.to_ascii_lowercase();
    let unsigned = lower.trim_start_matches(['+', '-']);
    if matches!(unsigned, "nan" | "inf" | "infinity") {
        let negative = lower.starts_with('-');
        return Some(match unsigned {
            "nan" => f64::NAN,
            _ if negative => f64::NEG_INFINITY,
            _ => f64::INFINITY,
        });
    }
    if t.is_empty() || t.contains(|c: char| c.is_alphabetic() && c != 'e' && c != 'E') {
        return None;
    }
    t.replace('_', "").parse().ok()
}

/// Python `str(float)` for values forwarded to a remote server.
pub fn py_float_str(value: f64) -> String {
    if value.is_finite() && value.fract() == 0.0 && value.abs() < 1e16 {
        format!("{value:.1}")
    } else {
        format!("{value}")
    }
}

fn negative_number(tok: &str) -> bool {
    let rest = &tok[1..];
    (!rest.is_empty() && rest.chars().all(|c| c.is_ascii_digit()))
        || rest.split_once('.').is_some_and(|(a, b)| {
            a.chars().all(|c| c.is_ascii_digit())
                && !b.is_empty()
                && b.chars().all(|c| c.is_ascii_digit())
        })
}

fn looks_like_option(tok: &str) -> bool {
    tok.len() > 1 && tok.starts_with('-') && !negative_number(tok)
}

/// Explicit `-h/--help`; local `execute` renders it with code 0, RPC rejects it.
#[derive(Debug)]
pub struct Help(pub String);
impl std::fmt::Display for Help {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Help {}

fn is_help(tok: &str) -> bool {
    tok == "-h" || tok == "--help"
}

fn root_usage() -> String {
    let mut lines = vec![
        "usage: agent-fleet [--home HOME] [--remote NAME] [--version] ACTION ...".to_string(),
        String::new(),
        "Local durable job broker for native Codex and Claude Code.".into(),
        String::new(),
        "actions:".into(),
    ];
    for action in ACTIONS {
        match operations(action) {
            Some(ops) => lines.push(format!("  {action} {{{}}}", ops.join(","))),
            None => lines.push(format!("  {action}")),
        }
    }
    lines.push(String::new());
    lines.push("Run `agent-fleet ACTION [OPERATION] --help` for its options.".into());
    lines.join("\n") + "\n"
}

fn group_usage(action: &str, ops: &[&str]) -> String {
    let mut lines = vec![
        format!("usage: agent-fleet {action} {{{}}} ...", ops.join(",")),
        String::new(),
    ];
    for op in ops {
        if let Some(cmd) = spec(action, Some(op)) {
            lines.push(format!(
                "  {}",
                usage(action, Some(op), &cmd).trim_start_matches("usage: ")
            ));
        }
    }
    lines.join("\n") + "\n"
}

fn usage(action: &str, op: Option<&str>, cmd: &Cmd) -> String {
    let mut parts = vec![format!("usage: agent-fleet {action}")];
    if let Some(op) = op {
        parts.push(op.into());
    }
    for (name, optional) in &cmd.positionals {
        parts.push(if *optional {
            format!("[{name}]")
        } else {
            name.to_string()
        });
    }
    for o in &cmd.opts {
        let text = if o.value {
            format!("{} VALUE", o.name)
        } else {
            o.name.to_string()
        };
        parts.push(if o.required {
            text
        } else {
            format!("[{text}]")
        });
    }
    parts.join(" ")
}

/// Parses argv that excludes `--home`; it may begin with `--remote NAME`.
pub fn parse(argv: &[String]) -> Result<Args> {
    let mut args = Args::default();
    let mut i = 0;
    while i < argv.len() && argv[i].starts_with('-') {
        let tok = argv[i].as_str();
        if tok == "--remote" {
            let v = argv.get(i + 1).filter(|v| !looks_like_option(v));
            args.remote = Some(
                v.ok_or_else(|| anyhow!("argument --remote: expected one argument"))?
                    .clone(),
            );
            i += 2;
        } else if let Some(v) = tok.strip_prefix("--remote=") {
            args.remote = Some(v.into());
            i += 1;
        } else if is_help(tok) {
            bail!(Help(root_usage()));
        } else if tok == "--version" {
            args.version = true;
            return Ok(args);
        } else if tok == "--home" || tok.starts_with("--home=") {
            bail!("--home is supplied by the caller, not inside argv");
        } else {
            bail!("unrecognized arguments: {tok}");
        }
    }
    let action = argv
        .get(i)
        .ok_or_else(|| anyhow!("the following arguments are required: action"))?;
    if !ACTIONS.contains(&action.as_str()) {
        bail!("invalid choice: '{action}'");
    }
    args.action = action.clone();
    i += 1;
    if let Some(ops) = operations(action) {
        let op = argv
            .get(i)
            .ok_or_else(|| anyhow!("the following arguments are required: operation"))?;
        if is_help(op) {
            bail!(Help(group_usage(action, ops)));
        }
        if !ops.contains(&op.as_str()) {
            bail!("invalid choice: '{op}'");
        }
        args.op = Some(op.clone());
        i += 1;
    }
    let cmd = spec(&args.action, args.op.as_deref()).ok_or_else(|| anyhow!("Unknown command"))?;
    let mut positionals = vec![];
    let mut only_positional = false;
    let mut seen_group: BTreeMap<u8, &'static str> = BTreeMap::new();
    while i < argv.len() {
        let tok = argv[i].as_str();
        i += 1;
        if !only_positional && tok == "--" {
            only_positional = true;
            continue;
        }
        if only_positional || !looks_like_option(tok) {
            positionals.push(tok.to_string());
            continue;
        }
        if is_help(tok) {
            bail!(Help(usage(&args.action, args.op.as_deref(), &cmd) + "\n"));
        }
        if !tok.starts_with("--") {
            bail!("unrecognized arguments: {tok}");
        }
        let (name, inline) = match tok.split_once('=') {
            Some((n, v)) => (n, Some(v.to_string())),
            None => (tok, None),
        };
        let opt = match cmd.opts.iter().find(|o| o.name == name) {
            Some(o) => *o,
            None => {
                // argparse accepts unambiguous prefixes of long options.
                let matches: Vec<&Opt> = cmd
                    .opts
                    .iter()
                    .filter(|o| o.name.starts_with(name))
                    .collect();
                match matches.as_slice() {
                    [one] => **one,
                    [] => bail!("unrecognized arguments: {tok}"),
                    _ => bail!("ambiguous option: {name}"),
                }
            }
        };
        if opt.group != 0 {
            if let Some(other) = seen_group.get(&opt.group) {
                if *other != opt.name {
                    bail!("argument {}: not allowed with argument {}", opt.name, other);
                }
            }
            seen_group.insert(opt.group, opt.name);
        }
        if opt.value {
            let value = match inline {
                Some(v) => v,
                None => {
                    let next = argv
                        .get(i)
                        .filter(|v| !looks_like_option(v) && v.as_str() != "--");
                    i += 1;
                    next.ok_or_else(|| anyhow!("argument {}: expected one argument", opt.name))?
                        .clone()
                }
            };
            if !opt.choices.is_empty() && !opt.choices.contains(&value.as_str()) {
                bail!("argument {}: invalid choice: '{}'", opt.name, value);
            }
            args.opts.insert(opt.name.into(), value);
        } else {
            if inline.is_some() {
                bail!("argument {}: ignored explicit argument", opt.name);
            }
            args.flags.insert(opt.name.into());
        }
    }
    let mut remaining = positionals.into_iter();
    for (name, optional) in &cmd.positionals {
        match remaining.next() {
            Some(v) => {
                args.pos.insert(name.to_string(), v);
            }
            None if *optional => {}
            None => bail!("the following arguments are required: {name}"),
        }
    }
    let extra: Vec<String> = remaining.collect();
    if !extra.is_empty() {
        bail!("unrecognized arguments: {}", extra.join(" "));
    }
    for o in &cmd.opts {
        if o.required && !args.opts.contains_key(o.name) {
            bail!("the following arguments are required: {}", o.name);
        }
    }
    for g in &cmd.required_groups {
        if !seen_group.contains_key(g) {
            let names: Vec<&str> = cmd
                .opts
                .iter()
                .filter(|o| o.group == *g)
                .map(|o| o.name)
                .collect();
            bail!("one of the arguments {} is required", names.join(" "));
        }
    }
    Ok(args)
}
