"""FASTA identifiers whose second field is not the protein (review of
30-Oct-2026).

Identifiers split on "|" were read by their second field (the last one of an
NCBI gnl|DB|ID). For a JGI proteome that is the genome (jgi|Aspni7|1234|...),
so every protein became the same identifier, in the pasted lists and in the
orthogroups; gi|n|ref|NP_207527.1| gave the GI number, so the accession pasted
was not found; and the chains of one PDB entry became one protein.
UniProt headers (sp|, tr|) are read as before.
"""
from __future__ import annotations

import pytest

from orthogather.core.excel import _accession
from orthogather.utils.parsing import (header_identifier, normalise_accession,
                                       orthogroup_cell_accessions, parse_identifier_list)


@pytest.mark.parametrize("header, expected", [
    ("sp|P12345|NAME_ECOLI", "P12345"),
    ("tr|A0QNX2|A0QNX2_MYCS2", "A0QNX2"),
    ("gnl|extdb|IS27_00001", "IS27_00001"),
    ("jgi|Aspni7|1234|e_gw1.1.1", "1234"),
    ("gi|15645353|ref|NP_207527.1|", "NP_207527.1"),
    ("pdb|1ABC|A", "1ABC_A"),
    ("ref|NP_207527.1|", "NP_207527.1"),
])
def test_each_prefix_gives_the_protein(header, expected):
    assert header_identifier(header.split("|")) == expected
    assert _accession(header) == expected


def test_a_jgi_proteome_keeps_one_identifier_per_protein():
    cell = "jgi|Aspni7|1234|e_gw1.1.1, jgi|Aspni7|5678|fgenesh1_pg.1_#_2"
    assert orthogroup_cell_accessions(cell) == ["1234", "5678"]
    pasted = parse_identifier_list(["jgi|Aspni7|1234|e_gw1.1.1", "jgi|Aspni7|5678|x"])["ids"]
    assert pasted == ["1234", "5678"]


def test_the_chains_of_a_pdb_entry_stay_apart():
    assert orthogroup_cell_accessions("pdb|1ABC|A, pdb|1ABC|B") == ["1ABC_A", "1ABC_B"]


def test_uniprot_headers_are_read_as_before():
    assert normalise_accession(">sp|P12345-2|NAME_ECOLI") == ("P12345", ["fasta_header", "isoform"])
    assert normalise_accession("tr|A0QNX2|A0QNX2_MYCS2")[0] == "A0QNX2"
