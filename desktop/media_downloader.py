"""
Media Downloader - IDM-style video/audio downloader (yt-dlp powered)
Supports YouTube, Facebook, Instagram, TikTok, X/Twitter, Vimeo, and 1000+ sites,
plus direct file links (.mp4, .mp3, .zip ...).

Requirements:  pip install yt-dlp      (+ ffmpeg for merging HD video & MP3 conversion)
Run:           python media_downloader.py
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("yt-dlp missing",
                         "yt-dlp is not installed.\n\nRun this in Command Prompt:\n  pip install yt-dlp")
    sys.exit(1)

APP_NAME = "Media Downloader"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".media_downloader.json")
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

FORMATS = [
    "Best Video (MP4)",
    "Video 1080p",
    "Video 720p",
    "Video 480p",
    "Video 360p",
    "Audio MP3 (320k)",
    "Audio MP3 (192k)",
    "Audio M4A (original)",
]

Cancelled = getattr(yt_dlp.utils, "DownloadCancelled", None)
if Cancelled is None:
    class Cancelled(Exception):
        pass


def find_ffmpeg():
    """Look for ffmpeg next to the app first, then in PATH."""
    for name in ("ffmpeg.exe", "ffmpeg"):
        local = os.path.join(APP_DIR, name)
        if os.path.isfile(local):
            return APP_DIR
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def human_size(n):
    if not n:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_eta(s):
    if s is None:
        return "-"
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def text_bar(pct, width=12):
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled) + f" {pct:5.1f}%"


class Task:
    counter = 0

    def __init__(self, url, fmt, folder, playlist):
        Task.counter += 1
        self.id = f"t{Task.counter}"
        self.url = url
        self.fmt = fmt
        self.folder = folder
        self.playlist = playlist
        self.cancel = False
        self.state = "waiting"   # waiting | running | done | error | cancelled


def build_options(task, ffmpeg_dir, progress_hook, pp_hook):
    opts = {
        "outtmpl": os.path.join(task.folder, "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [pp_hook],
        "noplaylist": not task.playlist,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,   # faster HLS/DASH downloads (IDM-style multi-part)
        "continuedl": True,                   # resume partial files
        "windowsfilenames": True,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    fmt = task.fmt
    if fmt.startswith("Audio"):
        if fmt == "Audio M4A (original)":
            opts["format"] = "ba[ext=m4a]/ba/b"
        else:
            opts["format"] = "ba/b"
            if ffmpeg_dir:
                quality = "320" if "320" in fmt else "192"
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
                    {"key": "FFmpegMetadata"},
                ]
    else:
        height = None
        for h in ("1080", "720", "480", "360"):
            if h in fmt:
                height = h
        if ffmpeg_dir:
            if height:
                opts["format"] = f"bv*[height<={height}]+ba/b[height<={height}]/b"
            else:
                opts["format"] = "bv*+ba/b"
            opts["merge_output_format"] = "mp4"
        else:
            # Without ffmpeg we can only take formats that already contain audio+video
            opts["format"] = f"b[height<={height}]/b" if height else "b"
    return opts


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("980x600")
        self.root.minsize(760, 460)

        self.cfg = self.load_config()
        self.tasks = {}
        self.pending = []
        self.running = 0
        self.ui_queue = queue.Queue()
        self.ffmpeg_dir = find_ffmpeg()
        self.last_clip = ""

        self.build_ui()
        self.root.after(100, self.process_ui_queue)
        self.root.after(500, self.dispatch)
        self.root.after(1000, self.watch_clipboard)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if not self.ffmpeg_dir:
            self.status_var.set("⚠ ffmpeg not found — HD video merging and MP3 conversion won't work. See README.")

    # ---------- config ----------
    def load_config(self):
        default = {"folder": os.path.join(os.path.expanduser("~"), "Downloads"),
                   "format": FORMATS[0], "parallel": 3, "clipboard": True}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                default.update(json.load(f))
        except Exception:
            pass
        return default

    def save_config(self):
        self.cfg.update(folder=self.folder_var.get(), format=self.format_var.get(),
                        parallel=int(self.parallel_var.get() or 3), clipboard=self.clip_var.get())
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception:
            pass

    # ---------- UI ----------
    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=26)

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Link(s) — one per line:").grid(row=0, column=0, sticky="w")
        self.url_text = tk.Text(top, height=4, wrap="none", font=("Consolas", 10))
        self.url_text.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(2, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Format:").grid(row=2, column=0, sticky="w")
        self.format_var = tk.StringVar(value=self.cfg["format"])
        ttk.Combobox(top, textvariable=self.format_var, values=FORMATS, state="readonly",
                     width=22).grid(row=2, column=1, sticky="w")

        self.playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Whole playlist", variable=self.playlist_var).grid(row=2, column=2, padx=8)

        ttk.Label(top, text="At once:").grid(row=2, column=3, sticky="e")
        self.parallel_var = tk.StringVar(value=str(self.cfg["parallel"]))
        ttk.Spinbox(top, from_=1, to=8, width=4, textvariable=self.parallel_var).grid(row=2, column=4, sticky="w")

        ttk.Button(top, text="⬇  Download", style="Accent.TButton",
                   command=self.add_from_box).grid(row=2, column=5, sticky="e", padx=(8, 0))

        ttk.Label(top, text="Folder:").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.folder_var = tk.StringVar(value=self.cfg["folder"])
        ttk.Entry(top, textvariable=self.folder_var).grid(row=3, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(top, text="Browse…", command=self.pick_folder).grid(row=3, column=4, pady=(8, 0))
        ttk.Button(top, text="Open folder", command=lambda: self.open_path(self.folder_var.get())
                   ).grid(row=3, column=5, sticky="e", pady=(8, 0))

        # Download list
        mid = ttk.Frame(self.root, padding=(10, 0))
        mid.pack(fill="both", expand=True)
        cols = ("title", "status", "progress", "size", "speed", "eta")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for col, text, w, stretch in (("title", "File / Title", 330, True), ("status", "Status", 110, False),
                                      ("progress", "Progress", 160, False), ("size", "Size", 85, False),
                                      ("speed", "Speed", 90, False), ("eta", "Time left", 75, False)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, stretch=stretch, anchor="w" if col == "title" else "center")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("done", foreground="#1a7f37")
        self.tree.tag_configure("error", foreground="#cf222e")
        self.tree.tag_configure("cancelled", foreground="#888888")

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Cancel", command=self.cancel_selected)
        self.menu.add_command(label="Retry", command=self.retry_selected)
        self.menu.add_command(label="Copy link", command=self.copy_link)
        self.menu.add_separator()
        self.menu.add_command(label="Remove from list", command=self.remove_selected)
        self.tree.bind("<Button-3>", self.show_menu)
        self.tree.bind("<Button-2>", self.show_menu)   # macOS

        # Bottom bar
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.cancel_selected).pack(side="left")
        ttk.Button(bottom, text="Retry", command=self.retry_selected).pack(side="left", padx=4)
        ttk.Button(bottom, text="Clear finished", command=self.clear_finished).pack(side="left")
        self.clip_var = tk.BooleanVar(value=self.cfg["clipboard"])
        ttk.Checkbutton(bottom, text="Clipboard watch (catch copied links)",
                        variable=self.clip_var).pack(side="left", padx=12)
        ttk.Button(bottom, text="Update yt-dlp", command=self.update_ytdlp).pack(side="right")

        self.status_var = tk.StringVar(value=f"Ready  •  yt-dlp {yt_dlp.version.__version__}"
                                             f"  •  ffmpeg: {'✔' if self.ffmpeg_dir else '✘'}")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w",
                  padding=(8, 3)).pack(fill="x", side="bottom")

    # ---------- actions ----------
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get())
        if d:
            self.folder_var.set(d)
            self.save_config()

    def add_from_box(self):
        urls = [u.strip() for u in self.url_text.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo(APP_NAME, "Paste a link first.")
            return
        for u in urls:
            self.add_task(u)
        self.url_text.delete("1.0", "end")

    def add_task(self, url, fmt=None):
        folder = self.folder_var.get().strip() or os.path.expanduser("~")
        os.makedirs(folder, exist_ok=True)
        task = Task(url, fmt or self.format_var.get(), folder, self.playlist_var.get())
        self.tasks[task.id] = task
        self.tree.insert("", "end", iid=task.id, values=(url, "Waiting", text_bar(0), "-", "-", "-"))
        self.pending.append(task)
        self.save_config()

    def dispatch(self):
        try:
            limit = max(1, int(self.parallel_var.get()))
        except ValueError:
            limit = 3
        while self.pending and self.running < limit:
            task = self.pending.pop(0)
            if task.cancel:
                continue
            task.state = "running"
            self.running += 1
            threading.Thread(target=self.run_task, args=(task,), daemon=True).start()
        self.root.after(500, self.dispatch)

    def run_task(self, task):
        post = lambda **kw: self.ui_queue.put((task.id, kw))
        post(status="Starting…")

        def progress_hook(d):
            if task.cancel:
                raise Cancelled("Cancelled by user")
            info = d.get("info_dict") or {}
            title = info.get("title") or os.path.basename(d.get("filename", "")) or task.url
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                pct = (done * 100 / total) if total else 0
                speed = d.get("speed")
                post(title=title, status="Downloading", progress=text_bar(min(pct, 100)),
                     size=human_size(total), speed=(human_size(speed) + "/s") if speed else "-",
                     eta=human_eta(d.get("eta")))
            elif d["status"] == "finished":
                post(title=title, status="Processing…", progress=text_bar(100), speed="-", eta="-")

        def pp_hook(d):
            if d.get("status") == "started":
                post(status="Converting…")

        try:
            opts = build_options(task, self.ffmpeg_dir, progress_hook, pp_hook)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([task.url])
            task.state = "done"
            post(status="✔ Complete", progress=text_bar(100), speed="-", eta="-", tag="done")
        except Cancelled:
            task.state = "cancelled"
            post(status="Cancelled", speed="-", eta="-", tag="cancelled")
        except Exception as e:
            if task.cancel:
                task.state = "cancelled"
                post(status="Cancelled", speed="-", eta="-", tag="cancelled")
            else:
                task.state = "error"
                msg = str(e).replace("ERROR: ", "").splitlines()[0][:200]
                post(status="✘ Error", speed="-", eta="-", tag="error", error=msg)
        finally:
            self.ui_queue.put(("__done__", {}))

    def process_ui_queue(self):
        try:
            while True:
                tid, kw = self.ui_queue.get_nowait()
                if tid == "__done__":
                    self.running = max(0, self.running - 1)
                    continue
                if not self.tree.exists(tid):
                    continue
                vals = list(self.tree.item(tid, "values"))
                for i, key in enumerate(("title", "status", "progress", "size", "speed", "eta")):
                    if key in kw:
                        vals[i] = kw[key]
                self.tree.item(tid, values=vals)
                if "tag" in kw:
                    self.tree.item(tid, tags=(kw["tag"],))
                if "error" in kw:
                    self.status_var.set(f"Error: {kw['error']}")
        except queue.Empty:
            pass
        active = self.running + len(self.pending)
        if active:
            self.root.title(f"{APP_NAME}  —  {active} active")
        else:
            self.root.title(APP_NAME)
        self.root.after(150, self.process_ui_queue)

    def selected_tasks(self):
        return [self.tasks[i] for i in self.tree.selection() if i in self.tasks]

    def cancel_selected(self):
        for t in self.selected_tasks():
            if t.state in ("waiting", "running"):
                t.cancel = True
                if t.state == "waiting":
                    t.state = "cancelled"
                    self.ui_queue.put((t.id, {"status": "Cancelled", "tag": "cancelled"}))

    def retry_selected(self):
        for t in self.selected_tasks():
            if t.state in ("error", "cancelled"):
                t.cancel = False
                t.state = "waiting"
                self.tree.item(t.id, tags=())
                self.ui_queue.put((t.id, {"status": "Waiting"}))
                self.pending.append(t)

    def remove_selected(self):
        for t in self.selected_tasks():
            t.cancel = True
            self.tree.delete(t.id)
            self.tasks.pop(t.id, None)

    def clear_finished(self):
        for tid, t in list(self.tasks.items()):
            if t.state in ("done", "cancelled", "error"):
                self.tree.delete(tid)
                self.tasks.pop(tid)

    def copy_link(self):
        sel = self.selected_tasks()
        if sel:
            self.root.clipboard_clear()
            self.root.clipboard_append(sel[0].url)
            self.last_clip = sel[0].url

    def show_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.menu.tk_popup(event.x_root, event.y_root)

    def watch_clipboard(self):
        if self.clip_var.get():
            try:
                clip = self.root.clipboard_get().strip()
            except tk.TclError:
                clip = ""
            if clip != self.last_clip:
                self.last_clip = clip
                if clip.startswith(("http://", "https://")) and "\n" not in clip and len(clip) < 2000 \
                        and all(t.url != clip for t in self.tasks.values()):
                    self.root.deiconify()
                    self.root.lift()
                    if messagebox.askyesno(APP_NAME, f"Download this link?\n\n{clip}\n\n"
                                                     f"Format: {self.format_var.get()}"):
                        self.add_task(clip)
        self.root.after(1000, self.watch_clipboard)

    def update_ytdlp(self):
        if getattr(sys, "frozen", False):
            messagebox.showinfo(APP_NAME, "The EXE version needs a new build to update.\n"
                                          "From source: pip install -U yt-dlp")
            return
        self.status_var.set("Updating yt-dlp…")

        def job():
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                               capture_output=True, text=True)
            ok = r.returncode == 0
            self.root.after(0, lambda: self.status_var.set(
                "✔ yt-dlp updated — restart the app." if ok else "✘ Update failed: " + r.stderr[-150:]))
        threading.Thread(target=job, daemon=True).start()

    def open_path(self, path):
        if not os.path.isdir(path):
            return
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def on_close(self):
        if self.running and not messagebox.askyesno(APP_NAME, "Downloads are running. Quit anyway?"):
            return
        for t in self.tasks.values():
            t.cancel = True
        self.save_config()
        self.root.destroy()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on HiDPI screens
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
