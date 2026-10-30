"""Species named "Candidatus ..." (review of 30-Oct-2026).

The base of "Candidatus Pelagibacter ubique HTCC1062" was read as
"Candidatus Pelagibacter", so the species was matched to the first proteome of
that genus, Candidatus Pelagibacter giovannonii, and its GOA file was used.
UniProt labels the right one "Pelagibacter ubique (strain HTCC1062)".
Matching applies only when the analysis does not know the proteome ID
(uploads, names without provenance).
"""
from __future__ import annotations

from orthogather.core.catalogue import match_species, split_species_name

CATALOGUE = [
    {"label": "Candidatus Pelagibacter giovannonii [UP000501094]", "Proteome Id": "UP000501094"},
    {"label": "Pelagibacter ubique (strain HTCC1062) [UP000002528]", "Proteome Id": "UP000002528"},
    {"label": "Escherichia coli (strain K12) [UP000000625]", "Proteome Id": "UP000000625"},
]


def _match(name):
    return (match_species([name], CATALOGUE)[0]["match"] or {}).get("Proteome Id")


def test_candidatus_is_not_part_of_the_binomial():
    assert split_species_name("Candidatus Pelagibacter ubique HTCC1062") == ("Pelagibacter ubique", "HTCC1062")


def test_the_strain_written_with_candidatus_finds_its_proteome():
    assert _match("Candidatus Pelagibacter ubique HTCC1062") == "UP000002528"


def test_a_label_that_keeps_candidatus_still_matches():
    assert _match("Candidatus Pelagibacter giovannonii") == "UP000501094"


def test_other_names_are_split_as_before():
    assert split_species_name("Escherichia coli K12") == ("Escherichia coli", "K12")
    assert _match("Escherichia coli K12") == "UP000000625"
