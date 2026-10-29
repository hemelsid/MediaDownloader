# Notes for AI assistants working on this repo

- This repo (`hemelsid/MediaDownloader`) is the single home of the Video Downloader app.
  Commit and push every change here so the owner always has the latest code and APKs.
- After each change: update `CHANGELOG.md` (and `docs/HOW-IT-WORKS.md` if behaviour changed),
  push to `main`, wait for the "Build APK" workflow, and give the owner the new Release APK.
- All in-app text must be plain English (no Banglish).
- Keep the committed signing key `app/release.jks`; changing it forces users to uninstall.
- Never put this app's code or build branches in other repos (e.g. Sathi.AI).
- The owner can't run builds locally; GitHub Actions is the build machine.
