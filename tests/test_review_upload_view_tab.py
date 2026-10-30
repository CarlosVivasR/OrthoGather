"""The Protein Analysis tab keeps an uploaded analysis (independent review of
30-Oct-2026).

After an External Data Upload, the view tab of the Gene Ontology page links to
cargar_carpeta?filename=Orthogroups.zip&modo=upload. That request emptied
static/data_folder, the upload included, and extracted the bundled Preselected
Dataset there instead of showing the user's upload. It now shows the upload and
extracts nothing.
"""
from __future__ import annotations

import zipfile


def test_the_view_tab_of_an_upload_keeps_the_upload(monkeypatch, tmp_path):
    import app as og
    extracted = []
    # The route works in paths relative to the current folder: use a scratch one.
    monkeypatch.chdir(tmp_path)
    upload = tmp_path / "static" / "data_folder" / "upload"
    upload.mkdir(parents=True)
    (upload / "Orthogroups.tsv").write_text("Orthogroup\tspA\nOG0000000\tP00001\n")
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: extracted.append(a) or (_ for _ in ()).throw(OSError))
    og.app.test_client().get("/cargar_carpeta?filename=Orthogroups.zip&modo=upload")
    assert extracted == []
    assert (upload / "Orthogroups.tsv").exists()
