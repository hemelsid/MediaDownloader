# Video Downloader (Android)

An IDM-style video & audio downloader for Android. Open any site in the built-in browser, play a
video, tap the orange ⬇ button, pick a quality and download. Powered by
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and ffmpeg (via
[youtubedl-android](https://github.com/yausername/youtubedl-android)).

## Install
1. On your phone open this repo's **Releases** and download `VideoDownloader-arm64-v8a.apk`.
2. Open it, allow "Install unknown apps" if asked, then **Install**.
3. Later versions install over the old one.

## Features
- **Home** — search box (paste a link or search for a video) and site shortcuts; add your own sites.
- **Browser + auto-detect** — detects the video that is actually playing on screen (IDM-style),
  including Facebook feeds, Instagram, TikTok, X, Vimeo, Dailymotion and most other sites.
- **Quality sheet** — preview with thumbnail and title, Video/Audio tabs, every resolution with its
  size, MP3 320/128 kbps or M4A, rename before download, whole playlists.
- **Share ▸ Download** from any app, and copied links are offered automatically.
- **Downloads** — thumbnails, progress, speed, time left; 3 at a time; keeps going in the background.
- **Files** — built-in player, share, open with…, delete.
- **🔒 Private** — PIN-locked folder that hides files from the gallery.
- **Logins** — if you are logged in to a site in the built-in browser, downloads use that login.
  You can also import a `cookies.txt`.
- yt-dlp updates itself daily.

Files are saved to **Download/MediaDownloader**.

## Not supported
DRM-protected services (Netflix, Prime Video, Disney+/Hotstar, Hoichoi, Chorki, Spotify…) can't be
downloaded by any downloader; use their own apps' offline download.

## Build
Every push to `main` builds the APKs with GitHub Actions and publishes a Release.
Locally: open in Android Studio, or run `./gradlew assembleRelease`.

`app/release.jks` (password `mediadownloader`) is committed so every build is signed with the same
key and updates install cleanly. To keep your own private key instead, replace the file, store the
password as a repository secret and use it in the workflow.
