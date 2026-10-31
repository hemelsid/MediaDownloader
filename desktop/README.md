# Video Downloader — PC (Windows)

The PC version of the app. Paste a link (or type words to search YouTube), see a preview with every
quality and its size, then download — same idea and same engine as the phone app.

## Install (Windows 10/11, 64-bit)
1. Open this repo's **Releases** and download **`VideoDownloader-Windows-Setup.exe`** from the newest version.
2. Run it. If Windows shows "Windows protected your PC", click **More info → Run anyway**
   (the app isn't signed with a paid certificate).
3. Open **Video Downloader** from the desktop or Start menu.

No installer wanted? Download `VideoDownloader-Windows-portable.zip`, unzip, run `VideoDownloader.exe`.
Everything needed is included — no Python, ffmpeg or anything else to install.

## Using it
- Paste a link and press **Find** (or press **Paste**). Copying a link anywhere also shows a
  "Copied link detected" bar.
- Type words instead of a link to search. Pick where under the box: **All**, YouTube, Facebook, Instagram,
  TikTok, X, Dailymotion, Vimeo or Web — or **Google ↗** to search Google videos in your browser.
- Pick **Video** or **Audio**, choose a quality (sizes shown), optionally change the file name, **Download**.
- Several links at once (one per line) are all added with the best quality.
- Downloads list: double-click to play, right-click for more. Files go to
  `Downloads\Video Downloader` (change it in **Settings**).
- If a site blocks you: **Settings → Logins** — pick a browser where you are logged in
  (Firefox works best on Windows) or choose a `cookies.txt` file.
- The engine (yt-dlp) updates itself once a day; **Settings → Update now** forces it.

## Download button in your browser (like IDM)
In the app click **Browser button** and follow the 4 steps (about a minute):
1. Open your browser's extensions page (the app has Chrome / Edge / Brave buttons for this).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and pick the folder the app shows
   (`%LOCALAPPDATA%\Programs\Video Downloader\extension`).
4. Play any video — an orange **Download this video** button appears on it. Click it: a panel opens
   beside the video with every quality and its size. Pick one — it downloads in the background, the
   panel shows the progress, and a Windows notification tells you when it's done (Play / Show in folder).
If the app is closed, clicking the button starts it quietly. After updating the app, press the reload
icon on the extension in the browser's extensions page once.

## What's inside
| File | Purpose |
|---|---|
| `video_downloader.py` | The window (Tkinter, dark theme) |
| `engine.py` | Runs yt-dlp / ffmpeg / Deno, builds the quality list, progress, retries, error messages |
| `bridge.py` | Local API for the browser extension (127.0.0.1:47811), single instance, `videodownloader://` links |
| `notify.py` | Windows "download complete" notification |
| `icons.py` | Draws the app icon sharply at every size |
| `installer.iss` | Inno Setup script for the installer (also registers `videodownloader://`) |
| `../browser-extension/` | The Chrome / Edge / Brave extension |

The release build bundles `yt-dlp.exe`, `ffmpeg.exe`/`ffprobe.exe` and `deno.exe` (needed for
YouTube) in a `bin` folder next to the app.

## Run from source (any OS)
```
pip install -r requirements.txt
python video_downloader.py
```
You also need ffmpeg (and Deno for YouTube) on your PATH or in a `bin` folder next to the script.
macOS: `brew install ffmpeg deno python-tk` · Linux: `sudo apt install ffmpeg python3-tk` + Deno.
