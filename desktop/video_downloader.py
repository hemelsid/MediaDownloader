"""
Video Downloader — PC version (Windows / macOS / Linux).

Paste a link (or search YouTube), see a preview with every quality and its size, then download.
Same engine as the phone app: yt-dlp + ffmpeg (+ Deno for YouTube), see engine.py.
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
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # thumbnails are optional when running from source
    Image = None

import engine
from engine import EngineError, MediaInfo, Quality

APP = "Video Downloader"
VERSION = os.environ.get("VD_VERSION", "dev")
try:
    from _version import VERSION  # written by the build
except Exception:
    pass

# ---------------------------------------------------------------- look

BG = "#111111"
CARD = "#1C1C1E"
CARD2 = "#26262A"
FG = "#F2F2F2"
MUTED = "#A0A0A8"
ORANGE = "#FF6A13"
ORANGE_D = "#E25A0B"
GOOD = "#3DDC84"
BAD = "#FF8A80"
FONT = "Segoe UI" if sys.platform.startswith("win") else ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "VideoDownloader")
    os.makedirs(d, exist_ok=True)
    return d


def default_folder() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", "Video Downloader")


def human_size(n: float) -> str:
    if not n or n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


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


def text_bar(pct: float, width: int = 8) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled) + f" {pct:.0f}%"


def open_path(path: str):
    if not path or not os.path.exists(path):
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path: str):
    if sys.platform.startswith("win") and os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)


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
    status: str = "Queued"          # Queued, Downloading, Processing, Done, Failed, Cancelled
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
                    name=self.name, q=dict(label=q.label, size=q.size, height=q.height, audio=q.audio), total=self.total)

    @staticmethod
    def from_json(d):
        q = d.get("q") or {}
        it = Item(d["id"], d["url"], d.get("title") or d["url"],
                  Quality(q.get("label", "Best quality"), q.get("size", 0), q.get("height"), q.get("audio")),
                  d.get("playlist", False), d.get("name"), d.get("folder", ""), d.get("status", "Done"),
                  files=d.get("files") or [], error=d.get("error", ""), detail=d.get("detail", ""),
                  added=d.get("added", time.time()), total=d.get("total", 0))
        if it.active:  # app was closed mid-download
            it.status, it.error = "Failed", "Stopped when the app was closed — press Retry."
        return it


# ---------------------------------------------------------------- widgets

class Btn(tk.Label):
    """Flat button that looks the same on every OS."""

    def __init__(self, master, text, command, kind="normal", **kw):
        colors = {"primary": (ORANGE, "white", ORANGE_D), "normal": (CARD2, FG, "#33333A"),
                  "ghost": (master["bg"], MUTED, CARD2)}[kind]
        self._bg, self._hover = colors[0], colors[2]
        super().__init__(master, text=text, bg=colors[0], fg=colors[1], cursor="hand2",
                         font=kw.pop("font", (FONT, 10, "bold" if kind == "primary" else "normal")),
                         padx=kw.pop("padx", 14), pady=kw.pop("pady", 7), **kw)
        self._cmd = command
        self._enabled = True
        self.bind("<Button-1>", lambda e: self._enabled and self._cmd and self._cmd())
        self.bind("<Enter>", lambda e: self._enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

    def enable(self, on: bool):
        self._enabled = on
        self.config(fg=("white" if self._bg == ORANGE else FG) if on else "#666670", cursor="hand2" if on else "arrow")


class Scrollable(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=kw.get("bg", CARD))
        self.canvas = tk.Canvas(self, bg=kw.get("bg", CARD), highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=kw.get("bg", CARD))
        self.inner.bind("<Configure>", lambda e: self._sync())
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width), self._sync()))
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _sync(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 2
        if need and not self.sb.winfo_ismapped():
            self.sb.pack(side="right", fill="y", before=self.canvas)
        elif not need and self.sb.winfo_ismapped():
            self.sb.pack_forget()

    def _wheel(self, e):
        if not self.sb.winfo_ismapped():
            return
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    def clear(self):
        for c in self.inner.winfo_children():
            c.destroy()
        self.canvas.yview_moveto(0)


# ---------------------------------------------------------------- app

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.ui_q: queue.Queue = queue.Queue()
        self.settings = self._load_settings()
        self.engine = engine.Engine(self.settings)
        self.items: list[Item] = self._load_history()
        self.running = 0
        self.info: MediaInfo | None = None
        self.info_url = ""
        self.req_id = 0
        self.quality_var = tk.IntVar(value=0)
        self.tab = "video"
        self.last_clip = ""
        self._thumb_ref = None
        self._thumb_cache: dict[str, bytes] = {}

        root.title(APP)
        root.geometry("1200x760")
        root.minsize(980, 640)
        root.configure(bg=BG)
        self._set_icon()
        self._style()
        self._build()
        self._refresh_list()

        root.after(100, self._pump)
        root.after(500, self._dispatch)
        root.after(1200, self._watch_clipboard)
        threading.Thread(target=self._startup_checks, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------ persistence
    def _load_settings(self) -> dict:
        s = {"folder": default_folder(), "parallel": 3, "clipboard": True, "auto_update": True,
             "cookies_browser": "None", "cookies_file": "", "last_update": 0}
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

    # ------------------------------------------------ look
    def _set_icon(self):
        if Image is None:
            return
        try:
            png = os.path.join(engine.app_dir(), "icon.png")
            if os.path.isfile(png):
                img = Image.open(png)
            else:
                img = make_icon(256)
            self._icon = ImageTk.PhotoImage(img.resize((64, 64)))
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass

    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=CARD2, font=(FONT, 10))
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG, rowheight=30, borderwidth=0,
                     bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Treeview.Heading", background=CARD2, foreground=MUTED, relief="flat", font=(FONT, 9, "bold"))
        st.map("Treeview", background=[("selected", "#3A1E0C")], foreground=[("selected", FG)])
        st.map("Treeview.Heading", background=[("active", CARD2)])
        st.configure("Vertical.TScrollbar", background=CARD2, troughcolor=CARD, bordercolor=CARD, arrowcolor=MUTED,
                     darkcolor=CARD2, lightcolor=CARD2, gripcount=0, arrowsize=12)
        st.map("Vertical.TScrollbar", background=[("active", "#3A3A40")])
        st.configure("TCheckbutton", background=CARD, foreground=FG, indicatorbackground=CARD2, indicatorforeground=ORANGE)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("TCombobox", fieldbackground=CARD2, background=CARD2, foreground=FG, arrowcolor=FG,
                     bordercolor=CARD2, lightcolor=CARD2, darkcolor=CARD2, selectbackground=CARD2, selectforeground=FG)
        st.map("TCombobox", fieldbackground=[("readonly", CARD2)], foreground=[("readonly", FG)],
               background=[("readonly", CARD2)])
        st.configure("TSpinbox", fieldbackground=CARD2, background=CARD2, foreground=FG, arrowcolor=FG,
                     bordercolor=CARD2, lightcolor=CARD2, darkcolor=CARD2)
        self.root.option_add("*TCombobox*Listbox.background", CARD2)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)

    # ------------------------------------------------ layout
    def _build(self):
        r = self.root
        # header
        top = tk.Frame(r, bg=BG)
        top.pack(fill="x", padx=22, pady=(16, 8))
        tk.Label(top, text=APP, bg=BG, fg=FG, font=(FONT, 20, "bold")).pack(side="left")
        Btn(top, "⚙  Settings", self.open_settings, "normal").pack(side="right")
        Btn(top, "📁  Open folder", lambda: (os.makedirs(self.settings["folder"], exist_ok=True),
                                             open_path(self.settings["folder"])), "normal").pack(side="right", padx=8)

        # search box
        sb = tk.Frame(r, bg=BG)
        sb.pack(fill="x", padx=22, pady=(4, 6))
        box = tk.Frame(sb, bg="white", highlightthickness=2, highlightbackground=ORANGE, highlightcolor=ORANGE)
        box.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(box, bd=0, font=(FONT, 13), bg="white", fg="#111", insertbackground="#111", relief="flat",
                              highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        self.placeholder = "Paste a video link, or type to search YouTube…"
        self._placeholder(True)
        self.entry.bind("<FocusIn>", lambda e: self._placeholder(False))
        self.entry.bind("<FocusOut>", lambda e: self._placeholder(not self.entry.get().strip()))
        self.entry.bind("<Return>", lambda e: self.go())
        tk.Label(box, text="📋 Paste", bg="white", fg="#555", cursor="hand2", font=(FONT, 10)).pack(side="left", padx=6)
        box.winfo_children()[-1].bind("<Button-1>", lambda e: self.paste_and_go())
        Btn(sb, "  Find  ▶  ", self.go, "primary", font=(FONT, 12, "bold"), pady=12).pack(side="left", padx=(10, 0))

        # copied-link banner
        self.banner = tk.Frame(r, bg=CARD2)
        self.banner_lbl = tk.Label(self.banner, bg=CARD2, fg=FG, font=(FONT, 10), anchor="w")
        self.banner_lbl.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        Btn(self.banner, "Dismiss", lambda: self.banner.pack_forget(), "ghost").pack(side="right", padx=4)
        Btn(self.banner, "⬇  Download", self._banner_go, "primary").pack(side="right", padx=4, pady=4)

        # body
        self.body = tk.Frame(r, bg=BG)
        self.body.pack(fill="both", expand=True, padx=22, pady=(6, 8))
        self.left = tk.Frame(self.body, bg=CARD, width=440)
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)
        right = tk.Frame(self.body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.preview = Scrollable(self.left, bg=CARD)
        self.preview.pack(fill="both", expand=True, padx=2, pady=2)
        self._show_welcome()

        # downloads
        hdr = tk.Frame(right, bg=BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Downloads", bg=BG, fg=FG, font=(FONT, 15, "bold")).pack(side="left")
        for txt, fn in (("Clear finished", self.clear_finished), ("Remove", self.remove_sel), ("Retry", self.retry_sel),
                        ("Cancel", self.cancel_sel), ("Show in folder", self.show_sel), ("Play", self.open_sel)):
            Btn(hdr, txt, fn, "normal", padx=10, pady=5).pack(side="right", padx=3)
        wrap = tk.Frame(right, bg=CARD)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("title", "quality", "status", "progress", "size", "speed")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        for c, t, w, st in (("title", "Title", 170, True), ("quality", "Quality", 88, False), ("status", "Status", 86, False),
                            ("progress", "Progress", 140, False), ("size", "Size", 74, False),
                            ("speed", "Speed • left", 120, False)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, minwidth=40, stretch=st, anchor="w" if c == "title" else "center")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("done", foreground=GOOD)
        self.tree.tag_configure("fail", foreground=BAD)
        self.tree.tag_configure("dim", foreground=MUTED)
        self.tree.bind("<Double-1>", lambda e: self.open_sel())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_error_of_sel())
        self.menu = tk.Menu(r, tearoff=0, bg=CARD2, fg=FG, activebackground=ORANGE, activeforeground="white", bd=0)
        for txt, fn in (("Play / open", self.open_sel), ("Show in folder", self.show_sel), ("Copy link", self.copy_sel),
                        ("Open source page", self.source_sel), (None, None), ("Cancel", self.cancel_sel),
                        ("Retry", self.retry_sel), ("Remove from list", self.remove_sel)):
            self.menu.add_separator() if txt is None else self.menu.add_command(label=txt, command=fn)
        self.tree.bind("<Button-3>", self._popup)
        self.tree.bind("<Button-2>", self._popup)
        self.err_lbl = tk.Label(right, bg=BG, fg=BAD, font=(FONT, 9), anchor="w", justify="left", wraplength=640)
        self.err_lbl.pack(fill="x", pady=(6, 0))

        # status bar
        self.status = tk.Label(r, bg=CARD, fg=MUTED, anchor="w", font=(FONT, 9), padx=14, pady=5)
        self.status.pack(fill="x", side="bottom")
        self._set_status("Starting engine…")

    def _placeholder(self, on: bool):
        if on and not self.entry.get():
            self.entry.insert(0, self.placeholder)
            self.entry.config(fg="#888")
        elif not on and self.entry.get() == self.placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg="#111")

    def _set_status(self, msg: str):
        self.status.config(text=f"{msg}   •   Saving to: {self.settings['folder']}   •   App {VERSION}")

    # ------------------------------------------------ preview panel
    def _card_title(self, text):
        tk.Label(self.preview.inner, text=text, bg=CARD, fg=FG, font=(FONT, 14, "bold"), anchor="w").pack(
            fill="x", padx=18, pady=(18, 6))

    def _show_welcome(self):
        self.preview.clear()
        p = self.preview.inner
        self._card_title("How to download")
        for n, t in (("1", "Copy a video link (YouTube, Facebook, Instagram, TikTok, X, Vimeo… almost any site)."),
                     ("2", "Paste it above and press Find — or just copy it: the app notices copied links."),
                     ("3", "Pick a quality (sizes are shown) and press Download."),
                     ("★", "No link? Type words above to search YouTube.")):
            row = tk.Frame(p, bg=CARD)
            row.pack(fill="x", padx=18, pady=6)
            tk.Label(row, text=n, bg="#3A1E0C", fg=ORANGE, font=(FONT, 10, "bold"), width=2).pack(side="left", anchor="n")
            tk.Label(row, text=t, bg=CARD, fg="#D0D0D5", font=(FONT, 10), wraplength=340, justify="left", anchor="w").pack(
                side="left", padx=10, fill="x")
        tk.Label(p, text="Netflix, Prime Video, Hotstar and other DRM services can't be downloaded by any downloader.",
                 bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=380, justify="left").pack(fill="x", padx=18, pady=(20, 10))

    def _show_loading(self, text="Finding video…"):
        self.preview.clear()
        p = self.preview.inner
        tk.Label(p, text="⏳", bg=CARD, fg=ORANGE, font=(FONT, 34)).pack(pady=(80, 6))
        tk.Label(p, text=text, bg=CARD, fg=FG, font=(FONT, 12)).pack()
        tk.Label(p, text=engine.host_of(self.info_url) or "", bg=CARD, fg=MUTED, font=(FONT, 9)).pack()

    def _show_error(self, e: EngineError, url: str):
        self.preview.clear()
        p = self.preview.inner
        tk.Label(p, text="🔒" if e.drm else "⚠", bg=CARD, fg="#FFB627" if e.drm else BAD, font=(FONT, 30)).pack(pady=(50, 6))
        tk.Label(p, text=e.friendly, bg=CARD, fg=FG, font=(FONT, 11), wraplength=380, justify="left").pack(padx=18, fill="x")
        if not e.drm:
            det = tk.Label(p, text="", bg=CARD2, fg=MUTED, font=(FONT, 9), wraplength=380, justify="left", anchor="w")
            def toggle():
                if det.winfo_ismapped():
                    det.pack_forget()
                else:
                    det.config(text=e.detail)
                    det.pack(fill="x", padx=18, pady=6, after=link)
            link = tk.Label(p, text="Details ▾", bg=CARD, fg=ORANGE, cursor="hand2", font=(FONT, 10))
            link.pack(anchor="w", padx=18, pady=(10, 0))
            link.bind("<Button-1>", lambda ev: toggle())
            row = tk.Frame(p, bg=CARD)
            row.pack(anchor="w", padx=18, pady=14)
            Btn(row, "Try again", lambda: self.load(url), "primary").pack(side="left")
            if e.login_site:
                Btn(row, "Settings", self.open_settings, "normal").pack(side="left", padx=8)

    def _show_results(self, results: list[engine.SearchResult], query: str):
        self.preview.clear()
        p = self.preview.inner
        self._card_title(f"Results for “{query[:40]}”")
        if not results:
            tk.Label(p, text="Nothing found.", bg=CARD, fg=MUTED).pack(padx=18, anchor="w")
        for res in results:
            row = tk.Frame(p, bg=CARD, cursor="hand2")
            row.pack(fill="x", padx=12, pady=3)
            thumb = tk.Label(row, bg=CARD2, width=16, height=5)
            thumb.pack(side="left", padx=(6, 10), pady=4)
            col = tk.Frame(row, bg=CARD)
            col.pack(side="left", fill="x", expand=True)
            t = tk.Label(col, text=res.title, bg=CARD, fg=FG, font=(FONT, 10, "bold"), wraplength=240, justify="left", anchor="w")
            t.pack(fill="x")
            meta = " • ".join(x for x in (res.channel, human_time(res.duration)) if x)
            m = tk.Label(col, text=meta, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w")
            m.pack(fill="x")
            for w in (row, thumb, col, t, m):
                w.bind("<Button-1>", lambda e, u=res.url: self.load(u))
                w.bind("<Enter>", lambda e, rw=row: [c.config(bg=CARD2) for c in [rw] + rw.winfo_children()])
                w.bind("<Leave>", lambda e, rw=row: [c.config(bg=CARD) for c in [rw] + rw.winfo_children()])
            if res.thumbnail:
                self._load_thumb(res.thumbnail, (128, 72), thumb)

    def _show_info(self, info: MediaInfo):
        self.info = info
        self.preview.clear()
        p = self.preview.inner
        self.thumb_lbl = tk.Label(p, bg=CARD2, width=400, height=225, cursor="hand2")
        self.thumb_lbl.pack(padx=18, pady=(18, 10))
        self.thumb_lbl.bind("<Button-1>", lambda e: webbrowser.open(info.url))
        blank = Image.new("RGB", (400, 225), CARD2) if Image else None
        if blank:
            self._thumb_ref = ImageTk.PhotoImage(blank)
            self.thumb_lbl.config(image=self._thumb_ref, width=400, height=225)
        if info.thumbnail:
            self._load_thumb(info.thumbnail, (400, 225), self.thumb_lbl, badge=human_time(info.duration))
        tk.Label(p, text=info.title, bg=CARD, fg=FG, font=(FONT, 12, "bold"), wraplength=400, justify="left",
                 anchor="w").pack(fill="x", padx=18)
        meta = " • ".join(x for x in (info.uploader, info.site, f"{compact(info.views)} views" if info.views else None,
                                       f"{info.count} videos" if info.is_playlist else None) if x)
        if meta:
            tk.Label(p, text=meta, bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=400, justify="left", anchor="w").pack(
                fill="x", padx=18, pady=(2, 8))

        tabs = tk.Frame(p, bg=CARD)
        tabs.pack(fill="x", padx=18, pady=(6, 0))
        self.tab = "video" if info.video else "audio"
        self.tab_btns = {}
        for key, label in (("video", "Video"), ("audio", "Audio")):
            b = tk.Label(tabs, text=label, bg=CARD, font=(FONT, 11, "bold"), cursor="hand2", padx=18, pady=6)
            b.pack(side="left", expand=True, fill="x")
            b.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self.tab_btns[key] = b
        tk.Frame(p, bg=CARD2, height=1).pack(fill="x", padx=18)
        self.opts = tk.Frame(p, bg=CARD)
        self.opts.pack(fill="x", padx=18, pady=4)

        opt = tk.Frame(p, bg=CARD)
        opt.pack(fill="x", padx=18, pady=(8, 2))
        tk.Label(opt, text="File name", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        self.name_var = tk.StringVar(value=info.title if not info.is_playlist else "")
        ne = tk.Entry(opt, textvariable=self.name_var, bg=CARD2, fg=FG, insertbackground=FG, bd=0, font=(FONT, 10),
                      relief="flat", highlightthickness=1, highlightbackground=CARD2, highlightcolor=ORANGE)
        ne.pack(fill="x", ipady=6, pady=(2, 6))
        if info.is_playlist:
            ne.config(state="disabled", disabledbackground=CARD, disabledforeground=MUTED)
        self.pl_var = tk.BooleanVar(value=info.is_playlist)
        if info.is_playlist or "list=" in info.url:
            ttk.Checkbutton(opt, text=f"Whole playlist ({info.count})" if info.is_playlist else "Download the whole playlist",
                            variable=self.pl_var).pack(anchor="w", pady=2)
        self.dl_btn = Btn(p, "⬇   Download", self.start_download, "primary", font=(FONT, 13, "bold"), pady=12)
        self.dl_btn.pack(fill="x", padx=18, pady=(10, 18))
        self._switch_tab(self.tab)

    def _switch_tab(self, key):
        self.tab = key
        for k, b in self.tab_btns.items():
            b.config(fg=ORANGE if k == key else MUTED)
        for c in self.opts.winfo_children():
            c.destroy()
        options = self.info.video if key == "video" else self.info.audio
        if not options:
            tk.Label(self.opts, text="No video in this link — see the Audio tab.", bg=CARD, fg=MUTED).pack(pady=10)
            return
        default = 0
        if key == "video":
            default = next((i for i, q in enumerate(options) if (q.height or 0) <= 1080), 0)
        self.quality_var.set(default)
        for i, q in enumerate(options):
            row = tk.Frame(self.opts, bg=CARD, cursor="hand2")
            row.pack(fill="x", pady=1)
            rb = tk.Radiobutton(row, variable=self.quality_var, value=i, bg=CARD, activebackground=CARD,
                                selectcolor=CARD2, fg=ORANGE, highlightthickness=0, bd=0)
            rb.pack(side="left")
            name = tk.Label(row, text=("♪  " if q.is_audio else "▶  ") + q.label, bg=CARD, fg=FG, font=(FONT, 11), anchor="w")
            name.pack(side="left", fill="x", expand=True, pady=7)
            size = tk.Label(row, text=("~ " + human_size(q.size)) if q.size else ("" if self.info.is_playlist else "size unknown"),
                            bg=CARD, fg=MUTED, font=(FONT, 10))
            size.pack(side="right", padx=4)
            for w in (row, name, size):
                w.bind("<Button-1>", lambda e, v=i: self.quality_var.set(v))
            tk.Frame(self.opts, bg=CARD2, height=1).pack(fill="x")

    def _load_thumb(self, url, size, label, badge=""):
        if Image is None:
            return

        def work():
            try:
                data = self._thumb_cache.get(url)
                if data is None:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=15).read()
                    self._thumb_cache[url] = data
                img = Image.open(io.BytesIO(data)).convert("RGB")
                w, h = size
                scale = max(w / img.width, h / img.height)
                img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1))
                l, t = (img.width - w) // 2, (img.height - h) // 2
                img = img.crop((l, t, l + w, t + h))
                if badge:
                    d = ImageDraw.Draw(img)
                    tw = 9 * len(badge) + 10
                    d.rounded_rectangle((8, h - 30, 8 + tw, h - 8), 5, fill=(0, 0, 0))
                    d.text((14, h - 27), badge, fill=(255, 255, 255))
                self.ui_q.put(("thumb", (label, img)))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------ actions
    def paste_and_go(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        self._placeholder(False)
        self.entry.delete(0, "end")
        self.entry.insert(0, text.strip())
        self.go()

    def go(self):
        text = self.entry.get().strip()
        if not text or text == self.placeholder:
            return self.paste_and_go() if self._clip_text() else None
        urls = engine.extract_urls(text)
        if len(urls) > 1:
            q = engine.BEST
            for u in urls:
                self.add_download(u, u, q, False, None)
            self._set_status(f"Added {len(urls)} links with best quality")
            return
        if urls:
            self.load(urls[0])
        else:
            self.search(text)

    def _clip_text(self) -> str:
        try:
            return self.root.clipboard_get().strip()
        except tk.TclError:
            return ""

    def load(self, url: str):
        self.req_id += 1
        rid = self.req_id
        self.info_url = url
        self._show_loading()
        threading.Thread(target=self._info_worker, args=(rid, url), daemon=True).start()

    def _info_worker(self, rid, url):
        try:
            info = self.engine.info(url)
            self.ui_q.put(("info", (rid, info)))
        except EngineError as e:
            self.ui_q.put(("info_err", (rid, e, url)))
        except Exception as e:
            self.ui_q.put(("info_err", (rid, EngineError(str(e)[:200], repr(e)), url)))

    def search(self, query: str):
        self.req_id += 1
        rid = self.req_id
        self.info_url = "https://youtube.com"
        self._show_loading("Searching YouTube…")

        def work():
            try:
                self.ui_q.put(("results", (rid, self.engine.search(query), query)))
            except EngineError as e:
                self.ui_q.put(("info_err", (rid, e, "https://youtube.com")))
        threading.Thread(target=work, daemon=True).start()

    def start_download(self):
        if not self.info:
            return
        options = self.info.video if self.tab == "video" else self.info.audio
        if not options:
            return
        q = options[self.quality_var.get()]
        name = self.name_var.get().strip()
        playlist = bool(self.pl_var.get())
        clean = None
        if name and not playlist and name != self.info.title:
            clean = "".join(c if c not in '\\/:*?"<>|' else " " for c in name).strip()[:150] or None
        self.add_download(self.info.url, name or self.info.title, q, playlist, clean)
        self._set_status("Download added ⬇")
        self.dl_btn.config(text="✔  Added — see Downloads")
        self.root.after(1500, lambda: self.dl_btn.winfo_exists() and self.dl_btn.config(text="⬇   Download"))

    def add_download(self, url, title, q: Quality, playlist, name):
        it = Item(uuid.uuid4().hex, url, title, q, playlist, name, self.settings["folder"])
        self.items.append(it)
        self._refresh_list()
        self._save_history()

    def _dispatch(self):
        limit = max(1, int(self.settings.get("parallel", 3)))
        for it in self.items:
            if self.running >= limit:
                break
            if it.status == "Queued":
                it.status = "Starting"
                self.running += 1
                threading.Thread(target=self._dl_worker, args=(it,), daemon=True).start()
        self.root.after(500, self._dispatch)

    def _dl_worker(self, it: Item):
        try:
            os.makedirs(it.folder, exist_ok=True)

            def prog(d):
                self.ui_q.put(("prog", (it.id, d)))
            files = self.engine.download(it.id, it.url, it.quality, it.folder, it.playlist, it.name, prog)
            self.ui_q.put(("done", (it.id, files)))
        except EngineError as e:
            self.ui_q.put(("fail", (it.id, e)))
        except Exception as e:
            self.ui_q.put(("fail", (it.id, EngineError(str(e)[:200], repr(e)))))

    # ------------------------------------------------ ui loop
    def _pump(self):
        changed = False
        try:
            while True:
                kind, data = self.ui_q.get_nowait()
                if kind == "info":
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
                elif kind == "thumb":
                    label, img = data
                    if label.winfo_exists():
                        ph = ImageTk.PhotoImage(img)
                        label.config(image=ph, width=img.width, height=img.height)
                        label.image = ph
                elif kind == "prog":
                    iid, d = data
                    it = self._get(iid)
                    if it and it.active and it.status != "Cancelled":
                        if d["stage"] == "processing":
                            it.status, it.speed, it.eta = "Processing", 0, 0
                        else:
                            it.status, it.pct, it.speed, it.eta = "Downloading", d["pct"], d["speed"], d["eta"]
                            it.total = d["total"] or it.total
                        changed = True
                elif kind == "done":
                    iid, files = data
                    it = self._get(iid)
                    self.running = max(0, self.running - 1)
                    if it and it.status != "Cancelled":
                        it.status, it.pct, it.files, it.speed, it.eta = "Done", 100, files, 0, 0
                        if files and not it.playlist:
                            it.title = os.path.splitext(os.path.basename(files[0]))[0] if it.title == it.url else it.title
                            try:
                                it.total = sum(os.path.getsize(f) for f in files)
                            except OSError:
                                pass
                        self._notify(f"Downloaded: {it.title[:60]}")
                    changed = True
                    self._save_history()
                elif kind == "fail":
                    iid, e = data
                    it = self._get(iid)
                    self.running = max(0, self.running - 1)
                    if it and it.status != "Cancelled":
                        it.status, it.error, it.detail = "Failed", e.friendly, e.detail
                    changed = True
                    self._save_history()
                elif kind == "status":
                    self._set_status(data)
        except queue.Empty:
            pass
        if changed:
            self._refresh_list()
        active = sum(1 for i in self.items if i.active)
        self.root.title(f"{APP} — {active} downloading" if active else APP)
        self.root.after(150, self._pump)

    def _notify(self, msg):
        self._set_status(msg)
        try:
            self.root.bell()
        except Exception:
            pass

    def _get(self, iid) -> Item | None:
        return next((i for i in self.items if i.id == iid), None)

    def _refresh_list(self):
        existing = set(self.tree.get_children())
        wanted = []
        for it in reversed(self.items):
            wanted.append(it.id)
            if it.status in ("Downloading",):
                prog = text_bar(it.pct)
            elif it.status == "Done":
                prog = text_bar(100)
            elif it.status == "Processing":
                prog = "converting…"
            elif it.status in ("Queued", "Starting"):
                prog = "waiting…"
            else:
                prog = ""
            ql = it.quality.label.replace(" Video", "").replace("Ultra HD", "UHD").replace(" kbps", "k").replace(" - ", " ")
            vals = (it.title, ql, it.status, prog,
                    human_size(it.total) if it.total else "",
                    " • ".join(x for x in ((human_size(it.speed) + "/s") if it.speed else "", human_time(it.eta)) if x))
            tag = ("done",) if it.status == "Done" else ("fail",) if it.status == "Failed" else (
                ("dim",) if it.status == "Cancelled" else ())
            if it.id in existing:
                self.tree.item(it.id, values=vals, tags=tag)
            else:
                self.tree.insert("", "end", iid=it.id, values=vals, tags=tag)
        for iid in existing - set(wanted):
            self.tree.delete(iid)
        for idx, iid in enumerate(wanted):
            if self.tree.index(iid) != idx:
                self.tree.move(iid, "", idx)

    # ------------------------------------------------ list actions
    def _sel(self) -> list[Item]:
        return [i for i in (self._get(x) for x in self.tree.selection()) if i]

    def _popup(self, e):
        row = self.tree.identify_row(e.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.menu.tk_popup(e.x_root, e.y_root)

    def _show_error_of_sel(self):
        s = self._sel()
        self.err_lbl.config(text=(s[0].error + ("\nDetails: " + s[0].detail.splitlines()[0] if s[0].detail else ""))
                            if s and s[0].status == "Failed" else "")

    def open_sel(self):
        for it in self._sel()[:1]:
            if it.files:
                open_path(it.files[0])
            elif it.status == "Done":
                open_path(it.folder)

    def show_sel(self):
        for it in self._sel()[:1]:
            show_in_folder(it.files[0] if it.files else it.folder)

    def copy_sel(self):
        for it in self._sel()[:1]:
            self.root.clipboard_clear()
            self.root.clipboard_append(it.url)
            self.last_clip = it.url

    def source_sel(self):
        for it in self._sel()[:1]:
            webbrowser.open(it.url)

    def cancel_sel(self):
        for it in self._sel():
            if it.active:
                if it.status == "Queued":
                    it.status = "Cancelled"
                else:
                    it.status = "Cancelled"
                    threading.Thread(target=self.engine.cancel, args=(it.id,), daemon=True).start()
        self._refresh_list()
        self._save_history()

    def retry_sel(self):
        for it in self._sel():
            if it.status in ("Failed", "Cancelled"):
                it.status, it.error, it.detail, it.pct, it.speed, it.eta = "Queued", "", "", 0, 0, 0
        self._refresh_list()
        self.err_lbl.config(text="")

    def remove_sel(self):
        for it in self._sel():
            if it.active:
                it.status = "Cancelled"
                threading.Thread(target=self.engine.cancel, args=(it.id,), daemon=True).start()
            self.items.remove(it)
        self._refresh_list()
        self._save_history()

    def clear_finished(self):
        self.items = [i for i in self.items if i.active or i.status == "Failed"]
        self._refresh_list()
        self._save_history()

    # ------------------------------------------------ clipboard
    def _watch_clipboard(self):
        if self.settings.get("clipboard", True) and self.root.focus_displayof() is not None:
            clip = self._clip_text()
            if clip != self.last_clip:
                self.last_clip = clip
                urls = engine.extract_urls(clip)
                if urls and len(clip) < 2000 and urls[0] != self.info_url:
                    self._clip_url = urls[0]
                    self.banner_lbl.config(text=f"🔗  Copied link detected:  {urls[0][:90]}")
                    self.banner.pack(fill="x", padx=22, pady=(0, 4), after=self.entry.master.master)
        self.root.after(1200, self._watch_clipboard)

    def _banner_go(self):
        self.banner.pack_forget()
        self._placeholder(False)
        self.entry.delete(0, "end")
        self.entry.insert(0, self._clip_url)
        self.load(self._clip_url)

    # ------------------------------------------------ settings
    def open_settings(self):
        SettingsDialog(self)

    def _startup_checks(self):
        v = self.engine.version()
        self.ui_q.put(("status", f"Engine: yt-dlp {v}"))
        if v == "not found":
            self.ui_q.put(("status", "⚠ Download engine not found — reinstall the app"))
            return
        if self.settings.get("auto_update", True) and engine._bin("yt-dlp") and \
                time.time() - float(self.settings.get("last_update", 0)) > 24 * 3600:
            msg = self.engine.update()
            self.settings["last_update"] = time.time()
            self._save_settings()
            v = self.engine.version()
            note = "up to date" if ("up to date" in msg.lower() or "updated" in msg.lower()) else "update check failed"
            self.ui_q.put(("status", f"Engine: yt-dlp {v} ({note})"))

    def _on_close(self):
        active = [i for i in self.items if i.active]
        if active and not messagebox.askyesno(APP, f"{len(active)} download(s) still running. Quit anyway?"):
            return
        for i in active:
            i.status = "Cancelled"
            self.engine.cancel(i.id)
        self._save_history()
        self._save_settings()
        self.root.destroy()


class SettingsDialog:
    BROWSERS = ["None", "Firefox", "Chrome", "Edge", "Brave", "Opera", "Vivaldi", "Chromium"]

    def __init__(self, app: App):
        self.app = app
        s = app.settings
        w = self.w = tk.Toplevel(app.root, bg=CARD)
        w.title("Settings")
        w.geometry("640x620")
        w.transient(app.root)
        w.grab_set()

        def section(title):
            tk.Label(w, text=title, bg=CARD, fg=FG, font=(FONT, 12, "bold"), anchor="w").pack(fill="x", padx=22, pady=(16, 4))

        def note(text):
            tk.Label(w, text=text, bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=590, justify="left", anchor="w").pack(
                fill="x", padx=22)

        section("Save downloads to")
        row = tk.Frame(w, bg=CARD)
        row.pack(fill="x", padx=22, pady=4)
        self.folder = tk.StringVar(value=s["folder"])
        tk.Entry(row, textvariable=self.folder, bg=CARD2, fg=FG, insertbackground=FG, bd=0, font=(FONT, 10),
                 highlightthickness=1, highlightbackground=CARD2, highlightcolor=ORANGE).pack(
            side="left", fill="x", expand=True, ipady=6)
        Btn(row, "Browse…", self.browse, "normal").pack(side="left", padx=(8, 0))

        section("Downloads")
        row = tk.Frame(w, bg=CARD)
        row.pack(fill="x", padx=22, pady=4)
        tk.Label(row, text="At the same time:", bg=CARD, fg=FG).pack(side="left")
        self.parallel = tk.StringVar(value=str(s.get("parallel", 3)))
        ttk.Spinbox(row, from_=1, to=6, width=4, textvariable=self.parallel).pack(side="left", padx=8)
        self.clip = tk.BooleanVar(value=s.get("clipboard", True))
        ttk.Checkbutton(w, text="Notice copied links (clipboard watch)", variable=self.clip).pack(anchor="w", padx=22, pady=2)

        section("Logins (only if a site blocks you)")
        note("Pick a browser where you are logged in to YouTube/Facebook/Instagram; downloads will use that login. "
             "On Windows, Chrome and Edge often lock their cookies — Firefox works best. "
             "Or choose a cookies.txt file (export it with the \"Get cookies.txt LOCALLY\" extension).")
        row = tk.Frame(w, bg=CARD)
        row.pack(fill="x", padx=22, pady=6)
        tk.Label(row, text="Browser:", bg=CARD, fg=FG).pack(side="left")
        self.browser = tk.StringVar(value=s.get("cookies_browser", "None"))
        ttk.Combobox(row, values=self.BROWSERS, textvariable=self.browser, state="readonly", width=12).pack(side="left", padx=8)
        row = tk.Frame(w, bg=CARD)
        row.pack(fill="x", padx=22, pady=2)
        self.cfile = tk.StringVar(value=s.get("cookies_file", ""))
        tk.Label(row, text="cookies.txt:", bg=CARD, fg=FG).pack(side="left")
        tk.Entry(row, textvariable=self.cfile, bg=CARD2, fg=FG, insertbackground=FG, bd=0, font=(FONT, 9),
                 highlightthickness=1, highlightbackground=CARD2, highlightcolor=ORANGE).pack(
            side="left", fill="x", expand=True, padx=8, ipady=5)
        Btn(row, "Choose…", self.pick_cookies, "normal").pack(side="left")
        Btn(row, "Clear", lambda: self.cfile.set(""), "ghost").pack(side="left", padx=4)

        section("Download engine")
        self.auto = tk.BooleanVar(value=s.get("auto_update", True))
        ttk.Checkbutton(w, text="Update automatically once a day (keeps sites working)", variable=self.auto).pack(
            anchor="w", padx=22, pady=2)
        row = tk.Frame(w, bg=CARD)
        row.pack(fill="x", padx=22, pady=6)
        self.upd_lbl = tk.Label(row, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
        Btn(row, "Update now", self.update_now, "normal").pack(side="left")
        self.upd_lbl.pack(side="left", padx=10)

        bottom = tk.Frame(w, bg=CARD)
        bottom.pack(fill="x", side="bottom", padx=22, pady=18)
        Btn(bottom, "Save", self.save, "primary").pack(side="right")
        Btn(bottom, "Cancel", w.destroy, "normal").pack(side="right", padx=8)
        tk.Label(bottom, text=f"Video Downloader {VERSION}", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left")

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.folder.get(), parent=self.w)
        if d:
            self.folder.set(d)

    def pick_cookies(self):
        f = filedialog.askopenfilename(parent=self.w, filetypes=[("cookies.txt", "*.txt"), ("All files", "*.*")])
        if f:
            self.cfile.set(f)

    def update_now(self):
        self.upd_lbl.config(text="Updating…")

        def work():
            msg = self.app.engine.update()
            v = self.app.engine.version()
            self.app.settings["last_update"] = time.time()
            self.app.ui_q.put(("status", f"Engine: yt-dlp {v}"))
            try:
                self.w.after(0, lambda: self.upd_lbl.config(text=f"{msg[:70]}  (now {v})"))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        s = self.app.settings
        s["folder"] = self.folder.get().strip() or default_folder()
        try:
            s["parallel"] = max(1, min(6, int(self.parallel.get())))
        except ValueError:
            pass
        s["clipboard"] = self.clip.get()
        s["cookies_browser"] = self.browser.get()
        s["cookies_file"] = self.cfile.get().strip()
        s["auto_update"] = self.auto.get()
        self.app._save_settings()
        self.app._set_status("Settings saved")
        self.w.destroy()


def make_icon(size=256):
    """Orange rounded square with a white download arrow (same as the phone app)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 108
    d.rounded_rectangle((4 * s, 4 * s, 104 * s, 104 * s), radius=24 * s, fill=(255, 106, 19, 255))
    d.polygon([(49 * s, 26 * s), (59 * s, 26 * s), (59 * s, 52 * s), (70 * s, 52 * s), (54 * s, 70 * s),
               (38 * s, 52 * s), (49 * s, 52 * s)], fill="white")
    d.polygon([(30 * s, 68 * s), (37 * s, 68 * s), (37 * s, 76 * s), (71 * s, 76 * s), (71 * s, 68 * s),
               (78 * s, 68 * s), (78 * s, 84 * s), (30 * s, 84 * s)], fill="white")
    return img


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hemelsid.VideoDownloader")
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        root.after(3000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
