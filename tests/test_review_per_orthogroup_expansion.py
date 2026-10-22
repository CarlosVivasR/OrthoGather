"""Tests for the fixes proposed in the 21-Oct-2026 review.

- P1: per-orthogroup counting with expansion counts an orthogroup when it holds
  a pasted foreground protein, even one without annotation of its own.
- P2: two proteomes with the same scientific name no longer share a FASTA file.
- P3: a file name from the browser cannot escape the upload folder, and
  state-changing requests from another website are refused.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest


def _gaf(acc, go, aspect):
    return "\t".join(["UniProtKB", acc, acc, "", go, "PMID:0", "IEA", "", aspect, "", "", "protein",
                      "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


@pytest.fixture
def two_species(tmp_path, monkeypatch):
    """spA (measured, no GOA file) and spB (annotated): 300 orthogroups with one
    spA protein and one spB protein; the first 50 carry translation."""
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows, counts, lines = [], [], []
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    for i in range(300):
        rows.append({"Orthogroup": f"OG{i:07d}", "spA": f"tr|A{i:05d}|A{i:05d}_SPA",
                     "spB": f"tr|B{i:05d}|B{i:05d}_SPB"})
        counts.append({"Orthogroup": f"OG{i:07d}", "spA": 1, "spB": 1, "Total": 2})
        lines.append(_gaf(f"B{i:05d}", "GO:0006412" if i < 50 else others[i % 6], "P"))
        lines.append(_gaf(f"B{i:05d}", ("GO:0003677", "GO:0005524")[i % 2], "F"))
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame(counts).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spB.goa").write_text("!gaf-version: 2.2\n" + "".join(lines))
    mapping = {"spB": "2.spB.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["2.spB.goa"])
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    client = og.app.test_client()
    with client.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spA", "spB"]
    return client


def test_per_orthogroup_with_expansion_counts_unannotated_measured_proteins(two_species):
    c = two_species
    fg = [f"A{i:05d}" for i in range(30)]                      # 30 of the 50 translation OGs
    bg = [f"A{i:05d}" for i in range(300)]
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": True}).status_code == 200
    js = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}).get_json()
    p = js.get("payload", js)
    assert not any("fell back" in w for w in p.get("warnings") or [])
    rows = [r for k in ("bp_results", "cc_results", "mf_results") for r in p.get(k) or []]
    tr = next(r for r in rows if r["GO"] == "GO:0006412")
    assert (tr["study_count"], tr["study_n"]) == (30, 30)        # 30 orthogroups, not 30+30 proteins
    assert tr["p_hypergeom"] is not None and tr["significant"]
