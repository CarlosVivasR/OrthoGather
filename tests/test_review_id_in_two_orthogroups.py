"""An identifier in two orthogroups (review of 30-Oct-2026).

UniParc names a sequence, so identical proteins of two strains that
OrthoFinder placed in different orthogroups give one identifier in both: six
UPI of the Preselected Dataset. Counted per orthogroup, the protein took the
orthogroup of the last row read, so the result hung on the row order of
Orthogroups.tsv, and nothing said so. Now it is the orthogroup with the highest
ID, the one the usual order already gave, and the run says which proteins.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import _gaf

N = 300
REF = [f"B{i:05d}" for i in range(N)]
UPI = [f"UPI{i:010X}" for i in range(1, N + 1)]


def _workspace(tmp_path, monkeypatch, reverse):
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    rows = [{"Orthogroup": f"OG{i:07d}", "spRef": f"tr|{REF[i]}|{REF[i]}_SPREF", "spUPI": UPI[i]}
            for i in range(N)]
    rows[-1]["spUPI"] = f"{UPI[-1]}, {UPI[0]}"     # UPI[0] also in the last orthogroup
    if reverse:
        rows = rows[::-1]
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": r["Orthogroup"], "spRef": 1, "spUPI": 1, "Total": 2}
                  for r in rows]).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spRef.goa").write_text("!gaf-version: 2.2\n" + "".join(
        _gaf(REF[i], "GO:0006412" if i < 50 else others[i % 6], "P") for i in range(N)))
    mapping = {"spRef": "2.spRef.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["2.spRef.goa"])
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    c = og.app.test_client()
    with c.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spRef", "spUPI"]
    assert c.post("/foreground_analysis", json={"uniprot_ids": UPI[:30], "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": UPI,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.mark.parametrize("reverse", [False, True], ids=["usual_order", "reversed_rows"])
def test_the_protein_is_counted_in_the_orthogroup_with_the_highest_id(tmp_path, monkeypatch, reverse):
    p = _workspace(tmp_path, monkeypatch, reverse)
    translation = next(t for t in p["bp_results"] if t["GO"] == "GO:0006412")
    # UPI[0] counts in OG0000299, not in OG0000000 (translation).
    assert "OG0000000" not in translation["study_items"]
    assert translation["study_count"] == 29
    assert any(w.startswith("1 of the proteins in this test (UPI0000000001) are in more than one "
                            "orthogroup") for w in p["warnings"])
