"""
End-to-end driver for a FROM-SCRATCH "New Analysis" against a running OrthoGather
server — the full pipeline a user would click through:

    select species → download proteomes → run OrthoFinder → match GOA →
    download GOA → foreground/background → GO enrichment

It drives the real HTTP endpoints (same ones the browser uses) and prints a JSON
summary at the end so a caller can turn it into a report. Intended for smoke /
acceptance testing after catalogue changes.

USAGE
-----
    # 8 species by UniProt proteome id, against a server on :5001
    python tools/e2e_new_analysis.py --base http://127.0.0.1:5001 \
        --ids UP000000625,UP000002311,UP000000589,UP000000803,UP000001570,\
UP000000557,UP000002494,UP000000437

Options:
    --base URL        server base (default http://127.0.0.1:5001)
    --ids  CSV        comma-separated UniProt proteome ids (>=4 recommended)
    --fg-n N          how many foreground UniProt IDs to sample (default 25)
    --pvalue F        GO significance cutoff (default 0.05)
    --out  PATH       write the JSON summary here (default stdout only)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent


def sse(session, url, on_event=None, terminal_phases=("done",), timeout=1800):
    """Consume a JSON Server-Sent-Events stream until a terminal phase. Returns the
    last terminal event dict. Each ``data: {json}`` line is parsed and passed to
    on_event(evt)."""
    last = {}
    with session.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            body = raw[len("data:"):].strip()
            try:
                evt = json.loads(body)
            except json.JSONDecodeError:
                continue
            if on_event:
                on_event(evt)
            if evt.get("phase") in terminal_phases:
                last = evt
                break
    return last


def sse_text(session, url, sentinel="DONE", timeout=3600):
    """Consume a plain-text SSE stream (``data: <line>``) until a sentinel line.
    Returns the collected lines."""
    lines = []
    with session.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            line = raw[len("data:"):].strip()
            lines.append(line)
            if line == sentinel or line.endswith(sentinel):
                break
    return lines


def load_taxid_to_url():
    """taxon_id -> GOA file_url from the local catalogue (NA filtered out)."""
    with open(REPO / "static" / "Proteomes_json" / "proteomes_list.json") as f:
        cat = json.load(f)
    m = {}
    for e in cat:
        u = e.get("file_url")
        if u and u != "NA":
            m.setdefault(str(e.get("taxon_id")), u)
    return m


def sample_foreground_ids(n):
    """Pull n UniProt accessions from the GO Excel built by /download_goa_files
    (first species column) so the foreground IDs exist in the dataset."""
    import pandas as pd
    excel = REPO / "static" / "results" / "Gene_Ontology_Analysis.xlsx"
    if not excel.exists():
        return []
    df = pd.read_excel(excel, sheet_name="Initial Groups")
    # first data column after the orthogroup id column
    cols = [c for c in df.columns if c.lower() not in ("orthogroup", "og", "total")]
    ids = []
    for col in cols:
        for v in df[col].dropna().astype(str):
            ids += re.findall(r"\|([^|]+)\||\b([A-NR-Z0-9]{6,10})\b", v)
        ids = [a or b for (a, b) in ids] if ids and isinstance(ids[0], tuple) else ids
        if len(ids) >= n * 3:
            break
    seen, out = set(), []
    for i in ids:
        if i and i not in seen:
            seen.add(i); out.append(i)
        if len(out) >= n:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5001")
    ap.add_argument("--ids", required=True, help="comma-separated UniProt proteome ids")
    ap.add_argument("--fg-n", type=int, default=25)
    ap.add_argument("--pvalue", type=float, default=0.05)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    base = args.base.rstrip("/")
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    S = requests.Session()
    report = {"base": base, "proteome_ids": ids, "steps": {}}

    def log(msg): print(msg, flush=True)

    # 0. warm the session on the species page (sets up new-analysis mode)
    S.get(base + "/1-seleccion_especies", timeout=60)

    # 1. download proteomes
    log(f"=== download proteomes (n={len(ids)}) ===")
    saved = []
    def on_dl(evt):
        if evt.get("phase") == "proteome_saved":
            saved.append(evt.get("species"))
            log(f"  saved {evt.get('pid')}  {evt.get('species')}")
        elif evt.get("phase") == "proteome_failed":
            log(f"  FAILED {evt.get('pid')}: {evt.get('reason')}")
    dl = sse(S, base + "/stream_download?mode=all&ids=" + ",".join(ids), on_event=on_dl)
    report["steps"]["download"] = {"downloaded": len(dl.get("downloaded", [])),
                                   "failed": len(dl.get("failed", [])),
                                   "empty": len(dl.get("empty", []))}
    if not dl.get("downloaded"):
        log("ERROR: nothing downloaded"); return 2

    # 2. OrthoFinder
    log("=== OrthoFinder ===")
    t0 = time.time()
    of_lines = sse_text(S, base + "/stream_orthofinder")
    of_ver = next((re.search(r"version (\S+)", l).group(1)
                   for l in of_lines if "OrthoFinder version" in l), None)
    elapsed = time.time() - t0
    log(f"  OrthoFinder done in {elapsed:.0f}s (version {of_ver})")
    of_failed = any("No 'Results_'" in l or "❌" in l for l in of_lines)
    report["steps"]["orthofinder"] = {"seconds": round(elapsed), "version": of_ver,
                                      "ok": not of_failed}
    if of_failed or elapsed < 3:
        log("ERROR: OrthoFinder did not produce orthogroups. Is `orthofinder` on PATH? "
            "(start the server with the conda env's bin on PATH). Aborting.")
        report["ok"] = False
        _emit(report, args.out, log)
        return 4

    # 2b. Activate the run. /stream_orthofinder saves the orthogroups to HISTORY
    # (it can't write the session from inside a streamed response), so we load the
    # just-created run into the active session — exactly what the UI does next.
    runs = S.get(base + "/api/history", timeout=60).json()
    run_id = runs[0]["id"] if runs else None
    log(f"=== load run {run_id} ===")
    if not run_id:
        log("ERROR: no run in history after OrthoFinder. Aborting.")
        report["ok"] = False; _emit(report, args.out, log); return 6
    S.get(base + f"/history/{run_id}/load", timeout=180)  # follows redirect → loads session
    report["run_id"] = run_id

    # 3. match species for GOA
    S.get(base + "/resultado_goa", timeout=120)
    sp = S.get(base + "/api/session_species_taxids", timeout=60).json().get("species", [])
    log(f"=== species matched: {len(sp)} ===")
    if not sp:
        log("ERROR: 0 species in session after OrthoFinder — orthogroups not loaded. Aborting.")
        report["ok"] = False
        _emit(report, args.out, log)
        return 5
    tax2url = load_taxid_to_url()
    species_to_url = {s["name"]: tax2url[s["taxon_id"]]
                      for s in sp if s.get("taxon_id") in tax2url}
    log(f"  with GOA: {len(species_to_url)} / {len(sp)}")
    report["steps"]["match"] = {"species": len(sp), "with_goa": len(species_to_url)}

    # 4. download GOA + build Excel
    log("=== download GOA files ===")
    goa = sse(S, None) if False else None
    with S.post(base + "/download_goa_files", json={"species_to_url": species_to_url},
                stream=True, timeout=1800) as r:
        last = {}
        for raw in r.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data:"):
                try:
                    evt = json.loads(raw[5:].strip())
                except json.JSONDecodeError:
                    continue
                if evt.get("phase") == "done":
                    last = evt; break
                if evt.get("phase") == "error":
                    log(f"  GOA error: {evt.get('reason')}"); last = evt; break
    report["steps"]["goa_download"] = {"success": last.get("success"),
                                       "downloaded": last.get("downloaded"),
                                       "failed": last.get("failed")}

    # 5. foreground / background / enrichment
    fg = sample_foreground_ids(args.fg_n)
    log(f"=== foreground (n={len(fg)}) ===")
    fr = S.post(base + "/foreground_analysis",
                json={"uniprot_ids": fg, "use_orthogroups": True, "single_copy_only": False},
                timeout=300).json()
    report["steps"]["foreground"] = {"input": len(fg),
                                     "expanded": len(fr.get("foreground_proteins", []))}
    S.post(base + "/background_analysis",
           json={"background_choice": "5", "use_orthogroups": False,
                 "single_copy_only": False, "custom_uniprot_ids": []}, timeout=300)
    log("=== GO enrichment ===")
    en = S.post(base + "/gene_ontology_analysis",
                json={"p_value": args.pvalue, "min_depth": 2,
                      "evidence_preset": "all", "counting_mode": "per_protein"},
                timeout=900).json()
    bp, cc, mf = en.get("bp_results", []), en.get("cc_results", []), en.get("mf_results", [])
    def top(results, k=5):
        return [{"GO": r.get("GO"), "name": r.get("name"),
                 "p_fdr_bh": r.get("p_fdr_bh"), "direction": r.get("direction")}
                for r in results[:k]]
    report["steps"]["enrichment"] = {
        "success": en.get("success"),
        "n_significant": {"BP": len(bp), "CC": len(cc), "MF": len(mf)},
        "top_BP": top(bp), "top_CC": top(cc), "top_MF": top(mf),
    }
    log(f"  significant: BP={len(bp)} CC={len(cc)} MF={len(mf)}")

    # A run is only OK if EVERY critical stage really happened: OrthoFinder ran,
    # species matched, GOA downloaded, and enrichment returned terms. This stops a
    # stale-data false positive (e.g. OrthoFinder silently missing from PATH).
    report["ok"] = bool(
        report["steps"]["orthofinder"]["ok"]
        and report["steps"]["match"]["with_goa"] > 0
        and report["steps"]["goa_download"].get("success")
        and en.get("success") and (bp or cc or mf)
    )
    _emit(report, args.out, log)
    return 0 if report["ok"] else 3


def _emit(report, out_path, log):
    out = json.dumps(report, indent=2, default=str)
    if out_path:
        Path(out_path).write_text(out)
        log(f"\nsummary written to {out_path}")
    log("\n===== SUMMARY =====")
    log(out)


if __name__ == "__main__":
    sys.exit(main())
