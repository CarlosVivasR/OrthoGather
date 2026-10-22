"""
Permutation p-values for per-orthogroup GO enrichment.

Counting per orthogroup puts an orthogroup in the foreground when it contains
at least one foreground protein. A family of eight detected paralogues is far
more likely to be "hit" by chance than a pair, so a hypergeometric p-value over
orthogroups favours the functions of large families (transcription regulators,
ABC transporters, two-component systems). In a null simulation it flagged a
large-family term in 77 % of random foregrounds.

The fix keeps the statistic and changes its null distribution: the foreground
labels are shuffled among the background proteins (the units the experiment
actually measured), each shuffle is collapsed to orthogroups exactly like the
observed foreground, and the observed p-value is compared with the shuffled
ones. Family size is then part of the null, and the p-values are valid by
construction (exchangeability of the labels among background proteins).

No Flask, no globals: arrays in, arrays out.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from scipy.stats import hypergeom


def n_permutations(n_terms: int, alpha: float = 0.05) -> int:
    """Enough permutations for the first Benjamini-Hochberg step to be
    reachable with margin: the smallest empirical p is 1/(B+1) and that step
    needs p <= alpha/m, so B = 2m/alpha gives half of it. Bounded to 5,000-50,000."""
    need = int(np.ceil(2 * n_terms / max(alpha, 1e-6)))
    return int(min(50_000, max(5_000, need)))


def permutation_pvalues(base_unit: np.ndarray, n_draw: int, observed_units: np.ndarray,
                        term_units: list, n_universe: int, n_perm: int,
                        seed: int = 20261020, chunk: int = 500):
    """One-sided permutation p-values for each term.

    Parameters
    ----------
    base_unit : int array, one entry per background protein that can carry the
        foreground label: the index of its unit (orthogroup, or the protein
        itself when it is in no orthogroup).
    n_draw : number of foreground proteins (drawn without replacement per shuffle).
    observed_units : int array of the units in the observed foreground.
    term_units : list (one per term) of int arrays: units annotated to the term.
    n_universe : number of units in the universe.
    n_perm : number of shuffles.

    Returns
    -------
    (p_perm, p_hyper) : arrays of length len(term_units). ``p_hyper`` is the
    observed per-orthogroup hypergeometric p-value (the statistic); ``p_perm``
    its permutation p-value, (1 + #{shuffles with p <= observed}) / (n_perm + 1).
    """
    n_terms = len(term_units)
    rows, cols = [], []
    for t, units in enumerate(term_units):
        rows.extend(units)
        cols.extend([t] * len(units))
    M = csr_matrix((np.ones(len(rows), dtype=np.int32), (rows, cols)),
                   shape=(n_universe, n_terms))
    K = np.asarray(M.sum(axis=0)).ravel()

    obs = np.unique(observed_units)
    k_obs = np.asarray(M[obs].sum(axis=0)).ravel()
    p_obs = hypergeom.sf(k_obs - 1, n_universe, K, len(obs))
    # Tolerance so that a shuffle tying the observed value counts as extreme.
    p_cut = p_obs * (1 + 1e-9)

    # A shuffle is at least as extreme as the observation when its p-value is
    # <= the observed one. For a given foreground size n the p-value falls as k
    # rises, so that is the same as k >= k_crit(n): one bisection per distinct
    # n instead of a hypergeometric tail for every shuffle and term.
    kcrit_by_n = {}

    def kcrit(n):
        if n not in kcrit_by_n:
            kmax = np.minimum(K, n)
            lo = np.zeros(n_terms, dtype=np.int64)
            hi = kmax + 1                      # kmax + 1 means "never as extreme"
            while True:
                active = lo < hi
                if not active.any():
                    break
                mid = (lo + hi) // 2
                ok = hypergeom.sf(mid - 1, n_universe, K, n) <= p_cut
                hi = np.where(active & ok, mid, hi)
                lo = np.where(active & ~ok, mid + 1, lo)
            kcrit_by_n[n] = lo
        return kcrit_by_n[n]

    rng = np.random.default_rng(seed)
    exceed = np.zeros(n_terms, dtype=np.int64)
    n_base = len(base_unit)
    done = 0
    while done < n_perm:
        b = min(chunk, n_perm - done)
        f_rows, f_cols, n_units = [], [], np.empty(b, dtype=np.int64)
        for i in range(b):
            units = np.unique(base_unit[rng.choice(n_base, n_draw, replace=False)])
            f_rows.append(np.full(len(units), i))
            f_cols.append(units)
            n_units[i] = len(units)
        F = csr_matrix((np.ones(sum(len(c) for c in f_cols), dtype=np.int32),
                        (np.concatenate(f_rows), np.concatenate(f_cols))),
                       shape=(b, n_universe))
        k = (F @ M).toarray()
        crit = np.stack([kcrit(int(n)) for n in n_units])
        exceed += (k >= crit).sum(axis=0)
        done += b
    p_perm = (1 + exceed) / (n_perm + 1)
    return p_perm, p_obs
