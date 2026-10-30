"""The GO Excel of one analysis is never read for another (review of
30-Oct-2026).

Gene_Ontology_Analysis.xlsx is one file in the results folder. Opening
another analysis (from the history or an upload) left the previous one's, and
loading the sets read its orthogroups: an expansion used the orthogroups of
analysis A on analysis B. The Excel now records the analysis it was built
for (Orthogroups.tsv and the GOA mapping), and every reader refuses another.
"""
from __future__ import annotations

import json
import shutil

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


def _other_analysis(c, tmp_path, regroup):
    """Analysis B: the same proteins, P0 and P1 in separate orthogroups."""
    with c.session_transaction() as s:
        a = s["folder_path"]
    b = tmp_path / "analysisB"
    shutil.copytree(a, b)
    if regroup:
        df = pd.read_csv(b / "Orthogroups.tsv", sep="\t")
        df = df.iloc[1:]           # B: one orthogroup fewer
        df.to_csv(b / "Orthogroups.tsv", sep="\t", index=False)
    with c.session_transaction() as s:
        s["folder_path"] = str(b)
    return b


def test_loading_a_set_on_another_analysis_is_refused(three_species, tmp_path):
    c = three_species
    _other_analysis(c, tmp_path, regroup=True)
    for route, body in (("/foreground_analysis", {"uniprot_ids": REF[:5], "use_orthogroups": True}),
                        ("/background_analysis", {"background_choice": "4", "custom_uniprot_ids": REF})):
        r = c.post(route, json=body)
        assert r.status_code == 409
        assert r.get_json()["error_code"] == "ERR_GO_ANALYSIS_EXCEL_STALE"
    assert c.post("/generate_go_image").status_code == 409
    assert c.get("/download_go_excel").status_code == 409


def test_a_run_after_opening_another_analysis_is_refused(three_species, tmp_path):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    _other_analysis(c, tmp_path, regroup=True)
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"})
    assert r.status_code == 409
    assert r.get_json()["error_code"] == "ERR_GO_ANALYSIS_EXCEL_STALE"


def test_the_same_analysis_in_another_folder_is_accepted(three_species, tmp_path):
    # Reopening an analysis copies the same orthogroups: the Excel still fits.
    c = three_species
    _other_analysis(c, tmp_path, regroup=False)
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:5], "use_orthogroups": True}).status_code == 200


def test_another_goa_mapping_is_another_analysis(three_species, tmp_path):
    c = three_species
    b = _other_analysis(c, tmp_path, regroup=False)
    (b / "goa_mapping.json").write_text(json.dumps({}))
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:5]}).status_code == 409
