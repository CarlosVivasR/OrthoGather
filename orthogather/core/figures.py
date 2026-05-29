"""
Data builders for the two interactive Plotly charts on the Protein Analysis
page (Figure 1: protein distribution per orthogroup; Figure 2: orthogroup
sharing across species).

These functions return plain dicts — the template renders them client-side.
No matplotlib, no filesystem.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd


def generate_figure_1(gene_count_df: pd.DataFrame):
    """Build the data for Figure 1 — distribution of proteins per orthogroup.

    Returns
    -------
    dict | None
        ``{'xs': [1, 2, ...], 'ys': [n1, n2, ...], 'total': total_orthogroups}``
        or ``None`` if the input is empty / malformed.
    """
    try:
        data = gene_count_df['Total'].replace([np.inf, -np.inf], np.nan).dropna()
        if data.empty:
            return None
        # Integer count per "number of proteins" — preserves every bin (no log
        # scale, no custom non-uniform bins). The frontend handles the long
        # tail via zoom.
        counts = data.astype(int).value_counts().sort_index()
        return {
            'xs': counts.index.tolist(),
            'ys': counts.values.tolist(),
            'total': int(counts.sum()),
        }
    except Exception as e:
        logging.error(f"[ERROR] Could not compute figure_1 data: {e}")
        return None


def generate_figure_2(gene_count_df: pd.DataFrame, axes=None):
    """Build the data for Figure 2 — orthogroup sharing across species.

    Returns
    -------
    dict | None
        ``{'xs': [1..N], 'ys': [...], 'N': num_species, 'total': total_OGs}``
        or ``None`` if the input is empty / malformed.
    """
    try:
        gene_count_df.iloc[:, 1:] = gene_count_df.iloc[:, 1:].apply(
            pd.to_numeric, errors='coerce'
        )
        species = gene_count_df.columns[1:-1]   # drop Orthogroup id + Total
        N = len(species)
        shared = (gene_count_df[species] > 0).sum(axis=1)
        counts = shared.value_counts().sort_index()
        # Make sure every integer 1..N is present (even if 0) so the bar
        # gradient is continuous.
        xs = list(range(1, N + 1))
        ys = [int(counts.get(i, 0)) for i in xs]
        return {
            'xs': xs,
            'ys': ys,
            'N': N,
            'total': int(sum(ys)),
        }
    except Exception as e:
        logging.error(f"[ERROR] Could not compute figure_2 data: {e}")
        return None
