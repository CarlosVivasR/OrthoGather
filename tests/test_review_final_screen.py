"""Tests for the final review (22-Oct-2026) of what the Gene Ontology page shows.

- Counted per orthogroup, the coverage banner reports the pasted proteins that
  entered the test and the units, not the proteins of the expanded sets (which
  read "0% of foreground with GO annotations" for a species without a GOA file
  even when the test ran).
- "Single-copy only" acts when an expanded set is loaded; if it is changed
  afterwards the run says so instead of using the old filter.
- The evidence breakdown of a per-orthogroup term counts the annotated
  background proteins behind its units.
"""
from __future__ import annotations

from pathlib import Path

from tests.test_review_expansion_counting import A, B, two_species  # noqa: F401  (fixture)


def _load(c, fg, bg, fg_expand=False, bg_expand=False, single_copy=False):
    r = c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": fg_expand,
                                             "single_copy_only": single_copy})
    assert r.status_code == 200, r.get_json()
    r = c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                             "use_orthogroups": bg_expand,
                                             "single_copy_only": single_copy})
    assert r.status_code == 200, r.get_json()


def test_banner_reports_tested_proteins_and_units(two_species):
    c = two_species
    _load(c, A[:30], A, True, True)          # spA has no GOA file
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}).get_json()
    s = p["annotation_stats"]
    assert s["counting"] == "per_orthogroup"
    assert s["tested_proteins"] == 30       # no annotation of their own, tested through their orthogroups
    assert s["foreground_units"] == p["counting"]["foreground_units"] == 30
    assert s["background_units"] == p["counting"]["background_units"] == 300
    assert s["background_proteins"] == 300


def test_banner_per_protein_has_no_unit_fields(two_species):
    c = two_species
    _load(c, B[:30], B)
    s = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).get_json()["annotation_stats"]
    assert "counting" not in s and s["with_annotations"] == 30


def test_orthogroup_filter_changed_after_loading_is_reported(two_species):
    c = two_species
    _load(c, A[:30], A, True, True, single_copy=False)
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup", "single_copy_only": True})
    assert r.status_code == 400
    assert "Load the foreground and the background again" in r.get_json()["hint"]
    # The same filter as when loaded runs.
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup", "single_copy_only": False})
    assert r.status_code == 200
    # Without expansion the filter does not act, so it is not checked.
    _load(c, B[:30], B)
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein", "single_copy_only": True})
    assert r.status_code == 200


def test_per_orthogroup_evidence_breakdown_counts_background_members(two_species):
    c = two_species
    _load(c, A[:30], A, True, True)
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}).get_json()
    t = next(t for k in ("bp_results", "cc_results", "mf_results") for t in p[k] if t["GO"] == "GO:0006412")
    # 30 foreground orthogroups, each with one annotated spB protein carrying IEA.
    assert t["evidence_breakdown"] == {"IEA": 30}


def test_page_sends_the_orthogroup_filter_and_explains_the_options():
    html = (Path(__file__).resolve().parents[1] / "templates" / "resultado_goa.html").read_text()
    assert "single_copy_only: readSingleCopyOnly()," in html      # the run sends it
    assert "renderOrthogroupBanner" in html
    assert "proteins without annotations of their own are tested through" in html
