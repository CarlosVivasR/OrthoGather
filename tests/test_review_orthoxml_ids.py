"""Test for the 22-Oct-2026 review: an OrthoXML file whose identifiers are not
UniProt accessions (OMA, OrthoDB and Ensembl write their own) is imported, and
the results page says that GO enrichment and the protein filter will not find
them. A file with UniProt accessions shows no note.
"""
from __future__ import annotations

import io

import pytest

TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<orthoXML xmlns="http://orthoXML.org/2011/" origin="test" originVersion="1" version="0.5">
  <species name="Escherichia coli" NCBITaxId="83333">
    <database name="db" version="1"><genes>
      <gene id="1" protId="{a1}"/><gene id="2" protId="{a2}"/>
    </genes></database>
  </species>
  <species name="Salmonella enterica" NCBITaxId="99287">
    <database name="db" version="1"><genes>
      <gene id="3" protId="{b1}"/><gene id="4" protId="{b2}"/>
    </genes></database>
  </species>
  <groups>
    <orthologGroup id="1"><geneRef id="1"/><geneRef id="3"/></orthologGroup>
    <orthologGroup id="2"><geneRef id="2"/><paralogGroup><geneRef id="4"/></paralogGroup></orthologGroup>
  </groups>
</orthoXML>
"""


@pytest.mark.parametrize("ids,note", [
    (dict(a1="ECOLI03899", a2="ECOLI00001", b1="SALTY01234", b2="SALTY00002"), True),
    (dict(a1="P0A6F5", a2="P0A6F9", b1="P0A1D3", b2="Q8ZKX5"), False),
])
def test_orthoxml_identifiers_that_are_not_uniprot_are_reported(tmp_path, monkeypatch, ids, note):
    import app as og
    monkeypatch.chdir(tmp_path)
    c = og.app.test_client()
    xml = TEMPLATE.format(**ids).encode()
    r = c.post("/cargar_carpeta", headers={"Origin": "http://localhost"},
               content_type="multipart/form-data",
               data={"file": (io.BytesIO(xml), "export.orthoxml"), "modo": "upload"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert ('id="upload-id-note"' in html) is note
    if note:
        assert "4 of the 4 identifiers" in html and "ECOLI03899" in html
    tsv = (tmp_path / "static" / "data_folder" / "upload" / "Orthogroups.tsv").read_text()
    assert len(tsv.strip().splitlines()) == 3      # header + two orthogroups
