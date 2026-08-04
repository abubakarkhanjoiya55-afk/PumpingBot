; SceneCut Pro+ — Inno Setup script (built by GitHub Actions on Windows)
#define MyAppName "SceneCut Pro+"
#define MyAppVersion "1.5.5"
#define MyAppPublisher "SceneCut"
#define MyAppExeName "SceneCutProPlus.exe"

[Setup]
AppId={{8F3C2A11-9B4E-4D2F-9C1A-7E6D5C4B3A21}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\SceneCutProPlus
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\releases
OutputBaseFilename=SceneCutPro-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableWelcomePage=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "..\dist\SceneCutProPlus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Clear stale version marker so desktop never thinks an old broken install is "current"
[InstallDelete]
Type: files; Name: "{app}\.scenecut_version"
Type: files; Name: "{localappdata}\SceneCutProPlus\.scenecut_version"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
