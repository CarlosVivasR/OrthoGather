"""Pasted proteins that carry a term themselves, and those that only get it
through their orthologues (review of 30-Oct-2026).

Counted per orthogroup with expanded sets, a term listed "OG0001234:
IS27_00012" without saying that IS27_00012 has no such annotation: an
orthologue in another species has it. The Excel adds two columns and the
table a count; nothing else changes.
"""
from __future__ import annotations

import pandas as pd

from tests.test_review_nonuniprot_ids import OWN, REF, three_species  # noqa: F401  (fixture)

ADDED = ["pasted_ids_annotated_themselves", "pasted_ids_through_orthologues_only"]


def _run(c, fg, bg):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200, r.get_json()
    import app as og
    sheet = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="BP").fillna("")
    return {t["GO"]: t for t in r.get_json()["bp_results"]}, sheet.set_index("GO")


def test_ids_without_annotation_get_the_term_through_orthologues(three_species):
    # spOwn has no GOA file: each of its proteins has translation only through
    # its spRef orthologue.
    terms, sheet = _run(three_species, OWN[:30], OWN)
    assert list(sheet.columns[-3:-1]) == ADDED
    row = sheet.loc["GO:0006412"]
    assert row["pasted_ids_annotated_themselves"] == ""
    assert row["pasted_ids_through_orthologues_only"].split(", ") == sorted(OWN[:30])
    assert (terms["GO:0006412"]["pasted_own"], terms["GO:0006412"]["pasted_through_orthologues"]) == (0, 30)


def test_annotated_ids_carry_the_term_and_its_parents_themselves(three_species):
    terms, sheet = _run(three_species, REF[:30], REF)
    for go in ("GO:0006412", "GO:0019538"):  # translation, and a term above it
        assert sheet.loc[go, "pasted_ids_annotated_themselves"].split(", ") == sorted(REF[:30])
        assert sheet.loc[go, "pasted_ids_through_orthologues_only"] == ""
        assert (terms[go]["pasted_own"], terms[go]["pasted_through_orthologues"]) == (30, 0)


def test_per_protein_has_no_split(three_species):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": REF}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).get_json()
    assert all("pasted_own" not in t for t in r["bp_results"])
