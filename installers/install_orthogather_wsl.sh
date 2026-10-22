
set -e

echo ""
echo "============================================================"
echo "🚀  Starting OrthoGather Installation for WSL/Linux"
echo "============================================================"
echo ""

# ------------------------------------------------------------
# 1️⃣ Check OS type
# ------------------------------------------------------------
if grep -qi microsoft /proc/version; then
  echo "✅ Running inside WSL environment."
else
  echo "⚠️  This script is intended for WSL or Linux only."
  exit 1
fi

# ------------------------------------------------------------
# 2️⃣ Install Micromamba if not found
# ------------------------------------------------------------
if ! command -v micromamba >/dev/null 2>&1; then
  echo ""
  echo "============================================================"
  echo "⚠️  Micromamba is not installed on this system."
  echo ""
  echo "Please install it manually and restart the terminal:"
  echo ""
  echo "   1️⃣ Run this command to install Micromamba:"
  echo "       curl -L https://micro.mamba.pm/install.sh | bash"
  echo ""
  echo "   2️⃣ CLOSE this terminal completely."
  echo "   3️⃣ Open a NEW terminal in WSL."
  echo "   4️⃣ Run again:"
  echo "       ./install_orthogather_wsl.sh"
  echo ""
  echo "💡 Micromamba is required to manage the OrthoGather environment."
  echo "============================================================"
  echo ""
  exit 0
fi

# Initialize micromamba shell
eval "$(micromamba shell hook -s bash)"

# ------------------------------------------------------------
# 3️⃣ Create or update the environment from environment.yml
# ------------------------------------------------------------
# environment.yml pins every dependency to the versions the tests and the
# worked example were verified with (statsmodels 0.15, for example, breaks
# GOATOOLS 1.6.4), so install from it rather than from package names.
cd "$(dirname "$0")/.."
if [[ ! -f environment.yml ]]; then
  echo "❌ environment.yml not found: run this script from the OrthoGather folder."
  exit 1
fi
if micromamba env list | grep -q "orthogather"; then
  echo "🧩 Updating environment 'orthogather' from environment.yml..."
  micromamba install -n orthogather -f environment.yml -y
else
  echo "🧩 Creating environment 'orthogather' from environment.yml..."
  micromamba create -n orthogather -f environment.yml -y
fi
micromamba activate orthogather

# ------------------------------------------------------------
# 5️⃣ Verify installation
# ------------------------------------------------------------
echo ""
echo "🔍 Verifying installation..."
python --version
orthofinder -h >/dev/null 2>&1 && echo "✅ OrthoFinder detected." || echo "⚠️ OrthoFinder not detected."

# ------------------------------------------------------------
# 6️⃣ Final instructions
# ------------------------------------------------------------
echo ""
echo "============================================================"
echo "🎉  INSTALLATION COMPLETED SUCCESSFULLY  🎉"
echo "============================================================"
echo ""
echo "⚠️  IMPORTANT REMINDER:"
echo ""
echo "✅  To use OrthoGather, follow these steps:"
echo ""
echo "👉  Every time you want to use OrthoGather, run:"
echo "        micromamba activate orthogather"
echo ""
echo "✅  Then start the tool with:"
echo "        python app.py"
echo ""
echo "📦  On the first launch the proteome catalogue (~250 MB) is unpacked"
echo "    automatically from its compressed copy — no Git LFS required."
echo ""
echo "============================================================"
echo "OrthoGather is ready to use 🚀"
echo "============================================================"

$SHELL
