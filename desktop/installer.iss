; Windows installer for the PC app. Built by GitHub Actions with Inno Setup.
; Installs per-user (no admin needed) so the download engine can update itself.

#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppId={{6E3F2C1A-6B2D-4E8B-9F4C-5A1D0B7C9E21}
AppName=Video Downloader
AppVersion={#AppVersion}
AppPublisher=hemelsid
AppPublisherURL=https://github.com/hemelsid/MediaDownloader
DefaultDirName={localappdata}\Programs\Video Downloader
DefaultGroupName=Video Downloader
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\out
OutputBaseFilename=VideoDownloader-Windows-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\VideoDownloader.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\VideoDownloader\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Registry]
; videodownloader:// links — lets the browser button open the app with a video when the app is closed
Root: HKCU; Subkey: "Software\Classes\videodownloader"; ValueType: string; ValueName: ""; ValueData: "URL:Video Downloader"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\videodownloader"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\videodownloader\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\VideoDownloader.exe,0"
Root: HKCU; Subkey: "Software\Classes\videodownloader\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\VideoDownloader.exe"" ""%1"""

; start with Windows, quietly in the tray (can be turned off in the app's Settings)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "VideoDownloader"; ValueData: """{app}\VideoDownloader.exe"" --background"; Flags: uninsdeletevalue
; the app registers itself so the browser extension can start it (native messaging) — removed on uninstall
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.hemelsid.videodownloader"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\com.hemelsid.videodownloader"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.hemelsid.videodownloader"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Chromium\NativeMessagingHosts\com.hemelsid.videodownloader"; Flags: uninsdeletekey dontcreatekey
Root: HKCU; Subkey: "Software\Vivaldi\NativeMessagingHosts\com.hemelsid.videodownloader"; Flags: uninsdeletekey dontcreatekey

[Icons]
Name: "{group}\Video Downloader"; Filename: "{app}\VideoDownloader.exe"; AppUserModelID: "hemelsid.VideoDownloader"
Name: "{group}\Uninstall Video Downloader"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Video Downloader"; Filename: "{app}\VideoDownloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VideoDownloader.exe"; Description: "Open Video Downloader"; Flags: nowait postinstall skipifsilent
