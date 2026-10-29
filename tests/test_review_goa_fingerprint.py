"""Each history run keeps the fingerprint and date of the GOA files used with
it, and says so when a new download differs (blind study, 29-Oct-2026).

GOAfiles/ is emptied on every download and EBI regenerates its files, so
reopening a run and downloading again could give other annotations without a
word.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)
from tests.test_review_provenance_history import _saved_run
from tests.test_review_provenance_snapshot import workdir  # noqa: F401  (fixture)

RUN = "20261020_000000"
SPECIES = "Old_one"


def _goa(date, terms):
    lines = [f"!gaf-version: 2.2\n!date-generated: {date}\n"]
    lines += ["\t".join(["UniProtKB", "P00000", "P00000", "", go, "PMID:0", "IEA", "", "P", "", "",
                         "protein", "taxon:1", "20261020", "UniProt", "", ""]) + "\n" for go in terms]
    return "".join(lines).encode()


@pytest.fixture
def reopened(workdir, tmp_path, monkeypatch):
    import app as og
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(tmp_path / "GOAfiles"))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(tmp_path / "results"))
    served = {}

    def fake_download(url, outpath):
        with open(outpath, "wb") as f:
            f.write(served[url.rsplit("/", 1)[-1]])
        return "ok", ""

    monkeypatch.setattr(og, "_download_goa_file", fake_download)
    _saved_run(tmp_path, RUN, ["UP000000009", "UP000000008"], ["UP000000009", "UP000000008"], "2025_04", "2.5.4")
    assert workdir.get(f"/history/{RUN}/load", follow_redirects=True).status_code == 200
    return workdir, served


def _download(c):
    body = c.post("/download_goa_files",
                  json={"species_to_url": {SPECIES: "https://example.org/9.Old_one.goa"}}).get_data(as_text=True)
    events = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    return events[-1]


def test_goa_fingerprint_is_kept_with_the_run_and_a_change_is_reported(reopened, tmp_path):
    c, served = reopened
    served["9.Old_one.goa"] = first = _goa("2026-10-11", ["GO:0006412"])
    done = _download(c)
    assert done["phase"] == "done" and not done.get("goa_changed")
    saved = json.loads((tmp_path / "runs" / RUN / "goa_provenance.json").read_text())
    assert saved["files"]["9.Old_one.goa"] == {"sha256": hashlib.sha256(first).hexdigest(),
                                               "date_generated": "2026-10-11"}

    served["9.Old_one.goa"] = _goa("2026-11-08", ["GO:0006412", "GO:0005524"])
    done = _download(c)
    changed = done["goa_changed"]
    assert changed["files"] == ["9.Old_one.goa"]
    assert changed["previous_data_generated"] == "2026-10-11"
    saved = json.loads((tmp_path / "runs" / RUN / "goa_provenance.json").read_text())
    assert saved["files"]["9.Old_one.goa"]["date_generated"] == "2026-11-08"


def test_same_files_again_are_not_reported(reopened):
    c, served = reopened
    served["9.Old_one.goa"] = _goa("2026-10-11", ["GO:0006412"])
    _download(c)
    assert not _download(c).get("goa_changed")


def test_new_analysis_snapshot_names_its_run(workdir, tmp_path):
    import app as og
    from flask import session
    results = tmp_path / "Proteomas" / "OrthoFinder" / "Results_Oct29"
    (results / "Orthogroups").mkdir(parents=True)
    with og.app.test_request_context():
        session["folder_path"] = None
        og._snapshot_run(str(results), "20261029_130000", 1.0)
    assert json.loads((tmp_path / "Proteomas" / "history_run.json").read_text()) == {"run_id": "20261029_130000"}


def test_page_reports_changed_goa_files():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "templates" / "resultado_goa.html").read_text()
    assert "finalEvent.goa_changed" in html


def test_results_provenance_lists_the_goa_fingerprints(three_species):
    import pandas as pd
    import app as og
    c = three_species
    with c.session_transaction() as s:
        folder = s["folder_path"]
    with open(f"{folder}/goa_provenance.json", "w") as f:
        json.dump({"n_files": 1, "files": {"2.spRef.goa": {"sha256": "ab" * 32, "date_generated": "2026-10-11"}}}, f)
    assert c.post("/foreground_analysis", json={"uniprot_ids": REF[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": REF}).status_code == 200
    assert c.post("/gene_ontology_analysis", json={}).status_code == 200
    prov = pd.read_excel(f"{og.RESULTS_FOLDER}/go_enrichment_report.xlsx", sheet_name="Provenance")
    assert prov["key"].iloc[-1] == "GOA files (SHA-256)"
    assert prov["value"].iloc[-1] == "2.spRef.goa: " + "ab" * 32
