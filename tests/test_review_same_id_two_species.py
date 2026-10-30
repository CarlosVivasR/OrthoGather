"""The same identifier in two proteomes (review of 30-Oct-2026).

Two genomes annotated with an old Prokka's default prefix both have
PROKKA_00001. The identifier was matched in both proteomes, so expanding the
protein of genome A also took the orthogroup of genome B's, and counted per
orthogroup it went to whichever orthogroup was read last, without a word.
Loading a list now says which identifiers are in more than one proteome, and
the run counts each in one fixed orthogroup and says so.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from tests.test_review_nonuniprot_ids import _gaf

N = 300
REF = [f"B{i:05d}" for i in range(N)]
GA = [f"PROKKA_{i:05d}" for i in range(N)]
GB = [f"PROKKA_{i:05d}" for i in range(1000, 1000 + N)]
GB[6] = GA[0]                     # genome B's protein in OG0000006 has GA[0]'s name


@pytest.fixture
def two_genomes(tmp_path, monkeypatch):
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows = [{"Orthogroup": f"OG{i:07d}", "spRef": f"tr|{REF[i]}|{REF[i]}_SPREF",
             "GenomeA": GA[i], "GenomeB": GB[i]} for i in range(N)]
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": r["Orthogroup"], "spRef": 1, "GenomeA": 1, "GenomeB": 1, "Total": 3}
                  for r in rows]).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spRef.goa").write_text("!gaf-version: 2.2\n" + "".join(
        _gaf(REF[i], "GO:0006412" if i < 50 else "GO:0055085", "P") for i in range(N)))
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
    c = og.app.test_client()
    with c.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spRef", "GenomeA", "GenomeB"]
    return c


def test_loading_says_which_identifiers_are_in_two_proteomes(two_genomes):
    c = two_genomes
    r = c.post("/foreground_analysis", json={"uniprot_ids": GA[:30], "use_orthogroups": True})
    assert r.status_code == 200
    warns = r.get_json()["input"]["warnings"]
    assert any(w.startswith("1 identifier is in the proteomes of more than one species (PROKKA_00000)")
               for w in warns)
    r = c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": GA,
                                             "use_orthogroups": True})
    assert any("PROKKA_00000" in w for w in r.get_json()["input"]["warnings"])
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200
    w = r.get_json()["warnings"]
    assert any(x.startswith("Foreground: 1 identifier is in the proteomes") for x in w)
    assert any("are in more than one orthogroup" in x for x in w)


def test_identifiers_of_one_proteome_give_no_note(two_genomes):
    r = two_genomes.post("/foreground_analysis", json={"uniprot_ids": GA[1:30]})
    assert not any("more than one species" in w for w in r.get_json()["input"]["warnings"])
