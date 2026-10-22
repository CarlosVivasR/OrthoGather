# Installers

This folder contains the scripts that install OrthoGather without the command line on macOS and
Windows. Instructions for users are in the
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
| `windows/Update OrthoGather.bat` | Windows | Updates an existing WSL installation, and its Conda environment, to the latest release. |
| `windows/tests/test_installer_logic.bat` | Windows | Checks the `cmd.exe` logic of the installer; run by `.github/workflows/test-windows-installer.yml`. |
| `common/setup_linux_env.sh` | Linux, inside WSL | Linux-side setup (Miniforge, environment, application), used by the Windows installer. |
| `assets/` | All | Application icons (`OrthoGather.icns`, `OrthoGather.ico`) built from `OrthoGather-icon.svg` with `build_icons.sh`. |
| `packaging/build_installer_zips.sh` | All | Builds `Install-OrthoGather-Mac.zip` and `Install-OrthoGather-Windows.zip`, the release assets. |
| `packaging/build_macos_pkg.sh`, `packaging/orthogather.iss` | macOS, Windows | Drafts for signed native packages (`.pkg`, `.exe`). They need an Apple Developer ID and a code-signing certificate. |

## Releasing

The installers, and the Windows updater, install the latest published release: they read the tags
of GitHub's releases and download the newest `vX.Y.Z` (catalogue releases and other tags are
skipped). `FALLBACK_TAG`, at the top of each script, is used only if the release list cannot be
read, and `ORTHOGATHER_REF` installs another tag or a branch when testing (for example
`ORTHOGATHER_REF=main`). A version therefore reaches users only when its release is published.

1. On `main`, with the GitHub Actions checks passing, update the version in
   `orthogather/config.py` (`ORTHOGATHER_VERSION`), `CITATION.cff` (`version`, `date-released`),
   `.zenodo.json` (`version`), `CHANGELOG.md`, the badge of `docs/INSTALL.html`, the `--branch`
   tag of the clone commands in `README.md` and `docs/INSTALL.html`, and `FALLBACK_TAG` in
   `macos/Install OrthoGather.command`, `common/setup_linux_env.sh` and both Windows `.bat` files.
   Zenodo takes the version label of the archived record from `.zenodo.json`.
2. Run `pytest tests/` and `python docs/validation/verify_example.py` (35/35), and regenerate
   `docs/Installation_guide.pdf` from `docs/INSTALL.html` with
   `python tools/build_installation_guide.py` (it needs Google Chrome or Chromium).
3. Tag the commit `vX.Y.Z` and push the tag.
4. Build the zips with `packaging/build_installer_zips.sh` and publish a GitHub release from the
   tag, marked as latest, with both zips and the PDF installation guide attached. The installation
   guide links to `releases/latest/download/Install-OrthoGather-Mac.zip` and `...-Windows.zip`.
   Attach no `.json` or `.json.gz` file to a software release: the application's catalogue update
   check treats any such asset on a full release as a proteome catalogue.
5. Zenodo archives the release. Add the new version DOI to `CITATION.cff` (`identifiers`) and to
   the citation section of `README.md`.

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
