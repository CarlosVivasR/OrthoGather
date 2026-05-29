"""
Kick off the /download_goa_files endpoint with the preselected 47-species mapping.

The endpoint is synchronous and serial — this script POSTs once and waits for
the response. Expected duration: 5–10 minutes on a normal connection.

Run with:
    python tools/kick_off_goa_download.py
"""
from __future__ import annotations

import json
import sys
import time
import zipfile
from pathlib import Path

import requests
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:5001"
SESSION = requests.Session()


def boot_session() -> None:
    """Hit /cargar_carpeta to initialise session in preselected mode."""
    r = SESSION.get(BASE + "/cargar_carpeta",
                    params={"filename": "Orthogroups.zip", "modo": "preselected"})
    r.raise_for_status()
    print(f"  /cargar_carpeta {r.status_code}")


def build_mapping() -> dict:
    """Build species->URL mapping by intersecting the preselected species list
    with the proteomes catalogue."""
    # Species in the preselected dataset
    with zipfile.ZipFile(REPO / "static" / "Orthogroups.zip") as zf:
        with zf.open("Orthogroups.tsv") as fh:
            df = pd.read_csv(fh, sep="\t", nrows=0)
    species_list = list(df.columns[1:])

    # Hit /resultado_goa to get the matches (uses the same matcher Phase A fixed)
    r = SESSION.get(BASE + "/resultado_goa")
    r.raise_for_status()
    # Resolve via the catalogue ourselves (don't scrape HTML)
    with open(REPO / "static" / "Proteomes_json" / "proteomes_list.json") as fh:
        proteomes = json.load(fh)

    sys.path.insert(0, str(REPO))
    from app import match_species, load_proteomes, JSON_PATH
    loaded = load_proteomes(JSON_PATH)
    results = match_species(species_list, loaded)

    mapping = {}
    skipped = []
    for r in results:
        m = r.get("match")
        if m and m.get("file_url") and m["file_url"] != "NA":
            mapping[r["original"]] = m["file_url"]
        else:
            skipped.append(r["original"])

    print(f"  species in dataset: {len(species_list)}")
    print(f"  with GOA URLs:      {len(mapping)}")
    print(f"  skipped (no GOA):   {len(skipped)}")
    if skipped:
        print("  first 5 skipped:   ", skipped[:5])
    return mapping


def main() -> int:
    print("=== /cargar_carpeta ===")
    boot_session()

    print("\n=== build mapping ===")
    mapping = build_mapping()
    if not mapping:
        print("ERROR: no GOA URLs resolved")
        return 1

    print(f"\n=== POST /download_goa_files (n={len(mapping)}) ===")
    print("  This is serial with retries; expect 5–10 minutes...")
    start = time.time()
    r = SESSION.post(
        BASE + "/download_goa_files",
        json={"species_to_url": mapping},
        timeout=60 * 30,  # 30 min hard ceiling
    )
    elapsed = time.time() - start
    print(f"  HTTP {r.status_code} after {elapsed:.1f}s")
    try:
        data = r.json()
        print(json.dumps({k: v for k, v in data.items() if k != "payload"}, indent=2))
        if data.get("payload"):
            p = data["payload"]
            for k in ("downloaded", "existed", "failed"):
                v = p.get(k, [])
                print(f"  {k}: {len(v) if isinstance(v, list) else v}")
    except Exception:
        print(r.text[:2000])
    return 0 if r.ok else 2


if __name__ == "__main__":
    sys.exit(main())
