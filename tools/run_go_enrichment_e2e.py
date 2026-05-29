"""
Drive the full GO enrichment flow against the running Flask app.

This is the second half of the E2E runbook — assumes /download_goa_files has
already populated GOAfiles/ and built the Excel.

Steps:
    1. /cargar_carpeta?modo=preselected     (ensure session)
    2. /resultado_goa                       (build species_matches in session)
    3. /foreground_analysis                 (paste E. coli IDs)
    4. /background_analysis                 (use all GOA)
    5. /gene_ontology_analysis              (with explicit settings)

Run with:
    python tools/run_go_enrichment_e2e.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:5001"
SESSION = requests.Session()

# Pull 20 sample UniProt IDs from the Excel built by /download_goa_files —
# specifically from the E.Coli K12 column. Using the Excel (rather than the
# raw GOA file) ensures the IDs match the format used by the Orthogroups,
# which is what /foreground_analysis searches against.
def sample_uniprot_ids(excel_path: Path, column: str = "E.Coli K12", n: int = 20) -> list:
    import pandas as pd
    import re
    df = pd.read_excel(excel_path, sheet_name="Initial Groups")
    ids = set()
    for v in df[column].dropna().astype(str):
        for m in re.findall(r"\|([^|]+)\|", v):
            ids.add(m)
        if len(ids) >= n * 4:
            break
    return sorted(ids)[:n]


def step(name: str):
    print(f"\n=== {name} ===")


def main() -> int:
    excel = REPO / "static" / "results" / "Gene_Ontology_Analysis.xlsx"
    if not excel.exists():
        print(f"ERROR: {excel} missing. Run kick_off_goa_download.py first.")
        return 1

    fg_ids = sample_uniprot_ids(excel, column="E.Coli K12", n=20)
    print(f"Foreground IDs (n={len(fg_ids)}): {fg_ids[:6]}…")

    step("/cargar_carpeta")
    SESSION.get(BASE + "/cargar_carpeta",
                params={"filename": "Orthogroups.zip", "modo": "preselected"}).raise_for_status()

    step("/resultado_goa")
    SESSION.get(BASE + "/resultado_goa").raise_for_status()

    step("/foreground_analysis")
    r = SESSION.post(BASE + "/foreground_analysis", json={
        "uniprot_ids": fg_ids,
        "use_orthogroups": True,
        "single_copy_only": False,
    })
    print(f"  HTTP {r.status_code}")
    fg_data = r.json()
    # respond() merges payload onto top-level, so foreground_proteins is top-level
    fg_proteins = fg_data.get("foreground_proteins", [])
    print(f"  foreground proteins after OG expansion: {len(fg_proteins)}")

    step("/background_analysis")
    r = SESSION.post(BASE + "/background_analysis", json={
        "background_choice": "5",
        "use_orthogroups": False,
        "single_copy_only": False,
        "custom_uniprot_ids": [],
    })
    print(f"  HTTP {r.status_code}")
    print(f"  {r.json().get('message')}")

    step("/gene_ontology_analysis (evidence=all, counting=per_protein)")
    t0 = time.time()
    r = SESSION.post(BASE + "/gene_ontology_analysis", json={
        "p_value": 0.05,
        "min_depth": 2,
        "evidence_preset": "all",
        "counting_mode": "per_protein",
    }, timeout=60 * 10)
    elapsed = time.time() - t0
    print(f"  HTTP {r.status_code} after {elapsed:.1f}s")
    data = r.json()
    if not data.get("success"):
        print(f"  FAIL: {data.get('message')}")
        return 2

    bp = data.get("bp_results", [])
    cc = data.get("cc_results", [])
    mf = data.get("mf_results", [])
    print(f"  significant terms: BP={len(bp)} CC={len(cc)} MF={len(mf)}")
    print(f"  settings echoed: {data.get('settings')}")

    if bp:
        sample = bp[0]
        print(f"  example BP term: {sample.get('GO')} {sample.get('name')!r}")
        print(f"    p_fdr_bh={sample.get('p_fdr_bh'):.2e}  "
              f"evidence={sample.get('evidence_breakdown')}")

    # Verification gate: at least one significant term
    if not (bp or cc or mf):
        print("  WARN: no significant terms — the foreground may be too small.")
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
