//! Generate, never silently install or restart, a persistent Linux worker.
use anyhow::{ensure, Result};

pub fn quote(value: &str) -> Result<String> {
    ensure!(
        !value.chars().any(|c| (c as u32) < 32),
        "Control characters are not permitted in service paths"
    );
    Ok(format!(
        "\"{}\"",
        value
            .replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('%', "%%")
            .replace('$', "$$")
    ))
}

pub fn unit(executable: &str, home: &str) -> Result<String> {
    ensure!(
        executable.starts_with('/') && home.starts_with('/'),
        "Service executable and home must be absolute paths"
    );
    Ok(format!(
        "[Unit]
Description=Agent Fleet durable personal worker
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
ExecStart={} --home {} work
Restart=on-failure
RestartSec=10
UMask=0077
KillMode=control-group
TimeoutStopSec=30
Environment=\"PATH=%h/.local/bin:%h/.npm-global/bin:%h/.npm/bin:/usr/local/bin:/usr/bin:/bin\"
NoNewPrivileges=yes

[Install]
WantedBy=default.target
",
        quote(executable)?,
        quote(home)?
    ))
}
