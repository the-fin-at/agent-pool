"""Small native Mac/Windows quota monitor. Provider reads run off the UI thread."""
import argparse
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import __version__
from .monitor import account_view, collect, snapshot
from .store import default_home

BG = "#f3f5f8"
WHITE = "#ffffff"
INK = "#18212e"
MUTED = "#687587"
LINE = "#e0e6ed"
GREEN = "#087f67"
MINT = "#e1f3ec"
ORANGE = "#b56813"
FONT = "SF Pro Text" if sys.platform == "darwin" else "Segoe UI"


class Dashboard:
    def __init__(self, root, home, *, initial=None, refresh_fn=collect, start_refresh=True):
        self.root, self.home = root, Path(home)
        self.refresh_fn = refresh_fn
        self.events = queue.Queue()
        self.accounts = initial if initial is not None else snapshot(self.home)
        self.refreshing = False
        self.closed = False
        self.last_refresh = None
        self.next_refresh = time.monotonic() + 60
        self.show_all = tk.BooleanVar(value=False)
        self.auto = tk.BooleanVar(value=True)
        self.search = tk.StringVar()
        self.rendered = []
        self.column_count = 2
        self.root.title("Agent Pool — Nutzung & Limits")
        self.root.geometry("1100x790")
        self.root.minsize(760, 560)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._layout()
        self.search.trace_add("write", lambda *_: self.render())
        self.root.bind("<Command-r>", lambda _: self.refresh())
        self.root.bind("<Control-r>", lambda _: self.refresh())
        self.root.bind("<Configure>", self._resized)
        self.root.after(100, self._poll)
        self.root.after(1000, self._clock)
        self.render()
        if start_refresh:
            self.root.after(250, self.refresh)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Pool.TButton", font=(FONT, 11, "bold"), padding=(14, 9),
                        background=INK, foreground=WHITE, borderwidth=0, focusthickness=2,
                        focuscolor="#8ccfbb")
        style.map("Pool.TButton", background=[("active", "#334155"), ("disabled", "#d9dee6")],
                  foreground=[("disabled", MUTED)])
        style.configure("Soft.TButton", font=(FONT, 10), padding=(10, 6),
                        background=WHITE, foreground=INK, borderwidth=1, bordercolor=LINE)
        style.map("Soft.TButton", background=[("active", "#eaf0f5")])
        style.configure("Pool.TCheckbutton", background=BG, foreground=MUTED, font=(FONT, 10))
        style.configure("Pool.TEntry", fieldbackground=WHITE, foreground=INK, padding=9,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure("Vertical.TScrollbar", background="#c9d2dc", troughcolor=BG,
                        borderwidth=0, arrowsize=12)

    def text(self, parent, text, *, size=11, bold=False, color=INK, bg=None, **kw):
        return tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                        fg=color, bg=bg or parent.cget("bg"), anchor="w", **kw)

    def _layout(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=30, pady=(26, 0))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left")
        mark = tk.Canvas(brand, width=36, height=36, bg=BG, highlightthickness=0)
        mark.pack(side="left", padx=(0, 10))
        mark.create_rectangle(0, 0, 36, 36, fill=INK, outline=INK)
        for y, width in [(11, 23), (18, 17), (25, 26)]:
            mark.create_line(8, y, width, y, fill="#8be2c2", width=3, capstyle="round")
        self.text(brand, "Agent Pool", size=17, bold=True).pack(side="left")
        self.refresh_button = ttk.Button(header, text="Jetzt aktualisieren", style="Pool.TButton", command=self.refresh)
        self.refresh_button.pack(side="right")
        ttk.Checkbutton(header, text="Automatisch · 60 s", variable=self.auto,
                        style="Pool.TCheckbutton").pack(side="right", padx=18)

        title = tk.Frame(self.root, bg=BG)
        title.pack(fill="x", padx=30, pady=(28, 20))
        self.text(title, "Nutzung & Limits", size=27, bold=True).pack(anchor="w")
        self.text(title, "Alle verbundenen Accounts. Die gemeldeten Kontingente auf einen Blick.",
                  size=11, color=MUTED).pack(anchor="w", pady=(7, 0))

        stats = tk.Frame(self.root, bg=BG)
        stats.pack(fill="x", padx=30)
        self.stat_labels = []
        for i, caption in enumerate(["Accounts verbunden", "Profile für Aufträge aktiv", "Quotenfenster gemeldet"]):
            tile = tk.Frame(stats, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 2 else 7))
            stats.grid_columnconfigure(i, weight=1, uniform="stats")
            value = self.text(tile, "—", size=24, bold=True)
            value.pack(anchor="w", padx=17, pady=(12, 2))
            self.text(tile, caption, size=10, color=MUTED).pack(anchor="w", padx=17, pady=(0, 14))
            self.stat_labels.append(value)

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=30, pady=(22, 13))
        self.section_label = self.text(toolbar, "DEINE ACCOUNTS", size=10, bold=True, color=MUTED)
        self.section_label.pack(side="left")
        ttk.Checkbutton(toolbar, text="Auch unverbundene Profile", variable=self.show_all,
                        command=self.render, style="Pool.TCheckbutton").pack(side="right", padx=(15, 0))
        search = ttk.Entry(toolbar, textvariable=self.search, width=26, style="Pool.TEntry")
        search.pack(side="right")
        self.text(toolbar, "Suchen", size=10, color=MUTED).pack(side="right", padx=(0, 8))

        content = tk.Frame(self.root, bg=BG)
        content.pack(fill="both", expand=True, padx=(24, 22))
        self.canvas = tk.Canvas(content, bg=BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.cards_window = self.canvas.create_window(0, 0, anchor="nw", window=self.cards)
        self.cards.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.cards_window, width=e.width))
        self.root.bind("<MouseWheel>", self._scroll)
        self.root.bind("<Button-4>", lambda _: self.canvas.yview_scroll(-3, "units"))
        self.root.bind("<Button-5>", lambda _: self.canvas.yview_scroll(3, "units"))

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=30, pady=(12, 18))
        self.status_text = self.text(footer, "Lokal gespeichert", size=10, color=MUTED)
        self.status_text.pack(side="left")
        self.text(footer, "Kontingente bleiben pro Account getrennt.", size=10, color=MUTED).pack(side="right")

    def _scroll(self, event):
        amount = int(-event.delta) if sys.platform == "darwin" else int(-event.delta / 120) * 3
        self.canvas.yview_scroll(amount, "units")

    def _resized(self, event):
        if event.widget != self.root:
            return
        columns = 1 if event.width < 950 else 2
        if columns != self.column_count:
            self.column_count = columns
            self.render()

    def render(self):
        if self.closed:
            return
        position = self.canvas.yview()[0]
        for child in self.cards.winfo_children():
            child.destroy()
        connected = [a for a in self.accounts if a.get("connected")]
        for label, value in zip(self.stat_labels, [len(connected), sum(bool(a.get("enabled")) for a in self.accounts),
                                                  sum(len(a.get("windows", [])) for a in connected)]):
            label.configure(text=str(value))
        query = self.search.get().strip().casefold()
        visible = [a for a in self.accounts if (self.show_all.get() or a.get("connected")) and
                   (not query or query in " ".join(str(a.get(k) or "") for k in ["name", "email", "provider", "plan"]).casefold())]
        visible.sort(key=lambda a: (not a.get("connected", False), a.get("managed", True), a["name"]))
        self.rendered = [a["name"] for a in visible]
        for col in range(2):
            self.cards.grid_columnconfigure(col, weight=1 if col < self.column_count else 0,
                                            uniform="cards" if col < self.column_count else "")
        if not visible:
            empty = tk.Frame(self.cards, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
            empty.grid(row=0, column=0, columnspan=self.column_count, sticky="ew", padx=6, pady=6)
            label = "Keine passenden Accounts" if query else "Noch keine verbundenen Accounts"
            self.text(empty, label, size=16, bold=True).pack(anchor="w", padx=22, pady=(24, 8))
            self.text(empty, "Zeige alle Profile an oder melde einen Account über agent-pool login an.",
                      color=MUTED).pack(anchor="w", padx=22, pady=(0, 24))
        for index, account in enumerate(visible):
            self._card(account_view(account), index // self.column_count, index % self.column_count)
        # Let the native event loop map the first window before processing layout.
        # A re-entrant update_idletasks here can leave Aqua clipped to 200x200.
        def restore_scroll():
            if not self.closed:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                self.canvas.yview_moveto(position)
        self.root.after_idle(restore_scroll)

    def _card(self, account, row, col):
        card = tk.Frame(self.cards, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        self.cards.grid_rowconfigure(row, weight=0)
        inner = tk.Frame(card, bg=WHITE)
        inner.pack(fill="both", expand=True, padx=19, pady=18)
        top = tk.Frame(inner, bg=WHITE)
        top.pack(fill="x")
        provider = "OPENAI · CODEX" if account["provider"] == "codex" else "ANTHROPIC · CLAUDE"
        self.text(top, provider, size=9, bold=True, color=MUTED).pack(side="left")
        colors = {"success": (GREEN, MINT), "warning": (ORANGE, "#fff1db"), "muted": (MUTED, "#eef1f5")}
        foreground, background = colors[account["tone"]]
        self.text(top, account["status_label"], size=9, bold=True, color=foreground, bg=background,
                  padx=8, pady=4).pack(side="right")
        email = account.get("email") or ("Codex-Hauptaccount" if not account["managed"] else account["name"])
        self.text(inner, email, size=13, bold=True, wraplength=445).pack(anchor="w", pady=(14, 5))
        self.text(inner, account["plan_label"] + "  ·  " + account["role_label"], size=9, color=MUTED,
                  wraplength=445).pack(anchor="w")
        tk.Frame(inner, bg=LINE, height=1).pack(fill="x", pady=(15, 13))
        if not account["windows_view"]:
            notice = "Nach dem Login werden die Limits hier angezeigt."
            if account["provider"] == "claude":
                notice = "Noch keine Quotenbeobachtung aus der Claude-CLI vorhanden."
            elif account["connected"]:
                notice = "Der Anbieter hat noch keine Kontingente gemeldet."
            self.text(inner, notice, size=10, color=MUTED, wraplength=440).pack(anchor="w", pady=(8, 18))
        for window in account["windows_view"]:
            line = tk.Frame(inner, bg=WHITE)
            line.pack(fill="x", pady=(0, 7))
            self.text(line, window["title"], size=10, bold=True).pack(side="left")
            remaining = window["remaining"]
            value = "Nicht aktuell" if window["expired"] else "Unbekannt" if remaining is None else f"{remaining:g} % frei"
            self.text(line, value, size=11, bold=True).pack(side="right")
            used = window["used"]
            bar = tk.Canvas(inner, height=7, bg="#edf1f5", highlightthickness=0)
            bar.pack(fill="x")
            if used is not None:
                color = GREEN if used < 75 else ORANGE if used < 95 else "#ce4d49"
                bar.bind("<Configure>", lambda e, b=bar, u=used, c=color: self._draw_bar(b, u, c, e.width))
            reset = (f"{used:g} % genutzt · " if used is not None else "") + window["reset_label"]
            if window["reset_absolute"]:
                reset += "  ·  " + window["reset_absolute"]
            self.text(inner, reset, size=9, color=MUTED, wraplength=440).pack(anchor="w", pady=(6, 13))
        bottom = tk.Frame(inner, bg=WHITE)
        bottom.pack(fill="x", pady=(3, 0))
        self.text(bottom, account["updated_label"], size=9, color=ORANGE if account["stale"] else MUTED).pack(side="left")
        ttk.Button(bottom, text="Details", style="Soft.TButton", command=lambda a=account: self.details(a)).pack(side="right")
        if account.get("error"):
            self.text(inner, "Aktualisierung fehlgeschlagen. Letzter bekannter Stand.",
                      size=9, color=ORANGE, wraplength=440).pack(anchor="w", pady=(10, 0))

    @staticmethod
    def _draw_bar(canvas, used, color, width):
        canvas.delete("fill")
        if used > 0:
            canvas.create_rectangle(0, 0, width * used / 100, 7, fill=color, outline=color, tags="fill")

    def details(self, account):
        lines = [account.get("email") or account["name"], "Profil: " + account["name"],
                 "Tarif: " + account["plan_label"], account["role_label"], "", account["updated_label"]]
        for window in account["windows_view"]:
            lines.append(window["title"] + ": " + window["reset_absolute"])
        if account.get("error"):
            lines += ["", "Letzter Fehler:", account["error"][:1600]]
        messagebox.showinfo("Account-Details", "\n".join(lines), parent=self.root)

    def refresh(self):
        if self.refreshing or self.closed:
            return
        self.refreshing = True
        self.refresh_button.configure(state="disabled", text="Wird aktualisiert …")
        self.status_text.configure(text="Account-Status und Limits werden abgefragt …")
        def background():
            try:
                self.events.put(("data", self.refresh_fn(self.home)))
            except Exception as exc:
                from .providers import redact
                self.events.put(("error", redact(str(exc))))
        threading.Thread(target=background, daemon=True, name="quota-monitor").start()

    def _poll(self):
        if self.closed:
            return
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.refreshing = False
            self.refresh_button.configure(state="normal", text="Jetzt aktualisieren")
            self.next_refresh = time.monotonic() + 60
            if kind == "data":
                self.accounts = payload
                self.last_refresh = time.time()
                self.render()
            else:
                self.status_text.configure(text="Aktualisierung fehlgeschlagen: " + payload[:160])
                self.next_refresh = time.monotonic() + 60
        self.root.after(100, self._poll)

    def _clock(self):
        if self.closed:
            return
        if not self.refreshing:
            if self.auto.get() and time.monotonic() >= self.next_refresh:
                self.refresh()
            elif self.last_refresh:
                stamp = time.strftime("%H:%M:%S", time.localtime(self.last_refresh))
                errors = sum(bool(a.get("error")) for a in self.accounts)
                suffix = " · " + str(errors) + " Profil(e) prüfen" if errors else ""
                if self.auto.get():
                    suffix += f" · nächste Abfrage in {max(0, int(self.next_refresh - time.monotonic()))} s"
                self.status_text.configure(text="Aktualisiert " + stamp + suffix)
        self.root.after(1000, self._clock)

    def close(self):
        self.closed = True
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agent Pool Desktop — Nutzung & Limits")
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = tk.Tk()
    dashboard = Dashboard(root, args.home)
    if args.smoke_report:
        deadline = time.monotonic() + 45
        def report():
            if (dashboard.refreshing or dashboard.last_refresh is None) and time.monotonic() < deadline:
                root.after(100, report)
                return
            payload = {"width": root.winfo_width(), "height": root.winfo_height(),
                       "refresh_completed": dashboard.last_refresh is not None,
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
