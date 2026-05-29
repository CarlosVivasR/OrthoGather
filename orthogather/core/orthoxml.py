"""
OrthoXML parser — Quest for Orthologs (QfO) consortium standard format.

Spec:  http://www.orthoxml.org/0.5/orthoxml_doc_v0.5.html
Supported by: OrthoFinder (also exports .xml), OrthoDB, OMA, eggNOG,
              Ensembl Compara, PANTHER, InParanoid, HieranoidDB, MetaPhOrs.

This parser converts an OrthoXML file into the same DataFrame structure
OrthoFinder produces:

    Orthogroups.tsv      : columns = ['Orthogroup', species1, species2, ...]
                           cells   = "src|ACCESSION|ACCESSION, src|..., ..." (comma-joined)
    Orthogroups.GeneCount.tsv : columns = ['Orthogroup', species1, ..., 'Total']
                           cells   = integers

Wrapping accessions in pipes (``src|ACC|ACC``) matches OrthoFinder's output
exactly, so downstream code (the ``re.findall(r'\\|([^|]+)\\|', s)`` extractor
used in foreground/background routes) works unchanged.

The parser also collects metadata (databases, versions, origin) for the
reproducibility manifest (Point 4 of the post-review plan).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# OrthoXML namespace pattern — different spec versions live under different
# URIs (orthoXML.org/2011/, orthoXML.org/2014/, etc.). We strip them all.
_NS_PATTERN = re.compile(r"^\{[^}]+\}")


def _local(tag: str) -> str:
    """Drop the XML namespace, leaving just the element name."""
    return _NS_PATTERN.sub("", tag)


def _iter_local(elem, name: str):
    """Yield direct children whose local name matches ``name``."""
    for child in elem:
        if _local(child.tag) == name:
            yield child


def _find_local(elem, name: str):
    """Return the first direct child with local name == ``name``, or None."""
    return next(_iter_local(elem, name), None)


def _findall_descendants(elem, name: str):
    """Yield every descendant whose local name == ``name`` (any depth)."""
    for d in elem.iter():
        if _local(d.tag) == name:
            yield d


def _safe_species_name(s: str) -> str:
    """Convert a free-text species name (e.g. ``Homo sapiens (Human) [UP000005640]``)
    into a column-friendly token that mirrors OrthoFinder's habit of using
    underscores instead of spaces in column headers.
    Whitespace becomes underscore; everything else is kept (callers can
    use the raw column directly)."""
    return re.sub(r"\s+", "_", s.strip()) or s


def parse_orthoxml(xml_path) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Parse an OrthoXML file into OrthoGather's internal DataFrames.

    Parameters
    ----------
    xml_path : str | Path
        Path to a ``.xml`` / ``.orthoxml`` file.

    Returns
    -------
    (orthogroups_df, gene_count_df, metadata)
        Two DataFrames matching the schema in :mod:`orthogather.core.orthofinder`
        plus a metadata dict for the reproducibility manifest.

    Raises
    ------
    FileNotFoundError
        ``xml_path`` does not exist.
    ValueError
        Malformed XML, missing required elements, or zero groups parsed.
    """
    path = Path(xml_path)
    if not path.exists():
        raise FileNotFoundError(f"OrthoXML file not found: {xml_path}")

    try:
        tree = ET.parse(str(path))
    except ET.ParseError as e:
        raise ValueError(f"Not a valid XML file: {e}")
    root = tree.getroot()

    if _local(root.tag) != "orthoXML":
        raise ValueError(
            f"Root element is <{_local(root.tag)}>, expected <orthoXML>. "
            "This file is XML but does not follow the OrthoXML spec."
        )

    # ------------------------------------------------------------------
    # Pass 1: build gene_id → (species_name, prot_id, source_db, db_version)
    # ------------------------------------------------------------------
    gene_lookup: Dict[str, Tuple[str, str, str, str]] = {}
    species_order: List[str] = []  # preserve XML order so columns are stable
    databases_seen: List[Tuple[str, str]] = []   # (name, version)

    for sp in _iter_local(root, "species"):
        sp_name = sp.attrib.get("name") or sp.attrib.get("NCBITaxId") or "Unknown"
        sp_col  = _safe_species_name(sp_name)
        if sp_col not in species_order:
            species_order.append(sp_col)
        for db in _iter_local(sp, "database"):
            db_name = db.attrib.get("name", "")
            db_ver  = db.attrib.get("version", "")
            if (db_name, db_ver) not in databases_seen:
                databases_seen.append((db_name, db_ver))
            genes_block = _find_local(db, "genes")
            if genes_block is None:
                continue
            for gene in _iter_local(genes_block, "gene"):
                gid = gene.attrib.get("id")
                if not gid:
                    continue
                # OrthoXML allows the protein accession to live under any of:
                #   protId, geneId, transcriptId. Pick the first present.
                acc = (gene.attrib.get("protId")
                       or gene.attrib.get("geneId")
                       or gene.attrib.get("transcriptId")
                       or gid)
                gene_lookup[gid] = (sp_col, acc, db_name, db_ver)

    if not gene_lookup:
        raise ValueError("OrthoXML contains <species> blocks but no <gene> entries.")

    # ------------------------------------------------------------------
    # Pass 2: walk every top-level <orthologGroup> and collect descendants.
    # OrthoXML allows nested <paralogGroup>/<orthologGroup>; for our flat
    # orthogroups model we treat every top-level orthologGroup as a single
    # OG and union its descendant geneRefs.
    # ------------------------------------------------------------------
    groups_block = _find_local(root, "groups")
    if groups_block is None:
        raise ValueError("OrthoXML has no <groups> section — nothing to import.")

    rows = []           # list of dict {Orthogroup, species_col: 'src|acc|acc, ...'}
    count_rows = []     # list of dict {Orthogroup, species_col: int, Total: int}
    og_counter = 0

    for top in _iter_local(groups_block, "orthologGroup"):
        og_counter += 1
        og_id = top.attrib.get("id") or f"OG{og_counter - 1:07d}"
        # Normalise: OrthoFinder uses 'OG0000000' style. Keep XML's id when
        # given, otherwise pad to 7 digits for consistency with TSV files.
        if not og_id.startswith("OG"):
            og_id = f"OG{og_id}"

        # Collect every gene reference descendant of this top-level group.
        gene_ids = [g.attrib["id"] for g in _findall_descendants(top, "geneRef")
                    if g.attrib.get("id")]

        # Group accessions by species
        per_species: Dict[str, List[str]] = {sp: [] for sp in species_order}
        for gid in gene_ids:
            entry = gene_lookup.get(gid)
            if entry is None:
                logging.warning(
                    f"[orthoxml] orthologGroup {og_id} references unknown "
                    f"gene id {gid}; skipped."
                )
                continue
            sp_col, acc, _, _ = entry
            per_species.setdefault(sp_col, []).append(acc)

        # Build the cell string: "src|ACC|ACC, src|ACC|ACC, ..."
        row_proteins = {"Orthogroup": og_id}
        row_counts   = {"Orthogroup": og_id, "Total": 0}
        for sp in species_order:
            accs = per_species.get(sp, [])
            row_proteins[sp] = ", ".join(f"src|{a}|{a}" for a in accs) if accs else ""
            row_counts[sp] = len(accs)
            row_counts["Total"] += len(accs)
        rows.append(row_proteins)
        count_rows.append(row_counts)

    if not rows:
        raise ValueError("OrthoXML <groups> section parsed but yielded zero orthogroups.")

    orthogroups_df = pd.DataFrame(rows, columns=["Orthogroup"] + species_order)
    gene_count_df  = pd.DataFrame(count_rows,
                                  columns=["Orthogroup"] + species_order + ["Total"])

    # Metadata for the manifest. The "origin" hint lets us tell whether
    # this came from OrthoDB, OMA, eggNOG, OrthoFinder, etc. — useful for
    # citations and provenance.
    origin = ""
    if root.attrib.get("origin"):
        origin = root.attrib["origin"]
    elif databases_seen:
        # Use the first database name as a heuristic
        origin = databases_seen[0][0]

    metadata = {
        "source_format": "orthoxml",
        "orthoxml_version": root.attrib.get("version", ""),
        "origin": origin,                 # e.g. "OrthoDB", "OMA", "eggNOG"
        "origin_version": root.attrib.get("originVersion", ""),
        "databases": [{"name": n, "version": v} for n, v in databases_seen],
        "n_species": len(species_order),
        "n_orthogroups": len(rows),
        "n_genes": len(gene_lookup),
    }

    logging.info(
        f"[orthoxml] Parsed {metadata['n_orthogroups']} orthogroups, "
        f"{metadata['n_species']} species, {metadata['n_genes']} genes "
        f"from {path.name} (origin={origin!r})"
    )
    return orthogroups_df, gene_count_df, metadata


def write_orthofinder_tsvs(orthogroups_df: pd.DataFrame,
                            gene_count_df: pd.DataFrame,
                            target_dir) -> None:
    """Write the two DataFrames produced by :func:`parse_orthoxml` to disk in
    the directory layout OrthoFinder uses. After this the rest of OrthoGather
    is able to consume them with zero changes.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    orthogroups_df.to_csv(target / "Orthogroups.tsv",            sep="\t", index=False)
    gene_count_df .to_csv(target / "Orthogroups.GeneCount.tsv",  sep="\t", index=False)
    # Also derive a single-copy list (every species column == 1) for parity
    # with what OrthoFinder writes. Optional — OrthoGather has its own
    # fallback derivation when this file is missing, but writing it speeds
    # up /foreground_analysis with single_copy_only=True.
    species_cols = [c for c in gene_count_df.columns if c not in ("Orthogroup", "Total")]
    if species_cols:
        single_copy = gene_count_df.loc[
            (gene_count_df[species_cols] == 1).all(axis=1), "Orthogroup"
        ].astype(str)
        with open(target / "Orthogroups_SingleCopyOrthologues.txt", "w") as f:
            for og in single_copy:
                f.write(og + "\n")
    logging.info(
        f"[orthoxml] Wrote Orthogroups.tsv + Orthogroups.GeneCount.tsv "
        f"+ Orthogroups_SingleCopyOrthologues.txt to {target}"
    )
