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

# Self-healing: downloads + steps retry automatically so a network blip during
# install heals itself with no user action; a re-run resumes where it left off.
dl()    { curl -fL --progress-bar --retry 6 --retry-delay 4 --retry-connrefused -o "$2" "$1"; }
retry() {  # retry <max> <label> -- <command...>
  local max="$1" label="$2"; shift 2; [ "${1:-}" = "--" ] && shift
  local n=1
  while true; do
    if "$@"; then return 0; fi
    if [ "$n" -ge "$max" ]; then return 1; fi
    warn "$label didn't finish (try $n/$max) — retrying in $((n*5)) s…"
    sleep $((n*5)); n=$((n+1))
  done
}
export CONDA_REMOTE_MAX_RETRIES=8 CONDA_REMOTE_BACKOFF_FACTOR=2

say "============================================================"
say "   🧬  OrthoGather — Linux/WSL setup"
say "============================================================"

# ---- 1. Base tools ---------------------------------------------------------
# Use sudo only when not already root (WSL runs this as root, where sudo may be absent).
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
ensure_pkg() {  # ensure_pkg <command> <apt-package>
  command -v "$1" >/dev/null 2>&1 && return 0
  warn "Installing $2…"
  $SUDO apt-get update -y >/dev/null 2>&1 || true
  retry 3 "$2 install" -- $SUDO apt-get install -y "$2" || die "Could not install $2."
}
ensure_pkg curl curl
ensure_pkg unzip unzip
ensure_pkg rsync rsync

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
  retry 5 "Miniforge download" -- dl "$MINIFORGE_BASE/$MF" /tmp/miniforge.sh \
    || die "Miniforge download failed after several tries — re-run the installer to resume."
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
  retry 5 "OrthoGather download" -- dl "$ZIP_URL" /tmp/orthogather.zip \
    || die "Could not download OrthoGather after several tries — re-run the installer to resume."
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
say ""
say "============================================================"
say "⚙️   Building the environment (Python 3.11 + OrthoFinder + tools)"
say "============================================================"
say "   ⬇️  This downloads ~1–2 GB and takes about 5–15 minutes."
say "   ⏳  It will sit silently at \"Solving environment…\" for a while —"
say "       that is NORMAL, it is NOT frozen. Please leave this window open."
say "       You'll see each package scroll past as it downloads."
say "============================================================"
say ""
# Show every package on its own line as it downloads (a plain, scrolling log)
# instead of conda's collapsing live bars that hide most of them behind
# "(N more hidden)" — so users can see the long download is really working.
# Piping conda's output makes it emit a full, non-collapsing package log.
# Heartbeat: print a line periodically so the long, quiet phase clearly looks alive.
( while sleep 45; do printf "   ⏳ still installing, please wait… (%s)\n" "$(date +%H:%M:%S)"; done ) &
HEARTBEAT=$!
trap 'kill "$HEARTBEAT" 2>/dev/null' EXIT
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  retry 3 "Environment setup" -- conda env update -n "$ENV_NAME" -f "$APP_DIR/environment.yml" --prune 2>&1 | cat \
    || { kill "$HEARTBEAT" 2>/dev/null || true; die "The environment didn't finish building after several tries — re-run the installer to resume."; }
else
  # -n overrides the name in environment.yml. An interrupted create leaves a partial
  # env that a re-run finishes via the update path above — so re-running always heals.
  retry 3 "Environment setup" -- conda env create -n "$ENV_NAME" -f "$APP_DIR/environment.yml" 2>&1 | cat \
    || { kill "$HEARTBEAT" 2>/dev/null || true; die "The environment didn't finish building after several tries — re-run the installer to resume."; }
fi
kill "$HEARTBEAT" 2>/dev/null || true; trap - EXIT
ok "Environment built."
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
