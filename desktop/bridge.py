"""
Connection between the browser extension and the app.

- The app listens on http://127.0.0.1:47811 (this PC only, extension origins only).
  The extension asks for a video's qualities (/info), starts a download (/download), follows its
  progress (/status) and opens the finished file (/open) — all without bringing the app forward.
- Only one copy of the app runs: a second launch passes its link to the running one and exits.
- videodownloader://… links: add?url= (open a video), start (wake the app quietly),
  play?file= / show?file= (from the "download complete" notification).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47811
PROTOCOL = "videodownloader"


def parse_launch_arg(arg: str) -> dict | None:
    """Command-line argument -> what to do. Plain http(s) links open that video."""
    if not arg:
        return None
    if arg.lower().startswith(PROTOCOL + ":"):
        u = urllib.parse.urlparse(arg)
        action = (u.netloc or u.path.strip("/").split("/")[0] or "").lower()
        q = urllib.parse.parse_qs(u.query or (arg.split("?", 1)[1] if "?" in arg else ""))
        get = lambda k: (q.get(k) or [""])[0]
        if action in ("play", "show") and get("file"):
            return {"action": action, "file": get("file")}
        if action == "start":
            return {"action": "start"}
        url = get("url")
        if url.startswith(("http://", "https://")):
            return {"action": "add", "url": url, "title": get("title"), "src": get("src")}
        return {"action": "start"}
    if arg.startswith(("http://", "https://")):
        return {"action": "add", "url": arg, "title": "", "src": ""}
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
    """True if another copy of the app is already running (it got the request)."""
    info = _call("/ping")
    if not info or info.get("app") != "VideoDownloader":
        return False
    if payload and payload.get("action") == "add":
        _call("/add", payload)
    elif not payload:
        _call("/focus", {})
    return True


class Bridge:
    """api: object with ext_add(d), focus(), api_info(d), api_download(d), api_status(id), api_open(d), api_cancel(d)."""

    def __init__(self, api, version: str):
        self.api, self.version = api, version
        self.last_seen = 0.0          # last time the extension talked to us
        self.server = None

    def start(self) -> bool:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _origin(self) -> str:
                return self.headers.get("Origin", "")

            def _allowed(self) -> bool:
                # Only the extension (or this app itself) may talk to us — never ordinary web pages.
                o = self._origin()
                return o == "" or o.startswith(("chrome-extension://", "moz-extension://", "extension://",
                                                "safari-web-extension://"))

            def _seen(self):
                if "extension://" in self._origin():
                    bridge.last_seen = time.time()

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
                self._seen()
                path, _, query = self.path.partition("?")
                if path == "/ping":
                    return self._reply(200, {"app": "VideoDownloader", "version": bridge.version})
                if path == "/status":
                    q = urllib.parse.parse_qs(query)
                    return self._reply(200, bridge.api.api_status((q.get("id") or [""])[0]))
                self._reply(404, {"ok": False})

            def do_POST(self):
                if not self._allowed() or "json" not in self.headers.get("Content-Type", ""):
                    return self._reply(403, {"ok": False})
                try:
                    n = min(int(self.headers.get("Content-Length", "0")), 100_000)
                    data = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return self._reply(400, {"ok": False})
                self._seen()
                path = self.path.partition("?")[0]
                try:
                    if path in ("/add", "/info"):
                        url = str(data.get("url", ""))
                        if not url.startswith(("http://", "https://")):
                            return self._reply(400, {"ok": False, "error": "Not a web link"})
                        d = {"url": url, "title": str(data.get("title", ""))[:300],
                             "src": str(data.get("src", "")), "page": str(data.get("page", ""))}
                        if path == "/add":
                            bridge.api.ext_add(d)
                            return self._reply(200, {"ok": True})
                        return self._reply(200, bridge.api.api_info(d))
                    if path == "/download":
                        return self._reply(200, bridge.api.api_download(data))
                    if path == "/open":
                        return self._reply(200, bridge.api.api_open(data))
                    if path == "/cancel":
                        return self._reply(200, bridge.api.api_cancel(data))
                    if path == "/focus":
                        bridge.api.focus()
                        return self._reply(200, {"ok": True})
                except Exception as e:  # never let one bad request kill the server
                    return self._reply(500, {"ok": False, "error": str(e)[:200]})
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


def file_link(action: str, path: str) -> str:
    return f"{PROTOCOL}://{action}?file=" + urllib.parse.quote(os.path.abspath(path))
