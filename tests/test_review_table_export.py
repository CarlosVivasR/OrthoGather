"""The results table says what it counts and exports the p-values (review of
30-Oct-2026).

The help of the Study and Pop columns said "proteins" also when counting per
orthogroup, where they are units; and the CSV/TSV export of the table left
out the raw p-value, the hypergeometric statistic of per-orthogroup runs and
whether each term is significant.
"""
from __future__ import annotations

import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "templates" / "resultado_goa.html").read_text()


def test_study_and_pop_help_says_units_per_orthogroup():
    for col in ("study_count", "pop_count"):
        th = re.search(rf'data-sort="{col}"[^>]*title="([^"]+)"', PAGE).group(1)
        assert "Counted per orthogroup, these are units" in th


def test_the_table_export_has_the_p_values_and_significance():
    cols = re.search(r'const cols = \[([^\]]+)\];', PAGE).group(1)
    for c in ("p_uncorrected", "p_hypergeom", "p_fdr_bh", "significant"):
        assert f'"{c}"' in cols


def test_the_run_summary_counts_the_identifiers_the_server_read():
    # The box holds lines; 70 identifiers pasted on one line were "1 pasted identifier".
    assert "loadedCounts.fg = js.input?.n_ids" in PAGE
    assert "loadedCounts.bg = js.input?.n_ids" in PAGE
    assert re.search(r"const n = loadedCounts\[which\] \?\?", PAGE)


def test_the_columns_of_the_table_export_keep_their_places():
    cols = [c.strip().strip('"') for c in re.search(r'const cols = \[([^\]]+)\];', PAGE).group(1).split(",")]
    assert cols[:11] == ["GO", "name", "namespace", "direction", "depth", "study_count", "study_n",
                         "pop_count", "pop_n", "p_fdr_bh", "neg_log10_fdr"]
