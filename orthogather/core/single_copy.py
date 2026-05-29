"""
Helper to identify single-copy orthogroups (1:1:1... across every species).

OrthoFinder writes ``Orthogroups_SingleCopyOrthologues.txt`` to the output
directory. If that file exists we read it verbatim; otherwise we derive the
set from ``Orthogroups.GeneCount.tsv`` (an OG is single-copy iff every
per-species column equals exactly 1).

The cache is module-level for performance — it's a read-only set whose
identity changes only when the user uploads a new OrthoFinder result, at
which point :func:`invalidate_single_copy_cache` resets it.
"""
from __future__ import annotations

import logging
import os

import pandas as pd


_single_copy_cache = None


def get_single_copy_orthogroups(upload_root: str) -> set:
    """Return the set of orthogroup IDs that are single-copy (1:1:1...).

    Parameters
    ----------
    upload_root : str
        The Flask ``UPLOAD_FOLDER`` (or any directory containing OrthoFinder
        output sub-folders). Pass ``app.config['UPLOAD_FOLDER']`` from the
        calling route.
    """
    global _single_copy_cache
    if _single_copy_cache is not None:
        return _single_copy_cache

    sc_set: set = set()
    if upload_root and os.path.isdir(upload_root):
        for sub in os.listdir(upload_root):
            base = os.path.join(upload_root, sub)
            if not os.path.isdir(base):
                continue
            sc_path = os.path.join(base, 'Orthogroups_SingleCopyOrthologues.txt')
            if os.path.exists(sc_path):
                try:
                    with open(sc_path) as fh:
                        sc_set = {ln.strip() for ln in fh if ln.strip()}
                    break
                except Exception as e:
                    logging.warning(f"[SC] Could not read {sc_path}: {e}")
            # Fallback: compute from GeneCount
            gc_path = os.path.join(base, 'Orthogroups.GeneCount.tsv')
            if not sc_set and os.path.exists(gc_path):
                try:
                    df = pd.read_csv(gc_path, sep='\t')
                    species_cols = [c for c in df.columns
                                    if c not in ('Orthogroup', 'Total')]
                    if species_cols:
                        mask = (df[species_cols] == 1).all(axis=1)
                        sc_set = set(df.loc[mask, 'Orthogroup'].astype(str))
                        break
                except Exception as e:
                    logging.warning(
                        f"[SC] Could not derive single-copy from {gc_path}: {e}"
                    )

    _single_copy_cache = sc_set
    logging.info(f"[SC] Loaded {len(sc_set)} single-copy orthogroup IDs")
    return sc_set


def invalidate_single_copy_cache() -> None:
    """Call after a fresh OrthoFinder upload so the next request reloads."""
    global _single_copy_cache
    _single_copy_cache = None
