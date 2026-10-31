# Changelog

Every push to `main` builds a new Release (`v1.<build number>`); all Releases are kept.
Earlier test builds v1–v6 were made before this repo existed; they are in Releases as v0.1–v0.6
(signed with different keys, so uninstall before installing one of them).

## v1.8 — 2026-11-01
- **Fixed: having to open the app before using the browser button.** The app now starts with Windows
  and waits quietly in the system tray (like IDM). Closing the window keeps it in the tray; use the
  tray icon → Quit to really exit. If it was quit, the browser button now starts it by itself
  (native messaging — works in Brave, Chrome, Edge, Vivaldi) and carries on with the download panel.
- If the app can't be started, the panel says so with a **Start the app** button instead of an error.
- Settings: "Start with Windows" and "Keep running in the tray when the window is closed" (both on).
- Browser extension 1.2.0 with a fixed ID. **One-time step:** in the browser's extensions page click
  Remove on the old Video Downloader extension, then Load unpacked the same folder again.

## v1.7 — 2026-11-01
- **Browser button now works right on the page (like IDM):** click "Download this video" and a panel
  opens beside the video with its thumbnail, title and every quality with its size (Video / Audio).
  Pick one — the PC app downloads it in the background (the app window doesn't pop up), progress
  shows in the panel, and when it's done you get a Windows notification with Play / Show in folder.
  If the app is closed, the button starts it quietly. Right-click menu and toolbar popup open the same panel.
- **Search everywhere:** the search box is no longer YouTube-only. "Search in" chips under the box:
  All, YouTube, Facebook, Instagram, TikTok, X, Dailymotion, Vimeo, Web — plus "Google ↗" to search
  Google videos in your browser. (The header site links were replaced by these chips.)
- Settings: browser button can "Choose on the page" (default), "Best quality at once" or "Open in the app";
  option to turn the Windows notification off.
- Direct video files downloaded from a page are saved under the caption shown on the page.
- Browser extension 1.1.0 — reload it once in the browser's extensions page after updating the app.

## v1.6 — 2026-11-01
- **New: IDM-style browser button** (Chrome, Edge, Brave). While a video plays on YouTube, Facebook,
  Instagram or any site, an orange "Download this video" button appears on it; one click sends that
  exact video to the PC app (its preview opens there). Right-click menu "Download with Video
  Downloader" too. If the app is closed it opens automatically (`videodownloader://` link).
  Setup: click **Browser button** in the app (1-minute guide).
- PC: ✕ to clear the search box and ✕ to close the preview.
- PC: site shortcuts in the header (YouTube, Facebook, Instagram, TikTok, X, Dailymotion, Vimeo) — open the
  site in your browser, then use the button on the video.
- PC: sharp app icon at every size (title bar, taskbar, installer).
- PC: only one copy of the app runs; opening it again brings the window to the front.
- Settings: choose what the browser button does — show qualities first, or download best quality at once.

## v1.5 — 2026-11-01
- PC app redesigned for a more professional look (CustomTkinter): rounded controls, dark title bar,
  logo, download cards with thumbnails, progress bars and icon buttons, filters (All / Active /
  Done / Failed), highlighted quality choices.
- Fits every screen: sizes follow Windows display scaling (100–150%+); small screens start maximized
  with a compact preview; long titles end with "…" instead of being cut off.
- Download button always visible below the preview; Settings scrolls with Save/Cancel always visible.

## v1.4 — 2026-10-31
- **New: PC app for Windows** — installer and portable zip in every Release. Paste a link or search
  YouTube, preview with thumbnail, every quality with its size, rename, playlists, download queue
  with progress/speed, clipboard detection, logins via browser or cookies.txt, daily engine update.
  Bundles yt-dlp, ffmpeg and Deno (needed for YouTube).
- Phone: shorter "Processing" step — finished files are no longer rewritten just to add metadata.
- One Release now contains both the phone APKs and the PC files.

## v1.3 — 2026-10-29
- Same app as v1.1. Every APK is now kept in Releases: newest on top, old test builds
  v0.1–v0.6 (the v1–v6 below) added as pre-releases.

## v1.2 — 2026-10-29
- Same app as v1.1 (documentation added).

## v1.1 — 2026-10-29 (first build from this repo)
- All text readable on the dark theme (some screens showed black text).
- YouTube: the PO token YouTube gives the built-in player while a video plays is captured and
  reused for that video, then other YouTube clients are tried automatically.
- Clearer YouTube error with what to do next.
- Settings screen no longer hides under the status bar.
- Same signing key for every build, so updates install over the old app.

## v6 — 2026-10-29
- ⬇ now downloads the exact video you are watching (IDM-style): asks the page which `<video>`
  is playing or most visible, then uses its post link, Facebook video id, or direct file.
- Streaming pieces (byte ranges) are merged into one entry; fixes Facebook
  "Postprocessing: Invalid data" errors and the "15 videos" count.
- Real titles/thumbnails from the page instead of random file names.
- "Not this video?" list for picking another video on the page.

## v5 — 2026-10-29
- All in-app text switched to English.

## v4 — 2026-10-29
- Complete redesign (dark/orange): Home with search and site shortcuts, built-in browser with
  floating ⬇ button, quality sheet with sizes and rename, Downloads list, Files with built-in
  player, PIN-locked Private folder, Settings.
- Logins from the built-in browser are used automatically for downloads.
- DRM services (Netflix, Prime, Hotstar…) are detected and explained.

## v3 — 2026-10-29
- Login page survives switching apps for an OTP.
- cookies.txt import.
- Automatic retry with other YouTube clients when blocked.

## v2 — 2026-10-29
- Preview (thumbnail, title, channel, length) before downloading.
- In-app site login; real error details.

## v1 — 2026-10-29
- First Android version: paste or share a link, pick quality, download in the background.

## Desktop prototype — 2026-10-28
- First simple Windows/desktop script (replaced by the PC app in v1.4).
