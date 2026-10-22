"""Tests for P6 of the 21-Oct-2026 review (audit item I4): pasted identifiers.

The foreground, background and UniProt filter accept FASTA headers, lower-case
accessions and isoform suffixes, and the enrichment reports, for every pasted
foreground identifier that is not tested, why: not found, not in the
background, no GO annotation, or left out by the orthogroup expansion.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from orthogather.utils.parsing import normalise_accession, parse_identifier_list, parse_uniprot_block

FASTA = """>sp|P0A6F5|CH60_ECOLI Chaperonin GroEL OS=Escherichia coli (strain K12) OX=83333 GN=groL PE=1 SV=2
MAAKDVKFGNDARVKMLRGVNVLADAVKVTLGPKGRNVVLDKSFGAPTITKDGVSVAREIELEDKFENMGAQ
MVKEVASKANDAAGDGTTTATVLAQAIITEGLKAVAAGMNPMDLKRGIDKAVTAAVEELKALSVPCSDSKAI
>tr|A0A0B7HXH8|A0A0B7HXH8_9MYCO Uncharacterized protein OS=Mycobacteroides abscessus
MSKQQIGVVGMAVMGRNLALNIESRGYTVSIFNRSREKTEEVIAENPGKKLVPYYTVKEF
>sp|P00350-2|6PGD_ECOLI Isoform 2 of 6-phosphogluconate dehydrogenase
MSKQQIGVVGMAV
"""


# ----------------------------------------------------------------- parsing
def test_fasta_text_gives_one_accession_per_header():
    r = parse_identifier_list(FASTA)
    assert r["ids"] == ["P0A6F5", "A0A0B7HXH8", "P00350"]
    assert (r["headers"], r["sequence_lines"]) == (3, 4)


def test_audit_v2_identifiers_are_kept():
    # V2 of the audit: these four were lost in silence.
    noisy = ["Q00001", "Q00001", "Q00002,", " Q00003 ", "q00004", "Q00005-2",
             ">tr|Q00006|Q00006_QSYN Some protein OS=Synthetic", "sp|Q00007|Q00007_QSYN", "Q01150"]
    r = parse_identifier_list(noisy)
    assert r["ids"] == ["Q00001", "Q00002", "Q00003", "Q00004", "Q00005", "Q00006", "Q00007", "Q01150"]
    assert r["duplicates"] == 1
    assert {c["input"]: c["changes"] for c in r["changed"]} == {
        "q00004": ["upper_case"], "Q00005-2": ["isoform"],
        "tr|Q00006|Q00006_QSYN": ["fasta_header"], "sp|Q00007|Q00007_QSYN": ["fasta_header"]}


@pytest.mark.parametrize("token, expected", [
    ("P12345", ("P12345", [])),
    ("p12345", ("P12345", ["upper_case"])),
    ("P12345-12", ("P12345", ["isoform"])),
    ("a0a0b7hxh8-2", ("A0A0B7HXH8", ["upper_case", "isoform"])),
    (">sp|P12345|NAME_ECOLI", ("P12345", ["fasta_header"])),
    ("sp|P12345", ("P12345", ["fasta_header"])),
    ('"P12345"', ("P12345", [])),
    ("upi00000000d1", ("UPI00000000D1", ["upper_case"])),
    # Not shaped like a UniProt accession: kept as pasted, case included.
    ("contig1_17", ("contig1_17", [])),
    ("gene-2", ("gene-2", [])),
    ("NAME_ECOLI", ("NAME_ECOLI", [])),
])
def test_normalise_accession(token, expected):
    assert normalise_accession(token) == expected


def test_header_without_marker_and_lists_of_pipe_identifiers():
    # A 'db|ACC|NAME' word followed by a description is a header ...
    assert parse_uniprot_block("sp|P12345|A_ECOLI Protein A OS=Escherichia coli") == ["P12345"]
    # ... several of them on one line are a list.
    assert parse_uniprot_block("sp|P12345|A_ECOLI tr|Q67890|B_ECOLI, sp|P00001|C") == \
        ["P12345", "Q67890", "P00001"]


def test_sequence_lines_are_skipped_only_inside_a_record():
    # Every accession carries a digit, so it is never taken for a sequence line,
    # and it ends the record: a letters-only word outside a record is kept.
    assert parse_uniprot_block(">sp|P12345|A_ECOLI\nMKVL\nQ67890\ndnaK") == ["P12345", "Q67890", "dnaK"]
    assert parse_uniprot_block("dnaK\nP12345") == ["dnaK", "P12345"]


def test_old_callers_unchanged():
    assert parse_uniprot_block("P12345  Q67890,P00001;Q11111\tP22222") == \
        ["P12345", "Q67890", "P00001", "Q11111", "P22222"]
    assert parse_uniprot_block(["P12345", "Q67890"]) == ["P12345", "Q67890"]
    assert parse_uniprot_block(None) == parse_uniprot_block("") == []


# ----------------------------------------------------------------- routes
def _gaf(acc, go, aspect):
    return "\t".join(["UniProtKB", acc, acc, "", go, "PMID:0", "IEA", "", aspect, "", "", "protein",
                      "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """spA (GOA file) and spB (none): 120 orthogroups of one spA and one spB
    protein. Q00000-Q00099 are annotated, Q00100-Q00119 are not; Q00900
    (annotated) and Q00901 are unassigned spA proteins."""
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core.excel import generate_go_excel

    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    rows, counts, lines = [], [], []
    others = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
    for i in range(120):
        rows.append({"Orthogroup": f"OG{i:07d}", "spA": f"tr|Q{i:05d}|Q{i:05d}_SPA",
                     "spB": f"tr|B0A{i:03d}|B0A{i:03d}_SPB"})
        counts.append({"Orthogroup": f"OG{i:07d}", "spA": 1, "spB": 1, "Total": 2})
        if i < 100:
            lines.append(_gaf(f"Q{i:05d}", "GO:0006412" if i < 40 else others[i % 6], "P"))
            lines.append(_gaf(f"Q{i:05d}", ("GO:0003677", "GO:0005524")[i % 2], "F"))
    lines.append(_gaf("Q00900", "GO:0006412", "P"))
    pd.DataFrame(rows).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame(counts).to_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": "OG0000120", "spA": "tr|Q00900|Q00900_SPA", "spB": ""},
                  {"Orthogroup": "OG0000121", "spA": "tr|Q00901|Q00901_SPA", "spB": ""}]).to_csv(
        folder / "Orthogroups_UnassignedGenes.tsv", sep="\t", index=False)
    (goa_dir / "1.spA.goa").write_text("!gaf-version: 2.2\n" + "".join(lines))
    mapping = {"spA": "1.spA.goa"}
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))
    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og._ANALYSIS_ACCESSIONS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=["1.spA.goa"])
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))
    client = og.app.test_client()
    with client.session_transaction() as s:
        s["folder_path"] = str(folder)
        s["species"] = ["spA", "spB"]
    return client


BACKGROUND = [f"Q{i:05d}" for i in range(120)] + ["Q00900", "Q00901"]
# Five tested in four spellings, then one of each reason.
PASTED = [">sp|Q00001|Q00001_SPA Some protein OS=Synthetic", "q00002", "Q00003-2",
          "sp|Q00004|Q00004_SPA", "Q00005", "Q00110", "B0A007", "Q09999"]
REASONS = {"Q00110": "no_annotation", "B0A007": "not_in_background", "Q09999": "not_found"}


def _payload(resp):
    js = resp.get_json()
    return js.get("payload", js)


def _load(c, fg, bg=BACKGROUND, expand=False):
    r = c.post("/foreground_analysis", json={"uniprot_ids": fg, "use_orthogroups": expand})
    assert r.status_code == 200
    assert c.post("/background_analysis", json={"background_choice": "4",
                                                "custom_uniprot_ids": bg}).status_code == 200
    return _payload(r)


def test_load_reports_how_the_list_was_read(ws):
    p = _load(ws, PASTED)
    assert p["input"]["n_ids"] == 8
    assert len(p["input"]["warnings"]) == 1 and "Q00003-2 → Q00003" in p["input"]["warnings"][0]
    assert "2 accessions read from FASTA headers." in p["input"]["notes"]
    assert "1 identifier converted to upper case." in p["input"]["notes"]
    with ws.session_transaction() as s:
        assert s["foreground_proteins"] == sorted(["Q00001", "Q00002", "Q00003", "Q00004", "Q00005",
                                                   "Q00110", "B0A007", "Q09999"])


def test_fasta_text_as_the_page_sends_it(ws):
    text = ">sp|Q00001|Q00001_SPA Some protein\nMKVLAAG\nMKVL\n>tr|Q00002|Q00002_SPA Other\nMKV\n"
    _load(ws, text.split("\n"))
    with ws.session_transaction() as s:
        assert s["foreground_input"] == ["Q00001", "Q00002"]


def test_each_untested_identifier_has_its_reason(ws):
    _load(ws, PASTED)
    p = _payload(ws.post("/gene_ontology_analysis", json={}))
    ids = p["input_ids"]
    assert ids["pasted"] == 8
    assert {r["id"]: r["reason"] for r in ids["untested"]} == REASONS
    assert p["annotation_stats"]["with_annotations"] == 5
    assert ids["summary"] == ("3 of the 8 pasted foreground identifiers did not enter the test: "
                              "1 not found in this analysis, 1 not in the background and 1 no GO annotation.")
    assert any(w.startswith("Foreground: Isoform suffix removed") for w in p["warnings"])


def test_pasted_as_is_kept_for_rewritten_identifiers(ws):
    _load(ws, ["q00110", "Q00001"])
    rows = _payload(ws.post("/gene_ontology_analysis", json={}))["input_ids"]["untested"]
    assert rows == [{"id": "Q00110", "pasted_as": "q00110", "reason": "no_annotation"}]


def test_reasons_per_orthogroup(ws):
    _load(ws, PASTED)
    p = _payload(ws.post("/gene_ontology_analysis", json={"counting_mode": "per_orthogroup"}))
    assert p["counting"]["mode"] == "per_orthogroup"
    assert {r["id"]: r["reason"] for r in p["input_ids"]["untested"]} == REASONS
    assert p["input_ids"]["labels"]["no_annotation"] == "no GO annotation, its own or its orthogroup's"


def test_evidence_filter_is_named_in_the_reason(ws):
    _load(ws, PASTED)
    # Every annotation here is IEA, so nothing is left to test, and the error says why.
    js = ws.post("/gene_ontology_analysis", json={"evidence_preset": "curated"}).get_json()
    assert js["success"] is False
    assert js["hint"] == ("8 of the 8 pasted foreground identifiers did not enter the test: "
                          "1 not found in this analysis, 1 not in the background and "
                          "6 no GO annotation with the selected evidence codes.")


def test_identifier_in_no_orthogroup_with_expansion(ws):
    # Q00900 is annotated and in the background, but in no orthogroup, so the
    # expansion (which keeps the members of the matched orthogroups) drops it.
    # Expanded sets are counted per orthogroup (P8), where a protein in no
    # orthogroup is a unit of its own, so it is still tested.
    _load(ws, ["Q00001", "Q00900"], expand=True)
    p = _payload(ws.post("/gene_ontology_analysis", json={}))
    assert p["counting"]["mode"] == "per_orthogroup"
    assert p["input_ids"]["untested"] == []


def test_upset_filter_reads_headers_and_case(ws):
    r = ws.post("/upset_data_filtered", json={"species": ["spA", "spB"], "uniprot_ids": [
        ">sp|Q00001|Q00001_SPA Some protein OS=Synthetic", "MKVLAAG", "q00002", "b0a003-2", "Q00900"]})
    js = r.get_json()
    assert js["ok"] is True
    assert js["ids_found"] == ["B0A003", "Q00001", "Q00002"]
    assert (js["ids_not_found"], js["ids_unassigned"]) == ([], ["Q00900"])
    assert js["n_orthogroups"] == 3 and js["n_ids_searched"] == 4
    assert "b0a003-2 → B0A003" in js["input_warnings"][0]


def test_page_texts_describe_what_is_accepted():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "templates"
    for name in ("resultado_goa.html", "tutorial.html"):
        text = (root / name).read_text()
        assert "not recognised" not in text
        assert "FASTA headers" in text
