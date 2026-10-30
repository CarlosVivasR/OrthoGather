"""The results Excel lists what is behind each term (blind study, 29-Oct-2026).

The BP, CC and MF sheets had the statistics only. Two columns are added at the
end, after the existing ones, which do not change: the proteins of the term
(its orthogroups or proteins in none, counted per orthogroup) and, per
orthogroup, the pasted foreground identifiers behind each one.
"""
from __future__ import annotations

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import REF, UPI, three_species  # noqa: F401  (fixture)

OLD = ["GO", "name", "NS", "Direction", "p_uncorrected", "p_fdr_bh", "-log10(FDR)", "fold_enrichment",
       "study_count", "study_n", "pop_count", "pop_n"]


def _run(c, fg, bg, expand, mode):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": expand}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": mode})
    assert r.status_code == 200, r.get_json()
    import app as og
    sheet = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="BP")
    return {t["GO"]: t for t in r.get_json()["bp_results"]}, sheet


def test_per_protein_lists_the_proteins_of_each_term(three_species):
    terms, sheet = _run(three_species, REF[:30], REF, False, "per_protein")
    assert list(sheet.columns[:len(OLD)]) == OLD
    assert list(sheet.columns[len(OLD):]) == ["study_items"]
    for _, row in sheet.iterrows():
        items = row["study_items"].split(", ")
        assert len(items) == row["study_count"]
        assert items == sorted(terms[row["GO"]]["study_items"])


def test_per_orthogroup_lists_the_orthogroups_and_the_pasted_ids_behind_them(three_species):
    terms, sheet = _run(three_species, UPI[:30], UPI, True, "per_orthogroup")
    assert list(sheet.columns[:len(OLD) + 1]) == OLD[:5] + ["p_hypergeom"] + OLD[5:]
    assert list(sheet.columns[len(OLD) + 1:]) == ["study_items", "pasted_ids_per_unit",
                                                  "pasted_ids_annotated_themselves",
                                                  "pasted_ids_through_orthologues_only"]
    row = sheet[sheet["GO"] == "GO:0006412"].iloc[0]
    units = row["study_items"].split(", ")
    assert len(units) == row["study_count"]
    behind = dict(part.split(": ") for part in row["pasted_ids_per_unit"].split("; "))
    assert sorted(behind) == units
    # Each orthogroup OGnnnnnnn holds the pasted UniParc protein UPI[n].
    assert all(behind[og] == UPI[int(og[2:])] for og in units)
