@echo off
setlocal EnableExtensions EnableDelayedExpansion
title OrthoGather Installer (Windows)

REM ============================================================================
REM  OrthoGather - robust one-click installer for Windows.
REM
REM  OrthoFinder has no native Windows build, so OrthoGather runs inside WSL2
REM  (a small Linux that Windows provides). This installer is designed to be
REM  autonomous and transparent: it checks each requirement, fixes what it can
REM  by itself, explains clearly what to do for the few things it cannot fix
REM  (like enabling virtualization in the BIOS), survives the one reboot WSL
REM  needs, and writes a full log so you always know what happened.
REM
REM  Just double-click this file. If Windows shows a SmartScreen warning,
REM  click "More info" -> "Run anyway".
REM ============================================================================

set "REPO=CarlosVivasR/OrthoGather"
set "BRANCH=main"
set "SETUP_URL=https://raw.githubusercontent.com/%REPO%/%BRANCH%/installers/common/setup_linux_env.sh"
set "OGHOME=%LOCALAPPDATA%\OrthoGather"
set "LOG=%OGHOME%\install-log.txt"
set "STATE=%OGHOME%\install_state.txt"
set "SELF=%~f0"
set "TOTAL=7"
set "MAXATTEMPTS=3"

if not exist "%OGHOME%" mkdir "%OGHOME%" >nul 2>&1

REM ---- Self-elevate to Administrator (needed for dism + wsl --install) --------
REM RunOnce resumes run NON-elevated, so this also re-elevates on resume. The
REM state file persists across the elevation hop, so we continue where we were.
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator permission ^(a Windows prompt will appear^)...
  powershell -NoProfile -Command "try { Start-Process -FilePath '%SELF%' -Verb RunAs -ErrorAction Stop } catch { exit 1 }" >nul 2>&1
  if errorlevel 1 (
    echo.
    echo   Administrator access was not granted, so setup cannot continue.
    echo   Please run this installer again and choose YES on the permission prompt.
    echo   ^(Your progress is saved - it will pick up where it left off.^)
    echo.
    pause
  )
  exit /b
)

REM ---- Begin transcript ------------------------------------------------------
>>"%LOG%" echo(
>>"%LOG%" echo ==================================================================
>>"%LOG%" echo  OrthoGather install run: %DATE% %TIME%
>>"%LOG%" echo ==================================================================

REM ---- Read resume state -----------------------------------------------------
set "PHASE=preflight"
set "ATTEMPTS=0"
if exist "%STATE%" (
  for /f "usebackq tokens=1,2 delims==" %%A in ("%STATE%") do (
    if /i "%%A"=="phase"    set "PHASE=%%B"
    if /i "%%A"=="attempts" set "ATTEMPTS=%%B"
  )
)

cls
call :banner "OrthoGather installer for Windows"
echo   OrthoFinder only runs on Linux, so OrthoGather sets up a small Linux
echo   ^(WSL2 + Ubuntu^) inside Windows. This is automatic.
echo.
echo   A full log is saved here in case you ever need it:
echo     %LOG%
echo.

if not "!PHASE!"=="preflight" (
  call :log "Resuming at phase !PHASE! (attempt !ATTEMPTS!)."
  echo   Welcome back - continuing where the install left off...
  echo.
)

REM ---- Route by phase (resume support) ---------------------------------------
if /i "!PHASE!"=="post_features" goto post_features
if /i "!PHASE!"=="phase2"        goto phase2
goto preflight


REM ###########################################################################
REM  PHASE: PREFLIGHT - check the things we cannot fix ourselves
REM ###########################################################################
:preflight
call :step 1 "Checking your Windows is ready"

REM --- Windows build must support 'wsl --install' (Win10 2004 / build 19041+) -
set "WINBUILD="
for /f "usebackq delims=" %%B in (`powershell -NoProfile -Command "[System.Environment]::OSVersion.Version.Build" 2^>nul`) do set "WINBUILD=%%B"
call :log "Windows build: !WINBUILD!"
if defined WINBUILD (
  if !WINBUILD! LSS 19041 (
    call :fail "Your Windows is too old for the automatic Linux setup." "OrthoGather needs Windows 10 version 2004 (2020) or newer, or Windows 11. Please run Windows Update, then run this installer again."
    goto :eof
  )
  call :ok "Windows version is fine (build !WINBUILD!)."
) else (
  call :log "Could not read the Windows build number; continuing anyway."
  call :ok "Windows version check skipped (will be caught later if unsupported)."
)

REM --- CPU virtualization must be available (BIOS/firmware) - CANNOT auto-fix --
REM Usable if the hypervisor is already present OR firmware virtualization is on.
set "VIRT=unknown"
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "try { $c=Get-CimInstance Win32_ComputerSystem; $p=Get-CimInstance Win32_Processor; if ($c.HypervisorPresent -or ($p | ForEach-Object { $_.VirtualizationFirmwareEnabled }) -contains $true) { 'on' } else { 'off' } } catch { 'unknown' }"`) do set "VIRT=%%V"
call :log "Virtualization firmware/hypervisor: !VIRT!"
if /i "!VIRT!"=="off" (
  call :banner "Action needed: turn on virtualization"
  echo   OrthoGather needs "virtualization" enabled in your computer's BIOS.
  echo   It's off right now, and this is the ONE thing an installer cannot turn
  echo   on for you. It's quick and safe:
  echo.
  echo     1^) Restart the PC and open the BIOS/UEFI ^(usually tapping F2, F10,
  echo        DEL or ESC right as it powers on - your make/model varies^).
  echo     2^) Find a setting called "Virtualization Technology", "Intel VT-x",
  echo        "AMD-V" or "SVM Mode" and set it to ENABLED.
  echo     3^) Save and exit, let Windows start, then run this installer again.
  echo.
  call :log "ABORT: firmware virtualization disabled."
  call :halt 2
  goto :eof
)
call :ok "Virtualization is available."


REM ###########################################################################
REM  PHASE: FEATURES - enable the Windows components WSL2 needs (auto)
REM ###########################################################################
call :step 2 "Turning on the Windows components for Linux"

set "NEEDREBOOT="
call :ensure_feature "Microsoft-Windows-Subsystem-Linux" || goto :eof
call :ensure_feature "VirtualMachinePlatform" || goto :eof

if defined NEEDREBOOT (
  REM Persist where to resume, guard against endless reboot loops.
  set /a ATTEMPTS+=1
  if !ATTEMPTS! GEQ %MAXATTEMPTS% (
    call :fail "Setup needed several restarts but isn't finishing." "Please restart your PC once manually and run this installer again. If it keeps happening, send Carlos the log file: %LOG%"
    goto :eof
  )
  call :write_state "post_features" "!ATTEMPTS!"
  call :set_runonce
  call :banner "Almost there - a restart is needed"
  echo   Windows turned on the Linux components, but they only activate after a
  echo   RESTART. Don't worry - after you restart, this installer opens again by
  echo   itself and keeps going. You don't have to do anything else.
  echo.
  choice /C YN /N /M "   Restart now? Press Y to restart, or N to restart later yourself: "
  if errorlevel 2 (
    echo.
    echo   OK - please restart your PC yourself, then it continues automatically.
    call :log "User chose manual restart."
    call :halt 0
    goto :eof
  )
  call :log "Auto-restart in 8 seconds."
  echo.
  echo   Restarting in 8 seconds... ^(close this window to cancel^)
  shutdown /r /t 8 /c "OrthoGather: restarting to finish the Linux setup." >nul 2>&1
  goto :eof
)
call :ok "Windows components are on."


REM ###########################################################################
REM  PHASE: POST_FEATURES - update WSL, ensure Ubuntu, verify health (auto)
REM ###########################################################################
:post_features
call :log "Entering post_features."

REM --- Make sure the WSL engine itself is present and up to date ---------------
call :step 3 "Updating the Linux engine (WSL)"
REM After a reboot the network may not be ready yet; wait up to ~30s so the
REM update/downloads below don't fail on a cold boot.
for /l %%I in (1,1,10) do (
  ping -n 1 8.8.8.8 >nul 2>&1 && goto :net_ready
  ping -n 3 127.0.0.1 >nul
)
:net_ready
wsl --update >>"%LOG%" 2>&1
REM 'wsl --update' returns non-zero when already up to date on some builds; not fatal.
call :log "wsl --update finished (rc=!errorlevel!) - non-fatal."
wsl --set-default-version 2 >>"%LOG%" 2>&1
call :ok "Linux engine ready."

REM --- Ensure Ubuntu is installed AND healthy (can actually run) ---------------
call :step 4 "Setting up Ubuntu Linux"
call :ubuntu_healthy
if defined UBUNTU_OK (
  call :ok "Ubuntu is already installed and working."
) else (
  call :log "Ubuntu not healthy yet; installing with --no-launch (no username prompt)."
  echo   Installing Ubuntu... this can take a few minutes and download ~500 MB.
  REM --no-launch avoids the interactive username/password screen entirely; we
  REM run everything as root, so no user account is needed.
  wsl --install --distribution Ubuntu --no-launch >>"%LOG%" 2>&1
  set "RC=!errorlevel!"
  call :log "wsl --install Ubuntu rc=!RC!"

  REM Give the new distro a few moments, then re-check health with retries.
  set "UBUNTU_OK="
  for /l %%I in (1,1,12) do (
    if not defined UBUNTU_OK (
      call :ubuntu_healthy
      if not defined UBUNTU_OK ping -n 3 127.0.0.1 >nul
    )
  )
  if not defined UBUNTU_OK (
    REM One self-heal attempt: a fresh 'wsl --update' fixes many E_UNEXPECTED cases.
    call :log "Ubuntu still not healthy; trying 'wsl --update' self-heal."
    wsl --update >>"%LOG%" 2>&1
    call :ubuntu_healthy
  )
  if not defined UBUNTU_OK (
    call :diagnose_wsl
    goto :eof
  )
  call :ok "Ubuntu installed and working."
)

REM Features are on and Ubuntu is healthy - advance the resume marker.
call :write_state "phase2" "!ATTEMPTS!"


REM ###########################################################################
REM  PHASE: PHASE2 - install the app + environment inside Ubuntu
REM ###########################################################################
:phase2
call :step 5 "Installing OrthoGather inside Linux"
echo   Downloading Python, OrthoFinder and dependencies. The first time this
echo   moves ~1-2 GB and takes about 5-15 minutes. It will look frozen at times
echo   - that's normal. Please leave this window open.
echo.
call :log "Running Linux setup script."
wsl -d Ubuntu -u root -- bash -c "apt-get update -y && apt-get install -y curl && curl -fsSL --retry 6 --retry-delay 4 --retry-connrefused '%SETUP_URL%' -o /tmp/og_setup.sh && bash /tmp/og_setup.sh"
REM Check for EXACTLY 0: wsl returns negative codes that 'if errorlevel 1' misses.
set "SETUP_RC=!errorlevel!"
call :log "phase2 setup rc=!SETUP_RC!"
if not "!SETUP_RC!"=="0" (
  call :fail "The Linux setup step didn't finish (code !SETUP_RC!)." "Usually a dropped internet connection, or Ubuntu wasn't ready. Just run this installer again - it resumes from here. If it keeps failing, send Carlos the log: %LOG%"
  goto :eof
)
call :ok "OrthoGather installed inside Linux."


REM ###########################################################################
REM  PHASE: FINISH - build the launcher + Desktop shortcut
REM ###########################################################################
call :step 6 "Creating your OrthoGather shortcut"
set "OGICON=%OGHOME%\OrthoGather.ico"
copy /Y "\\wsl.localhost\Ubuntu\root\OrthoGather\installers\assets\OrthoGather.ico" "%OGICON%" >nul 2>&1
if not exist "%OGICON%" copy /Y "\\wsl$\Ubuntu\root\OrthoGather\installers\assets\OrthoGather.ico" "%OGICON%" >nul 2>&1

set "RUNNER=%OGHOME%\OrthoGather-run.bat"
copy /Y "\\wsl.localhost\Ubuntu\root\OrthoGather\installers\windows\OrthoGather-run.bat" "%RUNNER%" >nul 2>&1
if not exist "%RUNNER%" copy /Y "\\wsl$\Ubuntu\root\OrthoGather\installers\windows\OrthoGather-run.bat" "%RUNNER%" >nul 2>&1
if not exist "%RUNNER%" (
  call :log "Runner copy failed; writing minimal fallback runner."
  > "%RUNNER%" echo @echo off
  >> "%RUNNER%" echo title OrthoGather
  >> "%RUNNER%" echo echo Starting OrthoGather... a browser tab opens in a few seconds.
  >> "%RUNNER%" echo start "" /b wsl -d Ubuntu -u root -- bash -lc "ORTHOGATHER_PORT=5000 ORTHOGATHER_NO_BROWSER=1 ~/OrthoGather/run_orthogather.sh"
  >> "%RUNNER%" echo timeout /t 12 /nobreak ^>nul
  >> "%RUNNER%" echo start "" "http://localhost:5000"
  >> "%RUNNER%" echo echo OrthoGather is running. Close this window to stop it.
  >> "%RUNNER%" echo pause ^>nul
)

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'OrthoGather.lnk'));" ^
  "$s.TargetPath='%RUNNER%'; $s.WorkingDirectory='%OGHOME%';" ^
  "if (Test-Path '%OGICON%') { $s.IconLocation='%OGICON%' };" ^
  "$s.Description='Launch OrthoGather'; $s.Save()" >>"%LOG%" 2>&1
call :ok "Shortcut created on your Desktop."

call :step 7 "Finishing up"
call :clear_runonce
del "%STATE%" >nul 2>&1
call :log "Install completed successfully."

call :banner "OrthoGather is installed!"
echo   Double-click "OrthoGather" on your Desktop ^(with the logo^) to start it.
echo   The first time you open it, it appears in your web browser.
echo.
pause
exit /b 0


REM ###########################################################################
REM  SUBROUTINES
REM ###########################################################################

:banner
echo.
echo ============================================================
echo   %~1
echo ============================================================
>>"%LOG%" echo [banner] %~1
exit /b 0

:step
REM :step <n> <text>
echo.
echo --- Step %~1 of %TOTAL%: %~2 ---
>>"%LOG%" echo [step %~1/%TOTAL%] %~2
exit /b 0

:ok
echo   [OK] %~1
>>"%LOG%" echo [ok] %~1
exit /b 0

:log
>>"%LOG%" echo [log] %~1
exit /b 0

:fail
REM :fail <headline> <what-to-do>
echo.
echo ============================================================
echo   Something needs your attention
echo ============================================================
echo   %~1
echo.
echo   %~2
echo.
echo   ^(A full log is saved at: %LOG% ^)
echo.
>>"%LOG%" echo [FAIL] %~1 : %~2
pause
exit /b 1

:halt
REM :halt <exitcode> - pause then exit without the scary "fail" framing
echo.
pause
exit /b %~1

:write_state
REM :write_state <phase> <attempts>
> "%STATE%" echo phase=%~1
>> "%STATE%" echo attempts=%~2
>>"%LOG%" echo [state] phase=%~1 attempts=%~2
exit /b 0

:set_runonce
REM Use 'cmd /c "<path>"' because RunOnce runs via CreateProcess, which does NOT
REM honour the .bat file association - a bare .bat path would silently not run.
powershell -NoProfile -Command "New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'OrthoGatherSetup' -Value ('cmd /c \"' + '%SELF%' + '\"') -PropertyType String -Force | Out-Null" >>"%LOG%" 2>&1
exit /b 0

:clear_runonce
powershell -NoProfile -Command "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'OrthoGatherSetup' -ErrorAction SilentlyContinue" >>"%LOG%" 2>&1
exit /b 0

:ensure_feature
REM :ensure_feature <FeatureName> - enable if disabled; set NEEDREBOOT only when a reboot is actually required.
set "FEAT=%~1"
set "FSTATE="
REM /english forces the English "State : ..." label so parsing works on any Windows language.
for /f "usebackq tokens=1,* delims=:" %%S in (`dism /online /get-featureinfo /featurename:%FEAT% /english 2^>nul ^| find /i "State :"`) do set "FSTATE=%%T"
set "FSTATE=!FSTATE: =!"
call :log "Feature %FEAT% state=!FSTATE!"
if /i "!FSTATE!"=="Enabled" exit /b 0
REM Already staged by another pending operation - it only needs the reboot.
if /i "!FSTATE!"=="EnablePending" ( set "NEEDREBOOT=1" & exit /b 0 )
echo   Turning on Windows feature: %FEAT% ...
dism /online /enable-feature /featurename:%FEAT% /all /norestart >>"%LOG%" 2>&1
set "DRC=!errorlevel!"
call :log "dism enable %FEAT% rc=!DRC!"
REM dism: 0 = enabled, no reboot needed; 3010 = enabled, reboot required; else = error.
if "!DRC!"=="0"    exit /b 0
if "!DRC!"=="3010" ( set "NEEDREBOOT=1" & exit /b 0 )
call :fail "Couldn't turn on the Windows feature '%FEAT%'." "Please open 'Turn Windows features on or off', tick 'Windows Subsystem for Linux' and 'Virtual Machine Platform', click OK, restart, and run this installer again. Log: %LOG%"
exit /b 1

:ubuntu_healthy
REM Sets UBUNTU_OK=1 only if Ubuntu is installed AND can actually run a command.
REM wsl.exe returns a NEGATIVE exit code when the distro is missing, and cmd's
REM 'if errorlevel 1' does NOT catch negatives - so require the code to be EXACTLY 0.
set "UBUNTU_OK="
wsl -d Ubuntu -u root -- true >nul 2>&1
if "!errorlevel!"=="0" set "UBUNTU_OK=1"
exit /b 0

:diagnose_wsl
REM Ubuntu couldn't start - translate the most likely causes into plain guidance.
call :log "diagnose_wsl: Ubuntu unhealthy after install+update."
call :banner "Linux couldn't start - here's what to check"
echo   Ubuntu was set up but couldn't start. The usual reasons, in order:
echo.
echo   1^) VIRTUALIZATION in the BIOS is off. Even if Windows looked fine, some
echo      PCs need it turned on in the BIOS ^(look for "Virtualization
echo      Technology" / "Intel VT-x" / "AMD-V" / "SVM" and ENABLE it^).
echo   2^) A restart is still pending - please restart the PC and run this again.
echo   3^) WSL needs a manual nudge: open Terminal ^(Admin^) and run:
echo         wsl --update
echo      then restart and run this installer again.
echo.
echo   If none of that helps, send Carlos this log file:
echo     %LOG%
echo.
>>"%LOG%" echo [FAIL] Ubuntu unhealthy - see diagnose_wsl guidance.
pause
exit /b 1
