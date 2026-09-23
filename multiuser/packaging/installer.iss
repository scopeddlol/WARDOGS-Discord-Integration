#define AppVersion "1.0.0"
[Setup]
AppId={{713DE43D-6FC3-47E3-A552-F21D0988F580}
AppName=WARDOGS Agent
AppVersion={#AppVersion}
AppPublisher=WARDOGS Agent contributors
AppPublisherURL=https://github.com/scopeddlol/WARDOGS-Discord-Integration
DefaultDirName={localappdata}\Programs\WARDOGS Agent
DefaultGroupName=WARDOGS Agent
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=WARDOGS-Agent-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\WARDOGS Agent.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
CloseApplicationsFilter=WARDOGS Agent.exe
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\WARDOGS Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WARDOGS Agent"; Filename: "{app}\WARDOGS Agent.exe"
Name: "{autodesktop}\WARDOGS Agent"; Filename: "{app}\WARDOGS Agent.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WARDOGS Agent.exe"; Description: "Open WARDOGS Agent"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "WARDOGSAgent"; Flags: uninsdeletevalue

; Per-user settings are deliberately retained on uninstall, including the DPAPI-encrypted
; token. See docs/AGENT.md for the settings location and pairing reset.
