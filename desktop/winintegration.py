"""
Windows integration so the browser button always finds the app (like IDM):

- start with Windows, quietly in the system tray
- closing the window keeps the app running in the tray
- the browser extension can start the app directly ("native messaging") — no prompts
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading

IS_WIN = sys.platform.startswith("win")
FROZEN = getattr(sys, "frozen", False)
HOST_NAME = "com.hemelsid.videodownloader"
EXTENSION_ID = "bnkgghgbeofkfjgbjhpkeanomfiapcmp"      # fixed by the "key" in browser-extension/manifest.json
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "VideoDownloader"
HOST_KEYS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
    r"Software\Vivaldi\NativeMessagingHosts",
]


def exe_command(*args: str) -> list[str]:
    if FROZEN:
        return [sys.executable, *args]
    return [sys.executable, os.path.abspath(sys.argv[0]), *args]


# ---------------------------------------------------------------- start with Windows

def set_autostart(on: bool):
    if not (IS_WIN and FROZEN):
        return
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --background')
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


# ---------------------------------------------------------------- native messaging host

def register_native_host(data_dir: str):
    """Lets Chrome / Edge / Brave start this app when the browser button is used while it's closed."""
    if not IS_WIN:
        return
    import winreg
    cmd = exe_command()
    if not FROZEN:
        return  # the source version can't be a native host (needs an .exe)
    manifest = {
        "name": HOST_NAME,
        "description": "Video Downloader",
        "path": cmd[0],
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    path = os.path.join(data_dir, "native-host.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        for base in HOST_KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + HOST_NAME) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, path)
    except OSError:
        pass


def is_native_host_launch(argv: list[str]) -> bool:
    return any(a.startswith("chrome-extension://") for a in argv[1:])


def run_native_host(app_running) -> None:
    """Started by the browser: make sure the app is running (detached), answer, and exit at once."""
    try:
        raw_len = os.read(0, 4)
        if len(raw_len) == 4:
            os.read(0, struct.unpack("<I", raw_len)[0])
    except Exception:
        pass
    started = False
    if not app_running():
        flags = 0x00000008 | 0x00000200 | 0x01000000 | 0x08000000   # DETACHED | NEW_GROUP | BREAKAWAY | NO_WINDOW
        for f in (flags, flags & ~0x01000000):                      # breakaway may be refused by the browser's job
            try:
                subprocess.Popen(exe_command("--background"), creationflags=f, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                started = True
                break
            except OSError:
                continue
    try:
        msg = json.dumps({"ok": True, "started": started}).encode()
        os.write(1, struct.pack("<I", len(msg)) + msg)
    except Exception:
        pass


# ---------------------------------------------------------------- tray icon

class Tray:
    """System-tray icon (Windows). on_open / on_quit are called on the tray's thread."""

    def __init__(self, image, on_open, on_quit):
        self.icon = None
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("Open Video Downloader", lambda: on_open(), default=True),
                pystray.MenuItem("Quit", lambda: on_quit()),
            )
            self.icon = pystray.Icon("VideoDownloader", image, "Video Downloader", menu)
            threading.Thread(target=self.icon.run, daemon=True).start()
        except Exception:
            self.icon = None

    @property
    def ok(self) -> bool:
        return self.icon is not None

    def notify(self, title: str, msg: str):
        try:
            if self.icon:
                self.icon.notify(msg, title)
        except Exception:
            pass

    def stop(self):
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
