"""The provenance stamps are kept out of OrthoFinder's input folder (video
review, 29-Oct-2026).

They were written to Proteomas/, the folder OrthoFinder reads, so every run
warned that proteome_provenance.json "is not a FASTA file".
"""
from __future__ import annotations

import json

from tests.test_review_provenance_history import _saved_run
from tests.test_review_provenance_snapshot import STAMP, workdir  # noqa: F401  (fixture)


def test_opening_a_run_leaves_only_orthogroups_in_proteomas(workdir, tmp_path):
    _saved_run(tmp_path, "20261020_000000", ["UP000000009"], ["UP000000009"], "2025_04", "2.5.4")
    assert workdir.get("/history/20261020_000000/load", follow_redirects=True).status_code == 200
    assert sorted(p.name for p in (tmp_path / "Proteomas").iterdir()) == ["Orthogroups.zip"]
    assert sorted(p.name for p in (tmp_path / "run_provenance").iterdir()) == [
        "history_run.json", "orthofinder_provenance.json", "proteome_provenance.json"]


def test_cleanup_moves_the_stamps_of_older_versions_out_of_proteomas(tmp_path, monkeypatch):
    from orthogather.core.history import cleanup_temp_run
    monkeypatch.chdir(tmp_path)
    prot = tmp_path / "Proteomas"
    prot.mkdir()
    (prot / "proteome_provenance.json").write_text(json.dumps(STAMP))
    (prot / "Alpha_beta.fasta").write_text(">a\nMK\n")
    (prot / "Orthogroups.zip").write_bytes(b"zip")
    cleanup_temp_run()
    assert sorted(p.name for p in prot.iterdir()) == ["Orthogroups.zip"]
    assert json.loads((tmp_path / "run_provenance" / "proteome_provenance.json").read_text()) == STAMP


def test_provenance_of_a_new_run_is_read_from_run_provenance(workdir):
    import app as og
    from flask import session
    with og.app.test_request_context():
        session["folder_path"] = None
        prov = og.build_provenance()
    assert prov["proteome"]["release"] == "2026_03" and prov["orthofinder_version"] == "2.5.5"
