#!/usr/bin/env bash
# Regenerate OrthoGather.icns (macOS) and OrthoGather.ico (Windows) from
# OrthoGather-icon.svg. Run on macOS (needs rsvg-convert, iconutil, sips, and
# Python with Pillow). The committed icns/ico are the output of this script.
#
#   ./build_icons.sh
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

WORK="$(mktemp -d)"; ICONSET="$WORK/OrthoGather.iconset"; mkdir -p "$ICONSET"
rsvg-convert -w 1024 -h 1024 OrthoGather-icon.svg -o "$WORK/master.png"

for s in 16 32 128 256 512; do
  sips -z "$s" "$s" "$WORK/master.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); sips -z "$d" "$d" "$WORK/master.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o OrthoGather.icns
echo "Wrote OrthoGather.icns"

"$PY" - "$WORK/master.png" <<'PYEOF'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert("RGBA").save(
    "OrthoGather.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("Wrote OrthoGather.ico")
PYEOF
