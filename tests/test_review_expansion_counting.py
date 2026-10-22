"""Test for P8 (22-Oct-2026): an expanded foreground or background is always
counted per orthogroup. Counted per protein, every paralogue of a family is a
separate observation, and in the expansion benchmark that gave a significant
term in 100% of random foregrounds. Without expansion nothing changes: per
protein stays available and gives the same results as before.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

NOTE = "so it was counted per orthogroup"


def _gaf(acc, go, aspect):
    return "\t".join(["UniProtKB", acc, acc, "", go, "PMID:0", "IEA", "", aspect, "", "", "protein",
                      "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


@pytest.fixture
def two_species(tmp_path, monkeypatch):
    """spA (measured, no GOA file) and spB (annotated): 300 orthogroups with one
    spA protein and one spB protein; the first 50 carry translation."""
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows, counts, lines = [], [], []
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    for i in range(300):
        rows.append({"Orthogroup": f"OG{i:07d}", "spA": f"tr|A{i:05d}|A{i:05d}_SPA",
                     "spB": f"tr|B{i:05d}|B{i:05d}_SPB"})
        counts.append({"Orthogroup": f"OG{i:07d}", "spA": 1, "spB": 1, "Total": 2})
        lines.append(_gaf(f"B{i:05d}", "GO:0006412" if i < 50 else others[i % 6], "P"))
        lines.append(_gaf(f"B{i:05d}", ("GO:0003677", "GO:0005524")[i % 2], "F"))
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame(counts).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spB.goa").write_text("!gaf-version: 2.2\n" + "".join(lines))
    mapping = {"spB": "2.spB.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["2.spB.goa"])
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    client = og.app.test_client()
    with client.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spA", "spB"]
    return client


def _run(c, fg, bg, fg_expand, bg_expand, mode):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": fg_expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": bg_expand}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": mode})
    assert r.status_code == 200
    p = r.get_json()
    rows = sorted((t["GO"], t["study_count"], t["pop_count"], t["p_fdr_bh"])
                  for k in ("bp_results", "cc_results", "mf_results") for t in p.get(k) or [])
    return p.get("warnings") or [], rows, p["counting"]["mode"]


A = [f"A{i:05d}" for i in range(300)]
B = [f"B{i:05d}" for i in range(300)]


@pytest.mark.parametrize("fg,bg,fg_expand,bg_expand", [
    (A[:30], A, True, True),    # measured species without GOA, both sets expanded
    (B[:30], B, True, False),   # annotated species, only the foreground expanded
    (B[:30], B, False, True),   # annotated species, only the background expanded
])
def test_expanded_sets_are_counted_per_orthogroup(two_species, fg, bg, fg_expand, bg_expand):
    warnings, asked_protein, mode = _run(two_species, fg, bg, fg_expand, bg_expand, "per_protein")
    assert mode == "per_orthogroup"
    assert sum(NOTE in w for w in warnings) == 1
    _, asked_orthogroup, _ = _run(two_species, fg, bg, fg_expand, bg_expand, "per_orthogroup")
    assert asked_protein == asked_orthogroup and asked_protein


def test_without_expansion_per_protein_is_unchanged(two_species):
    warnings, _, mode = _run(two_species, B[:30], B, False, False, "per_protein")
    assert mode == "per_protein" and not any(NOTE in w for w in warnings)
    warnings, _, mode = _run(two_species, A[:30], A, True, True, "per_orthogroup")
    assert mode == "per_orthogroup" and not any(NOTE in w for w in warnings)


def test_reloading_without_expansion_restores_per_protein(two_species):
    _run(two_species, A[:30], A, True, True, "per_protein")
    warnings, _, mode = _run(two_species, B[:30], B, False, False, "per_protein")
    assert mode == "per_protein" and not any(NOTE in w for w in warnings)


def test_use_all_goa_files_is_not_an_expanded_background(two_species):
    c = two_species
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": A,
                                                "use_orthogroups": True}).status_code == 200
    assert c.post("/foreground_analysis", json={"uniprot_ids": B[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "5", "custom_uniprot_ids": [],
                                                "use_orthogroups": True}).status_code == 200
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).get_json()
    assert p["counting"]["mode"] == "per_protein"
    assert not any(NOTE in w for w in p.get("warnings") or [])


def test_page_disables_per_protein_while_a_set_is_expanded():
    html = (Path(__file__).resolve().parent.parent / "templates" / "resultado_goa.html").read_text()
    block = re.search(r'<div id="counting-expansion-note"[^>]*>', html)
    assert block and " hidden" in block.group(0)
    assert "counted per orthogroup" in html[block.end():block.end() + 400]
    assert "perProtein.disabled = expanded;" in html
    assert "perOrthogroup.checked = true;" in html
    assert "counting-expansion-warning" not in html


def test_use_all_goa_files_for_a_species_without_goa(two_species):
    # spA has no GOA file. With "Use all GOA files" its universe is its proteome
    # in the analysis, each protein taking part through its orthogroup: the same
    # as pasting that proteome as the background and expanding it.
    c = two_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": A[:30], "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "5", "custom_uniprot_ids": [],
                                                "use_orthogroups": False}).status_code == 200
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"}).get_json()
    assert p["counting"]["mode"] == "per_orthogroup"
    assert any(NOTE in w for w in p.get("warnings") or [])
    assert not any("Do not rely" in w for w in p.get("warnings") or [])
    goa_all = sorted((t["GO"], t["study_count"], t["pop_count"], t["p_fdr_bh"])
                     for k in ("bp_results", "cc_results", "mf_results") for t in p.get(k) or [])
    _, pasted, mode = _run(c, A[:30], A, True, True, "per_orthogroup")
    assert mode == "per_orthogroup" and goa_all == pasted and goa_all


def test_species_without_goa_counted_per_protein_is_explained(two_species):
    c = two_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": A[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "5", "custom_uniprot_ids": []}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_protein"})
    assert r.status_code == 400 and "count per orthogroup" in r.get_json()["hint"].lower()
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}).get_json()
    assert p["counting"]["mode"] == "per_orthogroup"
    assert any(t["GO"] == "GO:0006412" and t["p_fdr_bh"] < 0.05 for t in p["bp_results"])


@pytest.mark.parametrize("species", ["A", "B"])
def test_use_all_goa_files_per_orthogroup_is_the_expanded_proteome(two_species, species):
    # Counted per orthogroup, "Use all GOA files" is the species' proteome in the
    # analysis, pasted as the background and expanded, whether the species has a
    # GOA file (spB) or not (spA).
    ids = A if species == "A" else B
    c = two_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": ids[:30]}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "5", "custom_uniprot_ids": []}).status_code == 200
    p = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}).get_json()
    goa_all = sorted((t["GO"], t["study_count"], t["pop_count"], t["p_fdr_bh"])
                     for k in ("bp_results", "cc_results", "mf_results") for t in p.get(k) or [])
    _, pasted, mode = _run(c, ids[:30], ids, False, True, "per_orthogroup")
    assert mode == "per_orthogroup" and goa_all == pasted and goa_all
