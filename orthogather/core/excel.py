"""
Excel writer for the GOA workflow + the seaborn 4-panel "annotation
distribution" figure that the GO landing page shows after a download.

Both pure functions: take input paths, write output files, return summaries.
No Flask, no globals.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

import pandas as pd

# matplotlib + seaborn were dropped 2026-05-26 (Point 10 — annotation-distribution
# figure migrated to client-side Plotly). The Excel writer itself doesn't need
# either library.


def generate_go_excel(tsv_path: str, species_to_goafile: dict,
                      output_excel_path: str, provenance: dict = None) -> dict:
    """Build the Gene_Ontology_Analysis.xlsx with five sheets:
    Meta, Initial Groups, Filtered Groups, Removed Groups, Groups of Interest,
    and Species & GOA Map.

    Returns a ``summary`` dict with diagnostics (rows, missing species, etc.)
    that the caller surfaces to the user.

    Raises
    ------
    FileNotFoundError
        ``tsv_path`` is missing.
    ValueError
        Empty mapping, malformed TSV, or Excel write failure.
    """
    summary = {
        "tsv_path": tsv_path,
        "output_excel_path": output_excel_path,
        "n_orthogroups": 0,
        "n_species_cols": 0,
        "species_with_goa": sorted(list(species_to_goafile.keys())),
        "species_without_goa": [],
        "rows_zero_annotation": 0,
        "rows_nonzero_annotation": 0,
        "problems": [],
        "warnings": [],
    }

    if not os.path.exists(tsv_path):
        raise FileNotFoundError(f"Orthogroups.tsv not found at {tsv_path}")
    if not isinstance(species_to_goafile, dict) or not species_to_goafile:
        raise ValueError("species_to_goafile is empty or not a dict")

    try:
        df = pd.read_csv(tsv_path, sep='\t')
    except Exception as e:
        raise ValueError(f"Could not read TSV as tab-delimited: {e}")

    if "Orthogroup" not in df.columns:
        raise ValueError("TSV must contain an 'Orthogroup' column as first column")

    species_all = list(df.columns[1:])
    summary["n_orthogroups"] = len(df)
    summary["n_species_cols"] = len(species_all)

    if summary["n_orthogroups"] == 0:
        summary["warnings"].append("TSV has 0 rows (no orthogroups).")

    tsv_species_set = set(species_all)
    goa_species_set = set(species_to_goafile.keys())
    missing_goa_for_tsv_species = sorted(
        [s for s in species_all if s not in goa_species_set]
    )
    extra_goa_species_not_in_tsv = sorted(list(goa_species_set - tsv_species_set))

    summary["species_without_goa"] = missing_goa_for_tsv_species
    if missing_goa_for_tsv_species:
        summary["warnings"].append(
            f"{len(missing_goa_for_tsv_species)} TSV species have no GOA mapping "
            "(ok, they will remain in 'Initial Groups')."
        )
    if extra_goa_species_not_in_tsv:
        summary["warnings"].append(
            f"{len(extra_goa_species_not_in_tsv)} GOA species not found as TSV "
            f"columns: {extra_goa_species_not_in_tsv[:5]}..."
        )

    # Annotation percentage per orthogroup
    percentages = []
    splitter = re.compile(r"\s*,\s*")

    for _, row in df.iterrows():
        total_proteins = 0
        annotated_proteins = 0
        for sp in species_all:
            val = row.get(sp)
            if pd.isna(val):
                continue
            s = str(val).strip()
            if not s:
                continue
            prots = [p for p in splitter.split(s) if p]
            total_proteins += len(prots)
            if sp in goa_species_set:
                annotated_proteins += len(prots)
        pct = (annotated_proteins / total_proteins * 100.0) if total_proteins > 0 else 0.0
        percentages.append(pct)

    df.insert(1, "Annotation Percentage", percentages)

    initial  = df.copy()
    filtered = df[df["Annotation Percentage"] > 0].copy()
    removed  = df[df["Annotation Percentage"] == 0].copy()

    summary["rows_zero_annotation"]   = len(removed)
    summary["rows_nonzero_annotation"] = len(filtered)

    species_with_goa_sorted = sorted(list(goa_species_set & tsv_species_set))
    columns_interest = ["Orthogroup", "Annotation Percentage"] + species_with_goa_sorted
    interest = initial[columns_interest].copy()

    try:
        with pd.ExcelWriter(output_excel_path) as writer:
            # The Meta sheet is the only context a reader gets when this file is
            # opened on its own (a reviewer, a collaborator, a supplementary
            # data archive). "Annotation Percentage" is easy to over-read as
            # "share of proteins carrying GO terms", so state what it really
            # counts, and which sheet is which.
            meta = pd.DataFrame({
                "key": ["n_orthogroups", "n_species_cols",
                        "rows_nonzero_annotation", "rows_zero_annotation",
                        "Annotation Percentage — definition",
                        "Annotation Percentage — caveat",
                        "Sheet: Initial Groups",
                        "Sheet: Filtered Groups",
                        "Sheet: Removed Groups",
                        "Sheet: Groups of Interest"],
                "value": [summary["n_orthogroups"],
                          summary["n_species_cols"],
                          summary["rows_nonzero_annotation"],
                          summary["rows_zero_annotation"],
                          ("For each orthogroup, the percentage of its proteins that belong to a "
                           "species with a GOA annotation file available."),
                          ("This is an upper bound on GO coverage, NOT the share of proteins that "
                           "carry GO terms: a species can have a GOA file and still leave part of "
                           "its proteome without a single GO annotation."),
                          "Every orthogroup, with its Annotation Percentage.",
                          "Orthogroups with Annotation Percentage > 0 (kept).",
                          "Orthogroups with Annotation Percentage = 0 (no GOA-covered species).",
                          ("Every orthogroup, restricted to the species columns that have a GOA "
                           "file. This is the sheet the per-orthogroup counting mode reads."),
                          ],
            })
            meta.to_excel(writer, sheet_name="Meta", index=False)
            initial.to_excel(writer, sheet_name="Initial Groups", index=False)
            filtered.to_excel(writer, sheet_name="Filtered Groups", index=False)
            removed.to_excel(writer, sheet_name="Removed Groups", index=False)
            interest.to_excel(writer, sheet_name="Groups of Interest", index=False)
            m = pd.DataFrame([
                {"species": s, "goa_file": species_to_goafile.get(s, "")}
                for s in species_all
            ])
            m.to_excel(writer, sheet_name="Species & GOA Map", index=False)
            if provenance:
                cat = provenance.get("catalogue", {}) or {}
                g = provenance.get("goa", {}) or {}
                onto = provenance.get("ontology", {}) or {}
                pr = provenance.get("proteome", {}) or {}
                _join = lambda v: ", ".join(v) if isinstance(v, list) else v
                prov_rows = [
                    ("OrthoGather version",           provenance.get("orthogather_version")),
                    ("Excel generated at",            provenance.get("generated_at")),
                    ("Proteome data source",          pr.get("source")),
                    ("UniProt release",               _join(pr.get("release"))),
                    ("UniProt release date",          _join(pr.get("release_date"))),
                    ("Proteome catalogue version",    cat.get("version")),
                    ("Proteome catalogue downloaded",  cat.get("downloaded_at")),
                    ("Proteome count",                cat.get("proteome_count")),
                    ("OrthoFinder version",           provenance.get("orthofinder_version")),
                    ("GO ontology version",           onto.get("data_version")),
                    ("GOA data generated (EBI)",      _join(g.get("data_generated"))),
                    ("GOA GO-version (EBI)",          _join(g.get("go_version"))),
                    ("GOA downloaded at",             g.get("downloaded_at")),
                    ("GOA source",                    g.get("source")),
                    ("GOA files",                     g.get("n_files")),
                ]
                pd.DataFrame(prov_rows, columns=["key", "value"]).to_excel(
                    writer, sheet_name="Provenance", index=False)
    except Exception as e:
        raise ValueError(f"Failed to write Excel: {e}")

    logging.info(f"✅ GOA Excel saved to {output_excel_path}")
    logging.info(
        f"🧬 Species (TSV) with GOA: {len(species_with_goa_sorted)} / {len(species_all)}"
    )
    if missing_goa_for_tsv_species:
        logging.warning(
            f"⚠️ Missing GOA (TSV): {missing_goa_for_tsv_species[:8]}"
            f"{'...' if len(missing_goa_for_tsv_species) > 8 else ''}"
        )
    if extra_goa_species_not_in_tsv:
        logging.warning(
            f"⚠️ Extra GOA (not in TSV): {extra_goa_species_not_in_tsv[:8]}"
            f"{'...' if len(extra_goa_species_not_in_tsv) > 8 else ''}"
        )
    return summary


def compute_annotation_distribution(excel_path: str) -> dict:
    """Compute the data series the frontend needs to render the annotation-
    distribution figure (interactive Plotly version, v2 — Point 10 redesign).

    The v2 figure is *one* stacked histogram of OGs with >0% annotation,
    stratified by how many annotated species contributed proteins to each OG
    (the "diversity of evidence" axis), plus a companion horizontal bar of
    per-species total annotated-protein contribution. This directly answers
    the reviewer-relevant question that the old 4-panel layout glossed over:
    *is the annotation broad-based or driven by a few well-studied species?*

    Returns
    -------
    dict
        ``{
          "all":     [pct, ...],            # every OG (used for stats)
          "nonzero": [pct, ...],            # OGs with >0% annotation
          "stats_all":     {...},           # min, q1, median, q3, max, mean, n
          "stats_nonzero": {...},
          "histogram_bins": [0, 10, ..., 100],
          "stratified": {                   # one stacked histogram, nonzero OGs
            "strata":     ["1 species", "2 species", ..., "5+ species"],
            "counts":     [[bin0..bin9], [bin0..bin9], ...],   # 5 × 10
            "bin_labels": ["0–10", "10–20", ..., "90–100"],
          },
          "n_annotated_species": int,       # species that had a GOA file
          "n_zero_og": int,                 # OGs with 0% annotation (context)
        }``

    Raises
    ------
    FileNotFoundError
        ``excel_path`` does not exist.
    ValueError
        The Excel exists but lacks an "Annotation Percentage" column (i.e.
        the user hasn't completed the GOA download step).
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel not found: {excel_path}")

    df = pd.read_excel(excel_path, sheet_name="Initial Groups")
    if "Annotation Percentage" not in df.columns:
        raise ValueError(
            "The 'Annotation Percentage' column is missing from "
            "'Initial Groups'. Re-run 'Download GOA files' to rebuild the Excel."
        )

    # Identify which species columns are "annotated" (i.e. had a GOA file).
    # We get that from the "Species & GOA Map" sheet that excel writer emits.
    annotated_species: set[str] = set()
    try:
        map_df = pd.read_excel(excel_path, sheet_name="Species & GOA Map")
        if {"species", "goa_file"}.issubset(map_df.columns):
            mask = map_df["goa_file"].astype(str).str.strip().ne("") & \
                   map_df["goa_file"].notna()
            annotated_species = set(map_df.loc[mask, "species"].astype(str))
    except Exception:
        # Older Excel without the map sheet — figure still renders, just
        # without the stratified breakdown.
        pass

    species_cols = [c for c in df.columns
                    if c not in ("Orthogroup", "Annotation Percentage")]
    annotated_cols = [c for c in species_cols if c in annotated_species]

    all_pct      = df["Annotation Percentage"].dropna()
    nonzero_mask = all_pct > 0
    nonzero_pct  = all_pct[nonzero_mask]

    def _stats(series):
        if series.empty:
            return {"min": 0, "q1": 0, "median": 0, "q3": 0,
                    "max": 0, "mean": 0, "n": 0}
        return {
            "min":    float(series.min()),
            "q1":     float(series.quantile(0.25)),
            "median": float(series.median()),
            "q3":     float(series.quantile(0.75)),
            "max":    float(series.max()),
            "mean":   float(series.mean()),
            "n":      int(series.shape[0]),
        }

    # ---- Stratified histogram + per-species contribution ----
    # For each OG with >0% annotation, count how many *annotated* species
    # contributed proteins. Strata are clipped to 5+ to keep the legend short.
    bin_edges = list(range(0, 101, 10))         # [0,10,...,100]
    n_bins = len(bin_edges) - 1                 # 10
    strata_labels = ["1 species", "2 species", "3 species",
                     "4 species", "5+ species"]
    n_strata = len(strata_labels)
    counts = [[0] * n_bins for _ in range(n_strata)]

    splitter = re.compile(r"\s*,\s*")

    nz_df = df[nonzero_mask]
    for _, row in nz_df.iterrows():
        n_sp_with_annot = 0
        for sp in annotated_cols:
            val = row.get(sp)
            if pd.isna(val):
                continue
            s = str(val).strip()
            if not s:
                continue
            prots = [p for p in splitter.split(s) if p]
            if prots:
                n_sp_with_annot += 1

        pct = float(row["Annotation Percentage"])
        # Bin index: clip 100% into last bin (0-10, 10-20, ..., 90-100).
        bin_idx = min(int(pct // 10), n_bins - 1)
        # Stratum: 1 species → idx 0, ..., 5+ species → idx 4. 0 should not
        # happen here (we're iterating nonzero OGs) but guard anyway.
        if n_sp_with_annot >= 1:
            stratum_idx = min(n_sp_with_annot - 1, n_strata - 1)
            counts[stratum_idx][bin_idx] += 1

    bin_labels = [f"{bin_edges[i]}–{bin_edges[i+1]}"
                  for i in range(n_bins)]
    # Make the first bin label honest: nonzero OGs in 0-10% means (0, 10].
    bin_labels[0] = "0–10"

    n_zero_og = int((~nonzero_mask).sum())

    return {
        "all":            all_pct.tolist(),
        "nonzero":        nonzero_pct.tolist(),
        "stats_all":      _stats(all_pct),
        "stats_nonzero":  _stats(nonzero_pct),
        "histogram_bins": bin_edges,
        "stratified": {
            "strata":     strata_labels,
            "counts":     counts,
            "bin_labels": bin_labels,
        },
        "n_annotated_species": len(annotated_cols),
        "n_zero_og":      n_zero_og,
    }


# `generate_go_image_from_excel` was removed 2026-05-26 (Point 10 of the
# post-review plan). The 4-panel matplotlib/seaborn PNG was replaced by an
# interactive Plotly chart rendered client-side. See `compute_annotation_distribution`
# above and `renderAnnotationDistribution()` in templates/resultado_goa.html.


def clear_goa_dir(goa_dir: str) -> None:
    """Remove everything inside ``goa_dir`` (files and subdirectories)."""
    p = Path(goa_dir)
    p.mkdir(parents=True, exist_ok=True)
    for item in p.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except FileNotFoundError:
                    pass
        except Exception as e:
            logging.warning(f"[WARN] Could not delete {item}: {e}")
