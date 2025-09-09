#!/usr/bin/env bash
# OrthoGather launcher (macOS/Linux) - requiere conda env 'ortho37'
# No crea entornos: si falta, muestra error y sale.
set -euo pipefail

# Evitar error por LD_LIBRARY_PATH no definido
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"

# --- Resolver la ruta REAL del script (sigue alias/symlinks) ---
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

# --- Cargar conda en esta shell ---
if command -v conda >/dev/null 2>&1; then
  if [ -n "${ZSH_VERSION:-}" ]; then
    eval "$(conda shell.zsh hook)"
  else
    eval "$(conda shell.bash hook)"
  fi
else
  echo "[ERROR] conda no está en PATH. Ejecuta 'conda init zsh|bash' y reabre la terminal." >&2
  exit 1
fi

# --- Comprobar que existe el entorno 'ortho37' ---
if ! conda info --envs | awk '{print $1}' | grep -qx "ortho37"; then
  echo "[ERROR] Falta el entorno 'ortho37'. Revisa el README de instalación." >&2
  exit 1
fi

# --- Activar y lanzar ---
conda activate ortho37
echo "[INFO] Dir: $PWD"
python app.py

# Mantener la terminal abierta después de terminar
exec $SHELL

