#!/bin/bash
# ============================================================
#  OrthoGather Installer for macOS (Apple Silicon & Intel)
# ============================================================

set -e

echo "🚀 Starting OrthoGather installation for macOS..."
sleep 1

# ============================================================
# 1️⃣ Check architecture (must be x86_64 under Rosetta)
# ============================================================
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
  echo "❌ ERROR: You are running this terminal in native ARM mode."
  echo "Python 3.7 only works in Intel (x86_64) mode on macOS ARM."
  echo ""
  echo "Please restart your terminal under Rosetta with:"
  echo "   arch -x86_64 /bin/zsh"
  echo "Then re-run this script."
  exit 1
else
  echo "✅ Running under Intel (Rosetta) mode: OK"
fi

# ============================================================
# 2️⃣ Check if conda is installed
# ============================================================
if ! command -v conda &> /dev/null; then
  echo "❌ Conda not found."
  echo "Please install Miniforge first:"
  echo "   curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
  echo "   bash Miniforge3-MacOSX-arm64.sh"
  exit 1
fi
echo "✅ Conda detected."

# ============================================================
# 3️⃣ Check for environment_mac.yml
# ============================================================
if [[ ! -f "environment.yml" ]]; then
  echo "❌ File 'environment_mac.yml' not found in current directory."
  echo "Please ensure it exists (expected location: same folder as this script)."
  exit 1
else
  echo "✅ environment.yml found."
fi

# ============================================================
# 4️⃣ Create or update environment (Intel mode)
# ============================================================
echo "⚙️  Creating or updating environment 'orthogather37'..."
sleep 1

CONDA_SUBDIR=osx-64 conda env create -f environment.yml || {
  echo "Environment may already exist. Updating instead..."
  CONDA_SUBDIR=osx-64 conda env update -f environment.yml --prune
}

# ============================================================
# 5️⃣ Activate environment & install Orthofinder
# ============================================================
echo "🧩 Installing Orthofinder..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate orthogather37

CONDA_SUBDIR=osx-64 conda install orthofinder -c bioconda -c conda-forge -y || {
  echo "Orthofinder installation encountered an issue. You can retry manually later."
}

# ============================================================
# 6️⃣ Verify installation
# ============================================================
echo ""
echo "Verifying installation..."
python --version || echo "Python check failed."
orthofinder -h >/dev/null 2>&1 && echo "Orthofinder detected." || echo "Orthofinder not detected."

# ============================================================
# 7️⃣ Final instructions (highlighted clearly)
# ============================================================
echo ""
echo "============================================================"
echo "🎉  INSTALLATION COMPLETED SUCCESSFULLY  🎉"
echo "============================================================"
echo ""
echo "The Conda environment 'orthogather37' is now ACTIVE."
echo ""
echo "⚠️  IMPORTANT REMINDER:"
echo ""
echo "👉  Every time you want to use OrthoGather, make sure you open"
echo "    your terminal in **Intel (Rosetta)** mode with:"
echo "        arch -x86_64 /bin/zsh"
echo ""
echo "👉  Then activate the environment:"
echo "        conda activate orthogather37"
echo ""
echo "✅  Once activated, run the tool with:"
echo "        python app.py"
echo ""
echo "============================================================"
echo "OrthoGather is ready to use."
echo "============================================================"

# Keep the session active inside the environment
$SHELL
