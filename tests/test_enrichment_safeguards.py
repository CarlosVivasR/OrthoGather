"""Tests for the safeguards added after the October 2026 audit.

- Per-orthogroup counting: the permutation p-values keep the hypergeometric
  statistic but stay calibrated when large families are more likely to be hit.
- Orthogroups.tsv cells: accessions are read from both ``db|ACC|NAME`` and
  bare identifiers.
- "Use all GOA files": each GOA file maps to the accessions it annotates, so the
  universe can be limited to the foreground's species.
- OrthoFinder: a failed run is reported as failed and leaves nothing behind
  that could be taken for its result.
"""
from __future__ import annotations

import os
import stat

import numpy as np
import pytest
from scipy.stats import fisher_exact

from orthogather.core.og_permutation import n_permutations, permutation_pvalues
from orthogather.core.goa import proteins_by_goa_file
from orthogather.utils.parsing import orthogroup_cell_accessions


# --------------------------------------------------------------------------
# Orthogroups.tsv cells
# --------------------------------------------------------------------------
def test_orthogroup_cell_accessions_reads_both_formats():
    assert orthogroup_cell_accessions("tr|A0QNX2|A0QNX2_MYCS2, sp|P12345|X_ECOLI") == ["A0QNX2", "P12345"]
    assert orthogroup_cell_accessions("contig1_17, UPI00000000D1") == ["contig1_17", "UPI00000000D1"]
    assert orthogroup_cell_accessions(None) == []
    assert orthogroup_cell_accessions("nan") == []


# --------------------------------------------------------------------------
# Per-orthogroup permutation p-values
# --------------------------------------------------------------------------
def _families():
    """40 families of 8 paralogues (term 0) and 320 pairs, 50 of them with term 1
    and the other 270 with term 2. Returns (unit of each protein, units of each
    term, number of units)."""
    unit, terms = [], [[], [], []]
    u = 0
    for _ in range(40):
        unit += [u] * 8
        terms[0].append(u)
        u += 1
    for i in range(320):
        unit += [u] * 2
        terms[1 if i < 50 else 2].append(u)
        u += 1
    return np.array(unit), [np.array(t) for t in terms], u


def test_permutation_statistic_is_the_one_sided_fisher_p():
    unit, terms, n_units = _families()
    rng = np.random.default_rng(0)
    drawn = rng.choice(len(unit), 100, replace=False)
    obs = np.unique(unit[drawn])
    _, p_hyp = permutation_pvalues(unit, 100, obs, terms, n_units, n_perm=200)
    for t, units in enumerate(terms):
        a = int(np.isin(obs, units).sum())
        b = len(obs) - a
        c = len(units) - a
        d = n_units - len(obs) - c
        assert p_hyp[t] == pytest.approx(fisher_exact([[a, b], [c, d]], alternative="greater")[1])


def test_permutation_pvalues_are_calibrated_where_hypergeometric_is_not():
    """Random foregrounds: the big-family term must not come out significant
    more often than alpha. The hypergeometric p-value on orthogroups fails this."""
    unit, terms, n_units = _families()
    rng = np.random.default_rng(1)
    reps, perm_hits, hyp_hits = 150, 0, 0
    for rep in range(reps):
        drawn = rng.choice(len(unit), 100, replace=False)
        obs = np.unique(unit[drawn])
        p_perm, p_hyp = permutation_pvalues(unit, 100, obs, terms, n_units, n_perm=400, seed=rep)
        perm_hits += p_perm[0] <= 0.05
        hyp_hits += p_hyp[0] <= 0.05
    assert perm_hits / reps <= 0.10
    assert hyp_hits / reps >= 0.30


def test_permutation_detects_a_real_signal():
    """One protein from each of 40 of the 50 term-1 pairs, plus 60 proteins from
    term-2 pairs: term 1 is genuinely over-represented and must come out."""
    unit, terms, n_units = _families()
    rng = np.random.default_rng(2)
    sig_pairs = rng.choice(terms[1], 40, replace=False)
    drawn = [np.flatnonzero(unit == u)[0] for u in sig_pairs]
    drawn += list(rng.choice(np.flatnonzero(np.isin(unit, terms[2])), 60, replace=False))
    drawn = np.array(drawn)
    p_perm, _ = permutation_pvalues(unit, len(drawn), np.unique(unit[drawn]), terms, n_units, n_perm=2000)
    assert p_perm[1] < 0.01


def test_n_permutations_reaches_the_first_bh_step():
    for m in (10, 600, 5000):
        b = n_permutations(m)
        assert 5_000 <= b <= 50_000
        if 2 * m / 0.05 <= 50_000:
            assert 1 / (b + 1) <= 0.05 / m


# --------------------------------------------------------------------------
# "Use all GOA files": accessions per GOA file
# --------------------------------------------------------------------------
def test_proteins_by_goa_file(tmp_path):
    (tmp_path / "1.A.goa").write_text("!gaf-version: 2.2\nUniProtKB\tA1\tx\t\tGO:0006412\tx\tIEA\t\tP\n"
                                      "UniProtKB\tA2\tx\t\tGO:0006412\tx\tIEA\t\tP\n")
    (tmp_path / "2.B.goa").write_text("UniProtKB\tB1\tx\t\tGO:0006412\tx\tIEA\t\tP\n")
    out = proteins_by_goa_file(str(tmp_path))
    assert out == {"1.A.goa": {"A1", "A2"}, "2.B.goa": {"B1"}}
    assert proteins_by_goa_file(str(tmp_path), limit_files=["2.B.goa"]) == {"2.B.goa": {"B1"}}


# --------------------------------------------------------------------------
# OrthoFinder failures
# --------------------------------------------------------------------------
@pytest.fixture
def orthofinder_workspace(tmp_path, monkeypatch):
    """Point the app's working folder to a temp dir and put a fake OrthoFinder
    on PATH. Never touches the real Proteomas/ folder."""
    import app as og
    work = tmp_path / "Proteomas"
    work.mkdir()
    monkeypatch.setattr(og, "PROTEOMES_FOLDER", str(work))
    monkeypatch.setattr(og, "_snapshot_run",
                        lambda *a, **k: pytest.fail("a failed run must not be saved"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def install(script):
        exe = bin_dir / "orthofinder"
        exe.write_text("#!/bin/sh\n" + script)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")

    return og, work, install


def _stream(og):
    body = og.app.test_client().get("/stream_orthofinder").get_data(as_text=True)
    return [l[6:] for l in body.splitlines() if l.startswith("data: ")]


def test_failed_orthofinder_run_is_reported_and_leaves_no_old_results(orthofinder_workspace):
    og, work, install = orthofinder_workspace
    old = work / "OrthoFinder" / "Results_Jan01" / "Orthogroups"
    old.mkdir(parents=True)
    for name in ("Orthogroups.tsv", "Orthogroups.GeneCount.tsv"):
        (old / name).write_text("Orthogroup\tSTALE\n")
    (work / "Orthogroups.zip").write_bytes(b"previous run")
    install("echo 'OrthoFinder version 2.5.5'\nexit 1\n")
    lines = _stream(og)
    assert lines[-1] == "FAILED"
    assert "DONE" not in lines
    assert not (work / "Orthogroups.zip").exists()
    assert not (work / "OrthoFinder").exists()


def test_missing_orthofinder_is_reported(orthofinder_workspace, monkeypatch):
    og, work, install = orthofinder_workspace
    monkeypatch.setenv("PATH", f"/usr/bin{os.pathsep}/bin")
    lines = _stream(og)
    assert lines[-1] == "FAILED"
    assert any("not found" in l for l in lines)


# --------------------------------------------------------------------------
# Single-copy orthogroups of the active analysis
# --------------------------------------------------------------------------
def _gene_count(folder, rows):
    import pandas as pd
    pd.DataFrame(rows, columns=["Orthogroup", "spA", "spB", "Total"]).to_csv(
        folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)


def test_single_copy_from_gene_counts(tmp_path):
    from orthogather.core.single_copy import get_single_copy_orthogroups
    _gene_count(tmp_path, [["OG1", 1, 1, 2], ["OG2", 2, 1, 3], ["OG3", 1, 0, 1]])
    assert get_single_copy_orthogroups(str(tmp_path)) == {"OG1"}


def test_single_copy_prefers_orthofinder_list(tmp_path):
    from orthogather.core.single_copy import get_single_copy_orthogroups
    _gene_count(tmp_path, [["OG1", 1, 1, 2]])
    (tmp_path / "Orthogroups_SingleCopyOrthologues.txt").write_text("OG7\nOG8\n")
    assert get_single_copy_orthogroups(str(tmp_path)) == {"OG7", "OG8"}


def test_single_copy_without_analysis_is_empty(tmp_path):
    from orthogather.core.single_copy import get_single_copy_orthogroups
    assert get_single_copy_orthogroups(None) == set()
    assert get_single_copy_orthogroups(str(tmp_path)) == set()
