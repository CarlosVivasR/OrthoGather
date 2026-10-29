"""The provenance of an analysis is its own, however it was loaded (blind
study, 29-Oct-2026).

The stamps a New Analysis writes to Proteomas/ (UniProt release, OrthoFinder
version) were copied into every analysis loaded afterwards, so the Provenance
sheet of an External Upload declared "UniProt 2026_03 / OrthoFinder 2.5.5".
"""
from __future__ import annotations

import io

from tests.test_review_provenance_snapshot import (  # noqa: F401  (fixture)
    _orthogroups_zip, _provenance, workdir)


def test_upload_does_not_take_the_stamps_of_a_new_analysis(workdir):
    c = workdir
    r = c.post("/cargar_carpeta", content_type="multipart/form-data",
               data={"file": (io.BytesIO(_orthogroups_zip(("Mine_one", "Mine_two"))), "mine.zip")})
    assert r.status_code == 200
    prov = _provenance(c)
    assert prov["mode"] == "upload"
    assert prov["proteome"] is None
    assert prov["orthofinder_version"] is None


def test_generated_analysis_keeps_its_stamps(workdir):
    c = workdir
    r = c.post("/cargar_carpeta", data={"modo": "generated"})
    assert r.status_code == 200
    prov = _provenance(c)
    assert prov["proteome"]["release"] == "2026_03"
    assert prov["orthofinder_version"] == "2.5.5"


def test_preselected_dataset_does_not_take_the_stamps_of_a_new_analysis(workdir, tmp_path):
    c = workdir
    (tmp_path / "static").mkdir(exist_ok=True)
    (tmp_path / "static" / "Orthogroups.zip").write_bytes(_orthogroups_zip(("Pre_one", "Pre_two")))
    r = c.get("/cargar_carpeta?filename=Orthogroups.zip&modo=preselected")
    assert r.status_code == 200
    prov = _provenance(c)
    assert prov["proteome"] is None and prov["orthofinder_version"] is None
