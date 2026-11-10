; Inno Setup script for ConvoHub-Setup.exe
; Build (after PyInstaller):  ISCC.exe /DAppVersion=0.1.0 packaging\convohub.iss
;
; - Per-user install (no admin rights): %LOCALAPPDATA%\Programs\ConvoHub
; - User data lives in %LOCALAPPDATA%\ConvoHub and is never touched by install/update.
;   Uninstall asks before deleting it.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{D0BFDFB6-8847-4A4F-B5F5-9141EA7645F8}
AppName=ConvoHub
AppVersion={#AppVersion}
AppVerName=ConvoHub {#AppVersion}
AppPublisher=ConvoHub (open source)
AppPublisherURL=https://github.com/KayPraktor/ConvoHub
AppSupportURL=https://github.com/KayPraktor/ConvoHub/issues
DefaultDirName={localappdata}\Programs\ConvoHub
DefaultGroupName=ConvoHub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=ConvoHub-Setup
SetupIconFile=..\convohub\static\icon.ico
UninstallDisplayIcon={app}\ConvoHub.exe
UninstallDisplayName=ConvoHub
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\ConvoHub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Old program files from a previous version (never the user data, which lives elsewhere).
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
; Remove the (by then empty) program folder; user data lives elsewhere and is handled in [Code].
Type: dirifempty; Name: "{app}"

[Icons]
Name: "{autoprograms}\ConvoHub\ConvoHub"; Filename: "{app}\ConvoHub.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\ConvoHub\Stop ConvoHub"; Filename: "{app}\ConvoHub.exe"; Parameters: "--stop"; WorkingDir: "{app}"; IconFilename: "{app}\ConvoHub.exe"
Name: "{autodesktop}\ConvoHub"; Filename: "{app}\ConvoHub.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ConvoHub.exe"; Description: "Start ConvoHub now"; Flags: nowait postinstall skipifsilent

[Code]
// Stop a running copy before files are replaced or removed (quietly, no pop-ups).
procedure StopRunningApp(const ExePath: String);
var
  ResultCode: Integer;
begin
  if FileExists(ExePath) then
    Exec(ExePath, '--stop --quiet', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp(ExpandConstant('{app}\ConvoHub.exe'));
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp(ExpandConstant('{app}\ConvoHub.exe'));
  Result := True;
end;

// Ask before deleting the user's library, backups and saved key. Default is "No".
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ConvoHub');
    if DirExists(DataDir) then
    begin
      if UninstallSilent() then
      begin
        // Scripted uninstall: keep the data unless /DELETEDATA=1 is given.
        if ExpandConstant('{param:DELETEDATA|0}') = '1' then
          DelTree(DataDir, True, True, True);
      end
      else if MsgBox('Also delete your ConvoHub data?' + #13#10 + #13#10 +
                     'This removes your conversation library, chats, backups and the saved OpenRouter key:' + #13#10 +
                     DataDir + #13#10 + #13#10 +
                     'Choose "No" to keep it (for example if you will install ConvoHub again).',
                     mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
