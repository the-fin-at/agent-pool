"""Worker liveness without touching the executor lease or exposing credentials."""
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


def worker_state(home):
    try:
        data = json.loads((Path(home) / "worker-status.json").read_text(encoding="utf-8"))
        age = max(0, time.time() - data["updated_at"])
        return {"online": bool(data.get("running")) and age < 35, "age_seconds": round(age, 1),
                "pid": data.get("pid"), "started_at": data.get("started_at"), "home": data.get("home")}
    except (OSError, ValueError, TypeError, KeyError):
        return {"online": False, "age_seconds": None}


@contextmanager
def heartbeat(home):
    path = Path(home) / "worker-status.json"
    stop = threading.Event()
    started = time.time()
    def write(running):
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as out:
                if os.name != "nt":
                    os.fchmod(out.fileno(), 0o600)
                json.dump({"running": running, "pid": os.getpid(), "started_at": started, "home": str(Path(home).resolve()), "updated_at": time.time()}, out)
            os.replace(tmp, path)
        except OSError:
            # Failure is reflected by a stale heartbeat, never a false online signal.
            pass
    def loop():
        while not stop.wait(10):
            write(True)
    write(True)
    thread = threading.Thread(target=loop, daemon=True, name="worker-heartbeat")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
        write(False)
