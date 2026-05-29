"""
Centralised paths and constants for the OrthoGather application.

Everything that used to be a module-level constant in app.py lives here so
that any module (routes, core helpers, tests) can import a single source of
truth instead of reaching back into the Flask app file.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
# Stamped onto every analysis's provenance block so a result can be traced back
# to the exact OrthoGather release that produced it. Bump on each release.
ORTHOGATHER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
# `BASE_DIR` is the project root (parent of the `orthogather/` package).
BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_FOLDER       = "static"
PROTEOMES_FOLDER    = "Proteomas"
GOA_DOWNLOAD_FOLDER = "GOAfiles"
RESULTS_FOLDER      = os.path.join(STATIC_FOLDER, "results")

JSON_PATH    = str(BASE_DIR / "static" / "Proteomes_json" / "proteomes_list.json")
GO_ROOT_OBO  = str(BASE_DIR / "go-basic.obo")

# History storage — persistent across app restarts. ~/.orthogather/runs/<id>/
HISTORY_DIR = Path.home() / ".orthogather" / "runs"

# Flask session storage
SESSION_FILE_DIR = ".orthogather_sessions"

# ---------------------------------------------------------------------------
# Side-effect: ensure required folders exist on import.
# ---------------------------------------------------------------------------
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
os.makedirs(PROTEOMES_FOLDER,   exist_ok=True)
os.makedirs(GOA_DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER,     exist_ok=True)
os.makedirs(SESSION_FILE_DIR,   exist_ok=True)
