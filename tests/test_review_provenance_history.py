"""A run opened from the history shows its own provenance (blind study,
29-Oct-2026).

Opening a saved run copied its orthogroups to Proteomas/ but left there the
stamps of the last New Analysis, so the run showed that analysis's UniProt
release and OrthoFinder version.
"""
from __future__ import annotations

import json

from tests.test_review_provenance_snapshot import (  # noqa: F401  (fixture)
    _orthogroups_zip, _provenance, workdir)


def _saved_run(tmp_path, run_id, ids, proteome_ids, release, of_version):
    run = tmp_path / "runs" / run_id
    run.mkdir(parents=True)
    (run / "Orthogroups.zip").write_bytes(_orthogroups_zip(("Old_one", "Old_two")))
    proteome = {"source": "UniProt (rest.uniprot.org)", "release": release,
                "per_proteome": {pid: {"filename": f"{pid}.fasta", "source": "UniProtKB"}
                                 for pid in proteome_ids}}
    (run / "meta.json").write_text(json.dumps({
        "id": run_id, "species_ids": ids,
        "provenance": {"proteome": proteome, "orthofinder_version": of_version, "mode": "generated"}}))


def test_history_run_shows_its_own_provenance(workdir, tmp_path):
    c = workdir
    _saved_run(tmp_path, "20261020_000000", ["UP000000009", "UP000000008"],
               ["UP000000009", "UP000000008"], "2025_04", "2.5.4")
    assert c.get("/history/20261020_000000/load", follow_redirects=True).status_code == 200
    prov = _provenance(c)
    assert prov["proteome"]["release"] == "2025_04"
    assert prov["orthofinder_version"] == "2.5.4"
    # run_provenance/ now describes Proteomas/Orthogroups.zip, which is this run's.
    stamp = json.loads((tmp_path / "run_provenance" / "proteome_provenance.json").read_text())
    assert stamp["release"] == "2025_04"


def test_history_run_saved_with_another_runs_provenance_shows_none(workdir, tmp_path):
    # 2.2.0 could save the provenance of the analysis open during the run: a
    # record of other proteomes than the run's is not restored.
    c = workdir
    _saved_run(tmp_path, "20261021_000000", ["UP000000009", "UP000000008"],
               ["UP000000001", "UP000000002"], "2026_03", "2.5.5")
    assert c.get("/history/20261021_000000/load", follow_redirects=True).status_code == 200
    prov = _provenance(c)
    assert prov["proteome"] is None and prov["orthofinder_version"] is None
    assert not (tmp_path / "run_provenance" / "proteome_provenance.json").exists()
    page = c.get("/cargar_carpeta").get_data(as_text=True)
    assert "not recorded for this run" in page and "externally supplied" not in page
