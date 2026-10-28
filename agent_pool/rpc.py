"""One SSH request per process. No listener, credential export, or remote shell API."""
import contextlib
import io
import json
import math
import sqlite3
import sys
import threading

from .remote import VERSION, MAX_REQUEST, MAX_RESPONSE
from .providers import redact
from .store import Store


HANDLE_LOCK = threading.Lock()


def handle(home, request):
    # redirect_stdout is process-global; local Manager windows share this endpoint.
    with HANDLE_LOCK:
        return _handle(home, request)


def _handle(home, request):
    from .cli import parser, dispatch, emit
    out = io.StringIO()
    code = 1
    try:
        if not isinstance(request, dict) or set(request) != {"version", "argv"} or type(request["version"]) is not int or request["version"] != VERSION:
            raise ValueError("Incompatible remote protocol")
        argv = request["argv"]
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
            raise ValueError("RPC argv must be a nonempty string array")
        for token in argv:
            try:
                token.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError("Invalid Unicode in RPC arguments") from exc
            if "\x00" in token:
                raise ValueError("NUL in RPC arguments")
        if argv[0] not in {"doctor", "connection-info", "status", "monitor", "workspace", "profile", "quota", "job", "auth"}:
            raise ValueError("RPC operation not allowed")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            try:
                args = parser().parse_args(argv)
            except SystemExit as exc:
                raise ValueError("Invalid RPC arguments") from exc
        # Root globals cannot follow subcommands. RPC never accepts a client home or nested remote.
        if args.remote:
            raise ValueError("Nested remotes are forbidden")
        if args.action in {"monitor", "status"} and args.refresh:
            raise ValueError("The persistent worker refreshes metadata; RPC reads the cache only")
        if args.action == "quota" and args.operation != "show":
            raise ValueError("Quota observations are maintained on the server")
        if args.action == "workspace" and args.operation != "list":
            raise ValueError("Register workspaces directly on the server")
        if args.action == "profile" and args.operation == "add":
            raise ValueError("Add native executables and profiles directly on the server")
        if args.action == "auth" and args.operation == "input" and args.code_file:
            raise ValueError("RPC login codes are transferred directly, not read from server files")
        if args.action == "job" and args.operation == "submit":
            if not args.workspace or args.cwd or args.prompt_file or not args.key:
                raise ValueError("Remote submit requires --workspace, --prompt and a stable --key")
        if args.action == "job" and args.operation == "wait":
            if not math.isfinite(args.seconds) or not 0 <= args.seconds <= 60:
                raise ValueError("Remote waits must be between 0 and 60 seconds")
        store = Store(home)
        try:
            if args.action == "job" and args.operation == "retry":
                if store.job(args.id)["status"] == "needs_review" and not args.acknowledge_review:
                    raise ValueError("Inspect the server workspace and surviving processes, then retry with --acknowledge-review")
            with contextlib.redirect_stdout(out):
                code = dispatch(store, args)
        finally:
            store.close()
    except (ValueError, OSError, sqlite3.Error, RecursionError) as exc:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            emit({"error": redact(str(exc))})
        code = 1
    response = {"version": VERSION, "code": code, "output": out.getvalue()}
    if len(json.dumps(response).encode("utf-8")) > MAX_RESPONSE:
        return {"version": VERSION, "code": 1, "output": json.dumps({"error": "Response exceeds 10 MiB; retrieve individual jobs"})}
    return response


def serve(home):
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError("Remote request exceeds 2 MiB")
        request = json.loads(raw)
        response = handle(home, request)
    except (ValueError, UnicodeError, RecursionError) as exc:
        response = {"version": VERSION, "code": 1, "output": json.dumps({"error": redact(str(exc))})}
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0
