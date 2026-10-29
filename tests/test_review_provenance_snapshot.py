"""The history snapshot of a New Analysis records that analysis, not the one
open in the browser while it ran (blind study, 29-Oct-2026).

The snapshot read the stamps of the open analysis first, so the meta.json of
the study 1 run (Pseudomonas) recorded the proteomes of study 3 (Bacillus).
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from flask import session

STAMP = {"source": "UniProt (rest.uniprot.org)", "release": "2026_03",
         "release_date": "02-September-2026", "n_proteomes": 2,
         "per_proteome": {"UP000000001": {"filename": "Alpha_beta.fasta", "source": "UniProtKB"},
                          "UP000000002": {"filename": "Gamma_delta.fasta", "source": "UniProtKB"}}}


def _orthogroups_zip(species=("Alpha_beta", "Gamma_delta")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Orthogroups.tsv", "Orthogroup\t" + "\t".join(species) + "\n"
                   "OG0000000\t" + "\t".join(f"tr|P{i:05d}|X" for i in range(len(species))) + "\n")
        z.writestr("Orthogroups.GeneCount.tsv", "Orthogroup\t" + "\t".join(species) + "\tTotal\n"
                   "OG0000000\t" + "\t".join("1" for _ in species) + f"\t{len(species)}\n")
    return buf.getvalue()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A working directory whose Proteomas/ holds the stamps of a New Analysis."""
    import app as og
    from orthogather.core import history as og_history
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".orthogather_sessions").mkdir()       # the session store is relative too
    monkeypatch.setattr(og, "HISTORY_DIR", tmp_path / "runs")
    monkeypatch.setattr(og_history, "HISTORY_DIR", tmp_path / "runs")
    prot = tmp_path / "Proteomas"
    prot.mkdir()
    (prot / "proteome_provenance.json").write_text(json.dumps(STAMP))
    (prot / "orthofinder_provenance.json").write_text(json.dumps({"version": "2.5.5", "source": "OrthoFinder"}))
    (prot / "Orthogroups.zip").write_bytes(_orthogroups_zip())
    return og.app.test_client()


def _provenance(c):
    return json.loads(c.get("/download_provenance?fmt=json").data)


def test_snapshot_takes_the_stamps_of_the_run_that_just_finished(workdir, tmp_path):
    import app as og
    # The analysis open in the browser while the New Analysis ran.
    old = tmp_path / "static" / "data_folder" / "generated"
    old.mkdir(parents=True)
    (old / "proteome_provenance.json").write_text(json.dumps({"release": "2025_01", "per_proteome": {}}))
    (old / "orthofinder_provenance.json").write_text(json.dumps({"version": "2.5.4"}))
    (old / "goa_provenance.json").write_text(json.dumps({"data_generated": "2025-01-01"}))
    # OrthoFinder's output for the new run.
    results = tmp_path / "Proteomas" / "OrthoFinder" / "Results_Oct29" / "Orthogroups"
    results.mkdir(parents=True)
    (results / "Orthogroups.tsv").write_text("Orthogroup\tAlpha_beta\tGamma_delta\nOG0000000\ta\tb\n")
    with og.app.test_request_context():
        session["folder_path"] = str(old)
        session["modo"] = "upload"
        meta = og._snapshot_run(str(results.parent), "20261029_120000", 1.0)
    prov = meta["provenance"]
    assert prov["proteome"]["release"] == "2026_03"
    assert prov["orthofinder_version"] == "2.5.5"
    assert prov["goa"] is None
    assert prov["mode"] == "generated"
    saved = json.loads((tmp_path / "runs" / "20261029_120000" / "meta.json").read_text())
    assert saved["provenance"]["proteome"]["per_proteome"] == STAMP["per_proteome"]
