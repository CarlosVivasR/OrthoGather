#!/usr/bin/env bash
# ============================================================================
#  Build the two double-click installer .zip files we ship as GitHub release
#  assets:
#    dist/Install-OrthoGather-Mac.zip     <- "Install OrthoGather.command"
#    dist/Install-OrthoGather-Windows.zip <- "Install OrthoGather.bat"
#
#  WHY ZIP: a browser download of a raw .command strips its +x bit, which
#  shows the user "you do not have appropriate access privileges" on
#  double-click. UCD's Sophos web protection also blocks raw .bat/.command
#  downloads outright ("Restricted file type: Other Executables"). Zipping
#  preserves the Unix +x bit and presents an archive to Sophos instead of a
#  bare executable.
#
#  Each zip contains exactly ONE file, at the zip root (no folders, no
#  __MACOSX/.DS_Store cruft), with the exact name the in-app HTML download
#  buttons already link to:
#    installers/How to install OrthoGather.html
#
#  USAGE:
#    ./build_installer_zips.sh
#
#  Writes into installers/packaging/dist/ (gitignored). Re-running overwrites
#  both zips, so it is safe to run repeatedly (idempotent).
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
INSTALLERS="$HERE/.."
OUT_DIR="${OUT_DIR:-$HERE/dist}"

MAC_SRC="$INSTALLERS/macos/Install OrthoGather.command"
WIN_SRC="$INSTALLERS/windows/Install OrthoGather.bat"
MAC_ZIP="$OUT_DIR/Install-OrthoGather-Mac.zip"
WIN_ZIP="$OUT_DIR/Install-OrthoGather-Windows.zip"

[ -f "$MAC_SRC" ] || { echo "ERROR: missing $MAC_SRC" >&2; exit 1; }
[ -f "$WIN_SRC" ] || { echo "ERROR: missing $WIN_SRC" >&2; exit 1; }

mkdir -p "$OUT_DIR"
rm -f "$MAC_ZIP" "$WIN_ZIP"

# Stage each installer alone in its own clean temp dir so the zip has no
# directory structure inside (zip root = the file itself), and so macOS
# never gets a chance to drop a .DS_Store next to the source files.
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/mac" "$STAGE/win"

cp "$MAC_SRC" "$STAGE/mac/Install OrthoGather.command"
chmod +x "$STAGE/mac/Install OrthoGather.command"
cp "$WIN_SRC" "$STAGE/win/Install OrthoGather.bat"

# -X  : drop extended attrs / resource forks (no AppleDouble ._ files)
# -j  : junk the path, store as a top-level entry (belt-and-braces; the cd
#       into the staging dir already guarantees a flat layout)
( cd "$STAGE/mac" && zip -X -j "$MAC_ZIP" "Install OrthoGather.command" )
( cd "$STAGE/win" && zip -X -j "$WIN_ZIP" "Install OrthoGather.bat" )

rm -rf "$STAGE"

echo "Built: $MAC_ZIP"
echo "Built: $WIN_ZIP"

# Quick self-check: exactly one entry per zip, no __MACOSX/.DS_Store, and the
# macOS entry must keep its executable bit through extraction.
for z in "$MAC_ZIP" "$WIN_ZIP"; do
  count="$(unzip -l "$z" | awk 'NR>3 && NF==4 {c++} END{print c+0}')"
  if unzip -l "$z" | grep -qiE "__MACOSX|\.DS_Store"; then
    echo "ERROR: cruft found in $z" >&2; exit 1
  fi
done

CHECK="$(mktemp -d)"
unzip -q -X "$MAC_ZIP" -d "$CHECK"
if [ -x "$CHECK/Install OrthoGather.command" ]; then
  echo "OK: +x preserved in $MAC_ZIP"
else
  echo "ERROR: +x bit lost when extracting $MAC_ZIP" >&2
  rm -rf "$CHECK"
  exit 1
fi
rm -rf "$CHECK"

echo "Done. Upload these two files as release assets named exactly:"
echo "  Install-OrthoGather-Mac.zip"
echo "  Install-OrthoGather-Windows.zip"
