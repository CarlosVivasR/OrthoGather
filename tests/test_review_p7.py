"""Tests for P7 (22-Oct-2026 review of P5/P6):

- A line of ``db|ACC|NAME`` entries and bare accessions is a list, not a FASTA
  header without ">" (the bare accessions used to be dropped).
- With per-orthogroup counting and expanded sets, a measured protein that is in
  no orthogroup keeps its own annotations and is tested, as the documentation says.
- The GO-version check compares release dates: an OBO "releases/2026-07-26" and
  a GOA purl ".../releases/2026-07-26/extensions/go-plus.ofn" are the same release.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from orthogather.utils.parsing import parse_identifier_list


def test_mixed_line_of_pipes_and_accessions_is_a_list():
    assert parse_identifier_list("sp|P0A6F5|CH60_ECOLI P00350")["ids"] == ["P0A6F5", "P00350"]
    assert parse_identifier_list("tr|A0QNX2|A0QNX2_MYCS2, P00350")["ids"] == ["A0QNX2", "P00350"]
    header = parse_identifier_list("sp|P0A6F5|CH60_ECOLI 60 kDa chaperonin OS=Escherichia coli")
    assert header["ids"] == ["P0A6F5"] and header["headers"] == 1
    assert parse_identifier_list("UniProtKB:P12345 uniprot:q67890")["ids"] == ["P12345", "Q67890"]


def _gaf(acc, go, aspect):
    return "\t".join(["UniProtKB", acc, acc, "", go, "PMID:0", "IEA", "", aspect, "", "", "protein",
                      "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


def _workspace(tmp_path, monkeypatch, go_version):
    """spA (measured, partly annotated, 40 proteins in no orthogroup) and spB
    (annotated): 300 orthogroups with one protein of each."""
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    rows, counts, lines_a, lines_b = [], [], [], []
    for i in range(300):
        rows.append({"Orthogroup": f"OG{i:07d}", "spA": f"tr|A{i:05d}|A{i:05d}_SPA",
                     "spB": f"tr|B{i:05d}|B{i:05d}_SPB"})
        counts.append({"Orthogroup": f"OG{i:07d}", "spA": 1, "spB": 1, "Total": 2})
        lines_b.append(_gaf(f"B{i:05d}", "GO:0006412" if i < 50 else others[i % 6], "P"))
    unassigned = [f"AU{k:04d}" for k in range(40)]
    for k, u in enumerate(unassigned):
        lines_a.append(_gaf(u, "GO:0006412" if k < 20 else others[k % 6], "P"))
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame(counts).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": f"OG{300 + k:07d}", "spA": f"tr|{u}|{u}_SPA", "spB": None}
                  for k, u in enumerate(unassigned)]).to_csv(
        folder / "Orthogroups_UnassignedGenes.tsv", sep="\t", index=False)
    head = "!gaf-version: 2.2\n" + (f"!go-version: {go_version}\n" if go_version else "")
    (goa_dir / "1.spA.goa").write_text(head + "".join(lines_a))
    (goa_dir / "2.spB.goa").write_text(head + "".join(lines_b))
    mapping = {"spA": "1.spA.goa", "spB": "2.spB.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    if go_version:   # what /download_goa_files records from the GOA headers
        (folder / "goa_provenance.json").write_text(json.dumps({"go_version": go_version}))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=list(mapping.values()))
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    client = og.app.test_client()
    with client.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spA", "spB"]
    return client, unassigned


def _run(c, fg, bg, expand, mode):
    assert c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg,
                                                "use_orthogroups": expand}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": mode})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_unassigned_measured_proteins_stay_in_per_orthogroup_with_expansion(tmp_path, monkeypatch):
    c, unassigned = _workspace(tmp_path, monkeypatch, None)
    fg = [f"A{i:05d}" for i in range(30)] + unassigned[:20]
    bg = [f"A{i:05d}" for i in range(300)] + unassigned
    p = _run(c, fg, bg, True, "per_orthogroup")
    untested = {r["id"] for r in p["input_ids"]["untested"]}
    assert not untested & set(unassigned[:20])
    assert not any("fell back" in w for w in p.get("warnings") or [])


@pytest.mark.parametrize("goa_version,warned", [
    ("http://purl.obolibrary.org/obo/go/releases/2026-07-26/extensions/go-plus.ofn", False),
    ("http://purl.obolibrary.org/obo/go/releases/2026-09-27/extensions/go-plus.ofn", True),
])
def test_go_version_check_compares_release_dates(tmp_path, monkeypatch, goa_version, warned):
    import app as og
    obo = (og.read_obo_metadata(og.GO_ROOT_OBO) or {}).get("data_version", "")
    if "2026-07-26" not in str(obo):
        pytest.skip(f"bundled go-basic.obo is {obo}")
    c, unassigned = _workspace(tmp_path, monkeypatch, goa_version)
    p = _run(c, unassigned[:20], unassigned, False, "per_protein")
    assert any("differs from the GOA GO-version" in w for w in p.get("warnings") or []) is warned
