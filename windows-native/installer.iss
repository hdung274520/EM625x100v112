; Inno Setup script: dist\NplayAIM.exe -> dist\NplayAIM-Setup-<version>.exe
; Per-user install (no admin rights needed).  Build: ISCC.exe installer.iss

#define AppName "Nplay AIM"
#define AppVersion "1.0.0"
#define AppExe "Nplay AIM.exe"

[Setup]
AppId={{6E2B6C1A-4F0D-4C7B-9C55-0E1A6D2B5A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Nplay AIM (community)
DefaultDirName={localappdata}\Programs\NplayAIM
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=NplayAIM-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình nền"; Flags: unchecked
Name: "autostart"; Description: "Chạy nền khi đăng nhập Windows (icon khay, báo DPI, cảnh báo pin)"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app's "Chạy nền khi đăng nhập Windows" menu toggles; removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --background"; Tasks: autostart; \
  Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#AppName}"; \
  Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Mở {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/f /im {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"
