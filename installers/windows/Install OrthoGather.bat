@echo off
setlocal EnableExtensions EnableDelayedExpansion
title OrthoGather Installer (Windows)

REM ============================================================================
REM  OrthoGather - one-click installer for Windows.
REM
REM  OrthoFinder has no native Windows build, so OrthoGather runs inside WSL
REM  (the lightweight Linux that Windows ships). This installer:
REM    1) installs WSL + Ubuntu if missing  (needs admin + one restart)
REM    2) inside Linux: installs Miniforge, the app, Python 3.11, OrthoFinder
REM    3) puts an "OrthoGather" launcher on your Desktop
REM
REM  Just double-click this file. If Windows shows a SmartScreen warning,
REM  click "More info" -> "Run anyway".
REM ============================================================================

REM ---- Self-elevate to Administrator (required by `wsl --install`) ----------
net session >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "OGZIP=https://github.com/CarlosVivasR/OrthoGather/archive/refs/heads/main.zip"

echo ============================================================
echo    OrthoGather installer for Windows
echo ============================================================
echo.
echo OrthoFinder only runs on Linux, so OrthoGather runs inside WSL
echo (a small Linux that Windows provides). Setting that up for you.
echo.

REM ---- Is WSL present with a distro? ----------------------------------------
set "HASWSL="
wsl --status >nul 2>&1 && set "HASWSL=1"
set "HASDISTRO="
for /f "usebackq delims=" %%d in (`wsl -l -q 2^>nul`) do if not "%%d"=="" set "HASDISTRO=1"

if not defined HASWSL    goto install_wsl
if not defined HASDISTRO goto install_wsl
goto phase2

:install_wsl
echo WSL is not ready yet. Installing WSL + Ubuntu (this requires a RESTART)...
echo.
wsl --install --distribution Ubuntu
REM Resume this installer automatically after the reboot:
powershell -NoProfile -Command "New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'OrthoGatherSetup' -Value ('\"' + '%~f0' + '\"') -PropertyType String -Force | Out-Null"
echo.
echo ============================================================
echo   WSL installed.  Please RESTART your computer now.
echo   After the restart this installer continues automatically.
echo   (Ubuntu may ask you to pick a username + password the first
echo    time it opens - choose a simple one and remember it.)
echo ============================================================
echo.
pause
exit /b

:phase2
echo WSL is ready. Installing OrthoGather inside Linux...
echo (first run downloads Python, OrthoFinder and dependencies - a few minutes)
echo.
REM Run the Linux setup script as root (no extra prompts). It downloads the app,
REM installs Miniforge + the conda env with OrthoFinder, and writes a launcher.
wsl -u root -- bash -lc "apt-get update -y && apt-get install -y curl && curl -fsSL --retry 6 --retry-delay 4 --retry-connrefused 'https://raw.githubusercontent.com/CarlosVivasR/OrthoGather/main/installers/common/setup_linux_env.sh' -o /tmp/og_setup.sh && bash /tmp/og_setup.sh"
if %errorlevel% NEQ 0 (
  echo.
  echo *** Setup failed inside WSL. See the messages above. ***
  pause
  exit /b 1
)

REM ---- Create the launcher + an icon'd Desktop shortcut --------------------
REM Put the runner .bat and the logo .ico in a per-user app folder, then make a
REM Desktop shortcut (.lnk) that points to it and shows the OrthoGather logo.
set "OGHOME=%LOCALAPPDATA%\OrthoGather"
if not exist "%OGHOME%" mkdir "%OGHOME%"

REM Copy the logo from inside WSL to Windows (best-effort; falls back to no icon).
set "OGICON=%OGHOME%\OrthoGather.ico"
copy /Y "\\wsl.localhost\Ubuntu\root\OrthoGather\installers\assets\OrthoGather.ico" "%OGICON%" >nul 2>&1
if not exist "%OGICON%" copy /Y "\\wsl$\Ubuntu\root\OrthoGather\installers\assets\OrthoGather.ico" "%OGICON%" >nul 2>&1

REM The actual runner: starts the app in WSL on a fixed port, opens the browser.
set "RUNNER=%OGHOME%\OrthoGather-run.bat"
> "%RUNNER%" echo @echo off
>> "%RUNNER%" echo title OrthoGather
>> "%RUNNER%" echo echo Starting OrthoGather... a browser tab opens in a few seconds.
>> "%RUNNER%" echo start "" /b wsl -u root -- bash -lc "ORTHOGATHER_PORT=5000 ORTHOGATHER_NO_BROWSER=1 ~/OrthoGather/run_orthogather.sh"
>> "%RUNNER%" echo timeout /t 12 /nobreak ^>nul
>> "%RUNNER%" echo start "" http://localhost:5000
>> "%RUNNER%" echo echo OrthoGather is running. Close this window to stop it.
>> "%RUNNER%" echo pause ^>nul

REM Desktop shortcut with the logo icon (falls back to default icon if .ico missing).
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'OrthoGather.lnk'));" ^
  "$s.TargetPath='%RUNNER%'; $s.WorkingDirectory='%OGHOME%';" ^
  "if (Test-Path '%OGICON%') { $s.IconLocation='%OGICON%' };" ^
  "$s.Description='Launch OrthoGather'; $s.Save()"

REM Clean up the resume key if it was set.
powershell -NoProfile -Command "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'OrthoGatherSetup' -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo ============================================================
echo   OrthoGather installed!
echo   Double-click "OrthoGather" on your Desktop (with the logo) to start it.
echo ============================================================
echo.
pause
exit /b
