@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ===========================================================================
REM  Validates the risky cmd.exe logic of Install OrthoGather.bat on REAL
REM  Windows (GitHub Actions windows-latest). Exits 1 if any assertion fails.
REM  Snippets are kept identical to the installer so the test is meaningful.
REM  NOTE: assertion labels must contain NO cmd special chars (no > < ^| ^& parens).
REM ===========================================================================
set "FAILS=0"
set "TESTS=0"
set "TMP=%TEMP%\og_installer_test"
if exist "%TMP%" rd /s /q "%TMP%" >nul 2>&1
mkdir "%TMP%" >nul 2>&1
goto :main

:check
set /a TESTS+=1
if "%~2"=="%~3" (
  echo [PASS] %~1  got "%~2"
) else (
  echo [FAIL] %~1  expected "%~3" got "%~2"
  set /a FAILS+=1
)
exit /b 0

:retzero
exit /b 0
:retone
exit /b 1

:feat_decision
REM Mirrors :ensure_feature decision: %1=FSTATE %2=dism-rc -> OUTCOME
set "OUTCOME=?"
if /i "%~1"=="Enabled"       ( set "OUTCOME=skip"     & exit /b 0 )
if /i "%~1"=="EnablePending" ( set "OUTCOME=reboot"   & exit /b 0 )
if "%~2"=="0"                ( set "OUTCOME=noreboot" & exit /b 0 )
if "%~2"=="3010"             ( set "OUTCOME=reboot"   & exit /b 0 )
set "OUTCOME=fail"
exit /b 0

:main
echo ============================================================
echo  Install OrthoGather.bat logic tests - real Windows cmd.exe
echo ============================================================

echo.
echo -- Group 1: state-file read plus phase routing --
> "%TMP%\state.txt" echo phase=post_features
>> "%TMP%\state.txt" echo attempts=2
set "PHASE=preflight"
set "ATTEMPTS=0"
for /f "usebackq tokens=1,2 delims==" %%A in ("%TMP%\state.txt") do (
  if /i "%%A"=="phase"    set "PHASE=%%B"
  if /i "%%A"=="attempts" set "ATTEMPTS=%%B"
)
call :check "state phase parsed"    "!PHASE!"    "post_features"
call :check "state attempts parsed" "!ATTEMPTS!" "2"
set "ROUTE=preflight"
if /i "!PHASE!"=="post_features" set "ROUTE=post_features"
if /i "!PHASE!"=="phase2"        set "ROUTE=phase2"
call :check "phase routing" "!ROUTE!" "post_features"

echo.
echo -- Group 2: dism feature-state parse mocked deterministic --
> "%TMP%\dism_en.txt" echo Feature Information:
>> "%TMP%\dism_en.txt" echo Feature Name : VirtualMachinePlatform
>> "%TMP%\dism_en.txt" echo State : Enabled
set "FSTATE="
for /f "usebackq tokens=1,* delims=:" %%S in (`type "%TMP%\dism_en.txt" ^| find /i "State :"`) do set "FSTATE=%%T"
set "FSTATE=!FSTATE: =!"
call :check "dism parse yields Enabled" "!FSTATE!" "Enabled"

> "%TMP%\dism_dis.txt" echo Feature Name : Foo
>> "%TMP%\dism_dis.txt" echo State : Disabled
set "FSTATE="
for /f "usebackq tokens=1,* delims=:" %%S in (`type "%TMP%\dism_dis.txt" ^| find /i "State :"`) do set "FSTATE=%%T"
set "FSTATE=!FSTATE: =!"
call :check "dism parse yields Disabled" "!FSTATE!" "Disabled"

echo.
echo -- Group 3: dism feature-state parse REAL dism on this runner --
set "RSTATE="
for /f "usebackq tokens=1,* delims=:" %%S in (`dism /online /get-featureinfo /featurename:VirtualMachinePlatform 2^>nul ^| find /i "State :"`) do set "RSTATE=%%T"
set "RSTATE=!RSTATE: =!"
echo   real dism reported state: "!RSTATE!"
set "RSTATE_OK=no"
if /i "!RSTATE!"=="Enabled"  set "RSTATE_OK=yes"
if /i "!RSTATE!"=="Disabled" set "RSTATE_OK=yes"
if /i "!RSTATE!"=="DisabledWithPayloadRemoved" set "RSTATE_OK=yes"
call :check "real dism yields a known state" "!RSTATE_OK!" "yes"

echo.
echo -- Group 4: control flow with call plus or-else --
set "TRIG=no"
call :retone || set "TRIG=yes"
call :check "or-else triggers on nonzero exit" "!TRIG!" "yes"
set "TRIG=no"
call :retzero || set "TRIG=yes"
call :check "or-else skips on zero exit" "!TRIG!" "no"

echo.
echo -- Group 5: attempt cap plus delayed-expansion retry loop --
set "ATT=2"
set /a ATT+=1
set "CAPPED=no"
if !ATT! GEQ 3 set "CAPPED=yes"
call :check "attempt cap fires at 3" "!CAPPED!" "yes"
set "GOT="
set "N=0"
for /l %%I in (1,1,8) do (
  if not defined GOT (
    set /a N+=1
    if !N! GEQ 3 set "GOT=1"
  )
)
call :check "retry loop stops at 3 via if-not-defined" "!N!" "3"

echo.
echo -- Group 6: real environment detection commands --
set "WINBUILD="
for /f "usebackq delims=" %%B in (`powershell -NoProfile -Command "[System.Environment]::OSVersion.Version.Build" 2^>nul`) do set "WINBUILD=%%B"
echo   Windows build detected: "!WINBUILD!"
set "BUILD_OK=no"
if defined WINBUILD if !WINBUILD! GEQ 19041 set "BUILD_OK=yes"
call :check "windows build detected and at least 19041" "!BUILD_OK!" "yes"

set "VIRT=unknown"
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "try { $c=Get-CimInstance Win32_ComputerSystem; $p=Get-CimInstance Win32_Processor; if ($c.HypervisorPresent -or ($p | ForEach-Object { $_.VirtualizationFirmwareEnabled }) -contains $true) { 'on' } else { 'off' } } catch { 'unknown' }"`) do set "VIRT=%%V"
echo   virtualization detected: "!VIRT!"
set "VIRT_OK=no"
if /i "!VIRT!"=="on"      set "VIRT_OK=yes"
if /i "!VIRT!"=="off"     set "VIRT_OK=yes"
if /i "!VIRT!"=="unknown" set "VIRT_OK=yes"
call :check "virtualization detection returns a known token" "!VIRT_OK!" "yes"

echo.
echo -- Group 7: write_state round-trip --
> "%TMP%\st2.txt" echo phase=phase2
>> "%TMP%\st2.txt" echo attempts=1
set "P2="
for /f "usebackq tokens=1,2 delims==" %%A in ("%TMP%\st2.txt") do if /i "%%A"=="phase" set "P2=%%B"
call :check "write_state round-trip" "!P2!" "phase2"

echo.
echo -- Group 8: ensure_feature decision logic --
set "X= Enable Pending"
set "X=!X: =!"
call :check "Enable Pending strips to EnablePending" "!X!" "EnablePending"
call :feat_decision "Enabled" ""
call :check "state Enabled means skip" "!OUTCOME!" "skip"
call :feat_decision "EnablePending" ""
call :check "state EnablePending means reboot" "!OUTCOME!" "reboot"
call :feat_decision "Disabled" "0"
call :check "dism rc 0 means no reboot" "!OUTCOME!" "noreboot"
call :feat_decision "Disabled" "3010"
call :check "dism rc 3010 means reboot" "!OUTCOME!" "reboot"
call :feat_decision "Disabled" "87"
call :check "dism rc other means fail" "!OUTCOME!" "fail"

echo.
echo -- Group 9: exact-zero error check (WSL returns negative codes) --
REM WSL exits with a NEGATIVE code when the distro is missing; 'if errorlevel 1'
REM misses that. Verify the exact-zero check catches negative AND positive fails.
cmd /c exit -1
set "RC=!errorlevel!"
echo   simulated wsl-missing exit code: "!RC!"
set "CAUGHT=no"
if not "!RC!"=="0" set "CAUGHT=yes"
call :check "exact-zero check catches negative code" "!CAUGHT!" "yes"
cmd /c exit 5
set "RC=!errorlevel!"
set "CAUGHT=no"
if not "!RC!"=="0" set "CAUGHT=yes"
call :check "exact-zero check catches positive code" "!CAUGHT!" "yes"
cmd /c exit 0
set "RC=!errorlevel!"
set "OKZERO=no"
if "!RC!"=="0" set "OKZERO=yes"
call :check "exact-zero check passes on success" "!OKZERO!" "yes"

echo.
echo ============================================================
echo  RESULT: !TESTS! tests, !FAILS! failures
echo ============================================================
if !FAILS! GTR 0 exit /b 1
exit /b 0
