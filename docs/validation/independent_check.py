"""Does an independent implementation of the enrichment give the same numbers?

The ontology parsing, the propagation over is_a and part_of, the term depth
(longest is_a path), the universe, the one-sided Fisher test (SciPy's
hypergeometric tail), the term-size and depth filters and the
Benjamini-Hochberg correction are written here from scratch, without GOATOOLS
or the application's code, and compared term by term with what OrthoGather
returns for the worked example:

- per protein: two foregrounds x three evidence settings x two universe
  conventions, and "Use all GOA files";
- per orthogroup: the hypergeometric statistic, and the permutation p-values
  of the ten smallest terms against a brute-force permutation with another
  random generator (agreement within Monte Carlo error).

Usage:  python docs/validation/independent_check.py
"""
from __future__ import annotations

import gzip
import random
from collections import defaultdict
from pathlib import Path

import _harness as h
import numpy as np
from orthogather.core.og_permutation import n_permutations
from scipy.stats import hypergeom

EX = h.EXAMPLE / "input_dataset"
PRESETS = {
    "all": None,
    "curated": {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "TAS", "IC", "IBA",
                "HTP", "HEP", "HDA", "HMP", "HGI"},
    "experimental": {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HEP", "HDA", "HMP", "HGI"},
}


def read_obo(path):
    terms, cur = {}, None
    for line in open(path):
        line = line.rstrip("\n")
        if line == "[Term]":
            cur = {"is_a": [], "part_of": [], "alt": [], "obsolete": False}
            continue
        if line.startswith("["):
            cur = None
            continue
        if cur is None or ": " not in line:
            continue
        k, v = line.split(": ", 1)
        if k == "id":
            terms[v] = cur
        elif k == "namespace":
            cur["ns"] = v
        elif k == "is_a":
            cur["is_a"].append(v.split(" ")[0])
        elif k == "relationship" and v.startswith("part_of "):
            cur["part_of"].append(v.split(" ")[1])
        elif k == "alt_id":
            cur["alt"].append(v)
        elif k == "is_obsolete" and v == "true":
            cur["obsolete"] = True
    live = {t: d for t, d in terms.items() if not d["obsolete"]}
    alt = {a: t for t, d in live.items() for a in d["alt"]}
    anc, depth = {}, {}

    def up(t):
        if t not in anc:
            s = set()
            for p in live[t]["is_a"] + live[t]["part_of"]:
                if p in live:
                    s |= {p} | up(p)
            anc[t] = s
        return anc[t]

    def dep(t):
        if t not in depth:
            ps = [p for p in live[t]["is_a"] if p in live]
            depth[t] = 1 + max(dep(p) for p in ps) if ps else 0
        return depth[t]
    for t in live:
        up(t), dep(t)
    return live, alt, anc, depth


def read_gaf(folder, files, codes):
    out = defaultdict(set)
    for fn in files:
        p = Path(folder) / fn
        with (gzip.open if str(p).endswith(".gz") else open)(p, "rt") as fh:
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if line.startswith("!") or len(c) < 9 or not c[4].startswith("GO:") or c[8] not in ("P", "F", "C"):
                    continue
                if "NOT" in c[3].split("|") or (codes is not None and c[6] not in codes):
                    continue
                out[c[1]].add(c[4])
    return dict(out)


def bh(p):
    p = np.asarray(p, float)
    o = np.argsort(p)
    r = np.minimum.accumulate((p[o] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    q = np.empty(len(p))
    q[o] = np.minimum(r, 1)
    return q


def propagate(assoc, onto):
    terms, alt, anc, _ = onto
    out = {}
    for u, gos in assoc.items():
        s = set()
        for g in gos:
            g = alt.get(g, g)
            if g in terms:
                s |= {g} | anc[g]
        out[u] = s
    return out


def enrich(study, assoc, onto, scope="pooled", min_depth=2, lo=10, hi=500):
    terms, _, _, depth = onto
    prop = propagate(assoc, onto)
    rows = []
    for ns in ("biological_process", "cellular_component", "molecular_function"):
        univ = set(assoc) if scope == "pooled" else {u for u, s in prop.items()
                                                     if any(terms[g]["ns"] == ns for g in s)}
        st = {u for u in study if u in univ}
        if not st:
            continue
        pop, hit = defaultdict(int), defaultdict(int)
        for u in univ:
            for g in prop[u]:
                if terms[g]["ns"] == ns:
                    pop[g] += 1
                    hit[g] += u in st
        for g, K in pop.items():
            if depth[g] >= min_depth and lo <= K <= hi:
                rows.append({"GO": g, "k": hit[g], "n": len(st), "K": K, "N": len(univ),
                             "p": float(hypergeom.sf(hit[g] - 1, len(univ), K, len(st)))})
    for r, q in zip(rows, bh([r["p"] for r in rows]) if rows else []):
        r["q"] = float(q)
    return rows


def compare(js, mine, family):
    app = {t["GO"]: t for t in h.terms(js)}
    shown = {r["GO"]: r for r in mine if r["q"] < 1}
    diffs = 0
    for g in set(app) | set(shown):
        a, m = app.get(g), shown.get(g)
        if a is None or m is None:
            diffs += 1
            continue
        same = (a["study_count"], a["study_n"], a["pop_count"], a["pop_n"]) == (m["k"], m["n"], m["K"], m["N"])
        close = all(abs(a[x] - m[y]) <= 1e-9 * max(abs(m[y]), 1e-300) + 1e-15
                    for x, y in (("p_uncorrected", "p"), ("p_fdr_bh", "q")))
        diffs += not (same and close)
    return {"terms_compared": len(set(app) | set(shown)), "differences": diffs,
            "family_app": family, "family_independent": len(mine),
            "significant": sum(r["q"] < 0.05 for r in mine)}


def family_size(ws):
    import pandas as pd
    prov = pd.read_excel(ws.results / "go_enrichment_report.xlsx", sheet_name="Provenance")
    return int(prov.set_index("key").loc["Terms in correction family", "value"])


def main():
    onto = read_obo(h.REPO / "go-basic.obo")
    bg = h.read_list(EX / "background_3181.txt")
    lists = {"decreased_306": h.read_list(EX / "foreground_down-regulated_306.txt"),
             "increased_185": h.read_list(EX / "foreground_up-regulated_185.txt")}
    ws = h.ExampleWorkspace("independent")
    files = list(ws.mapping.values())
    out = {"per_protein": {}, "all_goa": {}, "per_orthogroup": {}}
    ws.background_once(bg)
    for ev, codes in PRESETS.items():
        id2gos = read_gaf(ws.goa_dir, files, codes)
        assoc = {p: id2gos[p] for p in bg if p in id2gos}
        for scope in ("pooled", "per_ontology"):
            for name, fg in lists.items():
                ws.foreground(fg)
                _, js = ws.enrich(evidence_preset=ev, universe_scope=scope, display_p_value=1.0)
                c = compare(js, enrich([p for p in fg if p in assoc], assoc, onto, scope), family_size(ws))
                out["per_protein"][f"{name}/{ev}/{scope}"] = c
                print("per protein", name, ev, scope, c, flush=True)

    id2gos = read_gaf(ws.goa_dir, files, None)
    msm = next(f for sp, f in ws.mapping.items() if "smegmatis" in sp)
    msm_assoc = {p: id2gos[p] for p in read_gaf(ws.goa_dir, [msm], None)}
    ws.new_session()
    ws.background_once(None, all_goa=True)
    for name, fg in lists.items():
        ws.foreground(fg)
        _, js = ws.enrich(display_p_value=1.0)
        c = compare(js, enrich([p for p in fg if p in msm_assoc], msm_assoc, onto), family_size(ws))
        out["all_goa"][name] = c
        print("all GOA files", name, c, flush=True)

    import pandas as pd
    unit = {}
    for _, r in pd.read_csv(ws.folder / "Orthogroups.tsv", sep="\t", dtype=str).iterrows():
        for v in r.iloc[1:].dropna():
            for e in v.split(", "):
                unit[e.split("|")[1]] = r["Orthogroup"]
    u = lambda p: unit.get(p, p)
    ws.new_session()
    ws.background_once(bg)
    units = defaultdict(set)
    for p in bg:
        if p in id2gos:
            units[u(p)] |= set(id2gos[p])
    base = [p for p in dict.fromkeys(bg) if units.get(u(p))]
    prop = propagate(units, onto)
    N = len(units)
    for name, fg in lists.items():
        ws.foreground(fg)
        _, js = ws.enrich(counting_mode="per_orthogroup", display_p_value=1.0)
        b_app = n_permutations(family_size(ws))
        app = {t["GO"]: t for t in h.terms(js)}
        fgb = [p for p in dict.fromkeys(fg) if p in set(base)]
        obs = {u(p) for p in fgb}
        stat_diff = 0
        for g, t in app.items():
            K = sum(g in prop[x] for x in prop)
            k = sum(g in prop[x] for x in obs)
            ph = hypergeom.sf(k - 1, N, K, len(obs))
            stat_diff += (t["pop_count"], t["study_count"]) != (K, k) or abs(t["p_hypergeom"] - ph) > 1e-9 * ph
        top = sorted(app.values(), key=lambda t: t["p_uncorrected"])[:10]
        Ks = np.array([sum(t["GO"] in prop[x] for x in prop) for t in top])
        pobs = np.array([t["p_hypergeom"] for t in top]) * (1 + 1e-9)
        B, rng, exceed = 10000, random.Random(777), np.zeros(len(top))
        member = [{x for x in prop if t["GO"] in prop[x]} for t in top]
        for _ in range(B):
            us = {u(p) for p in rng.sample(base, len(fgb))}
            ks = np.array([len(us & m) for m in member])
            exceed += hypergeom.sf(ks - 1, N, Ks, len(us)) <= pobs
        zs = []
        for t, e in zip(top, exceed):
            pb = (1 + e) / (B + 1)
            se = np.sqrt(pb * (1 - pb) / B + t["p_uncorrected"] * (1 - t["p_uncorrected"]) / b_app)
            zs.append(round(float((t["p_uncorrected"] - pb) / se), 2))
        out["per_orthogroup"][name] = {"statistic_differences": int(stat_diff), "terms": len(app),
                                       "application_permutations": b_app, "brute_force_permutations": B,
                                       "permutation_z_ten_smallest": zs, "max_abs_z": max(map(abs, zs))}
        print("per orthogroup", name, out["per_orthogroup"][name], flush=True)
    h.write_result("independent_check", out)


if __name__ == "__main__":
    main()
