@echo off
setlocal EnableExtensions EnableDelayedExpansion
title OrthoGather

REM ===========================================================================
REM  OrthoGather launcher (Windows).
REM
REM  Started by the Desktop shortcut. It:
REM    1) if OrthoGather is already running, just reopens it (no second copy);
REM    2) otherwise picks a port that is free ON THE WINDOWS SIDE, launches the
REM       app inside Ubuntu (WSL) on that port, and opens it in the browser.
REM
REM  Why check the port on the WINDOWS side? In WSL2's default (NAT) networking,
REM  the app inside Linux can't see ports used by Windows programs. If a Windows
REM  app already holds 5000, the Linux app would bind 5000 happily but Windows
REM  localhost:5000 wouldn't reach it. So we choose the port here, on Windows.
REM ===========================================================================

echo Starting OrthoGather...

REM The app (running inside Ubuntu as root => home is /root) advertises its real
REM port here. Two ways Windows can reach WSL files; try modern path then legacy.
set "PORTFILE=\\wsl.localhost\Ubuntu\root\.orthogather\port.txt"
set "PORTFILE2=\\wsl$\Ubuntu\root\.orthogather\port.txt"

REM ---- Step 1: is OrthoGather already running from a previous launch? --------
REM Read the last advertised port and check something is actually answering as
REM OrthoGather there. If so, reopen it instead of starting a second instance.
set "EXIST="
if exist "%PORTFILE%"  set /p EXIST=<"%PORTFILE%"
if not defined EXIST if exist "%PORTFILE2%" set /p EXIST=<"%PORTFILE2%"
if not defined EXIST goto :launch
REM A blank port.txt leaves EXIST defined-but-empty (a set /p quirk) -> not running.
if "!EXIST!"=="" goto :launch
REM Non-numeric/garbage -> treat as not running.
for /f "delims=0123456789" %%c in ("!EXIST!") do goto :launch
curl -s -m 3 "http://localhost:!EXIST!" 2>nul | findstr /i "OrthoGather" >nul 2>&1
if errorlevel 1 goto :launch
echo OrthoGather is already running - reopening it in your browser.
start "" "http://localhost:!EXIST!"
goto :done_quiet

REM ---- Step 2: not running -> choose a Windows-free port and launch ----------
:launch
del "%PORTFILE%"  >nul 2>&1
del "%PORTFILE2%" >nul 2>&1

REM Find the first port from 5000 that nothing on Windows is using.
set "PORT=5000"
:findport
netstat -an | find ":!PORT! " >nul 2>&1
if not errorlevel 1 (
  set /a PORT+=1
  if !PORT! GTR 5100 ( set "PORT=5000" & goto :gotport )
  goto :findport
)
:gotport

REM Launch the app inside Ubuntu on that port. -d Ubuntu pins the distro so this
REM works even if the user's default WSL distro is something other than Ubuntu.
start "" /b wsl -d Ubuntu -u root -- bash -lc "ORTHOGATHER_PORT=!PORT! ORTHOGATHER_NO_BROWSER=1 ~/OrthoGather/run_orthogather.sh"

REM The app normally binds the port we chose. If that port happened to be busy
REM INSIDE Linux too (rare), the app moves to a free one and writes the real
REM value to port.txt - prefer that. Poll up to ~60s for cold starts.
set "REALPORT="
for /l %%i in (1,1,60) do (
  if not defined REALPORT (
    if exist "%PORTFILE%"  set /p REALPORT=<"%PORTFILE%"
    if not defined REALPORT if exist "%PORTFILE2%" set /p REALPORT=<"%PORTFILE2%"
    if not defined REALPORT ping -n 2 127.0.0.1 >nul
  )
)

REM Validate it's numeric; otherwise fall back to the port we picked above.
set "BAD="
if not defined REALPORT set "BAD=1"
REM Blank port.txt leaves REALPORT defined-but-empty -> also invalid.
if "!REALPORT!"=="" set "BAD=1"
if defined REALPORT for /f "delims=0123456789" %%c in ("!REALPORT!") do set "BAD=1"
if defined BAD (
  echo.
  echo Could not confirm the app's port automatically - using !PORT!.
  echo If the page does not load, the app may have failed to start: scroll up in
  echo this window to look for an error message.
  set "REALPORT=!PORT!"
)

echo Opening OrthoGather at http://localhost:!REALPORT!
start "" "http://localhost:!REALPORT!"
echo.
echo OrthoGather is running. Close this window to stop it.
pause >nul
endlocal
goto :eof

:done_quiet
REM Already-running path: this window is just a relauncher, closing it must not
REM stop the real instance, so exit straight away.
endlocal
goto :eof
