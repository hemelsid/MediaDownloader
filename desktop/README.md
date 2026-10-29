# Video Downloader — Windows / desktop version

A small IDM-style desktop downloader (Python + Tkinter, powered by yt-dlp). It downloads video or
audio from YouTube, Facebook, Instagram, TikTok, X, Vimeo and 1000+ other sites, plus direct file links.

## Features
- Paste many links at once (one per line); download queue with 1–8 parallel downloads
- Progress bar, size, speed and time left
- Quality: Best / 1080p / 720p / 480p / 360p, or audio as MP3 (320k/192k) or M4A
- Whole-playlist download
- Clipboard watch — copy a link and the app asks whether to download it
- Cancel / Retry, resume of broken downloads
- One-click yt-dlp update

## Setup (Windows)
1. Install **Python** from https://www.python.org/downloads/ and tick **"Add Python to PATH"**.
2. In Command Prompt:
   ```
   pip install -r requirements.txt
   ```
3. Install **ffmpeg** (needed for HD video and MP3):
   ```
   winget install Gyan.FFmpeg
   ```
   or put `ffmpeg.exe` next to this app.
4. Run:
   ```
   python media_downloader.py
   ```

macOS: `brew install ffmpeg python-tk` · Linux: `sudo apt install ffmpeg python3-tk`

## Build an EXE
Double-click `build_exe.bat`. You get `dist\MediaDownloader.exe`; keep `ffmpeg.exe` next to it.

## Notes
DRM-protected services (Netflix, Prime Video, Disney+…) and private/login-only videos can't be downloaded.
If a site stops working, press **Update yt-dlp** first.
