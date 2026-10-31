"""
Video Downloader — PC version (Windows / macOS / Linux).

Paste a link (or search YouTube), see a preview with every quality and its size, then download.
Same engine as the phone app: yt-dlp + ffmpeg (+ Deno for YouTube), see engine.py.
UI: CustomTkinter (scales with Windows display scaling, dark title bar).
"""
from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

import engine
from engine import EngineError, MediaInfo, Quality
from icons import make_icon
import bridge
import notify

APP = "Video Downloader"
VERSION = "dev"
try:
    from _version import VERSION  # written by the build
except Exception:
    pass

# ---------------------------------------------------------------- look

BG = "#0F0F10"
PANEL = "#18181B"
CARD = "#1F1F23"
CARD_HOVER = "#26262B"
LINE = "#2C2C32"
FG = "#F4F4F5"
MUTED = "#A1A1AA"
DIM = "#71717A"
ORANGE = "#FF6A13"
ORANGE_H = "#E85D0C"
ORANGE_SOFT = "#3A1E0C"
GOOD = "#34D399"
BAD = "#F87171"
WARN = "#FBBF24"
IS_WIN = sys.platform.startswith("win")
FAMILY = "Segoe UI" if IS_WIN else ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")
SYMBOLS = "Segoe UI Symbol" if IS_WIN else FAMILY


def F(size=13, weight="normal", family=None):
    return ctk.CTkFont(family=family or FAMILY, size=size, weight=weight)


# ---------------------------------------------------------------- helpers

def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "VideoDownloader")
    os.makedirs(d, exist_ok=True)
    return d


def default_folder() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", "Video Downloader")


def human_size(n: float) -> str:
    if not n or n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_time(s: float) -> str:
    if not s or s <= 0:
        return ""
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def compact(n: int) -> str:
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            return f"{n / div:.1f}{suf}"
    return str(n)


def open_path(path: str):
    if not path or not os.path.exists(path):
        return
    if IS_WIN:
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path: str):
    if IS_WIN and os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)


def ellipsize(widget, text: str, max_px: int) -> str:
    """Shortens text with … so it fits in max_px (real screen pixels) using the widget's own font."""
    try:
        inner = getattr(widget, "_label", None) or getattr(widget, "_text_label", None) or widget
        f = tkfont.Font(font=inner.cget("font"))
    except Exception:
        return text
    if max_px <= 20 or f.measure(text) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if f.measure(text[:mid] + "…") <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(w, int(img.width * scale + 0.5)), max(h, int(img.height * scale + 0.5))), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def placeholder(w, h, audio=False) -> Image.Image:
    img = Image.new("RGB", (w, h), CARD_HOVER)
    d = ImageDraw.Draw(img)
    cx, cy, r = w // 2, h // 2, min(w, h) // 6
    if audio:
        d.ellipse((cx - r, cy, cx, cy + r), fill=(113, 113, 122))
        d.rectangle((cx - 3, cy - 2 * r, cx, cy + r // 2), fill=(113, 113, 122))
    else:
        d.polygon([(cx - r // 2, cy - r), (cx - r // 2, cy + r), (cx + r, cy)], fill=(113, 113, 122))
    return img


# ---------------------------------------------------------------- state

@dataclass
class Item:
    id: str
    url: str
    title: str
    quality: Quality
    playlist: bool = False
    name: str | None = None
    folder: str = ""
    thumb: str | None = None
    duration: int = 0
    status: str = "Queued"          # Queued, Starting, Downloading, Processing, Done, Failed, Cancelled
    pct: float = 0.0
    speed: float = 0.0
    eta: float = 0.0
    total: float = 0.0
    files: list[str] = field(default_factory=list)
    error: str = ""
    detail: str = ""
    added: float = field(default_factory=time.time)

    @property
    def active(self):
        return self.status in ("Queued", "Starting", "Downloading", "Processing")

    def to_json(self):
        q = self.quality
        return dict(id=self.id, url=self.url, title=self.title, status=self.status, files=self.files,
                    folder=self.folder, error=self.error, detail=self.detail, added=self.added, playlist=self.playlist,
                    name=self.name, thumb=self.thumb, duration=self.duration, total=self.total,
                    q=dict(label=q.label, size=q.size, height=q.height, audio=q.audio))

    @staticmethod
    def from_json(d):
        q = d.get("q") or {}
        it = Item(d["id"], d["url"], d.get("title") or d["url"],
                  Quality(q.get("label", "Best quality"), q.get("size", 0), q.get("height"), q.get("audio")),
                  d.get("playlist", False), d.get("name"), d.get("folder", ""), d.get("thumb"), d.get("duration", 0),
                  d.get("status", "Done"), files=d.get("files") or [], error=d.get("error", ""),
                  detail=d.get("detail", ""), added=d.get("added", time.time()), total=d.get("total", 0))
        if it.active:  # app was closed mid-download
            it.status, it.error = "Failed", "Stopped when the app was closed — press Retry."
        return it


# ---------------------------------------------------------------- small widgets

class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#2E2E34", fg=FG, padx=8, pady=4, font=(FAMILY, 9)).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def icon_button(master, symbol, tip, command, danger=False, width=36):
    b = ctk.CTkButton(master, text=symbol, width=width, height=32, corner_radius=8, command=command,
                      fg_color=CARD_HOVER, hover_color=("#5A1F1F" if danger else "#34343B"), text_color=FG,
                      font=F(14, family=SYMBOLS))
    Tooltip(b, tip)
    return b


def ghost_button(master, text, command, width=0, **kw):
    return ctk.CTkButton(master, text=text, command=command, height=34, corner_radius=9, fg_color=CARD,
                         hover_color=CARD_HOVER, text_color=FG, border_width=1, border_color=LINE, font=F(12),
                         width=width or 0, **kw)


def primary_button(master, text, command, height=40, size=14, **kw):
    return ctk.CTkButton(master, text=text, command=command, height=height, corner_radius=10, fg_color=ORANGE,
                         hover_color=ORANGE_H, text_color="white", font=F(size, "bold"), **kw)


# ---------------------------------------------------------------- download card

class DownloadCard(ctk.CTkFrame):
    THUMB = (128, 72)

    def __init__(self, master, app: "App", item: Item):
        super().__init__(master, fg_color=CARD, corner_radius=12)
        self.app, self.item = app, item
        self.grid_columnconfigure(1, weight=1)
        self.thumb = ctk.CTkLabel(self, text="", width=self.THUMB[0], height=self.THUMB[1])
        self.thumb.grid(row=0, column=0, rowspan=3, padx=(12, 14), pady=12)
        self.title = ctk.CTkLabel(self, text=item.title, font=F(13, "bold"), anchor="w", text_color=FG)
        self.title.grid(row=0, column=1, sticky="ew", pady=(12, 0))
        self.info = ctk.CTkLabel(self, text="", font=F(12), anchor="w", text_color=MUTED)
        self.info.grid(row=1, column=1, sticky="ew")
        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3, progress_color=ORANGE, fg_color=LINE)
        self.bar.grid(row=2, column=1, sticky="ew", pady=(4, 12))
        self.btns = ctk.CTkFrame(self, fg_color="transparent")
        self.btns.grid(row=0, column=2, rowspan=3, padx=(10, 12))
        self._btn_state = None
        self._title_w = 0
        self.bind("<Configure>", lambda e: self.after_idle(self._fit_title))
        for w in (self, self.thumb, self.title, self.info):
            w.bind("<Double-Button-1>", lambda e: self.app.play(self.item))
        self._set_thumb_placeholder()
        if item.thumb:
            app.thumbs.get(item.thumb, self.THUMB, self._set_thumb)
        self.update_view()

    def _set_thumb_placeholder(self):
        img = rounded(placeholder(*[v * 2 for v in self.THUMB], audio=self.item.quality.is_audio), 16)
        self.thumb.configure(image=ctk.CTkImage(img, size=self.THUMB))

    def _set_thumb(self, img):
        if self.winfo_exists():
            self.thumb.configure(image=ctk.CTkImage(rounded(img, 16), size=self.THUMB))

    def _fit_title(self):
        if not self.winfo_exists():
            return
        w = self.title.winfo_width()
        if w > 30:
            self.title.configure(text=ellipsize(self.title, self.item.title, w - 8))
            info_txt = getattr(self, "_info_full", "")
            self.info.configure(text=ellipsize(self.info, info_txt, self.info.winfo_width() - 8))

    def update_view(self):
        it = self.item
        q = it.quality.label.replace(" Video", "").replace("Ultra HD", "UHD")
        color = MUTED
        if it.status == "Downloading":
            parts = [f"{it.pct:.0f}%", q, human_size(it.total),
                     (human_size(it.speed) + "/s") if it.speed else "", (human_time(it.eta) + " left") if it.eta else ""]
            self.bar.set(it.pct / 100)
            color = FG
        elif it.status == "Processing":
            parts = ["Converting…", q]
            self.bar.set(1)
        elif it.status in ("Queued", "Starting"):
            parts = ["Waiting…" if it.status == "Queued" else "Starting…", q]
            self.bar.set(0)
        elif it.status == "Done":
            parts = ["✓ Completed", q, human_size(it.total)]
            self.bar.set(1)
            color = GOOD
        elif it.status == "Failed":
            parts = ["Failed — " + (it.error or "unknown error")]
            self.bar.set(0)
            color = BAD
        else:
            parts = ["Cancelled", q]
            self.bar.set(0)
            color = DIM
        self._info_full = "   •   ".join(p for p in parts if p)
        self.info.configure(text_color=color)
        if it.active:
            self.bar.grid()
        else:
            self.bar.grid_remove()
        self._fit_title()
        self._buttons()

    def _buttons(self):
        st = "active" if self.item.active else self.item.status
        if st == self._btn_state:
            return
        self._btn_state = st
        for c in self.btns.winfo_children():
            c.destroy()
        a, it = self.app, self.item
        bs = []
        if it.active:
            bs.append(("⏹", "Cancel", lambda: a.cancel(it), True))
        elif it.status == "Done":
            bs += [("▶", "Play", lambda: a.play(it), False), ("📁", "Show in folder", lambda: a.show(it), False)]
        else:
            if it.status == "Failed" and it.detail:
                bs.append(("ⓘ", "Error details", lambda: a.details(it), False))
            bs.append(("⟳", "Retry", lambda: a.retry(it), False))
        bs.append(("✕", "Remove from list", lambda: a.remove(it), True))
        for i, (sym, tip, fn, danger) in enumerate(bs):
            icon_button(self.btns, sym, tip, fn, danger).grid(row=0, column=i, padx=3)


# ---------------------------------------------------------------- thumbnails

class Thumbs:
    """Downloads thumbnails in the background and caches them."""

    def __init__(self, ui_q):
        self.ui_q = ui_q
        self.cache: dict[str, Image.Image] = {}

    def get_raw(self, url, callback):
        if url in self.cache:
            callback(self.cache[url])
            return

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=15).read()))
                img.load()
                self.cache[url] = img
                self.ui_q.put(("call", lambda: callback(img)))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def get(self, url, size, callback):
        if url in self.cache:
            callback(cover(self.cache[url], size[0] * 2, size[1] * 2))
            return

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=15).read()))
                img.load()
                self.cache[url] = img
                self.ui_q.put(("call", lambda: callback(cover(img, size[0] * 2, size[1] * 2))))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------- app

class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.ui_q: queue.Queue = queue.Queue()
        self.thumbs = Thumbs(self.ui_q)
        self.settings = self._load_settings()
        self.engine = engine.Engine(self.settings)
        self.items: list[Item] = self._load_history()
        self.cards: dict[str, DownloadCard] = {}
        self.running = 0
        self.info: MediaInfo | None = None
        self.info_url = ""
        self.req_id = 0
        self.quality_var = tk.IntVar(value=0)
        self.tab = "Video"
        self.filter = "All"
        self.last_clip = ""
        self._clip_url = ""
        self._dirty: set[str] = set()

        root.title(APP)
        root.configure(fg_color=BG)
        self._set_icon()
        self._place_window()
        self._build()
        self._render_list()

        self.ext_infos: dict[str, MediaInfo] = {}
        self.bridge = bridge.Bridge(self, VERSION)
        self.bridge.start()

        root.after(100, self._pump)
        root.after(500, self._dispatch)
        root.after(1500, self._watch_clipboard)
        threading.Thread(target=self._startup_checks, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------ window
    def _set_icon(self):
        try:
            ico = os.path.join(engine.app_dir(), "icon.ico")
            if IS_WIN and os.path.isfile(ico):
                self.root.iconbitmap(ico)
            else:
                from PIL import ImageTk
                self._icon = ImageTk.PhotoImage(make_icon(64))
                self.root.iconphoto(True, self._icon)
        except Exception:
            pass

    def _place_window(self):
        """Fit the window to the screen (in scaled units); small or high-scaling screens start maximized."""
        scale = ctk.ScalingTracker.get_window_scaling(self.root)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        lw, lh = sw / scale, sh / scale                      # screen size in app units
        self.compact = lw < 1320
        self.pw = 340 if self.compact else 400              # preview column width
        self.short = lh < 820                               # low screen: small thumbnail beside the title
        self.root.minsize(int(min(900, lw * 0.9)), int(min(600, lh * 0.82)))
        w, h = 1280, 800
        if w > lw * 0.94 or h > lh * 0.88:
            self.root.geometry(f"{int(lw * 0.94)}x{int(lh * 0.86)}+10+10")
            if IS_WIN:
                self.root.after(80, lambda: self.root.state("zoomed"))
        else:
            self.root.geometry(f"{w}x{h}+{int((sw - w * scale) / 2)}+{int((sh - h * scale) / 3)}")

    # ------------------------------------------------ persistence
    def _load_settings(self) -> dict:
        s = {"folder": default_folder(), "parallel": 3, "clipboard": True, "auto_update": True,
             "cookies_browser": "None", "cookies_file": "", "last_update": 0, "ext_mode": "panel",
             "search_source": "All", "notify": True}
        try:
            with open(os.path.join(data_dir(), "settings.json"), encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception:
            pass
        return s

    def _save_settings(self):
        try:
            with open(os.path.join(data_dir(), "settings.json"), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _load_history(self) -> list[Item]:
        try:
            with open(os.path.join(data_dir(), "history.json"), encoding="utf-8") as f:
                return [Item.from_json(d) for d in json.load(f)]
        except Exception:
            return []

    def _save_history(self):
        try:
            p = os.path.join(data_dir(), "history.json")
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump([i.to_json() for i in self.items[-500:]], f)
            os.replace(p + ".tmp", p)
        except Exception:
            pass

    # ------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.grid_columnconfigure(0, weight=1)
        r.grid_rowconfigure(4, weight=1)

        # header
        head = ctk.CTkFrame(r, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        head.grid_columnconfigure(1, weight=1)
        logo = ctk.CTkLabel(head, text="", image=ctk.CTkImage(make_icon(128), size=(34, 34)))
        logo.grid(row=0, column=0, padx=(0, 12))
        ctk.CTkLabel(head, text=APP, font=F(22, "bold"), text_color=FG).grid(row=0, column=1, sticky="w")
        ghost_button(head, "Browser button", self.open_ext_setup).grid(row=0, column=3, padx=(0, 6))
        ghost_button(head, "Open folder", self.open_folder).grid(row=0, column=4, padx=(0, 6))
        ghost_button(head, "Settings", self.open_settings).grid(row=0, column=5)

        # search
        sb = ctk.CTkFrame(r, fg_color="transparent")
        sb.grid(row=1, column=0, sticky="ew", padx=24, pady=(8, 6))
        sb.grid_columnconfigure(0, weight=1)
        self.search_box = box = ctk.CTkFrame(sb, height=48, corner_radius=12, border_width=2, border_color=LINE,
                                             fg_color=PANEL)
        box.grid(row=0, column=0, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(box, height=40, border_width=0, corner_radius=8, fg_color=PANEL, text_color=FG,
                                  font=F(14), placeholder_text="Paste a video link, or type to search videos…",
                                  placeholder_text_color=DIM)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=3)
        self.clear_btn = ctk.CTkButton(box, text="✕", width=32, height=32, corner_radius=16, fg_color="transparent",
                                       hover_color=CARD_HOVER, text_color=MUTED, font=F(14, family=SYMBOLS),
                                       command=self.clear_search)
        Tooltip(self.clear_btn, "Clear")
        self.entry.bind("<Return>", lambda e: self.go())
        self.entry.bind("<KeyRelease>", lambda e: self._sync_clear())
        self.entry.bind("<FocusIn>", lambda e: box.configure(border_color=ORANGE))
        self.entry.bind("<FocusOut>", lambda e: box.configure(border_color=LINE))
        ghost_button(sb, "Paste", self.paste_and_go, width=86, ).grid(row=0, column=1, padx=(10, 0))
        primary_button(sb, "Find", self.go, height=48, size=15, width=120).grid(row=0, column=2, padx=(10, 0))

        # where to search (row 2)
        chips = ctk.CTkFrame(r, fg_color="transparent")
        chips.grid(row=2, column=0, sticky="ew", padx=24, pady=(2, 2))
        ctk.CTkLabel(chips, text="Search in", font=F(12), text_color=DIM).grid(row=0, column=0, padx=(2, 10))
        self.source = self.settings.get("search_source", "All")
        if self.source not in engine.SEARCH_SOURCES:
            self.source = "All"
        self.chip_btns = {}
        for i, name in enumerate(engine.SEARCH_SOURCES, start=1):
            b = self._chip(chips, name)
            b.grid(row=0, column=i, padx=3, pady=4)
            self.chip_btns[name] = b
        g = ctk.CTkButton(chips, text="Google  ↗", width=0, height=30, corner_radius=15, fg_color="transparent",
                          hover_color=CARD_HOVER, text_color=MUTED, border_width=1, border_color=LINE, font=F(12),
                          command=self.google_search)
        g.grid(row=0, column=len(self.chip_btns) + 1, padx=(10, 0))
        Tooltip(g, "Search Google videos in your browser (use the browser button there)")
        self._paint_chips()

        # copied-link banner (row 3, hidden until needed)
        self.banner = ctk.CTkFrame(r, fg_color=ORANGE_SOFT, corner_radius=10)
        self.banner.grid_columnconfigure(0, weight=1)
        self.banner_lbl = ctk.CTkLabel(self.banner, text="", font=F(12), text_color=FG, anchor="w")
        self.banner_lbl.grid(row=0, column=0, sticky="ew", padx=14, pady=8)
        ctk.CTkButton(self.banner, text="Dismiss", width=80, height=30, fg_color="transparent", hover_color=CARD,
                      text_color=MUTED, command=lambda: self.banner.grid_remove(), font=F(12)).grid(row=0, column=1)
        primary_button(self.banner, "Get this video", self._banner_go, height=30, size=12, width=130).grid(
            row=0, column=2, padx=(6, 10), pady=6)

        # body
        body = ctk.CTkFrame(r, fg_color="transparent")
        body.grid(row=4, column=0, sticky="nsew", padx=24, pady=(8, 10))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=14, width=self.pw + 24)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 18))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.preview = ctk.CTkScrollableFrame(left, width=self.pw, fg_color=PANEL, corner_radius=14,
                                              scrollbar_button_color=LINE, scrollbar_button_hover_color=DIM)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=4, pady=(4, 0))
        self.preview.grid_columnconfigure(0, weight=1)
        # Download button lives outside the scroll area so it is always visible
        self.action = ctk.CTkFrame(left, fg_color=PANEL, corner_radius=14)
        self.action.grid_columnconfigure(0, weight=1)
        self.dl_btn = primary_button(self.action, "Download", self.start_download, height=48, size=16)
        self.dl_btn.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 16))
        self.close_preview = ctk.CTkButton(left, text="✕", width=30, height=30, corner_radius=15, fg_color=CARD,
                                           hover_color="#5A1F1F", text_color=FG, font=F(13, family=SYMBOLS),
                                           command=self.close_preview_panel)
        Tooltip(self.close_preview, "Close preview")
        self._show_welcome()

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        rh.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(rh, text="Downloads", font=F(18, "bold"), text_color=FG).grid(row=0, column=0, sticky="w")
        self.filter_btn = ctk.CTkSegmentedButton(
            rh, values=["All", "Active", "Done", "Failed"], command=self._set_filter, font=F(12), height=32,
            selected_color=ORANGE, selected_hover_color=ORANGE_H, unselected_color=CARD, unselected_hover_color=CARD_HOVER,
            fg_color=CARD, text_color=FG)
        self.filter_btn.set("All")
        self.filter_btn.grid(row=0, column=2, padx=8)
        ghost_button(rh, "Clear finished", self.clear_finished).grid(row=0, column=3)

        self.list = ctk.CTkScrollableFrame(right, fg_color="transparent", scrollbar_button_color=LINE,
                                           scrollbar_button_hover_color=DIM)
        self.list.grid(row=1, column=0, sticky="nsew")
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.list, text="", font=F(13), text_color=DIM, justify="center")

        # status bar
        bar = ctk.CTkFrame(r, fg_color=PANEL, corner_radius=0, height=30)
        bar.grid(row=5, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(bar, text="", font=F(11), text_color=MUTED, anchor="w")
        self.status.grid(row=0, column=0, sticky="ew", padx=16, pady=4)
        self.status_right = ctk.CTkLabel(bar, text="", font=F(11), text_color=DIM, anchor="e")
        self.status_right.grid(row=0, column=1, sticky="e", padx=16)
        self.status.bind("<Configure>", lambda e: self._fit_status())
        self._status_text = ""
        self._set_status("Starting engine…")

    def _set_status(self, msg: str):
        self._status_text = msg
        folder = self.settings["folder"]
        if len(folder) > 48:
            folder = "…" + folder[-46:]
        self.status_right.configure(text=f"Saving to {folder}   •   v{VERSION}")
        self._fit_status()

    def _fit_status(self):
        self.status.configure(text=ellipsize(self.status, self._status_text, self.status.winfo_width() - 10))

    # ------------------------------------------------ preview panel
    def _clear_preview(self, closable=True):
        self.action.grid_remove()
        if closable:
            self.close_preview.place(relx=1.0, x=-12, y=12, anchor="ne")
            self.close_preview.lift()
        else:
            self.close_preview.place_forget()
        for c in self.preview.winfo_children():
            c.destroy()
        try:
            self.preview._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _section_title(self, text, row):
        ctk.CTkLabel(self.preview, text=text, font=F(17, "bold"), text_color=FG, anchor="w").grid(
            row=row, column=0, sticky="ew", padx=18, pady=(18, 8))

    def _show_welcome(self):
        self._clear_preview(closable=False)
        self._section_title("How to download", 0)
        steps = (("1", "Copy a video link from YouTube, Facebook, Instagram, TikTok, X, Vimeo — almost any site."),
                 ("2", "Paste it above and press Find. Copied links are also noticed automatically."),
                 ("3", "Pick Video or Audio and a quality (sizes are shown), then Download."),
                 ("★", "No link? Type a few words above to search — everywhere, or only on YouTube, Facebook… (pick below the box)."))
        for i, (n, t) in enumerate(steps, start=1):
            row = ctk.CTkFrame(self.preview, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", padx=18, pady=6)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=n, width=26, height=26, corner_radius=13, fg_color=ORANGE_SOFT, text_color=ORANGE,
                         font=F(12, "bold")).grid(row=0, column=0, sticky="n")
            ctk.CTkLabel(row, text=t, font=F(13), text_color="#D4D4D8", wraplength=self.pw - 80, justify="left", anchor="w").grid(
                row=0, column=1, sticky="w", padx=(12, 0))
        ctk.CTkLabel(self.preview, text="Netflix, Prime Video, Hotstar and other DRM services can't be downloaded by "
                                        "any downloader.", font=F(11), text_color=DIM, wraplength=self.pw - 40, justify="left",
                     anchor="w").grid(row=9, column=0, sticky="ew", padx=18, pady=(22, 18))

    def _show_loading(self, text="Finding video…"):
        self._clear_preview()
        ctk.CTkLabel(self.preview, text="", height=90).grid(row=0, column=0)
        bar = ctk.CTkProgressBar(self.preview, mode="indeterminate", progress_color=ORANGE, fg_color=LINE, width=220)
        bar.grid(row=1, column=0, pady=10)
        bar.start()
        ctk.CTkLabel(self.preview, text=text, font=F(15, "bold"), text_color=FG).grid(row=2, column=0, pady=(8, 2))
        ctk.CTkLabel(self.preview, text=engine.host_of(self.info_url), font=F(12), text_color=DIM).grid(row=3, column=0)

    def _show_error(self, e: EngineError, url: str):
        self._clear_preview()
        ctk.CTkLabel(self.preview, text="🔒" if e.drm else "⚠", font=F(40, family=SYMBOLS),
                     text_color=WARN if e.drm else BAD).grid(row=0, column=0, pady=(60, 8))
        ctk.CTkLabel(self.preview, text=e.friendly, font=F(14), text_color=FG, wraplength=self.pw - 50, justify="left").grid(
            row=1, column=0, sticky="ew", padx=22)
        if not e.drm:
            det = ctk.CTkTextbox(self.preview, height=110, fg_color=CARD, text_color=MUTED, font=F(11), wrap="word")
            det.insert("1.0", e.detail or "")
            det.configure(state="disabled")
            shown = {"v": False}

            def toggle():
                if shown["v"]:
                    det.grid_remove()
                else:
                    det.grid(row=3, column=0, sticky="ew", padx=22, pady=6)
                shown["v"] = not shown["v"]
            ctk.CTkButton(self.preview, text="Show details", command=toggle, fg_color="transparent", hover_color=CARD,
                          text_color=ORANGE, font=F(12), width=100, anchor="w").grid(row=2, column=0, sticky="w", padx=16,
                                                                                    pady=(12, 0))
            row = ctk.CTkFrame(self.preview, fg_color="transparent")
            row.grid(row=4, column=0, sticky="w", padx=22, pady=14)
            retry = (lambda: self.load(url)) if url else self.go          # empty url = a search failed
            primary_button(row, "Try again", retry, height=36, size=13, width=120).grid(row=0, column=0)
            if e.login_site:
                ghost_button(row, "Settings", self.open_settings, width=100).grid(row=0, column=1, padx=8)
            elif not url:
                ghost_button(row, "Search on Google  ↗", self.google_search, width=150).grid(row=0, column=1, padx=8)

    def _show_results(self, results: list[engine.SearchResult], query: str):
        self._clear_preview()
        where = "" if self.source == "All" else f" on {self.source}"
        self._section_title(f"“{query[:30]}”{where}", 0)
        if not results:
            ctk.CTkLabel(self.preview, text="Nothing found.", text_color=DIM, font=F(13)).grid(row=1, column=0, padx=18,
                                                                                              sticky="w")
        size = (112, 63)
        for i, res in enumerate(results, start=1):
            row = ctk.CTkFrame(self.preview, fg_color=CARD, corner_radius=10, cursor="hand2")
            row.grid(row=i, column=0, sticky="ew", padx=12, pady=4)
            row.grid_columnconfigure(1, weight=1)
            th = ctk.CTkLabel(row, text="", width=size[0], height=size[1],
                              image=ctk.CTkImage(rounded(placeholder(size[0] * 2, size[1] * 2), 12), size=size))
            th.grid(row=0, column=0, rowspan=2, padx=8, pady=8)
            t = ctk.CTkLabel(row, text=res.title, font=F(12, "bold"), text_color=FG, wraplength=self.pw - 170, justify="left",
                             anchor="w")
            t.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
            meta = " • ".join(x for x in ((res.channel if res.source == "YouTube" else ""), human_time(res.duration),
                                           "YouTube" if res.source == "YouTube" else res.source) if x)
            m = ctk.CTkLabel(row, text=meta, font=F(11), text_color=DIM, anchor="w")
            m.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))
            for w in (row, th, t, m):
                w.bind("<Button-1>", lambda e, u=res.url: self.load(u))
            row.bind("<Enter>", lambda e, rw=row: rw.configure(fg_color=CARD_HOVER))
            row.bind("<Leave>", lambda e, rw=row: rw.configure(fg_color=CARD))
            if res.thumbnail:
                self.thumbs.get(res.thumbnail, size,
                                lambda img, lb=th: lb.winfo_exists() and lb.configure(
                                    image=ctk.CTkImage(rounded(img, 12), size=size)))
            else:
                def with_favicon(icon, lb=th):
                    if not lb.winfo_exists():
                        return
                    base = Image.new("RGB", (size[0] * 2, size[1] * 2), CARD_HOVER)
                    ic = icon.convert("RGBA").resize((56, 56), Image.LANCZOS)
                    base.paste(ic, ((base.width - 56) // 2, (base.height - 56) // 2), ic)
                    lb.configure(image=ctk.CTkImage(rounded(base, 12), size=size))
                self.thumbs.get_raw(f"https://www.google.com/s2/favicons?domain={res.source}&sz=64", with_favicon)

    def _show_info(self, info: MediaInfo):
        self.info = info
        self._clear_preview()
        p = self.preview
        if self.short:
            size = (144, 81)
            head = ctk.CTkFrame(p, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
            head.grid_columnconfigure(1, weight=1)
            thumb_parent, text_parent, wrap = head, head, self.pw - size[0] - 50
        else:
            tw = self.pw - 28
            size = (tw, int(tw * 9 / 16))
            thumb_parent, text_parent, wrap = p, p, self.pw - 40
        radius = 14 if self.short else 24
        self.thumb_lbl = ctk.CTkLabel(thumb_parent, text="", width=size[0], height=size[1], cursor="hand2",
                                      image=ctk.CTkImage(rounded(placeholder(size[0] * 2, size[1] * 2), radius), size=size))
        if self.short:
            self.thumb_lbl.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 12))
        else:
            self.thumb_lbl.grid(row=0, column=0, padx=14, pady=(14, 10))
        self.thumb_lbl.bind("<Button-1>", lambda e: webbrowser.open(info.url))
        Tooltip(self.thumb_lbl, "Open the original page")
        if info.thumbnail:
            def set_img(img, d=info.duration):
                if not self.thumb_lbl.winfo_exists():
                    return
                if d:
                    dr = ImageDraw.Draw(img)
                    txt = human_time(d)
                    try:
                        from PIL import ImageFont
                        fnt = ImageFont.truetype("segoeuib.ttf" if IS_WIN else "DejaVuSans-Bold.ttf",
                                                 max(16, img.height // 12))
                    except Exception:
                        fnt = None
                    tw_ = int(dr.textlength(txt, font=fnt)) if fnt else 9 * len(txt)
                    pad = max(8, img.height // 40)
                    th_ = (fnt.size if fnt else 14) + pad * 2
                    x1, y1 = img.width - tw_ - pad * 4, img.height - th_ - pad * 2
                    dr.rounded_rectangle((x1, y1, img.width - pad * 2, img.height - pad * 2), pad, fill=(0, 0, 0))
                    dr.text((x1 + pad, y1 + pad * 0.6), txt, fill=(255, 255, 255), font=fnt)
                self.thumb_lbl.configure(image=ctk.CTkImage(rounded(img, radius * 2), size=size))
            self.thumbs.get(info.thumbnail, size, set_img)

        title_kw = dict(text=info.title, font=F(14 if self.short else 15, "bold"), text_color=FG, wraplength=wrap,
                        justify="left", anchor="w")
        meta = "  •  ".join(x for x in (info.uploader, info.site, f"{compact(info.views)} views" if info.views else None,
                                         f"{info.count} videos" if info.is_playlist else None) if x)
        if self.short:
            ctk.CTkLabel(text_parent, **title_kw).grid(row=0, column=1, sticky="new")
            if meta:
                ctk.CTkLabel(text_parent, text=meta, font=F(11), text_color=MUTED, wraplength=wrap, justify="left",
                             anchor="w").grid(row=1, column=1, sticky="new", pady=(4, 0))
        else:
            ctk.CTkLabel(p, **title_kw).grid(row=1, column=0, sticky="ew", padx=18)
            if meta:
                ctk.CTkLabel(p, text=meta, font=F(12), text_color=MUTED, wraplength=wrap, justify="left",
                             anchor="w").grid(row=2, column=0, sticky="ew", padx=18, pady=(4, 0))

        self.tabs = ctk.CTkSegmentedButton(
            p, values=["Video", "Audio"], command=self._switch_tab, font=F(13, "bold"), height=36,
            selected_color=ORANGE, selected_hover_color=ORANGE_H, unselected_color=CARD, unselected_hover_color=CARD_HOVER,
            fg_color=CARD, text_color=FG)
        self.tabs.grid(row=3, column=0, sticky="ew", padx=18, pady=(16, 8))
        self.opts = ctk.CTkFrame(p, fg_color="transparent")
        self.opts.grid(row=4, column=0, sticky="ew", padx=12)
        self.opts.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(p, text="File name", font=F(12), text_color=MUTED, anchor="w").grid(
            row=5, column=0, sticky="ew", padx=18, pady=(12, 2))
        self.name_entry = ctk.CTkEntry(p, height=38, corner_radius=9, fg_color=CARD, border_color=LINE, text_color=FG,
                                       font=F(13))
        self.name_entry.grid(row=6, column=0, sticky="ew", padx=18)
        if not info.is_playlist:
            self.name_entry.insert(0, info.title)
        else:
            self.name_entry.configure(placeholder_text="(each video keeps its own name)", state="disabled")
        self.pl_var = tk.BooleanVar(value=info.is_playlist)
        if info.is_playlist or "list=" in info.url:
            ctk.CTkCheckBox(p, text=f"Whole playlist ({info.count} videos)" if info.is_playlist else
                            "Download the whole playlist", variable=self.pl_var, font=F(12), text_color=FG,
                            fg_color=ORANGE, hover_color=ORANGE_H, border_color=DIM).grid(
                row=7, column=0, sticky="w", padx=18, pady=(10, 0))
        ctk.CTkLabel(p, text="", height=6).grid(row=8, column=0)
        self.action.grid(row=1, column=0, sticky="ew")
        self._switch_tab("Video" if info.video else "Audio")

    def _switch_tab(self, key):
        if not self.info or not getattr(self, "tabs", None) or not self.tabs.winfo_exists():
            return
        self.tab = key
        self.tabs.set(key)
        for c in self.opts.winfo_children():
            c.destroy()
        options = self.info.video if key == "Video" else self.info.audio
        if not options:
            ctk.CTkLabel(self.opts, text="No video in this link — see the Audio tab.", text_color=DIM, font=F(12)).grid(
                row=0, column=0, pady=12)
            return
        default = next((i for i, q in enumerate(options) if (q.height or 0) <= 1080), 0) if key == "Video" else 0
        self.quality_var.set(default)
        rows = []

        def paint():
            for i, rw in enumerate(rows):
                rw.configure(fg_color=ORANGE_SOFT if self.quality_var.get() == i else "transparent",
                             border_color=ORANGE if self.quality_var.get() == i else LINE)

        for i, q in enumerate(options):
            row = ctk.CTkFrame(self.opts, fg_color="transparent", corner_radius=10, border_width=1, border_color=LINE,
                               cursor="hand2")
            row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            row.grid_columnconfigure(1, weight=1)
            rb = ctk.CTkRadioButton(row, text="", variable=self.quality_var, value=i, width=22, fg_color=ORANGE,
                                    hover_color=ORANGE_H, border_color=DIM, command=paint)
            rb.grid(row=0, column=0, padx=(12, 4), pady=10)
            name = ctk.CTkLabel(row, text=q.label, font=F(13, "bold" if i == default else "normal"), text_color=FG,
                                anchor="w")
            name.grid(row=0, column=1, sticky="ew")
            size_txt = ("≈ " + human_size(q.size)) if q.size else ("" if self.info.is_playlist else "size unknown")
            sz = ctk.CTkLabel(row, text=size_txt, font=F(12), text_color=MUTED)
            sz.grid(row=0, column=2, padx=(6, 14))
            for w in (row, name, sz):
                w.bind("<Button-1>", lambda e, v=i: (self.quality_var.set(v), paint()))
            rows.append(row)
        paint()

    # ------------------------------------------------ actions
    def _sync_clear(self):
        if self.entry.get():
            self.clear_btn.grid(row=0, column=1, padx=(0, 8))
        else:
            self.clear_btn.grid_remove()

    def set_search(self, text: str):
        self.entry.delete(0, "end")
        if text:
            self.entry.insert(0, text)
        self._sync_clear()

    def clear_search(self):
        self.set_search("")
        self.entry.focus_set()

    def close_preview_panel(self):
        self.req_id += 1          # ignore any result still on its way
        self.info = None
        self.info_url = ""
        self._show_welcome()

    def open_folder(self):
        os.makedirs(self.settings["folder"], exist_ok=True)
        open_path(self.settings["folder"])

    def _clip_text(self) -> str:
        try:
            return self.root.clipboard_get().strip()
        except tk.TclError:
            return ""

    def paste_and_go(self):
        text = self._clip_text()
        if not text:
            self._set_status("Clipboard is empty — copy a link first")
            return
        self.set_search(text)
        self.last_clip = text
        self.go()

    def go(self):
        text = self.entry.get().strip()
        if not text:
            return self.paste_and_go()
        urls = engine.extract_urls(text)
        if len(urls) > 1:
            for u in urls:
                self.add_download(u, u, engine.BEST, False, None)
            self._set_status(f"Added {len(urls)} links with best quality")
            return
        if urls:
            self.load(urls[0])
        else:
            self.search(text)

    def load(self, url: str, fallback: str | None = None, title_hint: str | None = None):
        self.req_id += 1
        rid = self.req_id
        self.info_url = url
        self.banner.grid_remove()
        self._show_loading()
        threading.Thread(target=self._info_worker, args=(rid, url, fallback, title_hint), daemon=True).start()

    def _info_worker(self, rid, url, fallback=None, title_hint=None):
        try:
            try:
                info = self.engine.info(url)
            except EngineError as first:
                # The browser button also sends the video's own file — try it when the page link fails
                if not fallback or not fallback.startswith("http") or first.drm:
                    raise
                info = self.engine.info(fallback)
                if title_hint and (info.site is None or info.title in fallback):
                    info.title = title_hint
            self.ui_q.put(("info", (rid, info)))
        except EngineError as e:
            self.ui_q.put(("info_err", (rid, e, url)))
        except Exception as e:
            self.ui_q.put(("info_err", (rid, EngineError(str(e)[:200], repr(e)), url)))

    # ------------------------------------------------ from the browser button
    def handle_external(self, d: dict):
        url = d.get("url", "")
        if not url:
            return
        self.bring_to_front()
        self.set_search(url)
        self.last_clip = url
        if self.settings.get("ext_mode", "panel") == "best":
            self.add_download(url, d.get("title") or url, engine.BEST, False, None)
            self._set_status("Download started from your browser ⬇")
        else:
            self.load(url, fallback=d.get("src") or None, title_hint=d.get("title") or None)

    def bring_to_front(self):
        r = self.root
        try:
            if r.state() == "iconic":
                r.deiconify()
            r.lift()
            r.attributes("-topmost", True)
            r.after(400, lambda: r.attributes("-topmost", False))
            r.focus_force()
        except Exception:
            pass

    def open_ext_setup(self):
        ExtensionDialog(self)

    # ------------------------------------------------ API used by the browser button (runs on server threads)
    def call_in_ui(self, fn, timeout=15):
        """Run fn on the window's thread and return its result."""
        done, box = threading.Event(), {}

        def run():
            try:
                box["v"] = fn()
            except Exception as e:
                box["e"] = e
            done.set()
        self.ui_q.put(("call", run))
        if not done.wait(timeout):
            raise TimeoutError("App is busy")
        if "e" in box:
            raise box["e"]
        return box.get("v")

    def ext_add(self, d):
        self.ui_q.put(("ext_add", d))

    def focus(self):
        self.ui_q.put(("call", self.bring_to_front))

    @staticmethod
    def _q_json(q: Quality):
        return {"label": q.label, "size": q.size, "audio": q.is_audio}

    def api_info(self, d):
        mode = self.settings.get("ext_mode", "panel")
        if mode == "app":
            self.ext_add(d)
            return {"ok": True, "mode": "app"}
        if mode == "best":
            iid = self.call_in_ui(lambda: self.add_download(d["url"], d.get("title") or d["url"], engine.BEST, False, None))
            return {"ok": True, "mode": "started", "id": iid, "title": d.get("title") or ""}
        try:
            try:
                info = self.engine.info(d["url"])
            except EngineError as first:
                src = d.get("src") or ""
                if not src.startswith("http") or first.drm:
                    raise
                info = self.engine.info(src)
                if d.get("title") and (info.site is None or info.title in src):
                    info.title = d["title"]
        except EngineError as e:
            return {"ok": False, "error": e.friendly, "detail": e.detail, "drm": e.drm}
        token = uuid.uuid4().hex
        self.ext_infos[token] = info
        while len(self.ext_infos) > 40:
            self.ext_infos.pop(next(iter(self.ext_infos)))
        return {"ok": True, "mode": "panel", "token": token, "title": info.title, "thumbnail": info.thumbnail,
                "uploader": info.uploader, "site": info.site, "duration": info.duration, "views": info.views,
                "is_playlist": info.is_playlist, "count": info.count,
                "video": [self._q_json(q) for q in info.video], "audio": [self._q_json(q) for q in info.audio],
                "folder": self.settings["folder"]}

    def api_download(self, d):
        info = self.ext_infos.get(str(d.get("token", "")))
        if not info:
            return {"ok": False, "error": "Please press the download button on the video again."}
        options = info.audio if d.get("kind") == "audio" else info.video
        try:
            q = options[int(d.get("index", 0))]
        except (ValueError, IndexError):
            return {"ok": False, "error": "That quality isn't available."}
        playlist = bool(d.get("playlist")) and info.is_playlist
        # direct video files have no real title: save them under the caption shown on the page
        name = None
        if info.site is None and info.title and not playlist:
            name = "".join(c if c not in '\\/:*?"<>|\n\r\t' else " " for c in info.title).strip()[:150] or None
        iid = self.call_in_ui(lambda: self.add_download(info.url, info.title, q, playlist, name,
                                                        thumb=info.thumbnail, duration=info.duration))
        self.ui_q.put(("status", f"Download started from your browser: {info.title}"))
        return {"ok": True, "id": iid}

    def api_status(self, iid):
        it = self._get(iid)
        if not it:
            return {"ok": False}
        return {"ok": True, "status": it.status, "pct": round(it.pct, 1), "speed": it.speed, "eta": it.eta,
                "total": it.total, "error": it.error, "title": it.title, "quality": it.quality.label,
                "file": it.files[0] if it.files else ""}

    def api_open(self, d):
        it = self._get(str(d.get("id", "")))
        if not it:
            return {"ok": False}
        if d.get("action") == "folder":
            self.ui_q.put(("call", lambda: self.show(it)))
        else:
            self.ui_q.put(("call", lambda: self.play(it)))
        return {"ok": True}

    def api_cancel(self, d):
        it = self._get(str(d.get("id", "")))
        if it:
            self.ui_q.put(("call", lambda: self.cancel(it)))
        return {"ok": bool(it)}

    def _chip(self, master, name):
        icon_only = self.compact and name not in ("All", "Web")
        b = ctk.CTkButton(master, text="" if icon_only else name, width=34 if icon_only else 0, height=30,
                          corner_radius=15, border_width=1, font=F(12), command=lambda n=name: self.set_source(n),
                          compound="left")
        Tooltip(b, "Search everywhere" if name == "All" else ("Search the web" if name == "Web" else f"Search {name}"))
        dom = engine.SEARCH_SOURCES.get(name)
        if dom:
            self.thumbs.get_raw(f"https://www.google.com/s2/favicons?domain={dom}&sz=64",
                                lambda img, b=b: b.winfo_exists() and b.configure(
                                    text="" if icon_only else name,
                                    image=ctk.CTkImage(img.convert("RGBA").resize((32, 32), Image.LANCZOS), size=(16, 16))))
            if icon_only:
                b.configure(text=name[0])
        return b

    def _paint_chips(self):
        for n, b in self.chip_btns.items():
            on = n == self.source
            b.configure(fg_color=ORANGE_SOFT if on else CARD, border_color=ORANGE if on else LINE,
                        text_color=FG if on else MUTED, hover_color=ORANGE_SOFT if on else CARD_HOVER)

    def set_source(self, name):
        self.source = name
        self.settings["search_source"] = name
        self._save_settings()
        self._paint_chips()
        text = self.entry.get().strip()
        if text and not engine.extract_urls(text):
            self.search(text)
        else:
            self.entry.focus_set()

    def google_search(self):
        import urllib.parse
        q = self.entry.get().strip()
        if q and not engine.extract_urls(q):
            webbrowser.open("https://www.google.com/search?tbm=vid&q=" + urllib.parse.quote(q))
        else:
            webbrowser.open("https://www.google.com/videohp")

    def search(self, query: str):
        self.req_id += 1
        rid = self.req_id
        src = self.source
        self.info_url = "https://youtube.com" if src == "YouTube" else ""
        self._show_loading("Searching everywhere…" if src == "All" else f"Searching {src}…")

        def work():
            results, errors = [], []
            if src in ("All", "YouTube"):
                try:
                    results += self.engine.search(query, 8 if src == "All" else 15)
                except Exception as e:
                    errors.append(e)
            if src != "YouTube":
                try:
                    web = self.engine.web_search(query, engine.SEARCH_SOURCES.get(src), 12)
                    if src == "All":
                        web = [r for r in web if not engine.is_youtube(r.url)]
                    results += web
                except Exception as e:
                    errors.append(e)
            if not results and errors:
                e = errors[0]
                err = e if isinstance(e, EngineError) else EngineError(str(e)[:200], repr(e))
                self.ui_q.put(("info_err", (rid, err, "")))
            else:
                self.ui_q.put(("results", (rid, results, query)))
        threading.Thread(target=work, daemon=True).start()

    def start_download(self):
        if not self.info:
            return
        options = self.info.video if self.tab == "Video" else self.info.audio
        if not options:
            return
        q = options[self.quality_var.get()]
        playlist = bool(self.pl_var.get())
        name = self.name_entry.get().strip() if not self.info.is_playlist else ""
        clean = None
        if name and not playlist and name != self.info.title:
            clean = "".join(c if c not in '\\/:*?"<>|' else " " for c in name).strip()[:150] or None
        self.add_download(self.info.url, name or self.info.title, q, playlist, clean,
                          thumb=self.info.thumbnail, duration=self.info.duration)
        self.dl_btn.configure(text="✓  Added to Downloads", fg_color=GOOD, hover_color=GOOD)
        self.root.after(1600, lambda: self.dl_btn.winfo_exists() and self.dl_btn.configure(
            text="Download", fg_color=ORANGE, hover_color=ORANGE_H))

    def add_download(self, url, title, q: Quality, playlist, name, thumb=None, duration=0):
        it = Item(uuid.uuid4().hex, url, title, q, playlist, name, self.settings["folder"], thumb, duration)
        self.items.append(it)
        if self.filter in ("Done", "Failed"):
            self._set_filter("All")
        else:
            self._render_list()
        self._save_history()
        return it.id

    def play(self, it: Item):
        if it.files:
            open_path(it.files[0])
        elif it.status == "Done":
            open_path(it.folder)

    def show(self, it: Item):
        show_in_folder(it.files[0] if it.files else it.folder)

    def details(self, it: Item):
        messagebox.showinfo("Error details", f"{it.error}\n\n{it.detail}", parent=self.root)

    def cancel(self, it: Item):
        if it.active:
            was_running = it.status != "Queued"
            it.status = "Cancelled"
            if was_running:
                threading.Thread(target=self.engine.cancel, args=(it.id,), daemon=True).start()
            self._mark(it)
            self._save_history()

    def retry(self, it: Item):
        if it.status in ("Failed", "Cancelled"):
            it.status, it.error, it.detail, it.pct, it.speed, it.eta = "Queued", "", "", 0, 0, 0
            self._mark(it)
            self._render_list()

    def remove(self, it: Item):
        if it.active:
            self.cancel(it)
        if it in self.items:
            self.items.remove(it)
        self._render_list()
        self._save_history()

    def clear_finished(self):
        self.items = [i for i in self.items if i.active or i.status == "Failed"]
        self._render_list()
        self._save_history()

    def _set_filter(self, value):
        self.filter = value
        self.filter_btn.set(value)
        self._render_list()

    # ------------------------------------------------ downloads list
    def _visible(self) -> list[Item]:
        f = self.filter
        items = list(reversed(self.items))
        if f == "Active":
            items = [i for i in items if i.active]
        elif f == "Done":
            items = [i for i in items if i.status == "Done"]
        elif f == "Failed":
            items = [i for i in items if i.status in ("Failed", "Cancelled")]
        return items[:150]

    def _render_list(self):
        vis = self._visible()
        ids = [i.id for i in vis]
        for iid in list(self.cards):
            if iid not in ids:
                self.cards.pop(iid).destroy()
        for row, it in enumerate(vis):
            card = self.cards.get(it.id)
            if card is None:
                card = self.cards[it.id] = DownloadCard(self.list, self, it)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10), padx=(0, 6))
        if vis:
            self.empty.grid_remove()
        else:
            msg = {"All": "No downloads yet.\nPaste a link above and press Find.",
                   "Active": "Nothing downloading right now.", "Done": "No finished downloads.",
                   "Failed": "No failed downloads."}[self.filter]
            self.empty.configure(text=msg)
            self.empty.grid(row=0, column=0, pady=80)
        counts = {"Active": sum(i.active for i in self.items),
                  "Failed": sum(i.status in ("Failed", "Cancelled") for i in self.items)}
        self.root.title(f"{APP} — {counts['Active']} downloading" if counts["Active"] else APP)

    def _mark(self, it: Item):
        self._dirty.add(it.id)

    # ------------------------------------------------ workers
    def _dispatch(self):
        limit = max(1, int(self.settings.get("parallel", 3)))
        for it in self.items:
            if self.running >= limit:
                break
            if it.status == "Queued":
                it.status = "Starting"
                self.running += 1
                self._mark(it)
                threading.Thread(target=self._dl_worker, args=(it,), daemon=True).start()
        self.root.after(500, self._dispatch)

    def _dl_worker(self, it: Item):
        try:
            os.makedirs(it.folder, exist_ok=True)
            files = self.engine.download(it.id, it.url, it.quality, it.folder, it.playlist, it.name,
                                         lambda d: self.ui_q.put(("prog", (it.id, d))))
            self.ui_q.put(("done", (it.id, files)))
        except EngineError as e:
            self.ui_q.put(("fail", (it.id, e)))
        except Exception as e:
            self.ui_q.put(("fail", (it.id, EngineError(str(e)[:200], repr(e)))))

    def _get(self, iid) -> Item | None:
        return next((i for i in self.items if i.id == iid), None)

    def _pump(self):
        relist = False
        try:
            for _ in range(400):
                kind, data = self.ui_q.get_nowait()
                if kind == "call":
                    data()
                elif kind == "ext_add":
                    self.handle_external(data)
                elif kind == "info":
                    rid, info = data
                    if rid == self.req_id:
                        self._show_info(info)
                elif kind == "info_err":
                    rid, e, url = data
                    if rid == self.req_id:
                        self._show_error(e, url)
                elif kind == "results":
                    rid, res, query = data
                    if rid == self.req_id:
                        self._show_results(res, query)
                elif kind == "prog":
                    iid, d = data
                    it = self._get(iid)
                    if it and it.active:
                        if d["stage"] == "processing":
                            it.status, it.speed, it.eta = "Processing", 0, 0
                        else:
                            it.status, it.pct, it.speed, it.eta = "Downloading", d["pct"], d["speed"], d["eta"]
                            it.total = d["total"] or it.total
                        self._mark(it)
                elif kind == "done":
                    iid, files = data
                    it = self._get(iid)
                    self.running = max(0, self.running - 1)
                    if it and it.status != "Cancelled":
                        it.status, it.pct, it.files, it.speed, it.eta = "Done", 100, files, 0, 0
                        try:
                            it.total = sum(os.path.getsize(f) for f in files) or it.total
                        except OSError:
                            pass
                        self._set_status(f"Downloaded: {it.title}")
                        self._mark(it)
                        if self.settings.get("notify", True):
                            f0 = files[0] if files else ""
                            notify.toast("Download complete", it.title,
                                         bridge.file_link("play", f0) if f0 else None,
                                         bridge.file_link("show", f0) if f0 else None)
                        relist = True
                    self._save_history()
                elif kind == "fail":
                    iid, e = data
                    it = self._get(iid)
                    self.running = max(0, self.running - 1)
                    if it and it.status != "Cancelled":
                        it.status, it.error, it.detail = "Failed", e.friendly, e.detail
                        self._mark(it)
                        relist = True
                    self._save_history()
                elif kind == "status":
                    self._set_status(data)
        except queue.Empty:
            pass
        for iid in list(self._dirty):
            card = self.cards.get(iid)
            if card and card.winfo_exists():
                card.update_view()
        self._dirty.clear()
        if relist and self.filter != "All":
            self._render_list()
        elif relist:
            self._render_list()
        self.root.after(150, self._pump)

    # ------------------------------------------------ clipboard
    def _watch_clipboard(self):
        try:
            focused = self.root.focus_displayof() is not None
        except Exception:
            focused = False
        if self.settings.get("clipboard", True) and focused:
            clip = self._clip_text()
            if clip != self.last_clip:
                self.last_clip = clip
                urls = engine.extract_urls(clip)
                if urls and len(clip) < 2000 and urls[0] != self.info_url:
                    self._clip_url = urls[0]
                    self.banner_lbl.configure(text="Copied link detected:  " + urls[0])
                    self.banner.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 2))
                    self.root.after(50, lambda: self.banner_lbl.configure(
                        text=ellipsize(self.banner_lbl, "Copied link detected:  " + self._clip_url,
                                       self.banner_lbl.winfo_width() - 10)))
        self.root.after(1200, self._watch_clipboard)

    def _banner_go(self):
        self.set_search(self._clip_url)
        self.load(self._clip_url)

    # ------------------------------------------------ settings / lifecycle
    def open_settings(self):
        SettingsDialog(self)

    def _startup_checks(self):
        v = self.engine.version()
        if v == "not found":
            self.ui_q.put(("status", "⚠ Download engine not found — please reinstall the app"))
            return
        self.ui_q.put(("status", f"Ready  •  engine yt-dlp {v}"))
        if self.settings.get("auto_update", True) and engine._bin("yt-dlp") and \
                time.time() - float(self.settings.get("last_update", 0)) > 24 * 3600:
            msg = self.engine.update().lower()
            self.settings["last_update"] = time.time()
            self._save_settings()
            v = self.engine.version()
            note = "up to date" if ("up to date" in msg or "updated" in msg) else "update check failed"
            self.ui_q.put(("status", f"Ready  •  engine yt-dlp {v} ({note})"))

    def _on_close(self):
        active = [i for i in self.items if i.active]
        if active and not messagebox.askyesno(APP, f"{len(active)} download(s) still running. Quit anyway?",
                                              parent=self.root):
            return
        for i in active:
            i.status = "Cancelled"
            self.engine.cancel(i.id)
        self._save_history()
        self._save_settings()
        self.bridge.stop()
        self.root.destroy()


class SettingsDialog:
    BROWSERS = ["None", "Firefox", "Chrome", "Edge", "Brave", "Opera", "Vivaldi", "Chromium"]

    def __init__(self, app: App):
        self.app = app
        s = app.settings
        w = self.w = ctk.CTkToplevel(app.root, fg_color=PANEL)
        w.title("Settings")
        scale = ctk.ScalingTracker.get_window_scaling(app.root)
        lw, lh = app.root.winfo_screenwidth() / scale, app.root.winfo_screenheight() / scale
        sw_, sh_ = int(min(640, lw * 0.9)), int(min(680, lh * 0.82))
        x = app.root.winfo_rootx() + max(0, int((app.root.winfo_width() - sw_ * scale) / 2))
        y = app.root.winfo_rooty() + 30
        w.geometry(f"{sw_}x{sh_}+{x}+{max(0, y)}")
        w.minsize(int(min(480, lw * 0.8)), int(min(380, lh * 0.6)))
        w.transient(app.root)
        w.after(250, self._finish_open)
        w.grid_columnconfigure(0, weight=1)
        w.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(w, fg_color=PANEL, scrollbar_button_color=LINE)
        body.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 0))
        body.grid_columnconfigure(0, weight=1)
        self.r = 0

        def section(title, note=None):
            ctk.CTkLabel(body, text=title, font=F(15, "bold"), text_color=FG, anchor="w").grid(
                row=self.r, column=0, sticky="ew", padx=16, pady=(18, 4))
            self.r += 1
            if note:
                ctk.CTkLabel(body, text=note, font=F(12), text_color=MUTED, wraplength=sw_ - 90, justify="left",
                             anchor="w").grid(row=self.r, column=0, sticky="ew", padx=16)
                self.r += 1

        def line():
            f = ctk.CTkFrame(body, fg_color="transparent")
            f.grid(row=self.r, column=0, sticky="ew", padx=16, pady=5)
            self.r += 1
            return f

        section("Save downloads to")
        row = line()
        row.grid_columnconfigure(0, weight=1)
        self.folder = ctk.CTkEntry(row, height=36, fg_color=CARD, border_color=LINE, text_color=FG, font=F(12))
        self.folder.insert(0, s["folder"])
        self.folder.grid(row=0, column=0, sticky="ew")
        ghost_button(row, "Browse…", self.browse, width=90).grid(row=0, column=1, padx=(8, 0))

        section("Downloads")
        row = line()
        ctk.CTkLabel(row, text="Downloads at the same time", font=F(13), text_color=FG).grid(row=0, column=0, sticky="w")
        self.parallel = ctk.CTkSegmentedButton(row, values=["1", "2", "3", "4", "5"], font=F(12), selected_color=ORANGE,
                                               selected_hover_color=ORANGE_H, unselected_color=CARD, fg_color=CARD)
        self.parallel.set(str(min(5, int(s.get("parallel", 3)))))
        self.parallel.grid(row=0, column=1, padx=12)
        self.clip = tk.BooleanVar(value=s.get("clipboard", True))
        ctk.CTkCheckBox(line(), text="Notice copied links automatically", variable=self.clip, font=F(13), text_color=FG,
                        fg_color=ORANGE, hover_color=ORANGE_H, border_color=DIM).grid(row=0, column=0, sticky="w")

        section("Browser button", "What happens when you press \"Download this video\" in your browser.")
        row = line()
        self.MODES = {"panel": "Choose on the page", "best": "Best quality at once", "app": "Open in the app"}
        self.ext_mode = ctk.CTkSegmentedButton(row, values=list(self.MODES.values()), font=F(12),
                                               selected_color=ORANGE, selected_hover_color=ORANGE_H,
                                               unselected_color=CARD, fg_color=CARD)
        self.ext_mode.set(self.MODES.get(s.get("ext_mode", "panel"), self.MODES["panel"]))
        self.ext_mode.grid(row=0, column=0, sticky="w")
        ghost_button(row, "Set up…", lambda: (self.w.destroy(), app.open_ext_setup()), width=90).grid(
            row=0, column=1, padx=10)
        self.notify = tk.BooleanVar(value=s.get("notify", True))
        ctk.CTkCheckBox(line(), text="Show a Windows notification when a download finishes", variable=self.notify,
                        font=F(13), text_color=FG, fg_color=ORANGE, hover_color=ORANGE_H, border_color=DIM).grid(
            row=0, column=0, sticky="w")

        section("Logins — only if a site blocks you",
                "Choose a browser where you are logged in (YouTube, Facebook, Instagram…); downloads will use that "
                "login. On Windows, Chrome and Edge often lock their cookies — Firefox works best. Or use a "
                "cookies.txt file exported with the \"Get cookies.txt LOCALLY\" extension.")
        row = line()
        ctk.CTkLabel(row, text="Browser", font=F(13), text_color=FG, width=90, anchor="w").grid(row=0, column=0)
        self.browser = ctk.CTkOptionMenu(row, values=self.BROWSERS, font=F(12), fg_color=CARD, button_color=CARD_HOVER,
                                         button_hover_color=LINE, dropdown_fg_color=CARD, text_color=FG, width=160)
        self.browser.set(s.get("cookies_browser", "None"))
        self.browser.grid(row=0, column=1, sticky="w")
        row = line()
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text="cookies.txt", font=F(13), text_color=FG, width=90, anchor="w").grid(row=0, column=0)
        self.cfile = ctk.CTkEntry(row, height=34, fg_color=CARD, border_color=LINE, text_color=FG, font=F(11),
                                  placeholder_text="(none)", placeholder_text_color=DIM)
        if s.get("cookies_file"):
            self.cfile.insert(0, s["cookies_file"])
        self.cfile.grid(row=0, column=1, sticky="ew")
        ghost_button(row, "Choose…", self.pick_cookies, width=84).grid(row=0, column=2, padx=(8, 0))
        ghost_button(row, "Clear", lambda: self.cfile.delete(0, "end"), width=64).grid(row=0, column=3, padx=(6, 0))

        section("Download engine", "The engine (yt-dlp) keeps sites working. It can update itself once a day.")
        self.auto = tk.BooleanVar(value=s.get("auto_update", True))
        ctk.CTkCheckBox(line(), text="Update automatically once a day", variable=self.auto, font=F(13), text_color=FG,
                        fg_color=ORANGE, hover_color=ORANGE_H, border_color=DIM).grid(row=0, column=0, sticky="w")
        row = line()
        ghost_button(row, "Update now", self.update_now, width=110).grid(row=0, column=0)
        self.upd_lbl = ctk.CTkLabel(row, text="", font=F(12), text_color=MUTED)
        self.upd_lbl.grid(row=0, column=1, padx=12)

        section("Can't be downloaded",
                "Netflix, Prime Video, Disney+/Hotstar, Hoichoi, Chorki and Spotify lock their content with DRM. "
                "Use the download option inside their own apps.")

        # fixed bottom bar — always visible, whatever the screen size
        bottom = ctk.CTkFrame(w, fg_color=BG, corner_radius=0)
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bottom, text=f"Video Downloader v{VERSION}", font=F(11), text_color=DIM).grid(
            row=0, column=0, sticky="w", padx=18)
        ghost_button(bottom, "Cancel", w.destroy, width=90).grid(row=0, column=1, pady=12)
        primary_button(bottom, "Save", self.save, height=34, size=13, width=100).grid(row=0, column=2, padx=(8, 18))

    def _finish_open(self):
        try:
            ico = os.path.join(engine.app_dir(), "icon.ico")
            if IS_WIN and os.path.isfile(ico):
                self.w.iconbitmap(ico)
            self.w.lift()
            self.w.focus_force()
            self.w.grab_set()
        except Exception:
            pass

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get(), parent=self.w)
        if d:
            self.folder.delete(0, "end")
            self.folder.insert(0, os.path.normpath(d))

    def pick_cookies(self):
        f = filedialog.askopenfilename(parent=self.w, filetypes=[("cookies.txt", "*.txt"), ("All files", "*.*")])
        if f:
            self.cfile.delete(0, "end")
            self.cfile.insert(0, os.path.normpath(f))

    def update_now(self):
        self.upd_lbl.configure(text="Updating…")

        def work():
            msg = self.app.engine.update()
            v = self.app.engine.version()
            self.app.settings["last_update"] = time.time()
            self.app.ui_q.put(("status", f"Ready  •  engine yt-dlp {v}"))
            short = "Up to date" if "up to date" in msg.lower() else ("Updated" if "updated" in msg.lower() else msg[:60])
            self.app.ui_q.put(("call", lambda: self.w.winfo_exists() and self.upd_lbl.configure(text=f"{short}  (v{v})")))
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        s = self.app.settings
        s["folder"] = self.folder.get().strip() or default_folder()
        s["parallel"] = int(self.parallel.get() or 3)
        s["clipboard"] = self.clip.get()
        s["cookies_browser"] = self.browser.get()
        s["cookies_file"] = self.cfile.get().strip()
        s["auto_update"] = self.auto.get()
        s["ext_mode"] = next((k for k, v in self.MODES.items() if v == self.ext_mode.get()), "panel")
        s["notify"] = self.notify.get()
        self.app._save_settings()
        self.app._set_status("Settings saved")
        self.w.destroy()


def extension_folder() -> str:
    for p in (os.path.join(engine.app_dir(), "extension"),
              os.path.join(os.path.dirname(engine.app_dir()), "browser-extension")):
        if os.path.isfile(os.path.join(p, "manifest.json")):
            return p
    return os.path.join(engine.app_dir(), "extension")


BROWSERS = [
    ("Chrome", "chrome://extensions", [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                                       r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                                       r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"]),
    ("Edge", "edge://extensions", [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                                   r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"]),
    ("Brave", "brave://extensions", [r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
                                     r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"]),
]


class ExtensionDialog:
    """Step-by-step setup for the IDM-style button in Chrome / Edge / Brave."""

    def __init__(self, app: App):
        self.app = app
        w = self.w = ctk.CTkToplevel(app.root, fg_color=PANEL)
        w.title("Browser button")
        scale = ctk.ScalingTracker.get_window_scaling(app.root)
        lw, lh = app.root.winfo_screenwidth() / scale, app.root.winfo_screenheight() / scale
        ww, wh = int(min(660, lw * 0.9)), int(min(640, lh * 0.82))
        w.geometry(f"{ww}x{wh}+{app.root.winfo_rootx() + 60}+{app.root.winfo_rooty() + 30}")
        w.transient(app.root)
        w.after(250, self._finish_open)
        w.grid_columnconfigure(0, weight=1)
        w.grid_rowconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(w, fg_color=PANEL, scrollbar_button_color=LINE)
        body.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 0))
        body.grid_columnconfigure(0, weight=1)
        wrap = ww - 110
        self.folder = extension_folder()

        ctk.CTkLabel(body, text="Download button on every video", font=F(18, "bold"), text_color=FG, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        ctk.CTkLabel(body, text="Like IDM: while a video plays on YouTube, Facebook, Instagram or any site, an orange "
                                "\"Download this video\" button appears on it. Click it to pick a quality right there on the page — the "
                                "download runs in the background and you get a notification when it's done. "
                                "You can also right-click a page or link → \"Download with Video Downloader\".",
                     font=F(12), text_color=MUTED, wraplength=wrap, justify="left", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=16)
        self.status = ctk.CTkLabel(body, text="", font=F(13, "bold"), anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 4))

        def step(n, row, title, text=None, has_body=True):
            f = ctk.CTkFrame(body, fg_color=CARD, corner_radius=12)
            f.grid(row=row, column=0, sticky="ew", padx=12, pady=6)
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=str(n), width=28, height=28, corner_radius=14, fg_color=ORANGE_SOFT, text_color=ORANGE,
                         font=F(13, "bold")).grid(row=0, column=0, rowspan=3, sticky="n", padx=12, pady=12)
            ctk.CTkLabel(f, text=title, font=F(14, "bold"), text_color=FG, anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(12, 2), padx=(0, 12))
            if text:
                ctk.CTkLabel(f, text=text, font=F(12), text_color=MUTED, wraplength=wrap - 40, justify="left",
                             anchor="w").grid(row=1, column=1, sticky="ew", padx=(0, 12))
            if not has_body:
                ctk.CTkLabel(f, text="", height=4).grid(row=2, column=1)
                return None
            inner = ctk.CTkFrame(f, fg_color="transparent", height=10)
            inner.grid(row=2, column=1, sticky="ew", pady=(6, 12), padx=(0, 12))
            return inner

        s1 = step(1, 3, "Open your browser's extensions page",
                  "Pick your browser. If it doesn't open, type the address shown in its address bar.")
        for i, (name, page, _paths) in enumerate(BROWSERS):
            ghost_button(s1, name, lambda n=name: self.open_page(n), width=90).grid(row=0, column=i, padx=(0, 8))
        self.hint = ctk.CTkLabel(s1, text="", font=F(11), text_color=DIM, anchor="w", height=18)
        self.hint.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        step(2, 4, "Turn on \"Developer mode\"", "It's a switch at the top-right (Chrome, Brave) or on the left (Edge).",
             has_body=False)

        s3 = step(3, 5, "Click \"Load unpacked\" and choose this folder")
        s3.grid_columnconfigure(0, weight=1)
        e = ctk.CTkEntry(s3, height=34, fg_color=BG, border_color=LINE, text_color=FG, font=F(11))
        e.insert(0, self.folder)
        e.configure(state="readonly")
        e.grid(row=0, column=0, sticky="ew")
        ghost_button(s3, "Copy", self.copy_path, width=70).grid(row=0, column=1, padx=(8, 0))
        ghost_button(s3, "Open folder", lambda: open_path(self.folder), width=100).grid(row=0, column=2, padx=(8, 0))

        step(4, 6, "Done — play any video",
             "The orange button appears on the video. Pin the extension (puzzle icon → pin) to see its status. "
             "Keep this app installed; if it's closed, the button opens it for you.", has_body=False)

        bottom = ctk.CTkFrame(w, fg_color=BG, corner_radius=0)
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        primary_button(bottom, "Close", w.destroy, height=34, size=13, width=100).grid(row=0, column=1, padx=18, pady=12)
        self._poll()

    def _finish_open(self):
        try:
            ico = os.path.join(engine.app_dir(), "icon.ico")
            if IS_WIN and os.path.isfile(ico):
                self.w.iconbitmap(ico)
            self.w.lift()
            self.w.focus_force()
        except Exception:
            pass

    def _poll(self):
        if not self.w.winfo_exists():
            return
        if time.time() - self.app.bridge.last_seen < 24 * 3600 and self.app.bridge.last_seen:
            self.status.configure(text="✓  Browser button is connected", text_color=GOOD)
        else:
            self.status.configure(text="Not connected yet — follow the steps below", text_color=WARN)
        self.w.after(1000, self._poll)

    def copy_path(self):
        self.w.clipboard_clear()
        self.w.clipboard_append(self.folder)
        self.app.last_clip = self.folder
        self.hint.configure(text="Folder path copied ✓")

    def open_page(self, name):
        page, paths = next((p, ps) for n, p, ps in BROWSERS if n == name)
        self.w.clipboard_clear()
        self.w.clipboard_append(page)
        self.app.last_clip = page
        exe = next((os.path.expandvars(p) for p in paths if os.path.isfile(os.path.expandvars(p))), None)
        if exe:
            try:
                subprocess.Popen([exe, page])
                self.hint.configure(text=f"Opening {name}…  (address {page} is also copied — paste it if needed)")
                return
            except Exception:
                pass
        self.hint.configure(text=f"Open {name} and paste this in the address bar: {page}  (already copied)")


def main():
    payload = bridge.parse_launch_arg(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "--selftest" else None
    if payload and payload["action"] in ("play", "show"):      # clicked in the "download complete" notification
        (open_path if payload["action"] == "play" else show_in_folder)(payload["file"])
        return
    if "--selftest" not in sys.argv and bridge.hand_over_to_running_app(payload):
        return  # the app is already open: it got the request
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hemelsid.VideoDownloader")
        except Exception:
            pass
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    app = App(root)
    if payload and payload["action"] == "add":
        root.after(1200, lambda: app.handle_external(payload))
    elif payload and payload["action"] == "start":     # woken by the browser button: stay out of the way
        root.after(300, root.iconify)
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        root.after(4000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
