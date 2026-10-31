"""Windows 10/11 notification ("toast") when a download finishes — no extra libraries needed."""
from __future__ import annotations

import os
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

AUMID = "hemelsid.VideoDownloader"
POWERSHELL_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml($env:VD_XML)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:VD_AUMID).Show(
    [Windows.UI.Notifications.ToastNotification]::new($x))
"""


def _installed() -> bool:
    """The installer creates a Start-menu shortcut with our app id; without it Windows hides our toasts."""
    start = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Video Downloader")
    return os.path.isdir(start)


def toast(title: str, message: str, play_link: str | None = None, folder_link: str | None = None):
    if not sys.platform.startswith("win"):
        return
    launch = f' activationType="protocol" launch={quoteattr(play_link)}' if play_link else ""
    actions = ""
    if play_link or folder_link:
        actions = "<actions>"
        if play_link:
            actions += f'<action content="Play" activationType="protocol" arguments={quoteattr(play_link)}/>'
        if folder_link:
            actions += f'<action content="Show in folder" activationType="protocol" arguments={quoteattr(folder_link)}/>'
        actions += "</actions>"
    xml = (f"<toast{launch}><visual><binding template=\"ToastGeneric\"><text>{escape(title)}</text>"
           f"<text>{escape(message[:200])}</text></binding></visual>{actions}</toast>")
    env = dict(os.environ, VD_XML=xml, VD_AUMID=AUMID if _installed() else POWERSHELL_AUMID)
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", _SCRIPT], env=env, creationflags=0x08000000,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
