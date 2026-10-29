# Changelog

Every push to `main` builds a new Release (`v1.<build number>`); all Releases are kept.
Earlier test builds v1–v6 were made before this repo existed; they are in Releases as v0.1–v0.6
(signed with different keys, so uninstall before installing one of them).

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

## Desktop version — 2026-10-28
- Windows/desktop app in `desktop/` (Python + Tkinter).
