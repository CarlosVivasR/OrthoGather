#!/bin/bash
# ============================================================
#  OrthoGather Installer for macOS (Apple Silicon & Intel)
# ============================================================

set -e

# This script lives in installers/; work from the repo root (where environment.yml is).
cd "$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Starting OrthoGather installation for macOS..."
sleep 1

# ============================================================
# 1️⃣ Check if conda is installed
# ============================================================
if ! command -v conda &> /dev/null; then
  echo "❌ Conda not found."
  echo "Please install Miniforge first:"
  ARCH=$(uname -m)
  if [[ "$ARCH" == "arm64" ]]; then
    echo "   curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
    echo "   bash Miniforge3-MacOSX-arm64.sh"
  else
    echo "   curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-x86_64.sh"
    echo "   bash Miniforge3-MacOSX-x86_64.sh"
  fi
  exit 1
fi
echo "✅ Conda detected."

# ============================================================
# 2️⃣ Check for environment.yml
# ============================================================
if [[ ! -f "environment.yml" ]]; then
  echo "❌ File 'environment.yml' not found in current directory."
  echo "Please run this script from the OrthoGather repository root."
  exit 1
fi
echo "✅ environment.yml found."

# ============================================================
# 3️⃣ Create or update environment (native architecture)
# ============================================================
echo "⚙️  Creating or updating environment 'orthogather'..."
sleep 1

conda env create -f environment.yml || {
  echo "Environment may already exist. Updating instead..."
  conda env update -f environment.yml --prune
}

# ============================================================
# 4️⃣ Verify installation
# ============================================================
echo ""
echo "🔍 Verifying installation..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate orthogather
python --version || echo "Python check failed."
orthofinder -h >/dev/null 2>&1 && echo "✅ OrthoFinder detected." || echo "⚠️  OrthoFinder not detected."

# ============================================================
# 5️⃣ Final instructions
# ============================================================
echo ""
echo "============================================================"
echo "🎉  INSTALLATION COMPLETED SUCCESSFULLY  🎉"
echo "============================================================"
echo ""
echo "The Conda environment 'orthogather' is now ACTIVE."
echo ""
echo "👉  Every time you want to use OrthoGather, activate it with:"
echo "        conda activate orthogather"
echo ""
echo "✅  Then run the tool with:"
echo "        python app.py"
echo ""
echo "📦  On the first launch the proteome catalogue (~250 MB) is unpacked"
echo "    automatically from its compressed copy — no Git LFS required."
echo ""
echo "============================================================"
echo "OrthoGather is ready to use."
echo "============================================================"

# Keep the session active inside the environment
$SHELL
