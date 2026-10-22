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


class _Resp:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code, self._payload, self.text, self.headers = status, payload, text, headers or {}

    def json(self):
        return self._payload


def test_same_scientific_name_gets_two_files(tmp_path, monkeypatch):
    import app as og
    monkeypatch.setattr(og, "PROTEOMES_FOLDER", str(tmp_path))
    og._fasta_owner.clear()

    def fake_get(url, timeout=None):
        if "/proteomes/" in url:
            return _Resp(200, {"taxonomy": {"scientificName": "Escherichia coli"},
                               "proteomeType": "Excluded", "proteinCount": 1})
        pid = url.split("upid:")[-1].rstrip(")") if "uniparc" in url else None
        return _Resp(200, text="" if pid is None else f">UPI_{pid}\nMKV\n")

    monkeypatch.setattr(og.requests, "get", fake_get)
    names = []
    for pid in ("UP000000001", "UP000000002"):
        res = [json.loads(e[6:]) for e in og._attempt_download_one(pid, 1)][-1]
        assert res["status"] == "saved"
        names.append(res["filename"])
    assert len(set(names)) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(names)
