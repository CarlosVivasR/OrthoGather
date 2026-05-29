"""
Pure parsing helpers — string normalisation and tokenisation utilities used
across the species matcher, the GO routes, and the orthogroup pipeline.

These functions have no side effects, take no globals, and are individually
unit-tested in tests/test_species_matching.py.
"""
from __future__ import annotations

import re
from typing import List


def normalize(text: str) -> str:
    """Lower-case the input and strip every non-alphanumeric character.

    >>> normalize("Escherichia coli (strain K12) [UP000000625]")
    'escherichiacolistraink12up000000625'
    """
    return re.sub(r"[^a-zA-Z0-9]", "", text.lower())


def parse_uniprot_block(text_or_list) -> List[str]:
    """Accept either a string or a list of strings and return the cleaned
    list of UniProt accessions.

    Splits on whitespace, commas and semicolons; drops empty tokens.

    >>> parse_uniprot_block("P12345  Q67890,P00001")
    ['P12345', 'Q67890', 'P00001']
    >>> parse_uniprot_block(["P12345", "Q67890"])
    ['P12345', 'Q67890']
    >>> parse_uniprot_block(None)
    []
    """
    if text_or_list is None:
        return []
    if isinstance(text_or_list, list):
        raw = " ".join(map(str, text_or_list))
    else:
        raw = str(text_or_list)
    parts = re.split(r"[\s,;]+", raw.strip())
    return [p for p in (x.strip() for x in parts) if p]
