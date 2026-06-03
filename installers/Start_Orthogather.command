#!/usr/bin/env zsh
set -euo pipefail
SCRIPT="${(%):-%N}"
DIR="$(cd -P "$(dirname "$SCRIPT")" && pwd)"
exec "$DIR/start_orthogather.sh"

