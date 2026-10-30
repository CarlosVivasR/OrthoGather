"""The results Excel marks the terms that are not significant (review of
30-Oct-2026).

With a display threshold looser than the significance threshold, the BP, CC
and MF sheets (and the CSV/TSV exports made from them) listed the extra terms
like findings, while the chart draws them hollow and the table marks them
"n.s.". A "significant" column now says which are.
"""
from __future__ import annotations

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


def test_terms_shown_below_the_threshold_are_marked(three_species):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein", "p_value": 1e-10,
                                               "display_p_value": 1.0})
    assert r.status_code == 200
    import app as og
    sheet = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="BP")
    assert set(sheet["significant"]) == {True, False}
    assert (sheet["significant"] == (sheet["p_fdr_bh"] < 1e-10)).all()
    page = {t["GO"]: t["significant"] for t in r.get_json()["bp_results"]}
    assert dict(zip(sheet["GO"], sheet["significant"])) == page
