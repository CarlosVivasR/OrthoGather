"""Tests for the fixes proposed in the 21-Oct-2026 review.

- P1: per-orthogroup counting with expansion counts an orthogroup when it holds
  a pasted foreground protein, even one without annotation of its own.
- P2: two proteomes with the same scientific name no longer share a FASTA file.
- P3: a file name from the browser cannot escape the upload folder, and
  state-changing requests from another website are refused.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest


def test_upload_name_cannot_escape_and_foreign_origin_is_refused(tmp_path, monkeypatch):
    import app as og
    monkeypatch.chdir(tmp_path)
    c = og.app.test_client()
    xml = b'<?xml version="1.0"?><orthoXML xmlns="http://orthoXML.org/2011/" version="0.3"></orthoXML>'
    r = c.post("/cargar_carpeta", headers={"Origin": "https://evil.example"},
               content_type="multipart/form-data", data={"file": (io.BytesIO(xml), "../../../escape.xml")})
    assert r.status_code == 403
    c.post("/cargar_carpeta", headers={"Origin": "http://localhost"},
           content_type="multipart/form-data", data={"file": (io.BytesIO(xml), "../../../escape.xml")})
    assert not (tmp_path / "escape.xml").exists()
    assert (tmp_path / "static" / "data_folder" / "upload" / "escape.xml").exists()
    assert c.post("/history/20260101_000000/delete", headers={"Origin": "https://evil.example"}).status_code == 403
