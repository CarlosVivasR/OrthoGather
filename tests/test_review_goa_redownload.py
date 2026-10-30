"""Sets loaded before the GOA files are downloaded again are not used
(review of 30-Oct-2026).

Downloading the GOA files rewrites the GO Excel the sets are built from, but
the sets loaded before stayed and Run stayed enabled: a run then answered
with the old sets, and said that identifiers with annotation had none. The
server now refuses a run whose sets were loaded from an earlier Excel, and the
page marks them as not loaded when a download finishes.
"""
from __future__ import annotations

import os

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)


def _load(c):
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": REF}).status_code == 200


def _redownload():
    import app as og
    path = os.path.join(og.RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))   # rewritten


def test_a_run_with_sets_from_the_previous_download_is_refused(three_species):
    c = three_species
    _load(c)
    _redownload()
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"})
    assert r.status_code == 400
    assert r.get_json()["error_code"] == "ERR_SETS_CHANGED"
    assert "downloaded again" in r.get_json()["message"]
    _load(c)
    assert c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).status_code == 200


def test_the_page_marks_the_sets_as_not_loaded_after_a_download():
    page = open("templates/resultado_goa.html").read()
    assert 'dispatchEvent(new CustomEvent("goa-downloaded"))' in page
    assert 'addEventListener("goa-downloaded"' in page
