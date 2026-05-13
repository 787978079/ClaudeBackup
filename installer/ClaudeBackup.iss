; Inno Setup script for ClaudeBackup
; Build:   ISCC.exe installer\ClaudeBackup.iss     (from repo root)
; Output:  dist-installer\ClaudeBackup-Setup-v{version}.exe
;
; What this installer does:
;   1. Drops the PyInstaller --windowed bundle into "Program Files\ClaudeBackup\"
;   2. Optional Start Menu / desktop shortcuts
;   3. Optional post-install tasks: right-click context menu, daily Task Scheduler, login autostart
;   4. On uninstall: cleans up Task Scheduler / context menu / autostart;
;      asks whether to remove user data under %USERPROFILE%\.claude-backup\
;   5. Upgrade-mode aware: a newer install over an older one auto-uninstalls first
;
; All paths below are RELATIVE to this .iss file (Inno Setup resolves them
; from the script's directory), so the repo is portable.

#define MyAppName "ClaudeBackup"
#define MyAppVersion "0.2.3"
#define MyAppPublisher "787978079"
#define MyAppExeName "ClaudeBackup.exe"
#define MyAppURL "https://github.com/787978079/ClaudeBackup"
#define IconFile "..\claude_backup\gui\assets\icons\claudebackup.ico"
#define LicenseFile "..\LICENSE"

[Setup]
; A stable AppId so Inno Setup recognizes existing installs as the same app
AppId={{8C3A5D90-7E3C-4D3F-9C2A-CB1A2B3C4D5E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (c) 2026 787978079

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=..\dist-installer
OutputBaseFilename=ClaudeBackup-Setup-v{#MyAppVersion}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
SetupIconFile={#IconFile}
LicenseFile={#LicenseFile}
WizardImageStretch=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "contextmenu"; Description: "Add Explorer right-click menu (ClaudeBackup submenu on folders)"; GroupDescription: "Windows integration (recommended):"
Name: "autostart";   Description: "Start ClaudeBackup tray icon on login"; GroupDescription: "Windows integration (recommended):"
Name: "daily";       Description: "Register daily Task Scheduler (default 23:30)"; GroupDescription: "Windows integration (recommended):"

[Files]
Source: "..\dist\ClaudeBackup\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Optional CLI bundle if it was built — placed under {app}\cli\
Source: "..\dist\ClaudeBackup-cli\*"; DestDir: "{app}\cli"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Optional integrations — only run if user checked the matching task.
; These scripts are bundled in {app}\_internal\scripts (PyInstaller --add-data).
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\install-context-menu.ps1"""; \
    Tasks: contextmenu; Flags: runhidden; StatusMsg: "Adding Explorer right-click menu..."
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\install-autostart.ps1"""; \
    Tasks: autostart; Flags: runhidden; StatusMsg: "Configuring login autostart..."
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\install-task-scheduler.ps1"""; \
    Tasks: daily; Flags: runhidden; StatusMsg: "Registering daily backup task..."
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Always try to undo integrations on uninstall (idempotent — script noop if not installed)
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\uninstall-context-menu.ps1"""; \
    RunOnceId: "RemoveContextMenu"; Flags: runhidden
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\uninstall-autostart.ps1"""; \
    RunOnceId: "RemoveAutostart"; Flags: runhidden
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\_internal\scripts\uninstall-task-scheduler.ps1"""; \
    RunOnceId: "RemoveDailyTask"; Flags: runhidden

[Code]
// Ask the user (during uninstall) whether to also wipe user data.
// NOTE: Inno Setup's [Code] section runs in the uninstaller's own context, so
//       %USERPROFILE% gets resolved per-user at uninstall time.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataPath: String;
  Reply: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataPath := ExpandConstant('{userappdata}\..\.claude-backup');
    if DirExists(DataPath) then
    begin
      Reply := MsgBox(
        'Also remove user data under:' + #13#10 + DataPath + #13#10#13#10 +
        '(This contains your project list, logs, and onboarding state. ' +
        'Backup data in the NAS / external folder you picked is NOT touched.)',
        mbConfirmation, MB_YESNO);
      if Reply = IDYES then
        DelTree(DataPath, True, True, True);
    end;
  end;
end;
