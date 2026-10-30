"""The note shown when no term is significant per orthogroup says why
(review of 30-Oct-2026).

It said the p-values came from shuffling labels, which is false with the
two-sided test (they are hypergeometric), and it blamed large families when
the cause was the number of permutations: the smallest permutation p is
1/(B+1), so with many terms or a strict threshold even the strongest term
cannot get a q below the threshold.
"""
from __future__ import annotations

from tests.test_review_nonuniprot_ids import UPI, three_species  # noqa: F401  (fixture)


def _notice(c, **opts):
    assert c.post("/foreground_analysis", json={"uniprot_ids": UPI[:30], "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": UPI,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup", **opts})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["notice"]


def test_a_threshold_below_the_permutation_floor_is_explained(three_species):
    n = _notice(three_species, p_value=1e-6)
    assert "come from shuffling" in n
    assert "a term at the smallest p-value reachable, 1/50,001, gets q = " in n
    assert "not below the threshold of 1e-06" in n


def test_the_two_sided_test_is_not_said_to_shuffle(three_species):
    n = _notice(three_species, p_value=1e-60, test_direction="two-sided")
    assert "shuffling" not in n
    assert "hypergeometric" in n


def test_no_testable_term_with_the_one_sided_test_is_not_called_two_sided(three_species):
    # No term within the size limits: no permutations either, but the test was
    # one-sided.
    n = _notice(three_species, min_term_size=400, max_term_size=500)
    assert "two-sided" not in n
