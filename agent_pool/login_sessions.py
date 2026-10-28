"""Bounded native login sessions; OAuth credentials remain entirely with provider CLIs."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import queue
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .providers import environment, executable, spawn_options, stop_process, redact
from .store import Store, private_dir, file_lock, WorkerBusy

TTL = 900
ACTIVE = {"starting", "awaiting_browser", "awaiting_code", "verifying"}
LOGIN_HOSTS = {"auth.openai.com", "chatgpt.com", "claude.ai", "claude.com", "console.anthropic.com", "platform.claude.com"}


def safe_url(value):
    try:
        parts = urlsplit(value)
        return (parts.scheme == "https" and parts.hostname in LOGIN_HOSTS and not parts.username
                and not parts.password and parts.port in (None, 443))
    except ValueError:
        return False


def folder(home):
    path = Path(home) / "login-sessions"
    private_dir(path)
    return path


def paths(home, ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident):
        raise ValueError("Invalid login session")
    root = folder(home)
    return root / (ident + ".json"), root / (ident + ".input"), root / (ident + ".cancel")


def write_private(path, data):
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".login-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def status(home, ident):
    state, inputfile, cancelfile = paths(home, ident)
    if not state.exists():
        raise ValueError("Unknown login session")
    data = json.loads(state.read_text(encoding="utf-8"))
    # A killed daemon cannot leave an eternally active login in the UI.
    if data["state"] in ACTIVE and (time.time() > data["expires_at"] or time.time()-data.get("updated_at", data["created_at"]) > 45):
        data.update(state="expired", url=None, device_code=None, message="Die Anmeldung ist abgelaufen. Bitte neu starten.")
        write_private(state, data)
        inputfile.unlink(missing_ok=True)
        cancelfile.unlink(missing_ok=True)
    return data


def worker_command(home, ident):
    argv = ["--login-worker", str(Path(home).resolve()), ident]
    if getattr(sys, "frozen", False):
        return [sys.executable, *argv]
    launch = Path(sys.argv[0]).resolve()
    if launch.is_file() and zipfile.is_zipfile(launch):
        return [sys.executable, str(launch), *argv]
    return [sys.executable, "-m", "agent_pool", *argv]


def start(home, name, provider, key, spawn=None):
    """Idempotent start; only provider-default binaries may be registered remotely."""
    if provider not in {"codex", "claude"}:
        raise ValueError("Choose Codex or Claude")
    if not re.fullmatch(r"[a-f0-9]{32}", key or ""):
        raise ValueError("A stable 32-character login key is required")
    store = Store(home)
    try:
        root = folder(store.home)
        with file_lock(root / ".start.lock"):
            state, _, _ = paths(store.home, key)
            if state.exists():
                old = status(store.home, key)
                if (old["profile"], old["provider"]) != (name, provider):
                    raise ValueError("Login key already belongs to another account")
                return old
            existing = [p for p in store.profiles() if p["name"] == name]
            if existing and existing[0]["provider"] != provider:
                raise ValueError("This profile belongs to a different provider")
            # Resolve before modifying the profile registry.
            executable(existing[0]["binary"] if existing else provider)
            active_count = 0
            for oldfile in root.glob("*.json"):
                try:old = status(store.home, oldfile.stem)
                except (ValueError,KeyError,TypeError):continue
                if old["state"] in ACTIVE:
                    active_count += 1
                    if old["profile"] == name:
                        raise ValueError("Anmeldung für dieses Profil läuft bereits")
            if active_count >= 4:
                raise ValueError("Es laufen bereits vier Anmeldungen. Schließe zuerst eine davon ab.")
            if not existing:
                store.add_profile(name, provider, provider)
            now = time.time()
            data = {"id": key, "profile": name, "provider": provider, "state": "starting",
                    "created_at": now, "updated_at": now, "expires_at": now+TTL,
                    "url": None, "device_code": None, "message": "Anmeldung wird vorbereitet …"}
            if paths(store.home,key)[2].exists():
                data.update(state="cancelled",message="Anmeldung abgebrochen.")
                paths(store.home,key)[2].unlink(missing_ok=True)
                write_private(state,data)
                return data
            write_private(state, data)
            try:
                cwd = str(Path(__file__).resolve().parents[1]) if not getattr(sys, "frozen", False) and Path(__file__).is_file() else str(store.home)
                command = worker_command(store.home,key)
                child = None
                # A transient user unit also survives logind session cleanup when available.
                if spawn is None and sys.platform.startswith("linux") and shutil.which("systemd-run"):
                    try:
                        launched = subprocess.run(["systemd-run","--user","--collect","--quiet",
                            "--unit=agent-fleet-login-"+key,"--working-directory="+cwd,
                            "--setenv=PATH="+os.environ.get("PATH", os.defpath),
                            "--property=RuntimeMaxSec=960","--property=UMask=0077","--property=KillMode=control-group",
                            "--",*command],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                        managed = launched.returncode == 0
                    except (OSError,subprocess.TimeoutExpired):managed = False
                else:managed = False
                if not managed:
                    launch = spawn or subprocess.Popen
                    child = launch(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, cwd=cwd, **spawn_options(hidden=True))
                if hasattr(child, "wait"):
                    threading.Thread(target=child.wait, daemon=True, name="login-reaper").start()
            except (OSError, ValueError) as exc:
                data.update(state="failed", message="Login-Prozess konnte nicht gestartet werden: "+redact(str(exc)))
                write_private(state, data)
            return data
    finally:
        store.close()


def provide_code(home, ident, code):
    if not isinstance(code, str) or not code.strip() or len(code) > 4096 or any(ord(c) < 32 for c in code.strip()):
        raise ValueError("Please paste the complete authorization code")
    data = status(home, ident)
    if data["provider"] != "claude" or data["state"] not in {"awaiting_browser", "awaiting_code"}:
        raise ValueError("This login is not waiting for a Claude authorization code")
    _, path, _ = paths(home, ident)
    write_private(path, {"code": code.strip()})
    return {"accepted": True, "id": ident}


def cancel(home, ident):
    state, _, path = paths(home, ident)
    if not state.exists():
        # Cancel may reach the server before an uncertain start request.
        write_private(path, {"cancel": True})
        return {"id": ident, "cancel_requested": True}
    data = status(home, ident)
    if data["state"] in ACTIVE:
        write_private(path, {"cancel": True})
    return {"id": ident, "cancel_requested": data["state"] in ACTIVE}


def observe(provider, raw):
    """Allowlist public login instructions; never persist raw CLI logs or tokens."""
    raw = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", raw)
    raw = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw)
    urls = [u.rstrip('.,);') for u in re.findall(r'https://[^\s\x1b<>"\']+', raw)]
    urls = [u for u in urls if safe_url(u)]
    result = {}
    if urls:
        result.update(url=urls[-1], state="awaiting_browser", message="Bestätige die Anmeldung im Browser.")
    if provider == "codex":
        codes = re.findall(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,5}\b", raw)
        if codes:
            result["device_code"] = codes[-1]
    elif (urls or not re.search(r"https://",raw)) and re.search(r"paste.*code|code here", raw, re.I):
        result.update(state="awaiting_code", message="Öffne die Anmeldeseite. Falls ein Code erscheint, füge ihn hier ein.")
    return result


def check_claude_directory(profile,authdir):
    done=subprocess.run([executable(profile["binary"]),"auth","status"],capture_output=True,text=True,encoding="utf-8",timeout=20,
        env=environment("claude",authdir),**spawn_options(hidden=True))
    try:data=json.loads(done.stdout)
    except ValueError as exc:
        raise ValueError("Bitte die native Claude-CLI aktualisieren; ihr Profilstatus konnte nicht geprüft werden.") from exc
    reported=data.get("configDirectory")
    if not reported or Path(reported).resolve()!=Path(authdir).resolve():
        raise ValueError("Die Claude-CLI bestätigt nicht das gewählte Profilverzeichnis. Bitte die CLI aktualisieren.")
    return data


def verify(profile, authdir):
    provider = profile["provider"]
    argv = [executable(profile["binary"]), "login", "status"] if provider == "codex" else [executable(profile["binary"]), "auth", "status"]
    done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=20,
                          env=environment(provider, authdir), **spawn_options(hidden=True))
    if done.returncode:
        raise ValueError("Der Anbieter hat die Anmeldung noch nicht bestätigt")
    if provider == "claude":
        data = json.loads(done.stdout)
        if not data.get("configDirectory") or Path(data["configDirectory"]).resolve()!=Path(authdir).resolve():
            raise ValueError("Die Claude-CLI hat ein anderes Profilverzeichnis verwendet")
        if not data.get("loggedIn") or data.get("authMethod") != "claude.ai":
            raise ValueError("Die native CLI meldet keine Claude-Abonnement-Anmeldung")
        return {"connected": True, "email": data.get("email"), "plan": data.get("subscriptionType"),
                "account_type": "claude.ai", "windows": [], "error": None,
                "checked_at": time.time(), "observed_at": None}
    if "chatgpt" not in (done.stdout+done.stderr).lower():
        raise ValueError("Die native CLI meldet keine ChatGPT-Abonnement-Anmeldung")
    return None


def run_worker(home, ident):
    statefile, inputfile, cancelfile = paths(home, ident)
    data = status(home, ident)
    if data["state"] != "starting":
        return 1
    store = Store(home)
    proc = None
    completed = False
    owns_session = False
    def update(**values):
        data.update(values, updated_at=time.time())
        write_private(statefile, data)
    try:
        profile = store.profile(data["profile"])
        authdir = store.authdir(profile["name"])
        # Only one daemon may own this session, even after an uncertain client retry.
        with file_lock(statefile.with_suffix(".lock")):
            owns_session = True
            with file_lock(authdir / ".native.lock"):
                if profile["provider"] == "codex":
                    config = authdir / "config.toml"
                    if not config.exists():
                        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "w", encoding="utf-8") as stream:
                            stream.write('cli_auth_credentials_store = "file"\n')
                if profile["provider"] == "claude":
                    check_claude_directory(profile,authdir)
                command = ([executable(profile["binary"]), "login", "--device-auth"] if profile["provider"] == "codex" else
                           [executable(profile["binary"]), "auth", "login", "--claudeai"])
                env = environment(profile["provider"], authdir)
                env.update(BROWSER="echo", CI="1", TERM="dumb")
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env=env, cwd=str(authdir), **spawn_options(hidden=True))
                events = queue.Queue(maxsize=8192)
                def reader():
                    while True:
                        chunk = proc.stdout.read(1)
                        if not chunk:
                            break
                        events.put(chunk)
                thread = threading.Thread(target=reader, daemon=True)
                thread.start()
                raw = bytearray()
                last_write = 0
                while True:
                    if proc.poll() is None and cancelfile.exists():
                        update(state="cancelled", message="Anmeldung abgebrochen.")
                        break
                    if proc.poll() is None and time.time() > data["expires_at"]:
                        update(state="expired", message="Anmeldung abgelaufen. Bitte neu starten.")
                        break
                    try:
                        chunk = events.get(timeout=.1)
                        raw.extend(chunk)
                        if len(raw) > 128*1024:
                            raise ValueError("Unexpectedly large native login output")
                        while not events.empty() and len(raw) <= 128*1024:
                            raw.extend(events.get_nowait())
                    except queue.Empty:
                        pass
                    if time.monotonic()-last_write > .3:
                        changes = observe(profile["provider"], raw.decode("utf-8", errors="replace"))
                        if data["state"] == "verifying" and not re.search(r"paste.*code|code here", raw.decode("utf-8",errors="replace"),re.I):
                            changes.pop("state", None)
                            changes.pop("message", None)
                        update(**changes)
                        last_write = time.monotonic()
                    if inputfile.exists():
                        incoming = json.loads(inputfile.read_text(encoding="utf-8"))
                        inputfile.unlink(missing_ok=True)
                        code = incoming["code"]
                        raw.clear()
                        proc.stdin.write((code+"\n").encode("utf-8"));proc.stdin.flush()
                        update(state="verifying", message="Anmeldung wird bestätigt …")
                    if proc.poll() is not None:
                        thread.join(timeout=1)
                        if proc.returncode:
                            # Native diagnostics may contain secrets; use a safe actionable message.
                            raise ValueError("Anmeldung fehlgeschlagen. Prüfe, ob Device-Login erlaubt ist und der Anbieter erreichbar ist.")
                        cached = verify(profile, authdir)
                        if cached is not None:
                            store.cache_monitor(profile["name"], cached)
                        store.update_profile(profile["name"], enabled=True, hold_until=None, hold_reason=None,
                                             checked_at=None, observed_at=None)
                        completed = True
                        update(state="verifying", message="Account-Daten werden abgerufen …")
                        break
    except WorkerBusy:
        if not owns_session:
            return 1
        update(state="failed", message="Dieser Account wird gerade verwendet. Versuche die Anmeldung später erneut.")
    except Exception as exc:
        update(state="failed", message=redact(str(exc))[:500])
    finally:
        if proc:
            if proc.poll() is None:
                stop_process(proc)
            if proc.stdin:proc.stdin.close()
            if proc.stdout:proc.stdout.close()
        for path in (inputfile, cancelfile):
            path.unlink(missing_ok=True)
        if data["state"] not in ACTIVE:
            update(url=None, device_code=None)
        store.close()
    if completed:
        # Refresh the same read model used by the UI; no inference turn.
        try:
            from .monitor import read_source
            profile = {**profile, "enabled": True, "managed": True, "authdir": str(authdir)}
            read_source(home, profile)
        except Exception:
            pass
        update(state="succeeded", message="Account verbunden.", url=None, device_code=None)
        for path in (inputfile, cancelfile):
            path.unlink(missing_ok=True)
    return 0 if completed else 1


def run_cancel(home,target,ident):
    try:
        if target == "-":cancel(home,ident)
        else:
            from .remote import RemoteClient,RemoteConfig
            RemoteClient(RemoteConfig(home).get(target)).data(["auth","cancel",ident])
        return 0
    except (ValueError,OSError):return 1


def launch_cancel(home,target,ident):
    command=worker_command(home,ident)
    at=command.index("--login-worker")
    command[at:]=["--login-cancel",str(Path(home).resolve()),target or "-",ident]
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        cwd=str(Path(__file__).resolve().parents[1]) if Path(__file__).is_file() else str(home),**spawn_options(hidden=True))
    threading.Thread(target=child.wait,daemon=True,name="login-cancel-reaper").start()
