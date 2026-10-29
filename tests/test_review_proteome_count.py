"""The results page counts proteomes, and says how many species they are
(video review, 29-Oct-2026).

Figure 2 said "47 species" for the Preselected Dataset, which has 47
proteomes of 35 species (six strains of Pseudomonas aeruginosa, five of
Acinetobacter baumannii...). The figure itself does not change.
"""
from __future__ import annotations

import re

from tests.test_review_provenance_snapshot import _orthogroups_zip, workdir  # noqa: F401  (fixture)

NAMES = ("E.Coli K12", "E.Coli O157H7", "Bacillus_subtilis_(strain_168)")


def test_results_page_counts_proteomes_and_species(workdir, tmp_path):
    (tmp_path / "static").mkdir(exist_ok=True)
    (tmp_path / "static" / "Orthogroups.zip").write_bytes(_orthogroups_zip(NAMES))
    html = workdir.get("/cargar_carpeta?filename=Orthogroups.zip&modo=preselected").get_data(as_text=True)
    assert "Protein Analysis results — 3 proteomes of 2 species" in html
    assert "window.PROTEOME_COUNT = 3;" in html and "window.DISTINCT_SPECIES = 2;" in html
    assert "SPECIES_COUNT" not in html
    assert re.search(r"value: String\(N\),\s*label: 'proteomes'", html)
    assert "label: 'species'" in html          # shown when the proteomes are fewer species


def test_distinct_species_filter():
    import app as og
    assert og._n_distinct_species(["Total", *NAMES, "IS27"]) == 3
