"""Every combination of the Gene Ontology settings, through the real routes.

Runs tests/test_go_combinations.py with OG_FULL_MATRIX=1: for each of three
synthetic species (complete, partial and no GOA file), six foreground lists ×
three backgrounds × foreground expansion × the single-copy filter × two
counting modes × three evidence settings (1,296 combinations), each analysis
checked against the rules listed in that file, plus equivalences between
analyses. The summary of each species goes to results/combinations_matrix/.

Usage:  python docs/validation/combinations_matrix.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "results" / "combinations_matrix"

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OG_FULL_MATRIX="1", OG_MATRIX_OUT=str(OUT))
    code = subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            str(REPO / "tests" / "test_go_combinations.py")], cwd=REPO, env=env)
    total = {"combinations": 0, "analysed": 0, "failures": 0}
    for f in sorted(OUT.glob("sp*.json")):
        s = json.loads(f.read_text())
        for k in ("combinations", "analysed"):
            total[k] += s[k]
        total["failures"] += len(s["failures"])
    (OUT / "summary.json").write_text(json.dumps({**total, "pytest_exit_status": code}, indent=1) + "\n")
    print(total)
    sys.exit(code)
