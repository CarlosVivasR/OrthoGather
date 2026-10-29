"""The Provenance sheet states the smallest q a per-orthogroup run can reach
(blind study, 29-Oct-2026).

Per-orthogroup p-values come from B shuffles, so the smallest is 1/(B+1), and a
term there gets q = m/(k(B+1)), with m terms in the correction family and k of
them at that p. The study saw strong terms stop at q ~ 6e-4 to 1e-3 with no
explanation. The number of shuffles does not change.
"""
from __future__ import annotations

import re

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, UPI, three_species  # noqa: F401  (fixture)

KEY = "Smallest q reachable (per-orthogroup permutations)"


def _provenance(c, fg, bg, expand, mode):
    import app as og
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": expand}).status_code == 200
    assert c.post("/gene_ontology_analysis", json={"counting_mode": mode}).status_code == 200
    prov = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="Provenance")
    return dict(zip(prov["key"], prov["value"]))


def test_per_orthogroup_run_states_the_q_floor(three_species):
    p = _provenance(three_species, UPI[:30], UPI, True, "per_orthogroup")
    m = int(p["Terms in correction family"])
    b = int(re.search(r"permutation: (\d+) shuffles", p["Per-orthogroup p-values"]).group(1))
    assert b == 5000                      # unchanged: 2m/alpha, bounded to 5,000-50,000
    assert p[KEY].startswith(f"{m / (b + 1):.2g} ")
    assert f"1/{b + 1}" in p[KEY]


def test_per_protein_run_has_no_q_floor_row(three_species):
    assert KEY not in _provenance(three_species, REF[:30], REF, False, "per_protein")
