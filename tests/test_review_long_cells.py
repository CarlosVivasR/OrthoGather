"""Orthogroup cells longer than an Excel cell (review of 30-Oct-2026).

An Excel cell holds at most 32,767 characters and the writer cuts longer ones,
while the expansion and per-orthogroup counting read the orthogroups from the
GO Excel. The members of a family of more than ~1,200 proteins of one species
past the cut were not found: an expansion missed them, and one could come back
as a partial identifier. The cells are now read from Orthogroups.tsv, the file
the Excel was built from.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import _gaf

N = 300
REF = [f"B{i:05d}" for i in range(N)]
BIG = [f"UPI{i:010X}" for i in range(1, 3001)]        # one family of 3,000 in spUPI
OTHER = [f"UPI{i:010X}" for i in range(5001, 5001 + N)]


@pytest.fixture
def big_family(tmp_path, monkeypatch):
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows = [{"Orthogroup": f"OG{i:07d}", "spRef": f"tr|{REF[i]}|{REF[i]}_SPREF",
             "spUPI": ", ".join(BIG) if i == 0 else OTHER[i]} for i in range(N)]
    assert len(rows[0]["spUPI"]) > 32767
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": r["Orthogroup"], "spRef": 1, "spUPI": 1, "Total": 2}
                  for r in rows]).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spRef.goa").write_text("!gaf-version: 2.2\n" + "".join(
        _gaf(REF[i], "GO:0006412" if i < 50 else "GO:0055085", "P") for i in range(N)))
    mapping = {"spRef": "2.spRef.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["2.spRef.goa"])
    with pytest.warns(UserWarning):     # the Excel writer cuts the cell
        generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                          str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    c = og.app.test_client()
    with c.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spRef", "spUPI"]
    return c


def test_a_member_past_the_excel_limit_is_found(big_family):
    c = big_family
    r = c.post("/foreground_analysis", json={"uniprot_ids": [BIG[-1]], "use_orthogroups": True})
    assert r.status_code == 200, r.get_json()
    with c.session_transaction() as s:
        assert s["selected_orthogroups"] == ["OG0000000"]


def test_per_orthogroup_counting_puts_it_in_its_orthogroup(big_family):
    c = big_family
    fg = BIG[-40:]
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": BIG + OTHER,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup", "display_p_value": 1.0})
    assert r.status_code == 200, r.get_json()
    # All 40 pasted proteins are one unit, OG0000000, with spRef's translation.
    assert r.get_json()["annotation_stats"]["foreground_units"] == 1


def test_the_excel_says_which_cells_it_cut(big_family):
    import app as og
    meta = pd.read_excel(f"{og.RESULTS_FOLDER}/Gene_Ontology_Analysis.xlsx", sheet_name="Meta")
    row = dict(zip(meta["key"], meta["value"]))
    assert row["Cells cut to 32,767 characters"].startswith("1 cell(s) of the orthogroup sheets")


def test_an_excel_without_long_cells_has_no_such_row(tmp_path):
    from orthogather.core.excel import generate_go_excel
    tsv = tmp_path / "Orthogroups.tsv"
    pd.DataFrame([{"Orthogroup": "OG0000000", "spRef": "tr|B00000|X"}]).to_csv(tsv, sep="\t", index=False)
    out = tmp_path / "go.xlsx"
    generate_go_excel(str(tsv), {"spRef": "2.spRef.goa"}, str(out), annotated_ids=set())
    meta = pd.read_excel(out, sheet_name="Meta")
    assert "Cells cut to 32,767 characters" not in set(meta["key"])
