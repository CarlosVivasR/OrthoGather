"""Expansion with identifiers that are not UniProt accessions (blind study,
29-Oct-2026).

OrthoFinder keeps the first word of each FASTA header, so a proteome from
UniProtKB gives cells such as ``tr|A0QNX2|A0QNX2_MYCS2``, while one from UniParc
or from a lab's own annotation gives bare identifiers (``UPI00003962DA``,
``IS27_00398``, ``contig1_17``). The expansion matched the pasted identifiers
with a pattern that only reads the first form, so with the second it found no
orthogroup, reported success and the run then stopped at "Foreground missing".
"""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest


def _gaf(acc, go, aspect):
    return "\t".join(["UniProtKB", acc, acc, "", go, "PMID:0", "IEA", "", aspect, "", "", "protein",
                      "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


# Three species: spRef (UniProt FASTA, with a GOA file), spUPI (UniParc
# proteome) and spOwn (a lab's own FASTA). 300 orthogroups with one protein of
# each; the first 50 carry translation in spRef.
N = 300
REF = [f"B{i:05d}" for i in range(N)]
UPI = [f"UPI{i:010X}" for i in range(1, N + 1)]
OWN = [f"IS27_{i:05d}" for i in range(N)]


@pytest.fixture
def three_species(tmp_path, monkeypatch):
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows, counts, lines = [], [], []
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    for i in range(N):
        rows.append({"Orthogroup": f"OG{i:07d}", "spRef": f"tr|{REF[i]}|{REF[i]}_SPREF",
                     "spUPI": UPI[i], "spOwn": OWN[i]})
        counts.append({"Orthogroup": f"OG{i:07d}", "spRef": 1, "spUPI": 1, "spOwn": 1, "Total": 3})
        lines.append(_gaf(REF[i], "GO:0006412" if i < 50 else others[i % 6], "P"))
        lines.append(_gaf(REF[i], ("GO:0003677", "GO:0005524")[i % 2], "F"))
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame(counts).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    (goa_dir / "2.spRef.goa").write_text("!gaf-version: 2.2\n" + "".join(lines))
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
        s["species"] = ["spRef", "spUPI", "spOwn"]
    return client


@pytest.mark.parametrize("ids", [UPI, OWN], ids=["uniparc", "own_fasta"])
def test_expanded_foreground_finds_the_orthogroups_of_bare_ids(three_species, ids):
    c = three_species
    r = c.post("/foreground_analysis", json={"uniprot_ids": ids[:30], "use_orthogroups": True})
    assert r.status_code == 200
    with c.session_transaction() as s:
        assert s["selected_orthogroups"] == [f"OG{i:07d}" for i in range(30)]
        # The members in the species with a GOA file: their orthologues in spRef.
        assert s["foreground_proteins"] == sorted(REF[:30])


@pytest.mark.parametrize("ids", [UPI, OWN], ids=["uniparc", "own_fasta"])
def test_expanded_background_finds_the_orthogroups_of_bare_ids(three_species, ids):
    c = three_species
    r = c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": ids,
                                             "use_orthogroups": True})
    assert r.status_code == 200
    assert r.get_json()["background_ids"] == sorted(REF)


@pytest.mark.parametrize("ids", [UPI, OWN], ids=["uniparc", "own_fasta"])
def test_bare_ids_run_end_to_end(three_species, ids):
    # The blind study's plan: both sets expanded, counted per orthogroup.
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": ids[:30], "use_orthogroups": True}).status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": ids,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200, r.get_json()
    p = r.get_json()
    assert "GO:0006412" in {t["GO"] for t in p["bp_results"]}


def test_unexpanded_foreground_reports_the_orthogroups_of_bare_ids(three_species):
    c = three_species
    assert c.post("/foreground_analysis", json={"uniprot_ids": UPI[:5]}).status_code == 200
    with c.session_transaction() as s:
        assert s["selected_orthogroups"] == [f"OG{i:07d}" for i in range(5)]
        assert s["foreground_proteins"] == sorted(UPI[:5])


def _old_matcher(groups, ids):
    """The pattern used before 2.2.1, for the comparison below."""
    out = set()
    for _, row in groups.iterrows():
        for protein in row[1:].dropna():
            if any(uid in ids for uid in re.findall(r'\|([^|]+)\|', str(protein))):
                out.add(row["Orthogroup"])
                break
    return out


def _old_members(interest, ogs):
    out = set()
    for og in ogs:
        for _, row in interest[interest["Orthogroup"] == og].iterrows():
            for protein in row.dropna().astype(str):
                out.update(re.findall(r'\|([^|]+)\|', protein))
    return out


def test_uniprot_cells_give_the_same_orthogroups_and_members_as_before():
    import app as og
    rows = []
    for i in range(40):
        rows.append({"Orthogroup": f"OG{i:07d}", "Annotation Percentage": 50.0,
                     "spA": ", ".join(f"tr|A{i:03d}{k}|A{i:03d}{k}_SPA" for k in range(i % 3 + 1)),
                     "spB": (f"sp|B{i:04d}|B{i:04d}_SPB" if i % 4 else None)})
    groups = pd.DataFrame(rows)
    ids = {"A0011", "A0052", "B0007", "B0008", "A0391", "NOTHERE"}
    assert og._orthogroups_with_ids(groups, ids) == _old_matcher(groups, ids)
    ogs = _old_matcher(groups, ids)
    assert ogs and og._orthogroup_members(groups, ogs) == _old_members(groups, ogs)


# NCBI general identifiers (gnl|DATABASE|ID), the form of the protein FASTA that
# NCBI's annotation pipeline writes for a lab's genome (gnl|extdb|IS27_00001).
# The second field names the database and is the same for every protein: read
# as the accession, the whole proteome became one identifier.
GNL = [f"gnl|extdb|{own}" for own in OWN]


def test_ncbi_general_identifiers_keep_the_protein_id():
    from orthogather.core.excel import _accession
    from orthogather.utils.parsing import normalise_accession, orthogroup_cell_accessions
    assert orthogroup_cell_accessions(", ".join(GNL[:2])) == OWN[:2]
    assert normalise_accession(GNL[0]) == (OWN[0], ["fasta_header"])
    assert _accession(GNL[0]) == OWN[0]
    # UniProt headers are read as before.
    assert orthogroup_cell_accessions("tr|A0QNX2|A0QNX2_MYCS2") == ["A0QNX2"]
    assert normalise_accession(">sp|P12345-2|NAME_ECOLI") == ("P12345", ["fasta_header", "isoform"])


@pytest.mark.parametrize("pasted", [GNL, OWN], ids=["as_in_the_fasta", "protein_id"])
def test_ncbi_general_identifiers_run_end_to_end(three_species, pasted):
    c = three_species
    folder = None
    with c.session_transaction() as s:
        folder = s["folder_path"]
    # The lab's proteome written with NCBI general identifiers.
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel
    from pathlib import Path
    tsv = Path(folder) / "Orthogroups.tsv"
    df = pd.read_csv(tsv, sep="\t", dtype=str)
    df["spOwn"] = GNL
    df.to_csv(tsv, sep="\t", index=False)
    id2gos = og_goa.build_id2gos_from_goa_folder(og.GOA_DOWNLOAD_FOLDER, limit_files=["2.spRef.goa"])
    generate_go_excel(str(tsv), {"spRef": "2.spRef.goa"},
                      str(Path(og.RESULTS_FOLDER) / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    r = c.post("/foreground_analysis", json={"uniprot_ids": pasted[:30], "use_orthogroups": True})
    assert r.status_code == 200, r.get_json()
    with c.session_transaction() as s:
        assert s["selected_orthogroups"] == [f"OG{i:07d}" for i in range(30)]
        assert s["foreground_input"] == OWN[:30]
    assert c.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": pasted,
                                                "use_orthogroups": True}).status_code == 200
    r = c.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["annotation_stats"]["tested_proteins"] == 30
    assert "GO:0006412" in {t["GO"] for t in r.get_json()["bp_results"]}
