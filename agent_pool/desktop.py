"""Small native Mac/Windows quota monitor. Provider reads run off the UI thread."""
import argparse
import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path

from . import __version__
from .monitor import collect, snapshot
from .store import default_home
from .desktop_ui import FleetView
from .overview_panels import OverviewPanels
from .desktop_theme import BG, register_fonts

class Dashboard(OverviewPanels, FleetView):
    def __init__(self, root, home, *, initial=None, refresh_fn=collect, start_refresh=True, remote=None):
        self.root, self.home = root, Path(home)
        self.local_refresh_fn = refresh_fn
        self.remote = remote
        self.target_epoch = 0
        self.worker = None
        self.refresh_fn = refresh_fn
        if remote:
            self.refresh_fn = self._remote_collect
        self.events = queue.Queue()
        self.accounts = initial if initial is not None else ([] if remote else snapshot(self.home))
        self.refreshing = False
        self.closed = False
        self.last_refresh = None
        self.refresh_error = None
        self.next_refresh = time.monotonic() + 60
        self.show_all = tk.BooleanVar(value=False)
        self.auto = tk.BooleanVar(value=True)
        self.search = tk.StringVar()
        self.rendered = []
        self.column_count = 3
        self._after_ids = set()
        self.pending_jobs = 0
        self.remote_summaries = {}
        self.probing_connections = False
        self.connection_cards = {}
        self.connection_request = None
        self.form_busy = False
        self.form_error = None
        self.login_state = None
        self.login_key = None
        self.login_busy = False
        self.login_poll_id = None
        self.login_poll_inflight = False
        self.login_spec = None
        self.root.title("Agent Fleet")
        self.root.geometry("1280x900")
        self.root.minsize(760, 560)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._layout()
        self.search.trace_add("write", lambda *_: self.render())
        self.root.bind("<Command-r>", lambda _: self.refresh())
        self.root.bind("<Control-r>", lambda _: self.refresh())
        self.root.bind("<Command-f>", lambda _: self.search_entry.focus_set())
        self.root.bind("<Control-f>", lambda _: self.search_entry.focus_set())
        self.root.bind("<Configure>", self._resized)
        self._schedule(100, self._poll)
        self._schedule(1000, self._clock)
        self.render()
        if start_refresh:
            self._schedule(250, self.refresh)

    def _schedule(self, delay, callback):
        if self.closed:
            return
        def invoke():
            self._after_ids.discard(identifier)
            if not self.closed:
                callback()
        identifier = self.root.after(delay, invoke)
        self._after_ids.add(identifier)
        return identifier

    def _remote_collect(self, home):
        from .remote import RemoteClient, RemoteConfig
        return RemoteClient(RemoteConfig(home).get(self.remote)).data(["status"])

    def _select_target(self, event=None):
        self.leave_login()
        self.remote = None if self.target.get() == "Lokal" else self.target.get()
        self.scope = "remote" if self.remote else "local"
        self.scope_button.configure(text="Remote" if self.remote else "Lokal")
        self.scope_hint.configure(text="Verbundene Rechner" if self.remote else "Auf diesem Rechner")
        self.page = "accounts"
        self.render_connection_nav()
        self.target_epoch += 1
        self.refreshing = False
        self.last_refresh = None
        self.refresh_error = None
        self.accounts = []
        self.worker = None
        self.pending_jobs = 0
        self.status_text.configure(text="Verbindung wird abgefragt …")
        self.refresh_fn = self._remote_collect if self.remote else self.local_refresh_fn
        self.render()
        self.refresh()

    def refresh(self):
        if self.refreshing or self.closed:
            return
        if self.page == "connections":
            self.next_refresh = time.monotonic() + 60
            self.probe_connections()
            return
        epoch = self.target_epoch
        refresh_fn = self.refresh_fn
        # Capture the selected remote now; switching targets cannot relabel an old response.
        if self.remote:
            from .remote import RemoteClient, RemoteConfig
            try:
                client = RemoteClient(RemoteConfig(self.home).get(self.remote))
            except (ValueError, OSError) as exc:
                self.refresh_error = str(exc)
                self.refresh_button.configure(state="normal", text="")
                self.next_refresh = time.monotonic() + 60
                self.status_text.configure(text="Verbindung prüfen: " + str(exc)[:150])
                return
            refresh_fn = lambda home: client.data(["status"])
        self.refreshing = True
        self.refresh_button.configure(state="disabled", text="…")
        self.status_text.configure(text="Kontingente abrufen …")
        def background():
            try:
                self.events.put(("data", refresh_fn(self.home), epoch))
            except Exception as exc:
                from .providers import redact
                self.events.put(("error", redact(str(exc)), epoch))
        threading.Thread(target=background, daemon=True, name="quota-monitor").start()

    def _poll(self):
        if self.closed:
            return
        try:
            kind, payload, epoch = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            if kind == "panel":
                self.handle_panel_event(payload)
                self._schedule(100, self._poll)
                return
            if epoch != self.target_epoch:
                self._schedule(100, self._poll)
                return
            self.refreshing = False
            self.refresh_button.configure(state="normal", text="")
            self.next_refresh = time.monotonic() + 60
            if kind == "data":
                self.refresh_error = None
                if isinstance(payload, dict):
                    self.worker = payload.get("worker")
                    self.pending_jobs = payload.get("pending_jobs", 0)
                    payload = payload["accounts"]
                self.accounts = payload
                self.last_refresh = time.time()
                if self.page == "accounts":
                    self.render()
                self._update_status()
            else:
                self.refresh_error = payload
                self.status_text.configure(text="Abfrage fehlgeschlagen: " + payload[:160])
                self.next_refresh = time.monotonic() + 60
        self._schedule(100, self._poll)

    def _update_status(self):
        if self.page != "accounts" or self.refreshing:
            return
        if self.refresh_error:
            self.status_text.configure(text="Abfrage fehlgeschlagen: " + self.refresh_error[:160])
            return
        if not self.last_refresh:
            return
        stamp = time.strftime("%H:%M:%S", time.localtime(self.last_refresh))
        errors = sum(bool(a.get("error")) for a in self.accounts)
        suffix = f" · {errors} Abfrage{'' if errors == 1 else 'n'} fehlgeschlagen" if errors else ""
        if self.remote:
            suffix += " · " + self.remote + (" · Worker aktiv" if self.worker and self.worker.get("online") else " · Worker offline")
        if self.auto.get():
            suffix += f" · Nächste Abfrage in {max(0, int(self.next_refresh-time.monotonic()))} s"
        self.status_text.configure(text="Abgefragt " + stamp + suffix)

    def _clock(self):
        if self.closed:
            return
        if time.time() >= self.view_deadline:
            self.render()
        if not self.refreshing:
            if self.auto.get() and time.monotonic() >= self.next_refresh:
                self.refresh()
            else:
                self._update_status()
        self._schedule(1000, self._clock)

    def close(self):
        if self.closed:
            return
        self.leave_login(detached=True)
        self.closed = True
        for identifier in self._after_ids:
            self.root.after_cancel(identifier)
        self._after_ids.clear()
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self.close_scope_menu()
        self.root.destroy()


def main(argv=None):
    import sys
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "--login-cancel":
        if len(raw) != 4:return 1
        from .login_sessions import run_cancel
        return run_cancel(Path(raw[1]), raw[2], raw[3])
    if raw and raw[0] == "--login-worker":
        if len(raw) != 3:
            return 1
        from .login_sessions import run_worker
        return run_worker(Path(raw[1]), raw[2])
    parser = argparse.ArgumentParser(description="Agent Fleet Desktop")
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("--remote", help="Configured SSH server")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(raw)
    if args.remote:
        from .remote import RemoteConfig
        RemoteConfig(args.home).get(args.remote)
    register_fonts()
    root = tk.Tk()
    dashboard = Dashboard(root, args.home, remote=args.remote)
    if args.smoke_report:
        deadline = time.monotonic() + 45
        def report():
            if (dashboard.refreshing or dashboard.last_refresh is None) and time.monotonic() < deadline:
                root.after(100, report)
                return
            payload = {"width": root.winfo_width(), "height": root.winfo_height(),
                       "refresh_completed": dashboard.last_refresh is not None,
                       "font": dashboard.theme.family, "columns": dashboard.column_count,
                       "remote": dashboard.remote,
                       "accounts": [{"name": a["name"], "connected": a.get("connected"),
                                     "windows": len(a.get("windows", [])), "error": bool(a.get("error"))}
                                    for a in dashboard.accounts]}
            args.smoke_report.write_text(json.dumps(payload), encoding="utf-8")
            dashboard.close()
        root.after(1500, report)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
