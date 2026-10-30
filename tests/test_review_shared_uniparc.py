"""UniParc identifiers shared between strains (review of 30-Oct-2026).

UniParc names a sequence, so strains with identical proteins share their
identifiers: in the Preselected Dataset 42-73 % of the proteins of each
P. aeruginosa and A. baumannii strain share a UPI with another strain. With
'Use all GOA files' counted per orthogroup, the universe is the proteome of the
species the pasted list comes from, and a list from one strain took the
proteomes of every strain sharing those sequences. Now the universe is the
species that holds every pasted identifier, and when several do the run says
so. UniProt accessions are not shared, so nothing changes for them.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import _gaf

N = 300
REF = [f"B{i:05d}" for i in range(N)]
SHARED = [f"UPI{i:010X}" for i in range(1, 181)]       # identical in both strains
OWN1 = [f"UPI{i:010X}" for i in range(1001, 1121)]
OWN2 = [f"UPI{i:010X}" for i in range(2001, 2121)]
C1, C2 = SHARED + OWN1, SHARED + OWN2


@pytest.fixture
def strains(tmp_path, monkeypatch):
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    rows = [{"Orthogroup": f"OG{i:07d}", "spRef": f"tr|{REF[i]}|{REF[i]}_SPREF",
             "strain1": C1[i], "strain2": C2[i]} for i in range(N)]
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": r["Orthogroup"], "spRef": 1, "strain1": 1, "strain2": 1, "Total": 3}
                  for r in rows]).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spRef.goa").write_text("!gaf-version: 2.2\n" + "".join(
        _gaf(REF[i], "GO:0006412" if i < 40 else others[i % 6], "P") for i in range(N)))
    mapping = {"spRef": "2.spRef.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["2.spRef.goa"])
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    client = og.app.test_client()
    with client.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spRef", "strain1", "strain2"]
    return client


def _run(c, fg):
    assert c.post("/background_analysis", json={"background_choice": "5"}).status_code == 200
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_a_list_from_one_strain_takes_that_strain_only(strains):
    # Shared and own proteins of strain1: only strain1 holds them all.
    p = _run(strains, SHARED[:20] + OWN1[:10])
    assert p["annotation_stats"]["background_proteins"] == 300
    assert any("Only strain1 contains all of them" in w for w in p["warnings"])
    assert not any("spans" in w for w in p["warnings"])


def test_a_list_both_strains_hold_is_pooled_and_said(strains):
    p = _run(strains, SHARED[:30])
    assert p["annotation_stats"]["background_proteins"] == 420
    assert any("occurs in 2 proteomes (strain1; strain2)" in w for w in p["warnings"])


def test_a_list_of_unshared_proteins_is_unchanged(strains):
    p = _run(strains, OWN1[:30])
    assert p["annotation_stats"]["background_proteins"] == 300
    assert not any("UniParc" in w for w in p["warnings"])


def test_a_list_spanning_two_strains_still_pools_them(strains):
    p = _run(strains, OWN1[:15] + OWN2[:15])
    assert p["annotation_stats"]["background_proteins"] == 420
    assert any("spans 2 species" in w for w in p["warnings"])
