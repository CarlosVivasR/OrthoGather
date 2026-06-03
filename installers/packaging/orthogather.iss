; ============================================================================
;  Phase B scaffold - Inno Setup script to wrap the Windows installer .bat
;  into a proper OrthoGather-Setup.exe (double-click, Add/Remove Programs entry).
;
;  Build it with Inno Setup (free): https://jrsoftware.org/isinfo.php
;    iscc orthogather.iss      ->  Output\OrthoGather-Setup.exe
;
;  For a warning-free .exe you must CODE-SIGN it (SmartScreen otherwise warns):
;    • Get an Authenticode code-signing certificate (OV ~ 200-400 EUR/yr,
;      or EV for instant SmartScreen reputation).
;    • Uncomment the SignTool lines below and configure signtool.exe.
;  Without signing it still builds and runs (users click "More info > Run anyway").
; ============================================================================

[Setup]
AppId={{B8E4F2A1-OG01-4C2D-9E3F-ORTHOGATHER}}
AppName=OrthoGather
AppVersion=2026.06.03
AppPublisher=UCD Conway Institute / UCD Cancer Data Lab
DefaultDirName={autopf}\OrthoGather
DisableProgramGroupPage=yes
OutputBaseFilename=OrthoGather-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
; SignTool=mysign   ; <- define in Tools > Configure Sign Tools, then uncomment

[Files]
; Ship the one-click .bat (and the Linux setup it pulls in is fetched at runtime).
Source: "..\windows\Install OrthoGather.bat"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; After the files are placed, run the bootstrap installer.
Filename: "{app}\Install OrthoGather.bat"; Description: "Set up OrthoGather (installs WSL + Linux env)"; Flags: shellexec runascurrentuser postinstall

[Messages]
WelcomeLabel2=This will set up OrthoGather. Because OrthoFinder runs on Linux, the installer enables WSL (Windows Subsystem for Linux) and may need ONE restart, after which it continues automatically.
