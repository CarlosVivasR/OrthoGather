#!/usr/bin/env bash
# ============================================================================
#  OrthoGather — Linux / WSL environment setup (Phase 2 on Windows).
#
#  Runs INSIDE a Linux shell (a real Linux box, or Ubuntu under WSL on Windows).
#  Installs Miniforge if needed, downloads the app, builds the conda env with
#  OrthoFinder, and creates a launcher script. Idempotent: re-run = update.
#
#  Called by the Windows installer after WSL is ready, or directly on Linux.
# ============================================================================
set -euo pipefail

REPO="CarlosVivasR/OrthoGather"
BRANCH="main"
ENV_NAME="orthogather"
APP_DIR="$HOME/OrthoGather"
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
MINIFORGE_BASE="https://github.com/conda-forge/miniforge/releases/latest/download"

say()  { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✅ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m⚠️  %s\033[0m\n" "$*"; }
die()  { printf "\033[31m❌ %s\033[0m\n" "$*"; exit 1; }

say "============================================================"
say "   🧬  OrthoGather — Linux/WSL setup"
say "============================================================"

# ---- 1. Base tools ---------------------------------------------------------
command -v curl  >/dev/null 2>&1 || die "curl is required (sudo apt install -y curl)."
command -v unzip >/dev/null 2>&1 || { warn "Installing unzip…"; sudo apt-get update -y && sudo apt-get install -y unzip || die "Could not install unzip."; }

# ---- 2. conda / Miniforge --------------------------------------------------
find_conda() {
  command -v conda >/dev/null 2>&1 && { conda info --base; return 0; }
  for b in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/mambaforge"; do
    [ -x "$b/bin/conda" ] && { echo "$b"; return 0; }
  done
  return 1
}
if CONDA_BASE="$(find_conda)"; then
  ok "Conda found at $CONDA_BASE."
else
  ARCH="$(uname -m)"   # x86_64 or aarch64 (ARM Windows)
  MF="Miniforge3-Linux-${ARCH}.sh"
  say "⬇️  Installing Miniforge ($MF)…"
  curl -fL --progress-bar -o /tmp/miniforge.sh "$MINIFORGE_BASE/$MF" || die "Miniforge download failed."
  bash /tmp/miniforge.sh -b -p "$HOME/miniforge3" || die "Miniforge install failed."
  rm -f /tmp/miniforge.sh
  CONDA_BASE="$HOME/miniforge3"
  "$CONDA_BASE/bin/conda" init bash >/dev/null 2>&1 || true
  ok "Miniforge installed."
fi
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

# ---- 3. Obtain the app -----------------------------------------------------
# If the caller already extracted the source (Windows installer passes OG_SRC),
# reuse it; otherwise download the zip ourselves.
if [ -n "${OG_SRC:-}" ] && [ -d "$OG_SRC" ]; then
  ok "Using app source provided by the installer."
  src_dir="$OG_SRC"
else
  say "⬇️  Downloading OrthoGather…"
  curl -fL --progress-bar -o /tmp/orthogather.zip "$ZIP_URL" || die "Could not download OrthoGather."
  rm -rf /tmp/og_extract && mkdir -p /tmp/og_extract
  unzip -q /tmp/orthogather.zip -d /tmp/og_extract || die "Could not unpack the download."
  src_dir="$(find /tmp/og_extract -maxdepth 1 -type d -name 'OrthoGather-*' | head -1)"
  [ -d "$src_dir" ] || die "Unexpected download layout."
fi
if [ -d "$APP_DIR" ]; then
  warn "Updating existing install (data preserved)."
  rsync -a "$src_dir/" "$APP_DIR/" 2>/dev/null || cp -rf "$src_dir/." "$APP_DIR/"
else
  mv "$src_dir" "$APP_DIR"
fi
rm -rf /tmp/orthogather.zip /tmp/og_extract
ok "App at $APP_DIR"

# ---- 4. Environment --------------------------------------------------------
say "⚙️  Building the environment (Python 3.11 + OrthoFinder 2.5.5)…"
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda env update -n "$ENV_NAME" -f "$APP_DIR/environment.yml" --prune || die "Env update failed."
else
  # -n overrides the name baked into environment.yml so $ENV_NAME is authoritative.
  conda env create -n "$ENV_NAME" -f "$APP_DIR/environment.yml" || die "Env creation failed."
fi
conda activate "$ENV_NAME"
orthofinder -h >/dev/null 2>&1 && ok "OrthoFinder detected." || warn "OrthoFinder check failed."

# ---- 5. Launcher script (called by the Windows .bat via WSL) ---------------
cat > "$APP_DIR/run_orthogather.sh" <<LAUNCH
#!/usr/bin/env bash
set -euo pipefail
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$APP_DIR"
python app.py
LAUNCH
chmod +x "$APP_DIR/run_orthogather.sh"

ok "OrthoGather Linux/WSL setup complete."
