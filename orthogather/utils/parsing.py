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


# UniProtKB accession format (uniprot.org/help/accession_numbers) and UniParc.
_UNIPROT_ACC = r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
_ACCESSION_RE = re.compile(rf"(?:{_UNIPROT_ACC}|UPI[0-9A-F]{{10}})")
_ISOFORM_RE = re.compile(rf"({_UNIPROT_ACC})-([0-9]+)")
# A FASTA sequence line: residues only. Every accession carries a digit, so
# none of them can be mistaken for one.
_SEQUENCE_LINE_RE = re.compile(r"[A-Za-z*\-]+")


def normalise_accession(token: str):
    """Reduce one pasted identifier to the accession the GOA files use.

    Returns ``(accession, changes)``, where ``changes`` lists what was done:
    ``"fasta_header"`` (``>sp|P12345|NAME`` or ``sp|P12345|NAME`` -> ``P12345``),
    ``"upper_case"`` and ``"isoform"`` (``P12345-2`` -> ``P12345``: GOA files
    annotate the canonical accession). Case is changed only for tokens shaped
    like a UniProt accession, so identifiers from other FASTA files are kept.

    >>> normalise_accession(">sp|P12345-2|NAME_ECOLI")
    ('P12345', ['fasta_header', 'isoform'])
    >>> normalise_accession("q00004")
    ('Q00004', ['upper_case'])
    >>> normalise_accession("contig1_17")
    ('contig1_17', [])
    """
    changes = []
    acc = token.strip().strip("\"'").lstrip(">")
    if ":" in acc and acc.split(":", 1)[0].lower() in ("uniprotkb", "uniprot", "sp", "tr"):
        acc = acc.split(":", 1)[1]           # "UniProtKB:P12345", as in GAF files
    fields = acc.split("|")
    if len(fields) >= 3 or (len(fields) == 2 and fields[0].lower() in ("sp", "tr")):
        acc = fields[1].strip()
        changes.append("fasta_header")
    upper = acc.upper()
    if upper != acc and (_ACCESSION_RE.fullmatch(upper) or _ISOFORM_RE.fullmatch(upper)):
        acc = upper
        changes.append("upper_case")
    iso = _ISOFORM_RE.fullmatch(acc)
    if iso:
        acc = iso.group(1)
        changes.append("isoform")
    return acc, changes


def parse_identifier_list(text_or_list) -> dict:
    """Read a pasted list of identifiers, with what was changed along the way.

    Accepts accessions separated by whitespace, commas or semicolons, and FASTA:
    a line that starts with ``>``, or whose first word is ``db|ACC|NAME`` and
    is followed by a description, is a header and gives one accession; the
    sequence lines after a header are skipped. A list is read one element per
    line. Each identifier goes through :func:`normalise_accession`, and
    duplicates are dropped after normalisation, keeping the first.

    Returns a dict with ``ids`` (in input order), ``changed`` (one
    ``{"input", "id", "changes"}`` per identifier that was rewritten),
    ``duplicates``, ``headers`` and ``sequence_lines``.

    >>> r = parse_identifier_list(">sp|P12345|A_ECOLI Protein A OS=E. coli\\nMKVL\\nq67890 P12345")
    >>> r["ids"], r["duplicates"], r["headers"], r["sequence_lines"]
    (['P12345', 'Q67890'], 1, 1, 1)
    """
    out = {"ids": [], "changed": [], "duplicates": 0, "headers": 0, "sequence_lines": 0}
    if text_or_list is None:
        return out
    if isinstance(text_or_list, (list, tuple)):
        lines = [str(x) for x in text_or_list]
    else:
        lines = str(text_or_list).splitlines()
    seen = set()
    in_record = False
    for line in (l for chunk in lines for l in chunk.splitlines()):
        line = line.strip()
        if not line:
            continue
        tokens = [t for t in re.split(r"[\s,;]+", line) if t]
        if line.startswith(">"):
            tokens = line[1:].split()[:1]
            out["headers"] += 1
            in_record = True
        elif (tokens[0].count("|") >= 2 and any("|" not in t for t in tokens[1:])
              and not all(_ACCESSION_RE.fullmatch(t.upper()) or _ISOFORM_RE.fullmatch(t.upper())
                          for t in tokens[1:] if "|" not in t)):
            # "sp|P12345|NAME description words": a FASTA header without ">".
            # A line of db|ACC|NAME entries and bare accessions is a list.
            tokens = tokens[:1]
            out["headers"] += 1
            in_record = True
        elif in_record and _SEQUENCE_LINE_RE.fullmatch(line.replace(" ", "")):
            out["sequence_lines"] += 1
            continue
        else:
            in_record = False
        for token in tokens:
            acc, changes = normalise_accession(token)
            if not acc:
                continue
            if changes:
                out["changed"].append({"input": token, "id": acc, "changes": changes})
            if acc in seen:
                out["duplicates"] += 1
                continue
            seen.add(acc)
            out["ids"].append(acc)
    return out


def parse_uniprot_block(text_or_list) -> List[str]:
    """Accept either a string or a list of strings and return the cleaned
    list of UniProt accessions (see :func:`parse_identifier_list`).

    >>> parse_uniprot_block("P12345  Q67890,P00001")
    ['P12345', 'Q67890', 'P00001']
    >>> parse_uniprot_block(["P12345", "Q67890"])
    ['P12345', 'Q67890']
    >>> parse_uniprot_block(None)
    []
    """
    return parse_identifier_list(text_or_list)["ids"]


def orthogroup_cell_accessions(cell) -> List[str]:
    """Accessions in one species cell of Orthogroups.tsv.

    OrthoFinder keeps the first word of each FASTA header, so a cell built from
    UniProt FASTA reads ``tr|A0QNX2|A0QNX2_MYCS2, tr|A0QNX3|A0QNX3_MYCS2``,
    while one built from other FASTA files holds bare identifiers. Both forms
    are accepted, as in :func:`orthogather.core.excel._accession`.

    >>> orthogroup_cell_accessions("tr|A0QNX2|A0QNX2_MYCS2, sp|P12345|X_ECOLI")
    ['A0QNX2', 'P12345']
    >>> orthogroup_cell_accessions("contig1_17, UPI00000000D1")
    ['contig1_17', 'UPI00000000D1']
    """
    if cell is None:
        return []
    out = []
    for entry in str(cell).split(","):
        entry = entry.strip()
        if not entry or entry.lower() == "nan":
            continue
        fields = entry.split("|")
        out.append(fields[1] if len(fields) >= 3 else entry)
    return out
