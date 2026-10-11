; Build with Inno Setup 7 after packaging/build-windows.ps1.
#define ProjectRoot ExtractFileDir(ExtractFileDir(SourcePath))
#define Payload ProjectRoot + "\build\release\VideoDownloader-windows-x64"
#define Artwork ProjectRoot + "\build\windows"

[Setup]
AppId={{DD00B52D-B952-49DB-91EC-27C32DC3DA30}
AppName=VideoDownloader
AppVersion=1.0.0
AppPublisher=jotadev27
AppPublisherURL=https://github.com/jotadev27/Video-Downloader
AppSupportURL=https://github.com/jotadev27/Video-Downloader/issues
DefaultDirName={localappdata}\Programs\VideoDownloader
DefaultGroupName=VideoDownloader
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupArchitecture=x64
MinVersion=10.0
DisableWelcomePage=no
DisableProgramGroupPage=yes
WizardStyle=modern
WizardImageFile={#Artwork}\wizard-banner.bmp
WizardSmallImageFile={#Artwork}\wizard-logo.bmp
SetupIconFile={#Artwork}\VideoDownloader.ico
UninstallDisplayIcon={app}\VideoDownloader\VideoDownloader.exe
LicenseFile={#ProjectRoot}\LICENSE
OutputDir={#ProjectRoot}\installer
OutputBaseFilename=VideoDownloader-1.0.0-windows-x64-setup
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\*"

[Icons]
Name: "{userprograms}\VideoDownloader"; Filename: "{app}\VideoDownloader\VideoDownloader.exe"; WorkingDir: "{app}"; IconFilename: "{app}\VideoDownloader\VideoDownloader.exe"; AppUserModelID: "jotadev27.VideoDownloader"
Name: "{userdesktop}\VideoDownloader"; Filename: "{app}\VideoDownloader\VideoDownloader.exe"; WorkingDir: "{app}"; IconFilename: "{app}\VideoDownloader\VideoDownloader.exe"; AppUserModelID: "jotadev27.VideoDownloader"; Tasks: desktopicon

[Run]
Filename: "{app}\VideoDownloader\VideoDownloader.exe"; Description: "Launch VideoDownloader"; Flags: nowait postinstall skipifsilent
