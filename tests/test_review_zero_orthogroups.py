"""An expansion that finds no orthogroup is an error, not a success (blind
study, 29-Oct-2026).

Before 2.2.1 the page said "Foreground saved: 70 identifiers ... You can run the
GO enrichment now" with 0 orthogroups, and the run then failed with "Foreground
missing" and the hint "Load the foreground", which the user had just done.
"""
from __future__ import annotations

from tests.test_review_nonuniprot_ids import REF, UPI, three_species  # noqa: F401  (fixture)

MISSING = ["NOPE_1", "NOPE_2", "NOPE_3"]


def test_expanded_foreground_without_orthogroups_is_an_error(three_species):
    c = three_species
    r = c.post("/foreground_analysis", json={"uniprot_ids": MISSING, "use_orthogroups": True})
    assert r.status_code == 400
    js = r.get_json()
    assert js["success"] is False
    assert "None of your 3 identifiers is in the orthogroups of this analysis" in js["message"]
    assert "NOPE_1" in js["message"]
    with c.session_transaction() as s:
        assert not s.get("foreground_proteins")


def test_expanded_background_without_orthogroups_is_an_error(three_species):
    c = three_species
    r = c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": MISSING,
                                             "use_orthogroups": True})
    assert r.status_code == 400
    js = r.get_json()
    assert "None of your 3 identifiers is in the orthogroups of this analysis" in js["message"]
    with c.session_transaction() as s:
        assert not s.get("background_ids")


def test_a_failed_load_replaces_the_previous_foreground(three_species):
    # The set on screen and the set on the server must not diverge: after a
    # failed load there is no foreground, and the run says why.
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": UPI[:30], "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": UPI,
                                                "use_orthogroups": True}).status_code == 200
    assert c.post("/foreground_analysis", json={"uniprot_ids": MISSING, "use_orthogroups": True}).status_code == 400
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 400
    js = r.get_json()
    assert js["message"] == "Foreground missing"
    assert "last 'Load foreground' failed" in js["hint"]
    assert "None of your 3 identifiers" in js["hint"]


def test_foreground_missing_hint_when_nothing_was_loaded(three_species):
    r = three_species.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"})
    js = r.get_json()
    assert r.status_code == 400 and js["message"] == "Foreground missing"
    assert "click 'Load foreground'" in js["hint"]


def test_valid_ids_load_as_before(three_species):
    c = three_species
    r = c.post("/foreground_analysis", json={"uniprot_ids": REF[:30], "use_orthogroups": True})
    assert r.status_code == 200 and r.get_json()["foreground_proteins"] == sorted(REF[:30])
    r = c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": REF,
                                             "use_orthogroups": True})
    assert r.status_code == 200 and r.get_json()["background_ids"] == sorted(REF)


def test_go_page_errors_carry_their_codes(three_species):
    c = three_species
    js = c.post("/foreground_analysis", json={"uniprot_ids": MISSING, "use_orthogroups": True}).get_json()
    assert js["error_code"] == "ERR_IDS_NOT_IN_ORTHOGROUPS"
    js = c.post("/gene_ontology_analysis", json={}).get_json()
    assert js["error_code"] == "ERR_FOREGROUND_MISSING"
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    js = c.post("/gene_ontology_analysis", json={}).get_json()
    assert js["error_code"] == "ERR_BACKGROUND_MISSING"
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": REF}).status_code == 200
    js = c.post("/gene_ontology_analysis", json={"sets": {"foreground": {"uniprot_ids": REF[:5]},
                                                         "background": {"background_choice": "4",
                                                                        "custom_uniprot_ids": REF}}}).get_json()
    assert js["error_code"] == "ERR_SETS_CHANGED"
