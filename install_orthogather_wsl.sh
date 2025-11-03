
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
# 3️⃣ Create environment (if not exists)
# ------------------------------------------------------------
if micromamba env list | grep -q "orthogather37"; then
  echo "✅ Environment 'orthogather37' already exists."
else
  echo "🧩 Creating environment 'orthogather37' with Python 3.7..."
  micromamba create -n orthogather37 python=3.7 -y
fi

# ------------------------------------------------------------
# 4️⃣ Activate and install dependencies
# ------------------------------------------------------------
micromamba activate orthogather37

echo ""
echo "📦 Installing core dependencies from conda-forge..."
micromamba install -c conda-forge flask flask-session pandas numpy matplotlib seaborn upsetplot goatools requests openpyxl -y

echo ""
echo "🧬 Installing Orthofinder and bio dependencies from bioconda..."
micromamba install -c bioconda orthofinder -y

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
echo "        micromamba activate orthogather37"
echo ""
echo "✅  Then start the tool with:"
echo "        python app.py"
echo ""
echo "============================================================"
echo "OrthoGather is ready to use 🚀"
echo "============================================================"

$SHELL
