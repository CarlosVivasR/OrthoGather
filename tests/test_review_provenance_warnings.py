"""The Provenance sheet records the run's warnings (review of 30-Oct-2026).

A results file did not say what the page had warned (an unsuitable universe,
"Do not rely on these results", a low-power test), and the warning that the GO
ontology and the GOA files differ in version was computed after the file was
written. Every warning of the run is now a "Warning" row, and the scope of
'Use all GOA files' has its own row.
"""
from __future__ import annotations

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


def _provenance():
    import app as og
    prov = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="Provenance")
    return list(zip(prov["key"], prov["value"]))


def test_every_warning_of_the_run_is_in_the_file(three_species):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:3]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein", "display_p_value": 1.0})
    assert r.status_code == 200
    warnings = r.get_json()["warnings"]
    assert any(w.startswith("Only 3 foreground unit(s)") for w in warnings)
    assert [v for k, v in _provenance() if k == "Warning"] == warnings


def test_the_scope_of_use_all_goa_files_is_recorded(three_species):
    c = three_species
    assert c.post("/background_analysis", json={"background_choice": "5"}).status_code == 200
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).status_code == 200
    assert ("'Use all GOA files' universe (goa_all_scope)", "foreground_species") in _provenance()
