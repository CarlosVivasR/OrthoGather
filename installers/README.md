# Installers

This folder contains the scripts that install OrthoGather without the command line on macOS and
Windows, and the guided scripts for the Conda route. Instructions for users are in the
installation guide ([PDF](../docs/Installation_guide.pdf), [web page](https://carlosvivasr.github.io/OrthoGather/INSTALL.html)); this
page describes the files for maintainers.

OrthoFinder 2.5.5 has no native Windows build, so on Windows OrthoGather runs inside the Windows
Subsystem for Linux (WSL), which the Windows installer sets up.

## Files

| Path | Platform | Purpose |
|------|----------|---------|
| `macos/Install OrthoGather.command` | macOS (Apple Silicon and Intel) | Installs Miniforge if missing, the application, the Conda environment with OrthoFinder, and an `OrthoGather.app` launcher on the Desktop and in `~/Applications`. Running it again updates an existing installation and keeps the data. |
| `windows/Install OrthoGather.bat` | Windows 10 version 2004 or later, Windows 11 | Requests administrator rights, installs WSL and Ubuntu (one restart), sets up OrthoGather inside Linux and creates a Desktop shortcut. Writes a log to `%LOCALAPPDATA%\OrthoGather\install-log.txt`. |
| `windows/OrthoGather-run.bat` | Windows | Launcher started by the Desktop shortcut. |
| `windows/Update OrthoGather.bat` | Windows | Updates an existing WSL installation to the latest version. |
| `windows/tests/test_installer_logic.bat` | Windows | Checks the `cmd.exe` logic of the installer; run by `.github/workflows/test-windows-installer.yml`. |
| `common/setup_linux_env.sh` | Linux, inside WSL | Linux-side setup (Miniforge, environment, application), used by the Windows installer. |
| `install_orthogather_mac.sh` | macOS | Guided Conda installation from a cloned repository; needs Conda. |
| `install_orthogather_wsl.sh` | WSL | Guided installation from a cloned repository; needs Micromamba and stops on native Linux. |
| `start_orthogather.sh`, `Start_Orthogather.command` | macOS, Linux | Launchers for a Conda installation; they expect the `orthogather` environment to exist. |
| `assets/` | All | Application icons (`OrthoGather.icns`, `OrthoGather.ico`) built from `OrthoGather-icon.svg` with `build_icons.sh`. |
| `packaging/build_installer_zips.sh` | All | Builds `Install-OrthoGather-Mac.zip` and `Install-OrthoGather-Windows.zip`, the release assets. |
| `packaging/build_macos_pkg.sh`, `packaging/orthogather.iss` | macOS, Windows | Drafts for signed native packages (`.pkg`, `.exe`). They need an Apple Developer ID and a code-signing certificate. |

## Releasing

1. Before tagging, update the version in `orthogather/config.py` (`ORTHOGATHER_VERSION`),
   `CITATION.cff` (`version`, `date-released`, `identifiers`), `.zenodo.json` (`version`) and
   `CHANGELOG.md`. Zenodo takes the version label of the archived record from `.zenodo.json`.
2. Build the zips with `packaging/build_installer_zips.sh`.
3. Attach both zips, and the PDF installation guide, to the GitHub release. The installation guide
   links to `releases/latest/download/Install-OrthoGather-Mac.zip` and `...-Windows.zip`, so they
   must be attached to the release marked as latest. Attach no `.json` or `.json.gz` file to a
   software release: the application's catalogue update check treats any such asset on a full
   release as a proteome catalogue.
4. The installers download the application from the branch set in `BRANCH` at the top of each
   script (currently `main`). To make them install a specific release instead:
   - in `macos/Install OrthoGather.command`, `common/setup_linux_env.sh` and
     `windows/Update OrthoGather.bat`, set `BRANCH` to the tag and change `refs/heads` to
     `refs/tags` in the download URL (`ZIP_URL`, or `ZIP` in `Update OrthoGather.bat`);
   - in `windows/Install OrthoGather.bat`, set `BRANCH` to the same tag; it downloads
     `setup_linux_env.sh` from that ref.

Proteome catalogue snapshots are published as separate releases with a `proteomes_list.json.gz`
asset. Publish them as full releases (the update check skips pre-releases), untick "Set as latest"
so the installer links keep pointing at the software release, and title them "Proteome catalogue
YYYY-MM-DD". Zenodo archives every release, so a catalogue release also appears as a version of the
software record, labelled with the version in `.zenodo.json`.

The installers are not signed, so macOS and Windows show a security warning on first use. Signed
packages would remove it; the drafts in `packaging/` are ready for when certificates are
available.

The Windows batch files are stored with LF line endings, and the zips built from them keep those
endings. Because `cmd.exe` can mis-parse labels in LF-only files, test the built Windows zip on a
real Windows machine before each release (see below).

## Testing the Windows installer

The GitHub Actions workflow checks only the installer logic. Before a release, test the full
installation on a real Windows machine:

1. On a fresh Windows 10 (version 2004 or later) or 11 without WSL, run `Install OrthoGather.bat`
   and approve the administrator prompt.
2. WSL is installed and the installer asks to restart.
3. After the restart, the installer should resume automatically. Check that it does, and that
   Ubuntu does not ask for a username or password.
4. The installation ends with "OrthoGather is installed!" and an OrthoGather shortcut on the
   Desktop.
5. The Desktop shortcut opens the application in the browser (by default at
   `http://127.0.0.1:5000`). Search for a species and run a small analysis.

Points that depend on the Windows build and are worth checking each time: whether the automatic
resume after the restart works, whether `wsl -u root` works before Ubuntu has been started for the
first time, and whether Ubuntu shows its first-run user prompt. If the installer does not resume,
running it again continues from where it stopped.
