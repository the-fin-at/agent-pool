"""SSH transports only versioned JSON; credentials and SQLite stay on the server."""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .providers import spawn_options
from .store import private_dir

VERSION = 1
MAX_REQUEST = 2 * 1024 * 1024
MAX_RESPONSE = 10 * 1024 * 1024


class RemoteConfig:
    def __init__(self, home):
        self.home = Path(home)
        self.path = self.home / "remotes.json"

    def all(self):
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid remotes.json")
        return data

    def get(self, name):
        data = self.all()
        if name not in data:
            raise ValueError("Unknown SSH remote: " + name)
        return validate(data[name])

    def add(self, name, host, command="agent-fleet", home=None):
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 64 or any(ord(c) < 32 for c in name):
            raise ValueError("Verbindungsname: 1 bis 64 sichtbare Zeichen")
        if name.casefold() in {"lokal", "local"}:
            raise ValueError("Dieser Name ist für den lokalen Rechner reserviert")
        value = validate({"host": host, "command": command, "home": home})
        data = self.all()
        if name in data:
            raise ValueError("Remote already exists; remove it explicitly before replacing")
        data[name] = value
        self._save(data)

    def remove(self, name):
        data = self.all()
        if name not in data:
            raise ValueError("Unknown SSH remote: " + name)
        del data[name]
        self._save(data)

    def _save(self, data):
        private_dir(self.home)
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=self.home, prefix=".remotes-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def validate(config):
    if not isinstance(config, dict) or set(config) != {"host", "command", "home"}:
        raise ValueError("Invalid remote configuration")
    host, command, home = config["host"], config["command"], config["home"]
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:\[\]-]{0,254}", host):
        raise ValueError("Use an SSH config alias or user@host, without options or spaces")
    if not isinstance(command, str) or not command:
        raise ValueError("Remote executable must be a nonempty string")
    if not isinstance(home, str) or not home.startswith('/'):
        raise ValueError("Specify --server-home with the absolute state directory used by the worker")
    for value in (command, home):
        if value is not None and (not isinstance(value, str) or not value or any(ord(c) < 32 for c in value)):
            raise ValueError("Invalid remote executable or state path")
    if command.startswith('-') or (home is not None and not home.startswith('/')):
        raise ValueError("Remote state path must be absolute; executable cannot be an option")
    return dict(config)


def discover(host, timeout=20):
    """Fixed probe, never interpolates user data into the remote shell."""
    validate({"host": host, "command": "agent-fleet", "home": "/"})
    script = ('if command -v agent-fleet >/dev/null 2>&1; then exec agent-fleet connection-info; '
              'elif [ -x "$HOME/.local/bin/agent-fleet" ]; then exec "$HOME/.local/bin/agent-fleet" connection-info; '
              'elif command -v agent-pool >/dev/null 2>&1; then exec agent-pool connection-info; '
              'else echo "Agent Fleet is not installed on this server" >&2; exit 127; fi')
    try:
        done = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no",
                               "-o", "ConnectTimeout=10", host, script], capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                              **spawn_options(hidden=True))
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Der Server antwortet nicht. Prüfe Adresse und SSH-Zugang.") from exc
    if done.returncode:
        raise ValueError("Verbindung nicht möglich. Agent Fleet und SSH-Schlüsselzugang müssen auf dem Server eingerichtet sein. " + done.stderr.strip()[-400:])
    try:
        data = json.loads(done.stdout)
        config = validate({"host": host, "command": data["command"], "home": data["home"]})
        if "native-login-sessions" not in data.get("features", []):
            raise ValueError("Bitte Agent Fleet auf dem Server aktualisieren")
        return config
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Server benötigt die aktuelle Agent-Fleet-Version. Bei eingeschränkten SSH-Schlüsseln die erweiterten Einstellungen verwenden.") from exc


class RemoteClient:
    def __init__(self, config):
        self.config = validate(config)

    def command(self, action="rpc", interactive=False, extra=()):
        c = self.config
        remote = [c["command"]]
        if c["home"]:
            remote += ["--home", c["home"]]
        remote += [action, *extra]
        # The remote host uses a POSIX shell; only these configuration tokens enter it.
        # Prompts never enter this command line. SSH uses host-key checking as configured.
        return ["ssh", "-tt" if interactive else "-T", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "ForwardAgent=no",
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=2", self.config["host"], shlex.join(remote)]

    def request(self, argv, timeout=120):
        payload = json.dumps({"version": VERSION, "argv": argv}, ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_REQUEST:
            raise ValueError("Remote request exceeds 2 MiB")
        try:
            done = subprocess.run(self.command(), input=payload, text=True, encoding="utf-8",
                                  capture_output=True, timeout=timeout, **spawn_options(hidden=True))
        except subprocess.TimeoutExpired as exc:
            raise ValueError("SSH timed out. Submission outcome may be unknown; repeat the identical --key or list jobs. Never retry with a new key.") from exc
        if done.returncode:
            raise ValueError(f"SSH/RPC exited {done.returncode}. Submission may have reached the server; inspect jobs or reuse the identical --key. " + done.stderr.strip()[-1200:])
        if len(done.stdout.encode("utf-8")) > MAX_RESPONSE:
            raise ValueError("Remote response exceeds 10 MiB")
        try:
            result = json.loads(done.stdout)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid remote JSON; verify agent-pool installation and a quiet SSH shell") from exc
        if (not isinstance(result, dict) or result.get("version") != VERSION or
                type(result.get("code")) is not int or result["code"] not in (0, 1, 2) or
                not isinstance(result.get("output"), str)):
            raise ValueError("Incompatible remote protocol")
        return result

    def data(self, argv):
        result = self.request(argv)
        try:
            data = json.loads(result["output"])
        except ValueError as exc:
            raise ValueError("Invalid remote command response") from exc
        if result["code"] == 1:
            error = data.get("error", "Remote operation failed") if isinstance(data, dict) else "Remote operation failed"
            if argv and argv[0] == "auth" and error == "RPC operation not allowed":
                error = "Bitte Agent Fleet auf dem Server aktualisieren, um Accounts direkt in der App anzumelden."
            raise ValueError(error)
        return data


def task_argv(args):
    if not args.workspace or args.cwd:
        raise ValueError("Remote tasks require --workspace <server-name>; local --cwd is not transferred")
    if not args.key:
        raise ValueError("Remote tasks require a stable --key for safe retries after disconnection")
    prompt = args.prompt
    if args.prompt_file:
        prompt = sys.stdin.read() if args.prompt_file == "-" else Path(args.prompt_file).read_text(encoding="utf-8")
    argv = ["job", "submit", "--provider", args.provider, "--workspace", args.workspace,
            "--prompt=" + prompt, "--key", args.key, "--timeout", str(args.timeout),
            "--max-attempts", str(args.max_attempts)]
    for field in ("profile", "model", "bucket"):
        if getattr(args, field):
            argv += ["--" + field, getattr(args, field)]
    if args.allow_edits:
        argv.append("--allow-edits")
    return argv


def dispatch_remote(args):
    from .cli import emit
    client = RemoteClient(RemoteConfig(args.home).get(args.remote))
    action = args.action
    if action == "desktop":
        from .cli import launch_desktop
        return launch_desktop(args.home, args.remote)
    if action == "auth":
        argv = ["auth", args.operation]
        if args.operation == "start":
            argv += [args.name, "--provider", args.provider, "--key", args.key]
        else:
            argv.append(args.id)
        if args.operation == "input":
            code = args.code
            if args.code_file:
                code = sys.stdin.read() if args.code_file == "-" else Path(args.code_file).read_text(encoding="utf-8")
            argv += ["--code=" + code.strip()]
        result = client.request(argv)
        print(result["output"], end="")
        return result["code"]
    if action == "login":
        extra = [args.name] + (["--device-auth"] if args.device_auth else [])
        return subprocess.call(client.command("login", interactive=True, extra=extra))
    if action == "work":
        raise ValueError("Run work as a persistent service on Linux; use docs/remote.md")
    if action == "run" or (action == "job" and args.operation == "submit"):
        if action == "run":
            import math
            if not math.isfinite(args.wait_seconds) or not 0 <= args.wait_seconds <= 60:
                raise ValueError("Remote run --wait-seconds must be between 0 and 60; use job get for later results")
        result = client.request(task_argv(args))
        if action == "run" and result["code"] == 0:
            job = json.loads(result["output"])
            result = client.request(["job", "wait", job["id"], "--seconds", str(args.wait_seconds)])
        print(result["output"], end="")
        return result["code"]
    if action == "init" or (action == "workspace" and args.operation != "list") or (action == "profile" and args.operation == "add"):
        raise ValueError("Perform initial setup and workspace/profile registration directly on the server")
    if action == "doctor":
        argv = [action]
    elif action in ("monitor", "status"):
        if args.refresh:
            raise ValueError("The persistent server worker refreshes metadata; read status without --refresh")
        argv = [action]
    elif action in ("profile", "workspace"):
        argv = [action, args.operation]
        if hasattr(args, "name"):
            argv.append(args.name)
        if action == "workspace" and args.operation == "add":
            argv += ["--path", args.path]
        if action == "profile" and args.operation == "add":
            argv += ["--provider", args.provider]
            if args.binary:
                argv += ["--binary", args.binary]
    elif action == "quota" and args.operation == "show":
        argv = [action, args.operation] + ([args.name] if args.name else [])
    elif action == "job":
        argv = [action, args.operation]
        if hasattr(args, "id"):
            argv.append(args.id)
        if args.operation == "wait":
            argv += ["--seconds", str(args.seconds)]
        if getattr(args, "acknowledge_review", False):
            argv.append("--acknowledge-review")
        if getattr(args, "result_only", False):
            argv.append("--result-only")
    else:
        raise ValueError("This operation must be performed directly on the server")
    result = client.request(argv)
    print(result["output"], end="")
    return result["code"]
