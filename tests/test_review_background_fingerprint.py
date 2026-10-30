"""The Provenance sheet fingerprints the pasted background in its order
(review of 30-Oct-2026).

Counted per orthogroup, the permutations draw from the background in the
order it was pasted, so the same list in another order gives other
permutation p-values (terms near the threshold can change). The method is
not changed; the Provenance sheet records a SHA-256 of the list as read, in
its order, so a run can be repeated exactly.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from tests.test_review_nonuniprot_ids import REF, UPI, three_species  # noqa: F401  (fixture)

KEY = "Background as pasted (SHA-256, in pasted order)"


def _fingerprint(c, fg, bg, expand, mode):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": expand}).status_code == 200
    assert c.post("/gene_ontology_analysis", json={"counting_mode": mode}).status_code == 200
    import app as og
    prov = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="Provenance")
    return dict(zip(prov["key"], prov["value"]))[KEY]


def test_the_fingerprint_is_the_list_in_its_order(three_species):
    bg = UPI + UPI[:3]        # duplicates are dropped, as the run reads them
    value = _fingerprint(three_species, UPI[:30], bg, True, "per_orthogroup")
    assert value.startswith(hashlib.sha256("\n".join(UPI).encode()).hexdigest() + " (300 identifiers")


def test_another_order_gives_another_fingerprint(three_species):
    a = _fingerprint(three_species, REF[:30], REF, False, "per_orthogroup")
    b = _fingerprint(three_species, REF[:30], REF[::-1], False, "per_orthogroup")
    assert a.split()[0] != b.split()[0]
