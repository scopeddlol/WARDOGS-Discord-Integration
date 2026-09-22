#define AppVersion "1.0.0"
[Setup]
AppId={{481B894A-0BE2-4BCE-9247-EAA721A4DC48}
AppName=WARDOGS Discord
AppVersion={#AppVersion}
AppPublisher=WARDOGS Discord contributors
AppPublisherURL=https://github.com/scopeddlol/WARDOGS-Discord-Integration
DefaultDirName={localappdata}\Programs\WARDOGS Discord
DefaultGroupName=WARDOGS Discord
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=WARDOGS-Discord-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\WARDOGS Discord.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
CloseApplicationsFilter=WARDOGS Discord.exe
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\WARDOGS Discord\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WARDOGS Discord"; Filename: "{app}\WARDOGS Discord.exe"
Name: "{autodesktop}\WARDOGS Discord"; Filename: "{app}\WARDOGS Discord.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WARDOGS Discord.exe"; Description: "Open WARDOGS Discord"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "WARDOGSDiscord"; Flags: uninsdeletevalue

; Per-user settings are deliberately retained on uninstall, including the DPAPI-encrypted
; token. See docs/SETUP.md for the explicit reset/remove-data procedure.
