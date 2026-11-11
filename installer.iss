; Установщик «Трекер привычек» (Inno Setup 6)
; Собирается автоматически в GitHub Actions, вручную: ISCC.exe installer.iss (после build_exe.bat)

#define AppName "Трекер привычек"
#define AppExe "HabitTracker.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B2C3E1A-4D7F-4C55-9A1E-7F0D2B8C9A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Habit Tracker
DefaultDirName={localappdata}\Programs\HabitTracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; установка без прав администратора — в профиль пользователя
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=HabitTracker-Setup
SetupIconFile=build\habit.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Значок на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "autostart"; Description: "Запускать вместе с Windows (свёрнуто, чтобы трекер был доступен с телефона)"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\habit.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\habit.ico"
Name: "{group}\{#AppName} для iPhone (Wi-Fi)"; Filename: "{app}\{#AppExe}"; Parameters: "--lan"; IconFilename: "{app}\habit.ico"
Name: "{group}\Папка с данными"; Filename: "{localappdata}\HabitTracker"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\habit.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--lan --no-browser"; IconFilename: "{app}\habit.ico"; Flags: runminimized; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; данные пользователя (%LOCALAPPDATA%\HabitTracker) при удалении сохраняются
