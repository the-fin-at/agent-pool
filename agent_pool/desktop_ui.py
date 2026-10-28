"""Native account overview: provider navigation, remaining-quota rings and weekly bars."""
import math
import sys
import time
import tkinter as tk
from tkinter import ttk

from .desktop_theme import (Theme, BG, SURFACE, RAISED, INK, MUTED, LINE, BRAND,
                            ACCENT, SOFT, GREEN, WARNING, DANGER)
from .monitor import account_view


PROVIDERS = {"all": "Alle Accounts", "codex": "Codex", "claude": "Claude"}


def quota_sections(account):
    """Pair source metadata with formatted windows; never call a week a 5-hour limit."""
    windows = list(zip(account.get("windows", []), account["windows_view"]))
    candidates = [(raw, view) for raw, view in windows if raw.get("minutes") == 300]
    primary = next(((raw, view) for raw, view in candidates if not raw.get("model") and
                    raw.get("bucket") in (None, account["provider"])), None)
    if primary is None and candidates:
        primary = candidates[0]
    return (primary[1] if primary else None,
            [(raw, view) for raw, view in windows if primary is None or raw is not primary[0]])


def quota_color(remaining):
    return DANGER if remaining is not None and remaining <= 5 else WARNING if remaining is not None and remaining <= 25 else BRAND


class QuotaRing(tk.Canvas):
    """A live chart, not an image: every displayed arc encodes the reported balance."""
    def __init__(self, parent, theme, window, *, size=244):
        super().__init__(parent, width=size, height=size, bg=BG, bd=0, highlightthickness=0)
        self.theme, self.window = theme, window
        self.remaining = window["remaining"] if window else None
        self.bind("<Configure>", self._paint)

    def _paint(self, event=None):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        diameter = min(width - 18, height - 18, 288)
        cx, cy = width / 2, height / 2
        stroke = max(12, diameter * .075)
        radius = (diameter - stroke) / 2
        box = (cx-radius, cy-radius, cx+radius, cy+radius)
        self.create_oval(*box, outline=LINE, width=stroke)
        remaining = self.remaining
        if remaining is not None and remaining > 0:
            color = quota_color(remaining)
            if remaining >= 100:
                self.create_oval(*box, outline=color, width=stroke)
            else:
                self.create_arc(*box, start=90, extent=-360*remaining/100, style="arc", outline=color, width=stroke)
                for angle in [90, 90-360*remaining/100]:
                    rad = math.radians(angle)
                    x, y = cx+radius*math.cos(rad), cy-radius*math.sin(rad)
                    self.create_oval(x-stroke/2, y-stroke/2, x+stroke/2, y+stroke/2, fill=color, outline="")
        number = "—" if remaining is None else f"{remaining:g} %"
        small = diameter < 180
        number_size = 32 if small else 52 if diameter >= 230 else 43
        self.create_text(cx, cy-(15 if small else 25), text=number, fill=INK, font=self.theme.face(number_size))
        if self.window and self.window["expired"]:
            caption = "Reset-Zeit erreicht\nBitte aktualisieren"
        elif remaining is None:
            caption = "Kein Wert für das\n5-Stunden-Fenster"
        else:
            caption = "frei im\n5-Stunden-Fenster"
        self.create_text(cx, cy+(27 if small else 42), text=caption, fill=MUTED, font=self.theme.face(12 if small else 16), justify="center")


class FleetView:
    def _style(self):
        self.theme = Theme(self.root)

    def text(self, parent, text, *, size=14, bold=False, color=INK, bg=None, **kw):
        return tk.Label(parent, text=text, font=self.theme.face(size, bold), fg=color,
                        bg=bg or parent.cget("bg"), anchor="w", bd=0, **kw)

    def _layout(self):
        self.provider_filter = tk.StringVar(value="all")
        self.provider_filter.trace_add("write", lambda *_: self._provider_selected())
        self.target = tk.StringVar(value=self.remote or "Lokal")
        self.scope = "remote" if self.remote else "local"
        self.page = "accounts"
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.topbar = tk.Frame(self.root, bg=BG)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        top = tk.Frame(self.topbar, bg=BG)
        top.pack(fill="x", padx=24, pady=(18, 16))
        self.scope_button = ttk.Button(top, text="Remote" if self.remote else "Lokal",
            image=self.theme.icon("chevron-down", "ink"), compound="right", style="Scope.TButton", command=self.toggle_scope_menu)
        self.scope_button.pack(side="left")
        self.scope_hint = self.text(top, "Verbundene Rechner" if self.remote else "Auf diesem Rechner", size=13, color=MUTED)
        self.scope_hint.pack(side="left", padx=16)
        self.text(top, "Agent Fleet", size=16, color=MUTED,
                  image=self.theme.image("brand/compass-48.png"), compound="left").pack(side="right")
        tk.Frame(self.topbar, bg=LINE, height=1).pack(fill="x")
        self.scope_menu = None
        self.root.bind("<Escape>", lambda _: self.close_scope_menu())
        self.root.bind("<Button-1>", self._outside_scope_menu, add="+")

        self.sidebar = tk.Frame(self.root, bg=SURFACE, width=232)
        self.sidebar.grid(row=1, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        tk.Frame(self.sidebar, bg=LINE, width=1).pack(side="right", fill="y")
        side = tk.Frame(self.sidebar, bg=SURFACE)
        side.pack(fill="both", expand=True, padx=18, pady=26)
        self.text(side, "Übersicht", size=12, color=MUTED).pack(anchor="w", padx=12, pady=(0, 14))
        self.nav_buttons = {}
        for key, icon in [("all", "people"), ("codex", "hdd-stack"), ("claude", "diagram-3")]:
            button = ttk.Radiobutton(side, text="  " + PROVIDERS[key], value=key,
                variable=self.provider_filter, style="Nav.TRadiobutton",
                image=self.theme.icon(icon, "accent" if key == "all" else "ink", 24), compound="left")
            button.pack(fill="x", pady=(0, 8))
            self.nav_buttons[key] = (button, icon)
        self.connection_nav = tk.Frame(side, bg=SURFACE)
        self.connection_nav.pack(fill="x", pady=(28, 0))
        side_bottom = tk.Frame(side, bg=SURFACE)
        side_bottom.pack(side="bottom", fill="x")
        ttk.Checkbutton(side_bottom, text="Automatisch aktualisieren", variable=self.auto,
                        style="Side.TCheckbutton").pack(anchor="w")
        self.worker_text = self.text(side_bottom, "", size=11, color=MUTED, wraplength=180)
        self.worker_text.pack(anchor="w", pady=(4, 0))

        self.main = tk.Frame(self.root, bg=BG)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.compact_bar = tk.Frame(self.main, bg=BG)
        compact_nav = tk.Frame(self.compact_bar, bg=BG)
        compact_nav.pack(fill="x", padx=24, pady=(16, 4))
        for key in PROVIDERS:
            ttk.Radiobutton(compact_nav, text=PROVIDERS[key], value=key,
                variable=self.provider_filter, style="Compact.TRadiobutton").pack(side="left", padx=(0, 12))
        self.header = tk.Frame(self.main, bg=BG)
        self.header.pack(fill="x", padx=36, pady=(32, 0))
        self.breadcrumb = tk.Frame(self.header, bg=BG)
        self.back_button = ttk.Button(self.breadcrumb, text=" Verbindungen", image=self.theme.icon("arrow-left"),
            compound="left", style="Soft.TButton", command=self.go_back)
        self.back_button.pack(side="left")
        title_row = tk.Frame(self.header, bg=BG)
        title_row.pack(fill="x")
        self.page_title = self.text(title_row, "Alle Accounts", size=40)
        self.page_title.pack(side="left")
        self.refresh_button = ttk.Button(title_row, text="", style="Soft.TButton",
            image=self.theme.icon("arrow-clockwise"), compound="left", command=self.refresh)
        self.refresh_button.pack(side="right", padx=(8, 0))
        self.add_button = ttk.Button(title_row, text="Account hinzufügen", style="Fleet.TButton",
            command=self.add_action)
        self.add_button.pack(side="right")
        self.subtitle = self.text(self.header, "", size=16, color=MUTED)
        self.subtitle.pack(anchor="w", pady=(10, 16))
        toolbar = self.toolbar = tk.Frame(self.main, bg=BG)
        toolbar.pack(fill="x", padx=36, pady=(0, 18))
        ttk.Checkbutton(toolbar, text="Alle Profile anzeigen", variable=self.show_all,
            command=self.render, style="Fleet.TCheckbutton").pack(side="left")
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search, width=24, style="Fleet.TEntry", font=self.theme.face(14))
        self.search_entry.pack(side="right")
        self.text(toolbar, "Suchen", size=12, color=MUTED,
            image=self.theme.icon("search", "muted"), compound="left").pack(side="right", padx=10)
        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill="both", expand=True, padx=(16, 12))
        self.canvas = tk.Canvas(self.content, bg=BG, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.cards_window = self.canvas.create_window(0, 0, anchor="nw", window=self.cards)
        self.cards.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._canvas_configured)
        self.root.bind("<MouseWheel>", self._scroll)
        self.root.bind("<Button-4>", lambda _: self.canvas.yview_scroll(-3, "units"))
        self.root.bind("<Button-5>", lambda _: self.canvas.yview_scroll(3, "units"))
        footer = tk.Frame(self.main, bg=BG)
        footer.pack(fill="x", padx=32, pady=(12, 16))
        tk.Frame(footer, bg=LINE, height=1).pack(fill="x", pady=(0, 10))
        self.status_text = self.text(footer, "Gespeicherter Datenstand" if any(a.get("observed_at") for a in self.accounts) else "Noch keine Kontingentdaten", size=11, color=MUTED, wraplength=650)
        self.status_text.pack(anchor="w")
        self._compact = False
        self._resize_job = None
        self.card_views = {}
        self._set_width(1280)
        self.render_connection_nav()

    def _provider_selected(self):
        if hasattr(self, "page_title"):
            if self.page not in {"accounts", "connections"}:
                self.leave_login()
                self.page = "accounts" if self.scope == "local" or self.remote else "connections"
            self.page_title.configure(text=PROVIDERS[self.provider_filter.get()])
            for key, (button, icon) in self.nav_buttons.items():
                button.configure(image=self.theme.icon(icon, "accent" if key == self.provider_filter.get() else "ink", 24))
            self.render()
            self.canvas.yview_moveto(0)

    def _canvas_configured(self, event):
        self.canvas.itemconfigure(self.cards_window, width=event.width)

    def _scroll(self, event):
        # A manager window is a different scroll surface, even when this is its parent.
        if event.widget.winfo_toplevel() != self.root or not self.canvas.winfo_ismapped():
            return
        amount = int(-event.delta) if sys.platform == "darwin" else int(-event.delta / 120) * 3
        self.canvas.yview_scroll(amount, "units")

    def _set_width(self, width):
        scaled = self.theme.set_scale(width)
        scale = self.theme.scale
        self.sidebar.configure(width=round(220*scale))
        self.header.pack_configure(padx=round(32*scale), pady=(round(28*scale), 0))
        self.toolbar.pack_configure(padx=round(32*scale))
        compact = width < 880
        columns = 1 if compact else 2 if width < 1180 else 3
        changed = scaled or columns != self.column_count or compact != self._compact
        self.column_count = columns
        if compact != self._compact:
            self._compact = compact
            if compact:
                self.sidebar.grid_remove()
                self.compact_bar.pack(fill="x", before=self.header)
            else:
                self.sidebar.grid()
                self.compact_bar.pack_forget()
        if changed and hasattr(self, "cards"):
            self.render()

    def _resized(self, event):
        if event.widget != self.root or self.closed:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, lambda: self._finish_resize(event.width))

    def _finish_resize(self, width):
        self._resize_job = None
        if not self.closed:
            self._set_width(width)
            self.status_text.configure(wraplength=max(420, width-(80 if self._compact else 300)))

    def render(self):
        if self.closed:
            return
        if self.page != "accounts":
            self.render_panel()
            return
        self.sync_header()
        now = time.time()
        deadlines = [a["observed_at"]+150 for a in self.accounts if a.get("observed_at") and a["observed_at"]+150 > now]
        deadlines += [w["reset"] for a in self.accounts for w in a.get("windows", []) if w.get("reset") and w["reset"] > now]
        self.view_deadline = min(deadlines, default=float("inf"))
        position = self.canvas.yview()[0]
        for child in self.cards.winfo_children():
            child.destroy()
        provider = self.provider_filter.get()
        accounts = [a for a in self.accounts if provider == "all" or a["provider"] == provider]
        connected = sum(bool(a.get("connected")) for a in accounts)
        self.subtitle.configure(text=f"{connected} {'Account verbunden' if connected == 1 else 'Accounts verbunden'}", fg=MUTED)
        query = self.search.get().strip().casefold()
        visible = [a for a in accounts if (self.show_all.get() or a.get("connected")) and
                   (not query or query in " ".join(str(a.get(k) or "") for k in ["name", "email", "provider", "plan"]).casefold())]
        visible.sort(key=lambda a: (not a.get("connected", False), a.get("managed", True), a["name"]))
        self.rendered = [a["name"] for a in visible]
        self.card_views = {}
        for col in range(3):
            self.cards.grid_columnconfigure(col, weight=1 if col < self.column_count else 0,
                                            uniform="cards" if col < self.column_count else "", minsize=0)
        if not visible:
            empty = tk.Frame(self.cards, bg=BG)
            empty.grid(row=0, column=0, columnspan=self.column_count, sticky="ew", padx=20, pady=36)
            heading = "Keine passenden Accounts" if query else "Noch keine verbundenen Accounts"
            self.text(empty, heading, size=23).pack(anchor="w", pady=(0, 12))
            hint = ("Ändere die Suche oder lösche den Suchtext." if query else
                    "Verbinde einen Account, um seine Kontingente hier zu sehen.")
            self.text(empty, hint, color=MUTED, wraplength=530).pack(anchor="w")
            if not query:
                ttk.Button(empty, text="Account verbinden", style="Fleet.TButton", command=self.show_login).pack(anchor="w", pady=(20, 0))
        for index, account in enumerate(visible):
            self._card(account_view(account), index // self.column_count, index % self.column_count)
        if self.remote:
            self.worker_text.configure(text="Worker aktiv" if self.worker and self.worker.get("online") else "Worker nicht erreichbar",
                                       fg=GREEN if self.worker and self.worker.get("online") else WARNING)
        else:
            self.worker_text.configure(text="Auf diesem Rechner")
        def restore_scroll():
            if not self.closed:
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                self.canvas.yview_moveto(position)
        self._schedule(0, restore_scroll)

    def _card(self, account, row, col):
        card = tk.Frame(self.cards, bg=BG)
        card.grid(row=row, column=col, sticky="nsew", pady=(0, 12))
        if col < self.column_count-1:
            tk.Frame(card, bg=LINE, width=1).pack(side="right", fill="y")
        inner = tk.Frame(card, bg=BG)
        inner.pack(fill="both", expand=True, padx=20)
        summary = tk.Frame(inner, bg=BG) if self._compact else inner
        if self._compact:
            summary.pack(fill="x")
        header = tk.Frame(summary, bg=BG, height=round(112*self.theme.scale))
        header.pack(side="left", fill="both", expand=True) if self._compact else header.pack(fill="x")
        header.pack_propagate(False)
        top = tk.Frame(header, bg=BG)
        top.pack(fill="x")
        avatar_size = round((52 if self._compact else 72)*self.theme.scale)
        avatar = tk.Canvas(top, width=avatar_size, height=avatar_size, bg=BG, highlightthickness=0)
        avatar.pack(side="left", anchor="n", padx=(0, 12))
        avatar.create_oval(0, 0, avatar_size, avatar_size, fill=RAISED, outline="")
        avatar.create_image(avatar_size/2, avatar_size/2, image=self.theme.icon("person", "ink", 24 if self._compact else 32))
        identity = tk.Frame(top, bg=BG)
        identity.pack(side="left", fill="x", expand=True)
        name = account.get("display_name") or ("Standardaccount" if not account.get("managed") else account["name"])
        name_label = self.text(identity, name, size=24, bold=True)
        name_label.pack(anchor="w")
        email = self.text(identity, account.get("email") or "Nicht angemeldet", size=16, color=MUTED,
                          wraplength=200, justify="left")
        email.pack(anchor="w", pady=(5, 0))
        full_email = account.get("email") or "Nicht angemeldet"
        def fit_email(event):
            width = max(80, event.width-4)
            value = full_email
            face = self.theme.face(16)
            if face.measure(value) > width:
                local, separator, domain = value.partition("@")
                suffix = "…@"+domain if separator and face.measure("…@"+domain) < width else "…"
                prefix = local if separator and suffix != "…" else value
                while prefix and face.measure(prefix+suffix) > width:
                    prefix = prefix[:-1]
                value = prefix+suffix
            email.configure(text=value, wraplength=0)
            display = name
            name_face = self.theme.face(24, True)
            while display and name_face.measure(display+("…" if display != name else "")) > width:
                display = display[:-1]
            name_label.configure(text=display+("…" if display != name else ""))
        identity.bind("<Configure>", fit_email)
        metadata = tk.Frame(identity, bg=BG)
        metadata.pack(fill="x", pady=(8, 0))
        self.text(metadata, account["plan_label"].replace("Business / Team", "Business"), size=13, bg=RAISED, padx=9, pady=4).pack(side="left")
        provider = "Codex" if account["provider"] == "codex" else "Claude"
        role = "Nur Anzeige" if not account.get("managed") else "Für Aufträge aktiv" if account.get("enabled") else "Für Aufträge deaktiviert"
        role_label = self.text(identity, provider + " · " + role, size=13, color=MUTED, wraplength=250)
        role_label.pack(anchor="w", pady=(5, 0))
        primary, extra = quota_sections(account)
        status = account["status_label"]
        tone = account["tone"]
        if status == "Verbunden" and primary and primary["remaining"] is not None and primary["remaining"] <= 25:
            status, tone = "Wenig frei", "warning"
        if status != "Verbunden":
            self.text(metadata, status, size=12, color=WARNING if tone == "warning" else MUTED, bg=SOFT, padx=6, pady=4).pack(side="right")
        ring_parent = tk.Frame(summary, bg=BG) if self._compact else inner
        if self._compact:
            ring_parent.pack(side="right", padx=(20, 0))
        if primary and primary["title"] != "5 Stunden":
            self.text(ring_parent, primary["title"], size=12, color=MUTED, wraplength=260).pack(fill="x", pady=(0, 6))
        ring = QuotaRing(ring_parent, self.theme, primary, size=168 if self._compact else round(min(270, 244*self.theme.scale)))
        ring.pack(fill="x")
        reset = primary["reset_label"] if primary else "Kein 5-Stunden-Limit gemeldet"
        reset_label = self.text(ring_parent, reset, size=12 if self._compact else 16, color=MUTED, wraplength=168 if self._compact else 250, justify="center")
        reset_label.configure(anchor="center")
        reset_label.pack(fill="x", pady=(8, 12))
        for raw, window in extra:
            self._limit(inner, raw, window)
        if not account.get("windows"):
            notice = "Verbinde diesen Account direkt in der App." if not account.get("connected") else "Noch keine Kontingentdaten aus der Claude-CLI." if account["provider"] == "claude" else "Für diesen Account fehlen Kontingentdaten."
            self.text(inner, notice, size=12, color=MUTED, wraplength=270).pack(fill="x", pady=(8, 18))
        bottom = tk.Frame(inner, bg=BG)
        bottom.pack(fill="x", pady=(6, 0))
        self.text(bottom, account["updated_label"], size=11, color=WARNING if account["stale"] else MUTED).pack(side="left")
        details = ttk.Button(bottom, text="Details", style="Soft.TButton", command=lambda a=account: self.details(a))
        details.pack(side="right")
        if account.get("managed") and not account.get("connected"):
            ttk.Button(inner, text="Anmelden", style="Fleet.TButton", command=lambda a=account: self.show_login(a)).pack(anchor="w", pady=(12, 0))
        if account.get("error"):
            hint = "Abfrage fehlgeschlagen. Letzter gespeicherter Stand." if account.get("observed_at") else "Abfrage fehlgeschlagen. Noch keine Kontingentdaten."
            self.text(inner, hint, size=11, color=WARNING, wraplength=270).pack(fill="x", pady=(10, 0))
        self.card_views[account["name"]] = {"ring": ring, "status": status, "primary": primary,
                                                 "extra": extra, "frame": card, "details": details}

    def _limit(self, parent, raw, window):
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", pady=(0, 12))
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 10))
        title = window["title"].replace("Woche", "Wochenkontingent", 1) if raw.get("minutes") == 10080 else window["title"]
        limit_title = self.text(row, title, size=16, bold=True, wraplength=200, justify="left")
        limit_title.pack(side="left")
        remaining = window["remaining"]
        value = "Nicht aktuell" if window["expired"] else "Kein Wert" if remaining is None else f"{remaining:g} % frei"
        value_label = self.text(row, value, size=16)
        value_label.pack(side="right")
        row.bind("<Configure>", lambda e: limit_title.configure(wraplength=max(100, e.width-value_label.winfo_reqwidth()-10)))
        bar = tk.Canvas(parent, height=round(14*self.theme.scale), bg=BG, highlightthickness=0)
        bar.pack(fill="x")
        bar.bind("<Configure>", lambda e: self._draw_bar(bar, remaining, quota_color(remaining), e.width))
        self.text(parent, window["reset_label"], size=14, color=MUTED, wraplength=270).pack(fill="x", pady=(9, 8))

    @staticmethod
    def _draw_bar(canvas, remaining, color, width):
        canvas.delete("all")
        height = canvas.winfo_height()
        radius = height/2
        canvas.create_line(radius, radius, max(radius, width-radius), radius,
                           fill=LINE, width=height-1, capstyle="round")
        if remaining is not None and remaining > 0:
            canvas.create_line(radius, radius, radius+max(0, width-height)*remaining/100, radius,
                               fill=color, width=height-1, capstyle="round")

    def details(self, account):
        self.detail_account = account
        self.page = "details"
        self.render()
