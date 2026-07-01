@echo off
title Update OrthoGather (Windows)
setlocal

REM ===========================================================================
REM  OrthoGather - lightweight UPDATER for Windows (WSL installs).
REM
REM  Double-click this to refresh OrthoGather to the latest version.
REM  It ONLY replaces the app code inside WSL (~/OrthoGather). It does NOT:
REM    - reinstall WSL, ask for admin, or rebuild the conda environment, and
REM    - it never touches your data (analyses, history, downloaded proteomes,
REM      GO files) - those live in ignored folders the update leaves alone.
REM
REM  Keep this file handy: run it again whenever there is a new version.
REM ===========================================================================

set "REPO=CarlosVivasR/OrthoGather"

REM --- Branch the update is pulled from. Change ONLY this line if updates ever
REM     ship from a different branch. -----------------------------------------
set "BRANCH=main"

set "ZIP=https://github.com/%REPO%/archive/refs/heads/%BRANCH%.zip"

echo(
echo   ============================================================
echo      Updating OrthoGather to the latest version
echo      (your analyses and settings are kept - only the app
echo       code is refreshed)
echo   ============================================================
echo(

REM --- Is WSL present? If not, they never installed OrthoGather. --------------
wsl --status >nul 2>&1
if errorlevel 1 (
  echo   OrthoGather does not look installed yet ^(WSL was not found^).
  echo   Please run "Install OrthoGather.bat" first.
  echo(
  pause
  exit /b 1
)

REM --- Do the update inside WSL, as root, matching the installer layout. ------
wsl -d Ubuntu -u root -- bash -lc "set -e; APP=/root/OrthoGather; if [ ! -d $APP ]; then echo 'OrthoGather is not installed yet - please run the installer first.'; exit 1; fi; echo '== Downloading the latest version...'; curl -fL --retry 6 --retry-delay 4 --retry-connrefused -o /tmp/og_update.zip '%ZIP%'; rm -rf /tmp/og_update && mkdir -p /tmp/og_update; unzip -q /tmp/og_update.zip -d /tmp/og_update; SRC=$(find /tmp/og_update -maxdepth 1 -type d -name 'OrthoGather-*' | head -1); if [ ! -d $SRC ]; then echo 'Unexpected download layout - aborting (nothing changed).'; exit 1; fi; echo '== Applying update (your data is preserved)...'; rsync -a --checksum $SRC/ $APP/ 2>/dev/null || cp -rf $SRC/. $APP/; rm -rf /tmp/og_update.zip /tmp/og_update; echo '== Done.'"

if errorlevel 1 (
  echo(
  echo   ------------------------------------------------------------
  echo   Something went wrong, but nothing was broken - your current
  echo   version still works. Please send Carlos a screenshot of this
  echo   window and try again later.
  echo   ------------------------------------------------------------
  echo(
  pause
  exit /b 1
)

echo(
echo   ============================================================
echo      OrthoGather is up to date.
echo      If it is open, close it and open it again.
echo   ============================================================
echo(
pause
endlocal
