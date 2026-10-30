"""
Download engine for the PC app.

Runs the standalone yt-dlp program (bin/yt-dlp.exe on Windows) as a separate process, so it can
update itself (`yt-dlp -U`) without rebuilding the app. ffmpeg and Deno (needed for YouTube) sit
in the same bin folder. When run from source without a bin folder it falls back to
`yt-dlp` on PATH or `python -m yt_dlp`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from urllib.parse import urlparse

IS_WIN = sys.platform.startswith("win")
NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW: no black console popping up


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def bin_dir() -> str:
    return os.path.join(app_dir(), "bin")


def _bin(name: str) -> str | None:
    exe = name + (".exe" if IS_WIN else "")
    p = os.path.join(bin_dir(), exe)
    if os.path.isfile(p):
        return p
    return shutil.which(name)


def ytdlp_cmd() -> list[str]:
    p = _bin("yt-dlp")
    if p:
        return [p]
    return [sys.executable, "-m", "yt_dlp"]


def ffmpeg_dir() -> str | None:
    p = _bin("ffmpeg")
    return os.path.dirname(p) if p else None


def deno_path() -> str | None:
    return _bin("deno")


# ---------------------------------------------------------------- quality options

@dataclass(frozen=True)
class Quality:
    label: str
    size: int = 0
    height: int | None = None      # max video height; None = best
    audio: str | None = None       # "mp3_320" | "mp3_128" | "m4a" | None for video

    @property
    def is_audio(self) -> bool:
        return self.audio is not None

    def args(self) -> list[str]:
        if self.audio in ("mp3_320", "mp3_128"):
            return ["-f", "ba/b", "-x", "--audio-format", "mp3",
                    "--audio-quality", "320K" if self.audio == "mp3_320" else "128K"]
        if self.audio == "m4a":
            return ["-f", "ba[ext=m4a]/ba/b", "-x", "--audio-format", "m4a"]
        sort = f"res:{self.height},vcodec:h264,acodec:m4a" if self.height else "res,vcodec:h264,acodec:m4a"
        return ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", "mp4"]


BEST = Quality("Best quality")


@dataclass
class MediaInfo:
    url: str
    title: str
    thumbnail: str | None
    uploader: str | None
    site: str | None
    duration: int
    views: int
    is_playlist: bool
    count: int
    video: list[Quality] = field(default_factory=list)
    audio: list[Quality] = field(default_factory=list)


@dataclass
class SearchResult:
    url: str
    title: str
    channel: str
    duration: int
    thumbnail: str | None


class EngineError(Exception):
    def __init__(self, friendly: str, detail: str, drm: bool = False, login_site: str | None = None):
        super().__init__(friendly)
        self.friendly = friendly
        self.detail = detail
        self.drm = drm
        self.login_site = login_site


DRM_HOSTS = ["netflix.com", "primevideo.com", "disneyplus.com", "hotstar.com", "hulu.com", "max.com",
             "hbomax.com", "tv.apple.com", "peacocktv.com", "paramountplus.com", "zee5.com", "sonyliv.com",
             "chorki.com", "hoichoi.tv", "bongobd.com", "binge.buzz", "spotify.com", "music.apple.com"]

YT_FALLBACKS = [None, "youtube:player_client=tv_simply,web_safari,mweb", "youtube:player_client=android_vr,web_embedded,tv"]


def host_of(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def is_drm(url: str) -> bool:
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in DRM_HOSTS) or ("amazon." in h and "/gp/video" in url)


def is_youtube(url: str) -> bool:
    h = host_of(url)
    return h.endswith("youtube.com") or h == "youtu.be"


def extract_urls(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"https?://\S+", text):
        u = m.group(0).rstrip(".,)\"'")
        if u not in out:
            out.append(u)
    return out


def quality_name(h: int) -> str:
    if h >= 2160: return "4K Ultra HD"
    if h >= 1440: return "QHD Video"
    if h >= 1080: return "FHD Video"
    if h >= 720: return "HD Video"
    if h >= 480: return "SD Video"
    return "Low"


def parse_info(url: str, j: dict) -> MediaInfo:
    is_pl = j.get("_type") == "playlist"
    entries = j.get("entries") or []
    thumb = j.get("thumbnail")
    if not thumb:
        thumbs = j.get("thumbnails") or (entries[0].get("thumbnails") if entries and isinstance(entries[0], dict) else None) or []
        if thumbs:
            thumb = thumbs[-1].get("url")
    duration = float(j.get("duration") or 0)

    fs = []
    for f in j.get("formats") or []:
        vc, ac, ext = f.get("vcodec") or "", f.get("acodec") or "", f.get("ext") or ""
        h = int(f.get("height") or 0)
        size = int(f.get("filesize") or f.get("filesize_approx") or 0)
        is_v = (vc != "none") if vc else (h > 0 or ext in ("mp4", "webm", "mkv", "mov", "flv"))
        is_a = (ac != "none") if ac else (not vc or ext in ("m4a", "mp3", "opus", "ogg"))
        fs.append(dict(h=h, v=is_v, a=is_a, size=size, h264=vc.startswith(("avc1", "h264")), m4a=ext == "m4a"))
    audios = [f for f in fs if f["a"] and not f["v"] and f["size"] > 0]
    m4as = [f for f in audios if f["m4a"]]
    best_audio = max(m4as or audios, key=lambda f: f["size"], default=None)

    video: list[Quality] = []
    if not is_pl:
        vids = [f for f in fs if f["v"]]
        heights = sorted({f["h"] for f in vids if f["h"] >= 100}, reverse=True)[:8]
        for h in heights:
            at = [f for f in vids if f["h"] == h and f["size"] > 0]
            pick = max([f for f in at if f["h264"]] or at, key=lambda f: f["size"], default=None)
            size = 0 if pick is None else pick["size"] + (0 if pick["a"] else (best_audio["size"] if best_audio else 0))
            video.append(Quality(f"{quality_name(h)} - {h}p", size, height=h))
        if not video and (vids or not fs):
            size = max((f["size"] for f in vids), default=0) or int(j.get("filesize") or j.get("filesize_approx") or 0)
            video.append(Quality("Original quality", size))
    else:
        video = [Quality(f"{quality_name(h)} - {h}p", 0, height=h) for h in (1080, 720, 480, 360)]

    audio = [
        Quality("MP3 - 320 kbps", int(duration * 40_000), audio="mp3_320"),
        Quality("MP3 - 128 kbps", int(duration * 16_000), audio="mp3_128"),
        Quality("M4A - original", best_audio["size"] if best_audio else 0, audio="m4a"),
    ]
    site = j.get("extractor_key")
    return MediaInfo(
        url=url,
        title=j.get("title") or j.get("webpage_url") or url,
        thumbnail=thumb,
        uploader=j.get("uploader") or j.get("channel"),
        site=None if site in (None, "Generic") else site,
        duration=int(duration),
        views=int(j.get("view_count") or 0),
        is_playlist=is_pl,
        count=int(j.get("playlist_count") or len(entries)),
        video=video,
        audio=audio,
    )


# ---------------------------------------------------------------- errors

LOGIN_HINTS = ["Sign in to confirm", "LOGIN_REQUIRED", "login required", "--cookies", "log in", "logged-in",
               "rate-limit reached", "requested content is not available", "age-restricted", "confirm your age"]


def error_detail(text: str) -> str:
    errs = [l.split("ERROR:", 1)[1].strip() for l in text.splitlines() if "ERROR:" in l]
    if not errs:
        errs = [l for l in text.splitlines() if l.strip()][-3:]
    return "\n".join(errs)[:800]


def is_login_error(d: str) -> bool:
    return any(h.lower() in d.lower() for h in LOGIN_HINTS)


def friendly(d: str, url: str) -> EngineError:
    lo = d.lower()
    site = "YouTube" if is_youtube(url) else None
    if "drm" in lo:
        return EngineError("This video is DRM-protected and can't be downloaded.", d, drm=True)
    if is_login_error(d):
        name = site or (host_of(url) or "This site")
        return EngineError(
            f"{name} blocked this request. Try again in a minute, switch network, or in Settings choose a "
            f"browser where you are logged in (or a cookies.txt file).", d, login_site=name)
    if "unsupported url" in lo:
        return EngineError("No downloadable video found at this link.", d)
    if "private video" in lo:
        return EngineError("This video is private and can't be downloaded.", d)
    if "could not copy" in lo and "cookie" in lo or "failed to decrypt" in lo:
        return EngineError("Couldn't read that browser's cookies. Close the browser, or use Firefox / a cookies.txt file "
                           "in Settings.", d)
    if any(x in lo for x in ("unable to resolve host", "getaddrinfo failed", "network is unreachable", "timed out")):
        return EngineError("Internet connection problem.", d)
    if "http error 404" in lo:
        return EngineError("Nothing found at this link (404). Check that the link is complete.", d)
    if "http error 403" in lo:
        return EngineError("The site refused access (403). Try again, or update the engine in Settings.", d)
    first = d.splitlines()[0] if d else "Unknown error"
    return EngineError(first[:200], d)


# ---------------------------------------------------------------- engine

class Engine:
    def __init__(self, settings: dict):
        self.settings = settings  # shared dict: cookies_browser, cookies_file
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()

    # ---- helpers
    def _base(self, url: str, extractor_args: str | None, use_cookies: bool = True) -> list[str]:
        a = ytdlp_cmd() + ["--encoding", "utf-8", "--no-warnings", "--retries", "10", "--socket-timeout", "20"]
        ff = ffmpeg_dir()
        if ff:
            a += ["--ffmpeg-location", ff]
        d = deno_path()
        if d:
            a += ["--js-runtimes", f"deno:{d}"]
        if extractor_args:
            a += ["--extractor-args", extractor_args]
        if use_cookies:
            cf = self.settings.get("cookies_file")
            cb = self.settings.get("cookies_browser")
            if cf and os.path.isfile(cf):
                a += ["--cookies", cf]
            elif cb and cb != "None":
                a += ["--cookies-from-browser", cb.lower()]
        return a

    def _attempts(self, url: str) -> list[str | None]:
        return YT_FALLBACKS if is_youtube(url) else [None]

    def _run(self, args: list[str], key: str | None = None, on_line=None) -> tuple[int, str]:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=NO_WINDOW, env=env)
        if key:
            with self._lock:
                self._procs[key] = p
        out = []
        try:
            for raw in iter(p.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                out.append(line)
                if on_line:
                    on_line(line)
            p.wait()
        finally:
            if key:
                with self._lock:
                    self._procs.pop(key, None)
        return p.returncode, "\n".join(out)

    def _with_retries(self, url: str, build, key=None, on_line=None) -> str:
        """Runs yt-dlp; on YouTube blocks tries other clients; if browser cookies fail, retries without them."""
        last = ""
        for i, ex in enumerate(self._attempts(url)):
            for use_cookies in (True, False):
                code, out = self._run(build(ex, use_cookies), key, on_line)
                if code == 0:
                    return out
                if key and key in self._cancelled:
                    raise EngineError("Cancelled", "cancelled")
                last = out
                d = error_detail(out)
                cookie_problem = "cookie" in d.lower() and use_cookies and (
                    self.settings.get("cookies_browser") not in (None, "None") or self.settings.get("cookies_file"))
                if not cookie_problem:
                    break
            d = error_detail(last)
            retry_yt = is_youtube(url) and (is_login_error(d) or "403" in d or "format is not available" in d.lower()
                                             or "po token" in d.lower())
            if i == len(self._attempts(url)) - 1 or not retry_yt:
                break
        raise friendly(error_detail(last), url)



    # ---- public API
    def version(self) -> str:
        try:
            code, out = self._run(ytdlp_cmd() + ["--version"])
            return out.strip().splitlines()[-1] if code == 0 else "not found"
        except Exception:
            return "not found"

    def update(self) -> str:
        if not _bin("yt-dlp"):
            return "Engine runs from Python here — update it with: pip install -U yt-dlp"
        code, out = self._run(ytdlp_cmd() + ["-U"])
        tail = [l for l in out.splitlines() if l.strip()]
        return tail[-1] if tail else ("Updated" if code == 0 else "Update failed")

    def info(self, url: str) -> MediaInfo:
        if is_drm(url):
            raise EngineError("This service locks its videos with DRM (like Netflix and Prime Video), so no downloader "
                              "can save them. Use the download option in their own app instead.", "DRM", drm=True)
        out = self._with_retries(url, lambda ex, ck: self._base(url, ex, ck) + ["-J", "--flat-playlist", "--no-playlist", url])
        js = next((l for l in reversed(out.splitlines()) if l.lstrip().startswith("{")), None)
        if not js:
            raise friendly(error_detail(out), url)
        return parse_info(url, json.loads(js))

    def search(self, query: str, n: int = 12) -> list[SearchResult]:
        out = self._with_retries("https://youtube.com", lambda ex, ck: self._base("https://youtube.com", None, ck) +
                                 ["-J", "--flat-playlist", f"ytsearch{n}:{query}"])
        js = next((l for l in reversed(out.splitlines()) if l.lstrip().startswith("{")), "{}")
        res = []
        for e in json.loads(js).get("entries") or []:
            vid = e.get("id")
            url = e.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else None)
            if not url:
                continue
            thumbs = e.get("thumbnails") or []
            res.append(SearchResult(url, e.get("title") or url, e.get("channel") or e.get("uploader") or "",
                                    int(e.get("duration") or 0), thumbs[-1]["url"] if thumbs else None))
        return res

    def download(self, key: str, url: str, q: Quality, folder: str, playlist: bool, name: str | None, on_progress) -> list[str]:
        """Blocking. on_progress(dict) gets: pct, speed, eta, total, stage. Returns final file paths."""
        self._cancelled.discard(key)
        if name and not playlist:
            tmpl = f"{name}.%(ext)s"
        elif playlist:
            tmpl = "%(playlist_title,playlist|Playlist).80B/%(playlist_index)03d - %(title).140B.%(ext)s"
        else:
            tmpl = "%(title).150B.%(ext)s"
        files: list[str] = []

        def on_line(line: str):
            if line.startswith("[MDP]"):
                p = line[5:].split("|")
                def num(x):
                    try:
                        return float(x)
                    except Exception:
                        return 0.0
                done, total, est, speed, eta = (num(x) for x in (p + ["NA"] * 5)[:5])
                tot = total or est
                on_progress(dict(stage="download", pct=(done * 100 / tot) if tot else 0, speed=speed, eta=eta, total=tot))
            elif line.startswith("[MDF]"):
                files.append(line[5:].strip())
            elif line.startswith(("[Merger]", "[ExtractAudio]", "[Fixup", "[VideoConvertor]", "[Metadata]")):
                on_progress(dict(stage="processing"))

        def build(ex, ck):
            return (self._base(url, ex, ck) + q.args() + [
                "-o", os.path.join(folder, tmpl),
                "--yes-playlist" if playlist else "--no-playlist",
                "--windows-filenames", "--no-mtime", "--no-overwrites",
                "--concurrent-fragments", "8", "--http-chunk-size", "10M", "--fragment-retries", "10",
                "--newline", "--progress",
                "--progress-template",
                "download:[MDP]%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s"
                "|%(progress.speed)s|%(progress.eta)s",
                "--print", "after_move:[MDF]%(filepath)s",
                url,
            ])

        self._with_retries(url, build, key, on_line)
        return [f for f in files if os.path.isfile(f)]

    def cancel(self, key: str):
        self._cancelled.add(key)
        with self._lock:
            p = self._procs.get(key)
        if not p:
            return
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()
        except Exception:
            pass
