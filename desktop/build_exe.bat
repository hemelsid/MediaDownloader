@echo off
echo Installing build tools...
python -m pip install -U yt-dlp pyinstaller
echo Building MediaDownloader.exe ...
python -m PyInstaller --onefile --windowed --name MediaDownloader --collect-submodules yt_dlp media_downloader.py
if exist ffmpeg.exe copy /Y ffmpeg.exe dist\ffmpeg.exe >nul
echo.
echo Done! Open the "dist" folder. Keep ffmpeg.exe next to MediaDownloader.exe.
pause
