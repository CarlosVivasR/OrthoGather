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

set "OGZIP=https://github.com/CarlosVivasR/OrthoGather/archive/refs/heads/refactor/post-review.zip"

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
wsl -u root -- bash -lc "apt-get update -y && apt-get install -y curl unzip rsync >/dev/null && curl -fsSL '%OGZIP%' -o /tmp/og.zip && rm -rf /tmp/og_src && mkdir -p /tmp/og_src && unzip -q /tmp/og.zip -d /tmp/og_src && SRC=$(find /tmp/og_src -maxdepth 1 -type d -name 'OrthoGather-*' | head -1) && OG_SRC=\"$SRC\" bash \"$SRC/installers/common/setup_linux_env.sh\""
if %errorlevel% NEQ 0 (
  echo.
  echo *** Setup failed inside WSL. See the messages above. ***
  pause
  exit /b 1
)

REM ---- Create the Desktop launcher -----------------------------------------
REM Starts the app inside WSL on a fixed port, then opens the Windows browser.
set "LAUNCHER=%USERPROFILE%\Desktop\OrthoGather.bat"
> "%LAUNCHER%" echo @echo off
>> "%LAUNCHER%" echo title OrthoGather
>> "%LAUNCHER%" echo echo Starting OrthoGather... a browser tab opens in a few seconds.
>> "%LAUNCHER%" echo start "" /b wsl -u root -- bash -lc "ORTHOGATHER_PORT=5000 ORTHOGATHER_NO_BROWSER=1 ~/OrthoGather/run_orthogather.sh"
>> "%LAUNCHER%" echo timeout /t 12 /nobreak ^>nul
>> "%LAUNCHER%" echo start "" http://localhost:5000
>> "%LAUNCHER%" echo echo OrthoGather is running. Close this window to stop it.
>> "%LAUNCHER%" echo pause ^>nul

REM Clean up the resume key if it was set.
powershell -NoProfile -Command "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'OrthoGatherSetup' -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo ============================================================
echo   OrthoGather installed!
echo   Double-click "OrthoGather" on your Desktop to start it.
echo ============================================================
echo.
pause
exit /b
