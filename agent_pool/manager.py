"""Small task manager. Every network and database operation runs off the UI thread."""
import json
import queue
import threading
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk


class Manager:
    def __init__(self, parent, home, remote=None):
        self.home, self.remote = Path(home), remote
        self.root = tk.Toplevel(parent)
        self.root.title("Aufträge · " + (remote or "Lokal"))
        self.root.geometry("900x740")
        self.root.minsize(700, 600)
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        form = ttk.Frame(self.root, padding=18)
        form.pack(fill="both", expand=True)
        ttk.Label(form, text="Arbeitsverzeichnis auf dem ausführenden Rechner").pack(anchor="w")
        self.workspace = ttk.Combobox(form, state="readonly")
        self.workspace.pack(fill="x", pady=(4, 10))
        options = ttk.Frame(form)
        options.pack(fill="x")
        self.provider = ttk.Combobox(options, values=["codex", "claude"], state="readonly", width=12)
        self.provider.set("codex")
        self.provider.pack(side="left")
        ttk.Label(options, text="Modell (optional)").pack(side="left", padx=(12, 5))
        self.model = ttk.Entry(options, width=26)
        self.model.pack(side="left")
        self.edits = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Dateiänderungen erlauben", variable=self.edits).pack(side="right")
        ttk.Label(form, text="Auftrag").pack(anchor="w", pady=(12, 4))
        self.prompt = tk.Text(form, height=6, wrap="word")
        self.prompt.pack(fill="x")
        keys = ttk.Frame(form)
        keys.pack(fill="x", pady=8)
        ttk.Label(keys, text="Auftragsschlüssel").pack(side="left")
        self.key = ttk.Entry(keys, width=36)
        self.key.insert(0, uuid.uuid4().hex)
        self.key.pack(side="left", padx=8)
        ttk.Button(keys, text="Neuer Schlüssel", command=self.new_key).pack(side="left")
        self.submit_button = ttk.Button(keys, text="Übermitteln", command=self.submit)
        self.submit_button.pack(side="right")
        ttk.Label(form, text="Bei Verbindungsfehlern mit unverändertem Auftrag und Schlüssel erneut senden.").pack(anchor="w")
        row = ttk.Frame(form)
        row.pack(fill="x", pady=(14, 4))
        ttk.Label(row, text="Gespeicherte Aufträge").pack(side="left")
        ttk.Button(row, text="Aktualisieren", command=self.load).pack(side="right")
        self.jobs = ttk.Treeview(form, columns=("status", "provider", "profile"), height=5, selectmode="browse")
        self.jobs.heading("#0", text="ID")
        for name in ("status", "provider", "profile"):
            self.jobs.heading(name, text=name.title())
            self.jobs.column(name, width=110)
        self.jobs.pack(fill="x")
        self.jobs.bind("<<TreeviewSelect>>", self.inspect)
        self.result = tk.Text(form, height=8, wrap="word", state="disabled")
        self.result.pack(fill="both", expand=True, pady=(8, 0))
        self.status = ttk.Label(form, text="Verbinde …")
        self.status.pack(anchor="w", pady=(8, 0))
        self.root.after(100, self.poll)
        self.load()

    def call(self, argv):
        if self.remote:
            from .remote import RemoteClient, RemoteConfig
            return RemoteClient(RemoteConfig(self.home).get(self.remote)).data(argv)
        from .rpc import handle
        reply = handle(self.home, {"version": 1, "argv": argv})
        data = json.loads(reply["output"])
        if reply["code"] == 1:
            raise ValueError(data.get("error", "Auftrag fehlgeschlagen"))
        return data

    def background(self, kind, fn):
        if self.busy or self.closed:
            return
        self.busy = True
        self.submit_button.configure(state="disabled")
        self.status.configure(text="Abfrage läuft …")
        def run():
            try:
                self.events.put((kind, fn()))
            except Exception as exc:
                from .providers import redact
                self.events.put(("error", redact(str(exc))))
        threading.Thread(target=run, daemon=True).start()

    def new_key(self):
        if not self.busy:
            self.key.delete(0, "end")
            self.key.insert(0, uuid.uuid4().hex)

    def load(self):
        self.background("load", lambda: (self.call(["workspace", "list"]), self.call(["job", "list"])))

    def submit(self):
        argv = ["job", "submit", "--provider", self.provider.get(), "--workspace", self.workspace.get(),
                "--prompt=" + self.prompt.get("1.0", "end-1c"), "--key", self.key.get()]
        if self.model.get().strip():
            argv += ["--model", self.model.get().strip()]
        if self.edits.get():
            argv.append("--allow-edits")
        self.background("submit", lambda: self.call(argv))

    def inspect(self, event=None):
        selected = self.jobs.selection()
        if selected:
            self.background("result", lambda: self.call(["job", "get", selected[0]]))

    def display(self, text):
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)
        self.result.configure(state="disabled")

    def poll(self):
        if self.closed:
            return
        try:
            kind, data = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.submit_button.configure(state="normal")
            self.status.configure(text="Verbunden · " + (self.remote or "Lokal"))
            if kind == "error":
                self.status.configure(text="Fehler: " + data[:180])
            elif kind == "load":
                workspaces, jobs = data
                self.workspace.configure(values=[w["name"] for w in workspaces])
                if not self.workspace.get() and workspaces:
                    self.workspace.set(workspaces[0]["name"])
                for row in self.jobs.get_children():
                    self.jobs.delete(row)
                for job in jobs:
                    self.jobs.insert("", 0, iid=job["id"], text=job["id"], values=(job["status"], job["provider"], job.get("chosen_profile") or "—"))
            elif kind == "submit":
                self.new_key()
                self.display("Gespeichert: " + data["id"] + "\nSchlüssel: " + str(data.get("idempotency_key", "")) + "\nStatus: " + data["status"] + "\nEin separater Worker auf dem ausführenden Rechner verarbeitet die Queue. Mit Aktualisieren den Status abholen.")
                self.load()
            else:
                self.display("Status: " + data["status"] + "\n\n" + (data.get("result") or data.get("error") or "Noch kein Ergebnis. Mit Aktualisieren später erneut prüfen."))
        self.root.after(100, self.poll)

    def close(self):
        self.closed = True
        self.root.destroy()
