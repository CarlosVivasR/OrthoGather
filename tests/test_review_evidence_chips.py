"""The evidence chips of a term count the annotations the test used (review of
30-Oct-2026).

The chips counted only annotations to the term itself. A term is significant
through the annotations of its proteins to it or to any term below it (they
propagate over is_a and part_of), so in the article's example 15 of the 22
published terms showed no chips, as if nothing supported them. The p- and
q-values do not change.
"""
from __future__ import annotations

from tests.test_review_nonuniprot_ids import REF, UPI, three_species  # noqa: F401  (fixture)


def _terms(c, fg, bg, expand, mode):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": expand}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": mode})
    assert r.status_code == 200, r.get_json()
    p = r.get_json()
    return {t["GO"]: t for t in p["bp_results"] + p["mf_results"]}


def test_a_parent_term_counts_the_annotations_to_its_children(three_species):
    # The 30 foreground proteins are annotated (IEA) to translation, below
    # protein metabolic process; none to the parent itself.
    terms = _terms(three_species, REF[:30], REF, False, "per_protein")
    assert terms["GO:0019538"]["evidence_breakdown"] == {"IEA": 30}
    assert terms["GO:0010467"]["evidence_breakdown"] == {"IEA": 30}


def test_per_orthogroup_counts_the_members_annotations_to_children(three_species):
    terms = _terms(three_species, UPI[:30], UPI, True, "per_orthogroup")
    assert terms["GO:0019538"]["evidence_breakdown"] == {"IEA": 30}


def test_annotations_of_another_aspect_are_not_counted(three_species):
    # Each protein also has one MF annotation (IEA); a BP term counts only BP.
    terms = _terms(three_species, REF[:30], REF, False, "per_protein")
    assert sum(terms["GO:0008152"]["evidence_breakdown"].values()) == 30


def test_a_protein_counts_once_per_code(three_species):
    # The 30 proteins also get an IEA annotation to translational elongation,
    # below translation: still 30 proteins, not 60 annotations.
    import app as og
    path = f"{og.GOA_DOWNLOAD_FOLDER}/2.spRef.goa"
    from tests.test_review_nonuniprot_ids import _gaf
    with open(path, "a") as f:
        f.write("".join(_gaf(REF[i], "GO:0006414", "P") for i in range(30)))
    og._ID2GOS_CACHE.clear()
    terms = _terms(three_species, REF[:30], REF, False, "per_protein")
    assert terms["GO:0006412"]["evidence_breakdown"] == {"IEA": 30}
    assert terms["GO:0006412"]["study_count"] == 30
