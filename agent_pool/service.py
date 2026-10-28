"""Generate, never silently install or restart, a persistent Linux worker."""
from pathlib import PurePosixPath


def quote(value):
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control characters are not permitted in service paths")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def unit(executable, home):
    if not PurePosixPath(executable).is_absolute() or not PurePosixPath(home).is_absolute():
        raise ValueError("Service executable and home must be absolute paths")
    return f'''[Unit]
Description=Agent Fleet durable personal worker
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
ExecStart={quote(executable)} --home {quote(home)} work
Restart=on-failure
RestartSec=10
UMask=0077
KillMode=control-group
TimeoutStopSec=30
Environment="PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin"
NoNewPrivileges=yes

[Install]
WantedBy=default.target
'''
