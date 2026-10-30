"""The results file records the foreground and the identifiers left out
(review of 30-Oct-2026).

The page lists the pasted foreground identifiers that did not enter the test
and why, but the results file did not, and nothing in it identified the
foreground list. The Provenance sheet now has a SHA-256 of the foreground as
read and a summary of the identifiers not tested, listed in a new sheet.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


def test_the_foreground_and_its_untested_identifiers_are_recorded(three_species):
    c = three_species
    fg = REF[:30] + ["Q99999"]
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"})
    assert r.status_code == 200
    import app as og
    path = f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx"
    prov = dict(pd.read_excel(path, sheet_name="Provenance")[["key", "value"]].values)
    assert prov["Foreground as pasted (SHA-256, in pasted order)"].startswith(
        hashlib.sha256("\n".join(fg).encode()).hexdigest())
    assert prov["Foreground identifiers not tested"] == (
        r.get_json()["input_ids"]["summary"] + " Listed in the sheet 'Untested identifiers'.")
    sheet = pd.read_excel(path, sheet_name="Untested identifiers")
    assert list(sheet["identifier"]) == [u["id"] for u in r.get_json()["input_ids"]["untested"]]
    assert "Q99999" in set(sheet["identifier"])


def test_no_untested_sheet_when_every_identifier_is_tested(three_species):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200
    assert c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).status_code == 200
    import app as og
    assert "Untested identifiers" not in pd.ExcelFile(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx").sheet_names
