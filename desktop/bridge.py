"""
Connection between the browser extension and the app.

- The app listens on http://127.0.0.1:47811 (this PC only). The extension sends the video link there.
- Only one copy of the app runs: a second launch passes its link to the running one and exits.
- videodownloader://add?url=… links (used when the app is closed) open the app with that video.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47811
PROTOCOL = "videodownloader"


def parse_launch_arg(arg: str) -> dict | None:
    """'videodownloader://add?url=…' or a plain http(s) link -> {url, title, src}."""
    if not arg:
        return None
    if arg.lower().startswith(PROTOCOL + ":"):
        q = urllib.parse.urlparse(arg).query
        if not q and "?" in arg:
            q = arg.split("?", 1)[1]
        p = urllib.parse.parse_qs(q)
        url = (p.get("url") or [""])[0]
        if url.startswith(("http://", "https://")):
            return {"url": url, "title": (p.get("title") or [""])[0], "src": (p.get("src") or [""])[0]}
        return None
    if arg.startswith(("http://", "https://")):
        return {"url": arg, "title": "", "src": ""}
    return None


def _call(path: str, data: dict | None = None, timeout=1.5) -> dict | None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}",
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json"},
                                     method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def hand_over_to_running_app(payload: dict | None) -> bool:
    """True if another copy of the app is already running (and got the link / was brought forward)."""
    info = _call("/ping")
    if not info or info.get("app") != "VideoDownloader":
        return False
    if payload:
        _call("/add", payload)
    else:
        _call("/focus", {})
    return True


class Bridge:
    def __init__(self, on_add, on_focus, version: str):
        self.on_add, self.on_focus, self.version = on_add, on_focus, version
        self.last_seen = 0.0          # last time the extension talked to us
        self.server = None

    def start(self) -> bool:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _allowed(self) -> bool:
                # Only the extension (or this app itself) may talk to us — never ordinary web pages.
                origin = self.headers.get("Origin", "")
                return origin == "" or origin.startswith(("chrome-extension://", "moz-extension://",
                                                          "extension://", "safari-web-extension://"))

            def _reply(self, code: int, body: dict):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_OPTIONS(self):          # no CORS for web pages
                self._reply(403, {"ok": False})

            def do_GET(self):
                if not self._allowed():
                    return self._reply(403, {"ok": False})
                if self.path.startswith("/ping"):
                    if "extension://" in self.headers.get("Origin", ""):
                        bridge.last_seen = time.time()
                    return self._reply(200, {"app": "VideoDownloader", "version": bridge.version})
                self._reply(404, {"ok": False})

            def do_POST(self):
                if not self._allowed() or "json" not in self.headers.get("Content-Type", ""):
                    return self._reply(403, {"ok": False})
                try:
                    n = min(int(self.headers.get("Content-Length", "0")), 100_000)
                    data = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return self._reply(400, {"ok": False})
                if self.path.startswith("/add"):
                    url = str(data.get("url", ""))
                    if not url.startswith(("http://", "https://")):
                        return self._reply(400, {"ok": False})
                    if "extension://" in self.headers.get("Origin", ""):
                        bridge.last_seen = time.time()
                    bridge.on_add({"url": url, "title": str(data.get("title", ""))[:300],
                                   "src": str(data.get("src", "")), "page": str(data.get("page", ""))})
                    return self._reply(200, {"ok": True})
                if self.path.startswith("/focus"):
                    bridge.on_focus()
                    return self._reply(200, {"ok": True})
                self._reply(404, {"ok": False})

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError:
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.server:
            self.server.shutdown()
