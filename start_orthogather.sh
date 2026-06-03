#!/usr/bin/env bash
# OrthoGather launcher (macOS/Linux) - requires conda env 'orthogather'
# Does not create environments: if missing, shows error and exits.
set -euo pipefail

# Prevent error if LD_LIBRARY_PATH is not defined
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"

# --- Resolve the REAL path of the script (follows alias/symlinks) ---
if [ -n "${ZSH_VERSION:-}" ]; then
  SRC="${(%):-%N}"
else
  SRC="${BASH_SOURCE[0]:-$0}"
fi
while [ -h "$SRC" ]; do
  DIR="$( cd -P "$( dirname "$SRC" )" >/dev/null 2>&1 && pwd )"
  LINK="$(readlink "$SRC")"
  [[ $LINK != /* ]] && SRC="$DIR/$LINK" || SRC="$LINK"
done
APP_DIR="$( cd -P "$( dirname "$SRC" )" >/dev/null 2>&1 && pwd )"
cd "$APP_DIR"

# --- Load conda in this shell ---
if command -v conda >/dev/null 2>&1; then
  if [ -n "${ZSH_VERSION:-}" ]; then
    eval "$(conda shell.zsh hook)"
  else
    eval "$(conda shell.bash hook)"
  fi
else
  echo "[ERROR] conda is not in PATH. Run 'conda init zsh|bash' and reopen the terminal." >&2
  exit 1
fi

# --- Check that the 'orthogather' environment exists ---
if ! conda info --envs | awk '{print $1}' | grep -qx "orthogather"; then
  echo "[ERROR] The environment 'orthogather' is missing. Check the installation README." >&2
  exit 1
fi

# --- Activate and launch ---
conda activate orthogather
echo "[INFO] Dir: $PWD"
python app.py

# Keep the terminal open after finishing
exec $SHELL
