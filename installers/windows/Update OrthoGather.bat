@echo off
title Update OrthoGather (Windows)
setlocal

REM ===========================================================================
REM  OrthoGather - lightweight UPDATER for Windows (WSL installs).
REM
REM  Double-click this to update OrthoGather to the latest published version.
REM  Inside WSL it replaces the app code (~/OrthoGather) and brings the conda
REM  environment to the versions that release was tested with. It does NOT:
REM    - reinstall WSL or ask for admin, and
REM    - it never touches your data (analyses, history, downloaded proteomes,
REM      GO files) - those live in ignored folders the update leaves alone.
REM
REM  Keep this file handy: run it again whenever there is a new version.
REM ===========================================================================

set "REPO=CarlosVivasR/OrthoGather"

REM --- The update comes from the latest published release (a vX.Y.Z tag), not
REM     from the tip of main; FALLBACK_TAG is used only if GitHub's release list
REM     cannot be read. ----------------------------------------------------------
set "FALLBACK_TAG=v2.2.0"

echo(
echo   ============================================================
echo      Updating OrthoGather to the latest version
echo      (your analyses and settings are kept; this can take
echo       a few minutes if the environment changed)
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
wsl -d Ubuntu -u root -- bash -lc "set -e; if [ ! -d /root/OrthoGather ]; then echo 'OrthoGather is not installed yet - please run the installer first.'; exit 1; fi; TAG=$(curl -fsSL --retry 3 'https://api.github.com/repos/%REPO%/releases?per_page=30' | grep -o 'tag_name.: *.v[0-9][0-9.]*' | grep -o 'v[0-9][0-9.]*$' | head -1); TAG=${TAG:-%FALLBACK_TAG%}; echo == Updating to OrthoGather $TAG, your data is preserved...; curl -fsSL --retry 6 --retry-delay 4 --retry-connrefused https://raw.githubusercontent.com/%REPO%/$TAG/installers/common/setup_linux_env.sh -o /tmp/og_setup.sh; ORTHOGATHER_REF=$TAG bash /tmp/og_setup.sh; echo == Done."

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
