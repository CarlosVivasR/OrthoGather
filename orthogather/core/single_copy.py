"""
Helper to identify single-copy orthogroups (1:1:1... across every species).

OrthoFinder writes ``Orthogroups_SingleCopyOrthologues.txt`` to the output
directory. If the active analysis folder holds that file it is read verbatim;
otherwise the set is derived from ``Orthogroups.GeneCount.tsv`` (an OG is
single-copy iff every per-species column equals exactly 1), which is the same
definition and the file every input mode has.

The result is cached per analysis folder and file modification time, so a new
upload, run or preselected dataset is picked up without explicit invalidation.
"""
from __future__ import annotations

import logging
import os

import pandas as pd


_single_copy_cache = {}


def get_single_copy_orthogroups(folder_path: str) -> set:
    """Return the set of orthogroup IDs that are single-copy (1:1:1...).

    Parameters
    ----------
    folder_path : str
        The active analysis folder (``session['folder_path']``), which holds
        ``Orthogroups.GeneCount.tsv`` and, for OrthoFinder output, possibly
        ``Orthogroups_SingleCopyOrthologues.txt``.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return set()
    sc_path = os.path.join(folder_path, 'Orthogroups_SingleCopyOrthologues.txt')
    gc_path = os.path.join(folder_path, 'Orthogroups.GeneCount.tsv')
    source = sc_path if os.path.exists(sc_path) else gc_path
    if not os.path.exists(source):
        return set()
    key = (os.path.abspath(source), os.path.getmtime(source))
    if key in _single_copy_cache:
        return _single_copy_cache[key]

    sc_set: set = set()
    try:
        if source == sc_path:
            with open(sc_path) as fh:
                sc_set = {ln.strip() for ln in fh if ln.strip()}
        else:
            df = pd.read_csv(gc_path, sep='\t')
            species_cols = [c for c in df.columns if c not in ('Orthogroup', 'Total')]
            if species_cols:
                mask = (df[species_cols] == 1).all(axis=1)
                sc_set = set(df.loc[mask, 'Orthogroup'].astype(str))
    except Exception as e:
        logging.warning(f"[SC] Could not read single-copy orthogroups from {source}: {e}")

    _single_copy_cache.clear()
    _single_copy_cache[key] = sc_set
    logging.info(f"[SC] Loaded {len(sc_set)} single-copy orthogroup IDs from {os.path.basename(source)}")
    return sc_set


def invalidate_single_copy_cache() -> None:
    """Call after a fresh OrthoFinder upload so the next request reloads."""
    _single_copy_cache.clear()
