#!/bin/bash
# ============================================================================
#  OrthoGather — one-click installer for macOS (Apple Silicon & Intel)
#
#  Double-click this file. It installs everything OrthoGather needs:
#    • Miniforge (conda) — only if you don't already have it
#    • the OrthoGather app (downloaded from GitHub, no git required)
#    • a conda environment with Python 3.11 + OrthoFinder 2.5.5 + dependencies
#    • a double-click launcher on your Desktop
#
#  Re-running it later UPDATES an existing install (keeps your data).
# ============================================================================
set -euo pipefail

# ---- Configuration ---------------------------------------------------------
REPO="CarlosVivasR/OrthoGather"
BRANCH="refactor/post-review"          # switch to a release tag when one exists
ENV_NAME="${ORTHOGATHER_ENV:-orthogather}"            # override for testing
APP_DIR="${ORTHOGATHER_DIR:-$HOME/Applications/OrthoGather}"  # override for testing
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
MINIFORGE_BASE="https://github.com/conda-forge/miniforge/releases/latest/download"

# ---- Pretty output ---------------------------------------------------------
BOLD="$(tput bold 2>/dev/null || true)"; DIM="$(tput dim 2>/dev/null || true)"
GRN="$(tput setaf 2 2>/dev/null || true)"; YLW="$(tput setaf 3 2>/dev/null || true)"
RED="$(tput setaf 1 2>/dev/null || true)"; RST="$(tput sgr0 2>/dev/null || true)"
say()  { printf "%s\n" "${BOLD}$*${RST}"; }
ok()   { printf "%s\n" "${GRN}✅ $*${RST}"; }
warn() { printf "%s\n" "${YLW}⚠️  $*${RST}"; }
die()  { printf "%s\n" "${RED}❌ $*${RST}"; echo; read -r -p "Press Return to close..." _; exit 1; }
ask()  { local r; read -r -p "${BOLD}$1 [Y/n] ${RST}" r; [[ -z "$r" || "$r" =~ ^[Yy] ]]; }

clear 2>/dev/null || true
say "============================================================"
say "   🧬  OrthoGather installer for macOS"
say "============================================================"
echo

# ---- 1. Architecture -------------------------------------------------------
ARCH="$(uname -m)"
case "$ARCH" in
  arm64)  MF="Miniforge3-MacOSX-arm64.sh" ;;
  x86_64) MF="Miniforge3-MacOSX-x86_64.sh" ;;
  *) die "Unsupported architecture: $ARCH" ;;
esac
ok "Detected macOS on $ARCH."

# ---- 2. conda / Miniforge --------------------------------------------------
find_conda() {
  if command -v conda >/dev/null 2>&1; then conda info --base; return 0; fi
  for b in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/mambaforge"; do
    [ -x "$b/bin/conda" ] && { echo "$b"; return 0; }
  done
  return 1
}

if CONDA_BASE="$(find_conda)"; then
  ok "Conda found at $CONDA_BASE."
else
  warn "Conda (the package manager OrthoGather uses) is not installed."
  if ask "Install Miniforge now? (free, ~400 MB, goes in your home folder)"; then
    say "⬇️  Downloading Miniforge…"
    tmp_mf="$(mktemp -t miniforge).sh"
    curl -fL --progress-bar -o "$tmp_mf" "$MINIFORGE_BASE/$MF" || die "Download failed. Check your internet connection."
    say "⚙️  Installing Miniforge to \$HOME/miniforge3 …"
    bash "$tmp_mf" -b -p "$HOME/miniforge3" || die "Miniforge installation failed."
    rm -f "$tmp_mf"
    CONDA_BASE="$HOME/miniforge3"
    "$CONDA_BASE/bin/conda" init bash zsh >/dev/null 2>&1 || true
    ok "Miniforge installed."
  else
    die "Cannot continue without conda. Re-run when you're ready."
  fi
fi
# Load conda into THIS shell so we can use it below.
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

# ---- 3. Download the app ---------------------------------------------------
say "⬇️  Downloading OrthoGather…"
mkdir -p "$HOME/Applications"
tmp_zip="$(mktemp -t orthogather).zip"
tmp_dir="$(mktemp -d -t orthogather)"
curl -fL --progress-bar -o "$tmp_zip" "$ZIP_URL" || die "Could not download OrthoGather from GitHub."
unzip -q "$tmp_zip" -d "$tmp_dir" || die "Could not unpack the download."
src_dir="$(find "$tmp_dir" -maxdepth 1 -type d -name 'OrthoGather-*' | head -1)"
[ -d "$src_dir" ] || die "Unexpected download layout."

if [ -d "$APP_DIR" ]; then
  warn "An existing install was found — updating it (your data is preserved)."
  # rsync new code over, WITHOUT --delete so runtime data (Proteomas, GOAfiles,
  # results, history, the decompressed catalogue) survives.
  rsync -a "$src_dir/" "$APP_DIR/"
else
  mv "$src_dir" "$APP_DIR"
fi
rm -rf "$tmp_zip" "$tmp_dir"
ok "App installed at $APP_DIR"

# ---- 4. Create / update the conda environment ------------------------------
say "⚙️  Setting up the environment (Python 3.11 + OrthoFinder 2.5.5 + deps)."
say "${DIM}    First time takes a few minutes — it downloads scientific packages.${RST}"
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda env update -n "$ENV_NAME" -f "$APP_DIR/environment.yml" --prune || die "Environment update failed."
else
  # -n overrides the name baked into environment.yml so $ENV_NAME is authoritative.
  conda env create -n "$ENV_NAME" -f "$APP_DIR/environment.yml" || die "Environment creation failed."
fi
ok "Environment '$ENV_NAME' ready."

# ---- 5. Launcher: a real OrthoGather.app with the logo ---------------------
# A proper .app bundle → shows the OrthoGather icon in Finder/Launchpad/Dock,
# double-click like any app, no Terminal window. The executable just activates
# the env and runs the server (which opens the browser).
build_app_bundle() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest/Contents/MacOS" "$dest/Contents/Resources"
  cp "$APP_DIR/installers/assets/OrthoGather.icns" "$dest/Contents/Resources/OrthoGather.icns" 2>/dev/null || true
  cat > "$dest/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>OrthoGather</string>
  <key>CFBundleDisplayName</key><string>OrthoGather</string>
  <key>CFBundleIdentifier</key><string>org.ucd.orthogather</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>OrthoGather</string>
  <key>CFBundleIconFile</key><string>OrthoGather</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
  cat > "$dest/Contents/MacOS/OrthoGather" <<LAUNCH
#!/bin/bash
# OrthoGather — double-click to start. Opens your browser automatically.
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$APP_DIR"
exec python app.py
LAUNCH
  chmod +x "$dest/Contents/MacOS/OrthoGather"
  touch "$dest"   # nudge Finder to pick up the icon
}
build_app_bundle "$HOME/Desktop/OrthoGather.app"
mkdir -p "$HOME/Applications" && build_app_bundle "$HOME/Applications/OrthoGather.app"
ok "Launcher created: OrthoGather.app (Desktop + Applications) with the OrthoGather logo"

# ---- 6. Verify + offer to launch ------------------------------------------
conda activate "$ENV_NAME"
if orthofinder -h >/dev/null 2>&1; then ok "OrthoFinder detected."; else warn "OrthoFinder check failed — the environment may need a moment."; fi

echo
say "============================================================"
ok  "OrthoGather is installed!"
say "============================================================"
echo "From now on, just double-click ${BOLD}OrthoGather${RST} on your Desktop (the app with the OrthoGather logo)."
echo
if ask "Launch OrthoGather now?"; then
  open "$HOME/Desktop/OrthoGather.app" 2>/dev/null || { cd "$APP_DIR"; exec python app.py; }
fi
read -r -p "Done. Press Return to close..." _
