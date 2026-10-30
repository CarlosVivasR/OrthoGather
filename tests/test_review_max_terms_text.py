"""max_terms sent as text is applied (review of 30-Oct-2026).

A max_terms of "1" was ignored, every term was returned, and the Provenance
sheet said "Max terms per namespace: 1". The page sends a number; other
callers may send text.
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


@pytest.mark.parametrize("value, shown, recorded", [(1, 1, 1), ("1", 1, 1), ("all", None, "all")])
def test_max_terms(three_species, value, shown, recorded):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein", "max_terms": value})
    assert r.status_code == 200
    bp = r.get_json()["bp_results"]
    assert len(bp) == shown if shown else len(bp) > 1
    import app as og
    prov = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="Provenance")
    assert str(dict(zip(prov["key"], prov["value"]))["Max terms per namespace"]) == str(recorded)
