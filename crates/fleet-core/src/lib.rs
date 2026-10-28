//! Native Agent Fleet core: durable queue, scheduling, native provider adapters,
//! login sessions and the version-1 SSH RPC endpoint. State is interoperable with Python 0.4.x.
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub mod args;
pub mod commands;
pub mod db;
pub mod login;
pub mod monitor;
pub mod provider;
pub mod quota;
pub mod remote;
pub mod service;
pub mod worker;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Result of one command: process exit code and its stdout (JSON for all commands
/// except `service`, `job get --result-only` and `--version`, which print plain text).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Reply {
    pub code: i32,
    pub output: String,
}

/// `AGENT_POOL_HOME`, else the platform's existing AgentPool state directory.
pub fn default_home() -> PathBuf {
    db::default_home()
}

/// Runs one command. `argv` excludes `--home` and may begin with `--remote NAME`.
/// Local errors are returned as `Err`; use [`commands::error_reply`] to render them.
/// `overview [--refresh]` is a local-only addition that includes the default Codex source.
pub fn execute(home: &Path, argv: &[String]) -> anyhow::Result<Reply> {
    commands::execute(home, argv)
}

/// Version-1 RPC envelope for one decoded request (same allowlist and limits as Python `rpc.py`).
pub fn rpc(home: &Path, request: serde_json::Value) -> serde_json::Value {
    commands::rpc(home, request)
}

/// Raw-stdin variant of [`rpc`] enforcing the 2 MiB request limit and UTF-8/JSON validity.
pub fn rpc_bytes(home: &Path, raw: &[u8]) -> serde_json::Value {
    commands::rpc_bytes(home, raw)
}

/// Body of `--login-worker HOME ID`; runs detached from any client.
pub fn login_worker(home: &Path, id: &str) -> anyhow::Result<()> {
    login::login_worker(home, id)
}

/// Body of `--login-cancel HOME TARGET ID` (`TARGET` is `-` for local).
pub fn login_cancel(home: &Path, target: &str, id: &str) -> anyhow::Result<()> {
    login::login_cancel(home, target, id)
}
