# How the app works

## Overview
Kotlin + Jetpack Compose Android app (minSdk 26). Downloads are done by **yt-dlp** running on an
embedded Python, with **ffmpeg** for merging/converting, via
[youtubedl-android](https://github.com/yausername/youtubedl-android) `0.18.1`.

## Source files (`app/src/main/java/com/mediadownloader/app/`)
| File | What it does |
|---|---|
| `App.kt` | Starts notifications, library and the download engine; Coil loader with video thumbnails |
| `MainActivity.kt` | Bottom navigation (Home / Browser / Download / Files), share-intent and clipboard handling |
| `HomeScreen.kt` | Search box, copied-link card, site shortcuts (custom ones saved in prefs), how-to |
| `Browser.kt` | The single long-lived WebView, media sniffing, IDM-style "which video is playing" detection, YouTube PO-token capture, `UiBus` event bus |
| `BrowserScreen.kt` | Address bar, page, pulsing ⬇ button |
| `QualitySheet.kt` | Bottom sheet: preview, Video/Audio options with sizes, rename, playlist switch, errors |
| `Downloads.kt` | Engine: `loadInfo` (yt-dlp `-J`), quality list, queue (3 parallel), retries, error messages, DRM list |
| `DownloadService.kt` / `Notifications.kt` | Foreground service + progress/complete notifications |
| `Storage.kt` | Saves finished files to `Download/MediaDownloader` (MediaStore) |
| `Library.kt` | Finished-file history (JSON) and the PIN-locked private vault |
| `FilesScreen.kt` | Video / Audio / Private lists, PIN pad |
| `PlayerActivity.kt` | Built-in Media3 ExoPlayer |
| `Cookies.kt` | Exports WebView cookies (and imported cookies.txt) into a private cookies file per run |
| `SettingsScreen.kt` | Site logins, cookies import, yt-dlp update, what can't be downloaded |
| `Ui.kt` | Theme/colours, thumbnail widget, formatting helpers |

## Video detection in the browser (`Browser.detect()`)
1. Ask the page (JavaScript) for the playing or most-visible `<video>`: its source, poster,
   nearby post link and caption.
2. Facebook: use the post link, or the video id inside the CDN link's `efg` parameter
   (`video_id` / `xpv_asset_id`) → `facebook.com/watch/?v=ID`.
3. Pages that are themselves one video (YouTube watch/shorts, reels, tweets…) → the page URL.
4. Otherwise the post link, then the `<video>` file itself, then the newest media request.
Byte-range parameters (`bytestart`, `byteend`, `range`…) are stripped so pieces become one file.

## YouTube
YouTube needs a "PO token". While a video plays in the built-in browser, its `videoplayback`
requests carry `pot=…` for that video; it is stored per video id and passed as
`--extractor-args youtube:player_client=mweb;po_token=mweb.gvs+TOKEN` together with the browser's
cookies. Then the default client and fallbacks (`tv_simply,web_safari,mweb`, `android_vr,web_embedded,tv`)
are tried. If YouTube still blocks: switch Wi-Fi/mobile data or log in to YouTube in the browser.

## Not possible
DRM services (Netflix, Prime Video, Disney+/Hotstar, Hoichoi, Chorki, Spotify…) — the app shows an
explanation instead of trying.

## Building & releasing
- Push to `main` → GitHub Actions builds `arm64-v8a`, `armeabi-v7a`, `x86_64` APKs and publishes a Release.
- Version code = 100 + build number.
- Signed with the committed `app/release.jks` (password `mediadownloader`) so updates install over the old app.

## Known limitations / ideas
- Not yet tested on many phones; YouTube behaviour depends on network.
- No WhatsApp status saver yet.
- Pieces of DASH-only streams without a page link (rare) download as video-only.
