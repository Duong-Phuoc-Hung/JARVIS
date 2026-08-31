; JARVIS AI Assistant — Inno Setup Installer Script
; Tạo file cài đặt .exe chuyên nghiệp cho Windows
;
; Cách build (khuyến nghị): python scripts/build_installer.py
;   -- script này tự đọc jarvis.__version__ (nguồn phiên bản canonical) và
;      truyền vào ISCC qua /DAppVersion=..., không cần chỉnh sửa file này.
;
; Cách build thủ công (phải cung cấp AppVersion rõ ràng -- không có giá trị
; mặc định trong file này):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=4.1.0 installer\setup.iss
;
; File output: installer\JARVIS_Setup_v<AppVersion>.exe

#define AppName "JARVIS AI Assistant"
#ifndef AppVersion
  #error "AppVersion is not defined. Pass it explicitly: ISCC.exe /DAppVersion=<version> installer\setup.iss -- or build via 'python scripts/build_installer.py', which supplies it automatically from jarvis.__version__."
#endif
#define AppPublisher "Duong Phuoc Hung"
#define AppURL "https://github.com/Duong-Phuoc-Hung/JARVIS"
#define AppExeName "JARVIS.exe"
#define AppIcon "..\assets\jarvis_icon.ico"

[Setup]
AppId={{A7B3D9E2-4F1C-4A2B-8E5D-1234567890AB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\JARVIS
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=JARVIS_Setup_v{#AppVersion}
SetupIconFile={#AppIcon}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng Desktop"; GroupDescription: "Tùy chọn:"; Flags: unchecked
Name: "startmenushortcut"; Description: "Thêm vào Start Menu"; GroupDescription: "Tùy chọn:"
Name: "autostart"; Description: "Khởi động cùng Windows"; GroupDescription: "Tùy chọn:"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\jarvis_icon.ico"
Name: "{group}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\jarvis_icon.ico"; Tasks: desktopicon
Name: "{userstartmenu}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenushortcut

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Khởi động JARVIS ngay"; Flags: nowait postinstall skipifsilent

[Registry]
; Thêm vào autostart khi chọn task "autostart"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JARVIS"; ValueData: "{app}\{#AppExeName} --tray"; Tasks: autostart; Flags: uninsdeletevalue

; Thêm vào Programs & Features
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#AppPublisher}\{#AppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM JARVIS.exe"; Flags: runhidden; RunOnceId: "KillJARVIS"

[Code]
function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  // Kill existing JARVIS process if running
  Exec('taskkill', '/F /IM JARVIS.exe', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
end;
