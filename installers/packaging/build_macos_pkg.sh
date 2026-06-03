#!/usr/bin/env bash
# ============================================================================
#  Phase B scaffold — build a macOS .pkg that wraps the one-click installer.
#
#  This produces OrthoGather-Installer.pkg from "Install OrthoGather.command".
#  WITHOUT signing it still builds, but macOS Gatekeeper will warn on open.
#  For a warning-free installer you need an Apple Developer ID + notarization.
#
#  PREREQUISITES YOU MUST PROVIDE (cannot be automated here):
#    • Apple Developer Program membership (~99 EUR/yr)
#    • A "Developer ID Installer" certificate in your login keychain
#    • An app-specific password / notarytool profile for notarization
#
#  USAGE:
#    ./build_macos_pkg.sh                 # unsigned (for testing)
#    SIGN_ID="Developer ID Installer: Your Name (TEAMID)" \
#    NOTARY_PROFILE="og-notary" ./build_macos_pkg.sh   # signed + notarized
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d)/OrthoGather"
OUT="${OUT:-$HERE/OrthoGather-Installer.pkg}"
VERSION="${VERSION:-2026.06.03}"

mkdir -p "$STAGE"
cp "$HERE/../macos/Install OrthoGather.command" "$STAGE/Install OrthoGather.command"
chmod +x "$STAGE/Install OrthoGather.command"

# Build a component pkg whose postinstall runs the .command for the user.
SCRIPTS="$(mktemp -d)"
cat > "$SCRIPTS/postinstall" <<'POST'
#!/bin/bash
exec "/Applications/OrthoGather/Install OrthoGather.command"
POST
chmod +x "$SCRIPTS/postinstall"

PKG_ARGS=(--root "$STAGE" --identifier org.ucd.orthogather.installer
          --version "$VERSION" --install-location "/Applications/OrthoGather"
          --scripts "$SCRIPTS")
[ -n "${SIGN_ID:-}" ] && PKG_ARGS+=(--sign "$SIGN_ID")

pkgbuild "${PKG_ARGS[@]}" "$OUT"
echo "Built: $OUT"

if [ -n "${NOTARY_PROFILE:-}" ]; then
  echo "Notarizing…"
  xcrun notarytool submit "$OUT" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$OUT"
  echo "Notarized + stapled."
else
  echo "NOTE: unsigned/unnotarized — Gatekeeper will warn. Set SIGN_ID + NOTARY_PROFILE to fix."
fi
