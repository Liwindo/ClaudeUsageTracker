; Inno Setup script for the C# variant.
;
; Payload is the framework-dependent single-file publish (publish\fdd): the
; installer stays ~5 MB and instead detects the .NET Desktop Runtime 10 at
; install time, downloading the official runtime installer if it is missing.
; (The portable download covers the "no dependencies at all" case.)
;
; Runtime detection is done on the file system, NOT via the registry: the
; HKLM\SOFTWARE\dotnet\Setup\InstalledVersions key is only written by some
; install channels and was absent on a machine that demonstrably had 10.0.10.
;
; Build:  ISCC.exe /DMyAppVersion=2.0.0 ClaudeUsageTracker.iss
; (build-release.ps1 does this with the version read from the csproj.)

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef PayloadDir
  #define PayloadDir "..\publish\fdd"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

#define MyAppName "Claude Usage Tracker"
; The EXE keeps the CS suffix on purpose: it is the process-level identity that
; separates this variant from the Python ClaudeUsageTracker.exe (uninstall
; taskkill, autostart Run value, process lists). Display names stay plain.
#define MyAppExeName "ClaudeUsageTrackerCS.exe"
#define MyAppPublisher "Liwindo"
#define MyAppURL "https://github.com/Liwindo/ClaudeUsageTracker"
#define DotNetURL "https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe"
#define DotNetPage "https://dotnet.microsoft.com/download/dotnet/10.0"

[Setup]
; Never change AppId — upgrades match on it.
AppId={{9E3D8B0C-5A71-4F2E-B6D4-1C7F30A9E5D2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
; Per-user install: no UAC, {autopf} resolves to %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=ClaudeUsageTracker-Setup-{#MyAppVersion}
SetupIconFile=..\ClaudeUsageTracker\Assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english";  MessagesFile: "compiler:Default.isl"
Name: "german";   MessagesFile: "compiler:Languages\German.isl"
Name: "spanish";  MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french";   MessagesFile: "compiler:Languages\French.isl"
Name: "italian";  MessagesFile: "compiler:Languages\Italian.isl"
Name: "dutch";    MessagesFile: "compiler:Languages\Dutch.isl"
Name: "polish";   MessagesFile: "compiler:Languages\Polish.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "russian";  MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
AutostartTask=Start automatically when you sign in to Windows
german.AutostartTask=Automatisch beim Anmelden an Windows starten
spanish.AutostartTask=Iniciar automáticamente al iniciar sesión en Windows
french.AutostartTask=Démarrer automatiquement à l'ouverture de session Windows
italian.AutostartTask=Avvia automaticamente all'accesso a Windows
dutch.AutostartTask=Automatisch starten bij aanmelden bij Windows
polish.AutostartTask=Uruchamiaj automatycznie po zalogowaniu do systemu Windows
portuguese.AutostartTask=Iniciar automaticamente ao entrar no Windows
russian.AutostartTask=Запускать автоматически при входе в Windows
DotNetFailed=The .NET Desktop Runtime 10 could not be installed. %1 will not start without it.%nYou can install it manually from:%n%2
german.DotNetFailed=Die .NET Desktop Runtime 10 konnte nicht installiert werden. %1 startet ohne sie nicht.%nManuelle Installation:%n%2
spanish.DotNetFailed=No se pudo instalar el runtime de escritorio de .NET 10. %1 no se iniciará sin él.%nInstalación manual:%n%2
french.DotNetFailed=Le runtime .NET Desktop 10 n'a pas pu être installé. %1 ne démarrera pas sans lui.%nInstallation manuelle :%n%2
italian.DotNetFailed=Impossibile installare il runtime desktop .NET 10. %1 non si avvierà senza di esso.%nInstallazione manuale:%n%2
dutch.DotNetFailed=De .NET Desktop Runtime 10 kon niet worden geïnstalleerd. %1 start niet zonder deze runtime.%nHandmatige installatie:%n%2
polish.DotNetFailed=Nie udało się zainstalować środowiska .NET Desktop Runtime 10. %1 nie uruchomi się bez niego.%nInstalacja ręczna:%n%2
portuguese.DotNetFailed=Não foi possível instalar o .NET Desktop Runtime 10. O %1 não iniciará sem ele.%nInstalação manual:%n%2
russian.DotNetFailed=Не удалось установить .NET Desktop Runtime 10. %1 не запустится без него.%nУстановить вручную:%n%2

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
; The AppUserModelID gives the app a shell identity (future toast support).
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "Liwindo.ClaudeUsageTrackerCS"

[Registry]
; Autostart entry; the app itself keeps it in sync with its config afterwards.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClaudeUsageTrackerCS"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#MyAppExeName}"; Flags: runhidden skipifdoesntexist; RunOnceId: "KillTracker"

[Code]
var
  DownloadPage: TDownloadWizardPage;

function DirHasDesktopRuntime10(const DotnetRoot: String): Boolean;
var
  FR: TFindRec;
begin
  Result := False;
  if FindFirst(DotnetRoot + '\shared\Microsoft.WindowsDesktop.App\10.*', FR) then
  begin
    try
      repeat
        if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          Result := True;
          break;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

function RuntimeInstalled: Boolean;
begin
  Result := DirHasDesktopRuntime10(ExpandConstant('{commonpf64}\dotnet'));
  if (not Result) and (GetEnv('DOTNET_ROOT') <> '') then
    Result := DirHasDesktopRuntime10(GetEnv('DOTNET_ROOT'));
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing),
    SetupMessage(msgPreparingDesc), nil);
end;

procedure ReportRuntimeFailure;
var
  ErrorCode: Integer;
begin
  MsgBox(FmtMessage(CustomMessage('DotNetFailed'), ['{#MyAppName}', '{#DotNetPage}']),
    mbError, MB_OK);
  ShellExec('open', '{#DotNetPage}', '', '', SW_SHOW, ewNoWait, ErrorCode);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if (CurPageID = wpReady) and (not RuntimeInstalled) then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#DotNetURL}', 'windowsdesktop-runtime.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        // The Microsoft installer elevates itself (UAC prompt).
        if not Exec(ExpandConstant('{tmp}\windowsdesktop-runtime.exe'),
          '/install /quiet /norestart', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
          ResultCode := 1;
      except
        ResultCode := 1;
      end;
    finally
      DownloadPage.Hide;
    end;
    // 3010 = success, reboot required — fine for a runtime.
    if (not RuntimeInstalled) and (ResultCode <> 0) and (ResultCode <> 3010) then
      ReportRuntimeFailure;
    // Install the app regardless: it will run once the runtime is present.
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigFile: String;
begin
  // Seed autostart=true into a fresh config so the app's own registry sync
  // (which mirrors the config on every start) keeps the task's Run entry.
  // An existing config is the user's — never touch it.
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('autostart') then
  begin
    ConfigDir := ExpandConstant('{userappdata}\claude-usage-tracker-cs');
    ConfigFile := ConfigDir + '\config.toml';
    if not FileExists(ConfigFile) then
    begin
      ForceDirectories(ConfigDir);
      SaveStringToFile(ConfigFile, 'autostart = true' + #13#10, False);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // The app re-creates the Run entry itself when config says autostart=true,
  // so remove it on uninstall even when the task-created one was replaced.
  // Config/log under %APPDATA%\claude-usage-tracker-cs are left in place.
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'ClaudeUsageTrackerCS');
end;
