; Inno Setup script for the C# variant.
;
; Payload is the framework-dependent single-file publish (publish\fdd): the
; installer stays ~5 MB and instead detects the .NET Desktop Runtime 10 at
; install time. If it is missing, the installer opens Microsoft's official,
; code-signed runtime download directly in the user's browser rather than
; fetching an EXE and running it elevated itself — Windows then enforces the
; Authenticode signature and shows Microsoft as the verified publisher on the
; user's own action. (The portable download covers the "no dependencies at all"
; case.)
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
; Direct aka.ms alias for the latest 10.0 Windows Desktop Runtime x64 installer —
; opening it drops the user straight onto the correct, Microsoft-signed download
; (no hunting on the overview page). The USER runs it, so Windows enforces the
; Authenticode signature; this installer never fetches and executes it itself.
#define DotNetDownloadUrl "https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe"
; Human-readable overview page, shown as a fallback link in the prompt.
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
DotNetRequired=%1 needs the .NET Desktop Runtime 10. The official Microsoft installer will now download in your browser — run it, then start %1.%nIf the download doesn't start, get it here:%n%2
german.DotNetRequired=%1 benötigt die .NET Desktop Runtime 10. Der offizielle Microsoft-Installer wird jetzt in Ihrem Browser heruntergeladen — führen Sie ihn aus und starten Sie dann %1.%nFalls der Download nicht startet, hier herunterladen:%n%2
spanish.DotNetRequired=%1 necesita .NET Desktop Runtime 10. El instalador oficial de Microsoft se descargará ahora en su navegador: ejecútelo y luego inicie %1.%nSi la descarga no comienza, obténgalo aquí:%n%2
french.DotNetRequired=%1 nécessite le .NET Desktop Runtime 10. Le programme d'installation officiel de Microsoft va être téléchargé dans votre navigateur — exécutez-le, puis démarrez %1.%nSi le téléchargement ne démarre pas, obtenez-le ici :%n%2
italian.DotNetRequired=%1 richiede .NET Desktop Runtime 10. Il programma di installazione ufficiale di Microsoft verrà ora scaricato nel browser: eseguilo, quindi avvia %1.%nSe il download non si avvia, scaricalo qui:%n%2
dutch.DotNetRequired=%1 heeft .NET Desktop Runtime 10 nodig. Het officiële Microsoft-installatieprogramma wordt nu in uw browser gedownload — voer het uit en start daarna %1.%nAls de download niet start, haal het hier op:%n%2
polish.DotNetRequired=%1 wymaga środowiska .NET Desktop Runtime 10. Oficjalny instalator Microsoft zostanie teraz pobrany w przeglądarce — uruchom go, a następnie uruchom %1.%nJeśli pobieranie się nie rozpocznie, pobierz go tutaj:%n%2
portuguese.DotNetRequired=O %1 precisa do .NET Desktop Runtime 10. O instalador oficial da Microsoft será baixado agora no seu navegador — execute-o e depois inicie o %1.%nSe o download não começar, obtenha-o aqui:%n%2
russian.DotNetRequired=Для %1 требуется .NET Desktop Runtime 10. Официальный установщик Microsoft сейчас загрузится в вашем браузере — запустите его, затем запустите %1.%nЕсли загрузка не началась, скачайте здесь:%n%2

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

// The runtime is installed by the USER from Microsoft's official, code-signed
// download page — this installer deliberately does NOT fetch an EXE and run it
// elevated itself. Downloading an executable and running it with admin rights
// without verifying its signature is the weak link this avoids: when the user
// installs the runtime from Microsoft's page, Windows enforces the Authenticode
// signature and shows "Microsoft Corporation" as the verified publisher on the
// UAC prompt. See REQUIREMENTS.md R-update-10.
procedure PromptInstallRuntime;
var
  ErrorCode: Integer;
begin
  MsgBox(FmtMessage(CustomMessage('DotNetRequired'), ['{#MyAppName}', '{#DotNetPage}']),
    mbInformation, MB_OK);
  // Open the direct aka.ms installer link so the correct, Microsoft-signed
  // runtime downloads immediately — no hunting on the overview page.
  ShellExec('open', '{#DotNetDownloadUrl}', '', '', SW_SHOW, ewNoWait, ErrorCode);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  // Point the user at Microsoft's official download page when the runtime is
  // missing, then install the app regardless (it starts once the runtime is
  // present).
  if (CurPageID = wpReady) and (not RuntimeInstalled) then
    PromptInstallRuntime;
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
