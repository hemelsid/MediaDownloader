# Notes for AI assistants working on this repo

- This repo (`hemelsid/MediaDownloader`) is the single home of the Video Downloader app —
  Android (`app/`), PC/Windows (`desktop/`) and the browser button extension (`browser-extension/`).
  Each Release contains all of them.
  Commit and push every change here so the owner always has the latest code and APKs.
- After each change: update `CHANGELOG.md` (and `docs/HOW-IT-WORKS.md` if behaviour changed),
  push to `main`, wait for the "Build APK" workflow, and give the owner the new Release files.
- Keep phone and PC features in step where it makes sense (same engine ideas, same English wording).
- All in-app text must be plain English (no Banglish).
- Keep the committed signing key `app/release.jks`; changing it forces users to uninstall.
- Never put this app's code or build branches in other repos (e.g. Sathi.AI).
- The owner can't run builds locally; GitHub Actions is the build machine.
- Keep every APK: never delete a Release. Each build adds a new one; the newest is "Latest" and on top.
  Old test builds v0.1–v0.6 (made before this repo) are kept as pre-releases.
  To add an already-built APK, use the "Publish saved APK" workflow (`legacy-apk` branch).
- Talk to the owner in Bengali (Bangla script, not Banglish). The app itself stays in English.
