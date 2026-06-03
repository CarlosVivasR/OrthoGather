# OrthoGather installers

One-click installers for non-technical users. They install **everything**
(package manager, the app, Python 3.11, OrthoFinder, a Desktop launcher) so the
user never touches a terminal.

> **Why Windows needs WSL:** OrthoFinder 2.5.5 has no native Windows build, so on
> Windows OrthoGather runs inside **WSL** (the Linux that Windows ships). The
> Windows installer sets that up automatically.

## Files

| Path | Platform | What it is |
|------|----------|------------|
| `macos/Install OrthoGather.command` | macOS (Apple Silicon + Intel) | Double-click. Installs Miniforge (if missing), the app, the conda env + OrthoFinder, and a branded **`OrthoGather.app`** (logo icon, no Terminal window) on the Desktop + in Applications. |
| `windows/Install OrthoGather.bat` | Windows 10 2004+ / 11 | Double-click. Self-elevates, installs WSL + Ubuntu (one restart), sets up everything inside Linux, and creates a **Desktop shortcut with the OrthoGather logo**. |
| `common/setup_linux_env.sh` | Linux / inside WSL | The Linux-side setup (Miniforge + env + app). Reused by the Windows installer; also works on a plain Linux box. |
| `assets/` | — | App icon (`OrthoGather.icns` for macOS, `OrthoGather.ico` for Windows) built from `OrthoGather-icon.svg` via `build_icons.sh`. |
| `packaging/build_macos_pkg.sh` | macOS | **Phase B** scaffold — wrap the `.command` into a signed `.pkg` (needs an Apple Developer ID). |
| `packaging/orthogather.iss` | Windows | **Phase B** scaffold — wrap the `.bat` into a signed `OrthoGather-Setup.exe` via Inno Setup (needs a code-signing cert). |

## Two-phase rollout

- **Phase A (these scripts) — ready now, no certificates.** Distribute the
  `.command` and `.bat` as **GitHub Release assets**. Users download one file and
  double-click. macOS/Windows may show a one-time Gatekeeper/SmartScreen warning
  (right-click → Open / "More info → Run anyway").
- **Phase B — signed native packages.** Once you have signing certificates, use
  `packaging/` to produce a signed `.pkg` and `.exe` that install without
  warnings. The certs are the only blocker (they can't be scripted away).

## Configuration

Both scripts download the app from a GitHub URL set at the top of each file
(`BRANCH` / `OGZIP`). Currently they point at `main`. **When you
merge to `main` or cut a versioned app release, update that ref** so installers
pull the right code.

## Windows test checklist (please run on a real Windows machine — I can't test it here)

1. Fresh Windows 10 (2004+) or 11, no WSL. Double-click `Install OrthoGather.bat`.
2. Approve the admin prompt. WSL installs → installer asks you to **restart**.
3. After restart, the installer **resumes automatically** (RunOnce). If Ubuntu
   prompts for a username/password the first time, set a simple one.
4. Watch it download the app + build the env (a few minutes). It ends with
   "OrthoGather installed!" and an `OrthoGather` shortcut on the Desktop.
5. Double-click the Desktop `OrthoGather` → a browser opens at
   `http://localhost:5000` with the app. Search a species, run a small analysis.
6. Report back which step (if any) failed, with the on-screen message.

Known uncertainties to watch for (Windows-only, untested by the author):
the Ubuntu first-run user prompt, whether `wsl -u root` works before that prompt,
and whether the RunOnce resume fires reliably on your Windows build.
