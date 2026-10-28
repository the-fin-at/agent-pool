"""THE-FIN tokens and process-local desktop resources. No GUI dependency outside Tk."""
import ctypes
import ctypes.util
import os
import sys
import tempfile
from importlib import resources
from pathlib import Path
import tkinter as tk
from tkinter import font, ttk

BG = "#F9F6F2"
SURFACE = "#F4EFE9"
RAISED = "#F0E8E0"
INK = "#1B1612"
SECONDARY = "#413A36"
MUTED = "#6D6863"
LINE = "#DCD6D1"
BORDER = "#C9C3BC"
BRAND = "#BD775F"
ACCENT = "#9D5035"
SOFT = "#FCE6DC"
WHITE = "#FEFDFB"
GREEN = "#317A45"
WARNING = "#986106"
DANGER = "#B63132"
_asset_temp = None
_registered = False


def asset_root():
    """Resolve installed, PyInstaller and zipapp resources without personal paths."""
    global _asset_temp
    local = Path(__file__).resolve().parent / "assets"
    if local.is_dir():
        return local
    if _asset_temp is None:
        _asset_temp = tempfile.TemporaryDirectory(prefix="agent-fleet-assets-")
        def extract(source, destination):
            destination.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                target = destination / item.name
                if item.is_dir():
                    extract(item, target)
                else:
                    target.write_bytes(item.read_bytes())
        extract(resources.files("agent_pool").joinpath("assets"), Path(_asset_temp.name))
    return Path(_asset_temp.name)


def register_fonts():
    """Register bundled upright Albert Sans for this process, never system-wide."""
    global _registered
    if _registered:
        return
    paths = sorted((asset_root() / "fonts").glob("*.ttf"))
    try:
        if sys.platform == "darwin":
            cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            ct = ctypes.CDLL("/System/Library/Frameworks/CoreText.framework/CoreText")
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
            ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            for path in paths:
                raw = os.fsencode(path)
                url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
                if url:
                    ct.CTFontManagerRegisterFontsForURL(url, 1, None)
                    cf.CFRelease(url)
        elif sys.platform == "win32":
            add = ctypes.windll.gdi32.AddFontResourceExW
            add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            for path in paths:
                add(str(path), 0x10, None)
        else:
            name = ctypes.util.find_library("fontconfig")
            if name:
                fc = ctypes.CDLL(name)
                fc.FcConfigGetCurrent.restype = ctypes.c_void_p
                fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
                config = fc.FcConfigGetCurrent()
                for path in paths:
                    fc.FcConfigAppFontAddFile(config, os.fsencode(path))
        _registered = True
    except (AttributeError, OSError):
        # An explicit system fallback keeps the UI usable on minimal installations.
        pass


class Theme:
    def __init__(self, root):
        register_fonts()
        families = set(font.families(root))
        self.family = next((f for f in ["Albert Sans", "Helvetica Neue", "Segoe UI", "Arial", "DejaVu Sans"] if f in families), "TkDefaultFont")
        self.images = {}
        self.fonts = {}
        self.scale = 1.0
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self._styles()

    def face(self, pixels=14, bold=False):
        key = (pixels, bold)
        if key not in self.fonts:
            self.fonts[key] = font.Font(root=self.root, family=self.family,
                size=-round(pixels*self.scale), weight="bold" if bold else "normal")
        return self.fonts[key]

    def set_scale(self, width):
        scale = max(1.0, min(1.225, width/1280))
        changed = abs(scale-self.scale) > .005
        self.scale = scale
        if changed:
            for (pixels, bold), face in self.fonts.items():
                face.configure(size=-round(pixels*scale))
            for style, padding in [("Fleet.TButton", (16, 11)), ("Soft.TButton", (12, 4)), ("Nav.TRadiobutton", (16, 16))]:
                self.style.configure(style, padding=tuple(round(p*scale) for p in padding))
        return changed

    def image(self, name):
        if name not in self.images:
            self.images[name] = tk.PhotoImage(master=self.root, file=str(asset_root() / name))
        return self.images[name]

    def icon(self, name, color="ink", size=20):
        return self.image(f"icons/{name}-{color}-{size}.png")

    def _button(self, name, normal, active, foreground, padding, selected=None):
        style = self.style
        element = name + ".background"
        variants = [("disabled", self.image("controls/primary-disabled.png"))] if name == "Fleet.TButton" else []
        if selected:
            variants.append(("selected", self.image(f"controls/{selected}.png")))
        variants.append(("active", self.image(f"controls/{active}.png")))
        style.element_create(element, "image", self.image(f"controls/{normal}.png"), *variants, border=10, sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew", "children": [("Button.focus", {"sticky": "nsew", "children": [("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]})])
        style.configure(name, font=self.face(16 if name == "Fleet.TButton" else 14, name == "Fleet.TButton"), foreground=foreground,
                        background=BG, padding=padding, borderwidth=0, anchor="center", width=0,
                        focuscolor=WHITE if name == "Fleet.TButton" else ACCENT, focusthickness=1)
        style.map(name, foreground=[("disabled", MUTED), ("selected", ACCENT)])

    def _styles(self):
        s = self.style
        s.configure(".", background=BG, foreground=INK, font=self.face(), bordercolor=LINE)
        self._button("Fleet.TButton", "primary", "primary-hover", WHITE, (16, 11))
        self._button("Scope.TButton", "soft", "soft-hover", INK, (18, 10))
        s.configure("Scope.TButton", font=self.face(23, True))
        self._button("Menu.TButton", "nav", "nav-hover", INK, (16, 14), "nav-selected")
        s.configure("Menu.TButton", font=self.face(17), anchor="w")
        s.layout("ScopeOption.TButton",[("Button.focus",{"sticky":"nsew","children":[("Button.padding",{"sticky":"nsew","children":[("Button.label",{"sticky":"nsew"})]})]})])
        s.configure("ScopeOption.TButton",font=self.face(17),background=SURFACE,foreground=INK,padding=(12,8),anchor="w",width=0,borderwidth=0)
        s.map("ScopeOption.TButton",background=[("selected",SOFT),("active",RAISED)],foreground=[("selected",ACCENT)])
        self._button("Soft.TButton", "soft", "soft-hover", INK, (12, 4))
        self._button("Nav.TRadiobutton", "nav", "nav-hover", INK, (16, 16), "nav-selected")
        s.configure("Nav.TRadiobutton", font=self.face(18), anchor="w", background=SURFACE)
        for name, asset, padding in [("Popover.TFrame", "soft", (8, 8)), ("MenuRow.TFrame", "nav", (4, 6)), ("SelectedMenuRow.TFrame", "nav-selected", (4, 6))]:
            element=name+".surface"
            s.element_create(element,"image",self.image("controls/"+asset+".png"),border=10,sticky="nsew")
            s.layout(name,[(element,{"sticky":"nsew"})])
            s.configure(name,padding=padding,background=BG)
        s.configure("Compact.TRadiobutton", font=self.face(13), padding=(10, 10), indicatorrelief="flat")
        s.configure("Fleet.TCheckbutton", background=BG, foreground=MUTED, font=self.face(12), padding=(0, 5))
        s.map("Fleet.TCheckbutton", background=[("active", BG)])
        s.configure("Side.TCheckbutton", background=SURFACE, foreground=MUTED, font=self.face(13), padding=(0, 8))
        s.map("Side.TCheckbutton", background=[("active", SURFACE)])
        s.configure("Fleet.TEntry", fieldbackground=SURFACE, foreground=INK, padding=(10, 10),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, font=self.face(14))
        s.map("Fleet.TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])
        s.configure("TCombobox", fieldbackground=BG, background=SURFACE, foreground=INK, padding=7, font=self.face(13), arrowsize=12)
        s.map("TCombobox", fieldbackground=[("readonly", BG)], selectbackground=[("readonly", BG)], selectforeground=[("readonly", INK)])
        s.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, borderwidth=0, arrowsize=10)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=INK, font=self.face(14))
        s.configure("TButton", font=self.face(13), padding=(10, 7))
        s.configure("TCheckbutton", background=BG, font=self.face(13))
        s.configure("Treeview", background=BG, fieldbackground=BG, foreground=INK, font=self.face(13), rowheight=28)
        s.configure("Treeview.Heading", background=SURFACE, font=self.face(13, True))
