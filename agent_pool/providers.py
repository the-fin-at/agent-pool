"""Native CLI adapters: no OAuth-token parsing or direct subscription HTTP calls."""
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .quota import claude_window, codex_windows

# Ambient keys/base URLs must not silently change the selected subscription or bill an API key.
AUTH_ENV = {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL",
            "OPENAI_API_BASE", "CODEX_SQLITE_HOME", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
            "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_MODEL", "CLAUDECODE", "CODEX_THREAD_ID"}


def environment(provider, authdir):
    env = {k: v for k, v in os.environ.items() if k not in AUTH_ENV}
    env.pop("CODEX_HOME", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env["CODEX_HOME" if provider == "codex" else "CLAUDE_CONFIG_DIR"] = str(authdir)
    return env


def executable(binary):
    # Finder and Windows GUI launches have a smaller PATH than a login shell.
    search = [os.environ.get("PATH", ""), str(Path.home() / ".local/bin")]
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        search += [str(local / "Programs/OpenAI/Codex/bin"), str(local / "Microsoft/WinGet/Links")]
    else:
        search += ["/opt/homebrew/bin", "/usr/local/bin"]
    found = shutil.which(binary, path=os.pathsep.join(search))
    if found is None:
        raise ValueError(f"Native CLI not found: {binary}; install it or set profile --binary")
    if Path(found).suffix.lower() in {".cmd", ".bat"}:
        raise ValueError("Use the native .exe CLI on Windows, or run the whole broker in WSL; shell shims are unsupported")
    return found


def spawn_options(hidden=False):
    if os.name != "nt":
        return {"start_new_session": True}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hidden:
        flags |= subprocess.CREATE_NO_WINDOW
    return {"creationflags": flags}


def stop_process(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def redact(text):
    text = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", str(text))
    text = re.sub(r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", "[REDACTED]", text)
    return text


@dataclass
class Outcome:
    kind: str
    result: str = ""
    error: str = ""
    windows: list = field(default_factory=list)


def command(profile, job, final_path):
    binary = executable(profile["binary"])
    model = ["--model", job["model"]] if job.get("model") else []
    if profile["provider"] == "codex":
        return [binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", "workspace-write" if job["allow_edits"] else "read-only",
                "--output-last-message", str(final_path), *model, "-"]
    tools = "Read,Glob,Grep,Edit,Write" if job["allow_edits"] else "Read,Glob,Grep"
    return [binary, "--print", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--permission-mode", "dontAsk",
            "--permission-prompts", "none", "--restricted", "--strict-mcp-config",
            "--tools", tools, "--allowedTools", tools, *model]


def parse_run(provider, stdout, stderr, code, final=""):
    events = []
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
            if isinstance(e, dict):
                events.append(e)
        except (ValueError, TypeError):
            continue
    windows = []
    errors = []
    completed = False
    result = final
    for e in events:
        kind = e.get("type")
        if provider == "codex":
            if kind == "turn.completed":
                completed = True
            if kind in {"error", "turn.failed"}:
                errors.append(e.get("error", e.get("message", "Codex turn failed")))
            if kind == "item.completed" and e.get("item", {}).get("type") == "agent_message" and not final:
                result = e["item"].get("text", "")
        else:
            if kind == "rate_limit_event":
                w = claude_window(e)
                if w:
                    windows.append(w)
            if kind == "result":
                completed = e.get("subtype") == "success" and not e.get("is_error", False)
                result = e.get("result", "")
                if not completed:
                    errors.extend(e.get("errors") or [e.get("result") or e.get("subtype", "Claude failed")])
            if kind == "assistant" and e.get("error"):
                errors.append(e["error"])
    if completed and code == 0 and not errors:
        return Outcome("success", redact(result), windows=windows)
    # Match provider error fields only, never a successful model's prose.
    detail = json.dumps(errors, ensure_ascii=False) if errors else stderr[-4000:] if code else "Missing successful completion event"
    lowered = detail.lower()
    if any(s in lowered for s in ("usage_limit_reached", "rate_limit", "rate limit", "usage limit", "hit your limit")):
        return Outcome("quota", error=redact(detail), windows=windows)
    return Outcome("failed", error=redact(detail), windows=windows)


def run_native(profile, job, authdir):
    with tempfile.TemporaryDirectory(prefix="agent-pool-run-") as folder:
        final = Path(folder) / "final.txt"
        argv = command(profile, job, final)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out, tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                    cwd=job["cwd"], env=environment(profile["provider"], authdir),
                                    text=True, encoding="utf-8", **spawn_options())
            try:
                proc.communicate(job["prompt"], timeout=job["timeout"])
            except subprocess.TimeoutExpired:
                stop_process(proc)
                return Outcome("uncertain", error="Native CLI timed out; inspect workspace before retry")
            except BaseException:
                stop_process(proc)
                raise
            out.seek(0, 2)
            if out.tell() > 32 * 1024 * 1024:
                return Outcome("uncertain", error="Output exceeded 32 MiB; inspect workspace before retry")
            out.seek(0)
            err.seek(max(0, err.seek(0, 2) - 8192))
            return parse_run(profile["provider"], out.read(), err.read(), proc.returncode,
                             final.read_text(encoding="utf-8") if final.exists() else "")


@contextmanager
def codex_metadata_session(profile, authdir, timeout=20):
    """Documented JSONL metadata session; no model turn is started."""
    proc = subprocess.Popen([executable(profile["binary"]), "app-server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            env=environment("codex", authdir), **spawn_options(hidden=True))
    messages = queue.Queue()

    def reader():
        for line in proc.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
        messages.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def response(ident):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Codex quota read timed out")
            try:
                msg = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise ValueError("Codex quota read timed out") from exc
            if msg is None:
                raise ValueError("Codex app-server exited before its quota response")
            if msg.get("id") != ident:
                continue
            if "error" in msg:
                raise ValueError("Codex quota unavailable: " + redact(json.dumps(msg["error"])))
            return msg.get("result", {})
    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "local_agent_pool", "title": "Local Agent Pool", "version": "0.2.0"}}})
        response(1)
        send({"method": "initialized", "params": {}})
        next_id = 1
        def request(method, params=None):
            nonlocal next_id
            next_id += 1
            send({"id": next_id, "method": method, "params": params or {}})
            return response(next_id)
        yield request
    finally:
        stop_process(proc)
        thread.join(timeout=2)
        proc.stdin.close()
        proc.stdout.close()


def read_codex_quota(profile, authdir, timeout=20):
    with codex_metadata_session(profile, authdir, timeout) as request:
        windows = codex_windows(request("account/rateLimits/read"))
        if not windows:
            raise ValueError("Codex returned no subscription quota windows")
        return windows


def read_codex_status(profile, authdir, timeout=20):
    """Return an allowlisted account identity plus real quota observations."""
    with codex_metadata_session(profile, authdir, timeout) as request:
        account = request("account/read", {"refreshToken": False}).get("account")
        if not account:
            return {"connected": False, "email": None, "plan": None, "windows": None, "error": None}
        identity = {"connected": True, "email": account.get("email"),
                    "plan": account.get("planType"), "account_type": account.get("type")}
        try:
            windows = codex_windows(request("account/rateLimits/read"))
            if not windows:
                raise ValueError("Keine Kontingent-Fenster vom Anbieter gemeldet")
            return {**identity, "windows": windows, "error": None}
        except (ValueError, OSError) as exc:
            return {**identity, "windows": None, "error": redact(str(exc))}
