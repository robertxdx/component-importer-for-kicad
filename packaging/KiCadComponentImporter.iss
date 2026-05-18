#define MyAppName "KiCad Component Importer"
#define MyAppExeName "KiCadComponentImporter.exe"

#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

#ifndef SourceDir
#define SourceDir "..\\dist\\KiCadComponentImporter"
#endif

#ifndef OutputDir
#define OutputDir "..\\installer"
#endif

[Setup]
AppId={{3E2489DF-7A97-4A21-A47A-4D03BD37F8F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=RTR Tech Labs
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=KiCadComponentImporter_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\gui_assets\app_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
