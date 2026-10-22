"""Does expansion to orthogroups recover the functions of a species whose GO
annotations are hidden, without inventing any?

The data are the worked example's (six species, OrthoFinder run of 5 August
2026, GOA files of 28 July 2026). One species' GOA file is left out, the
foreground and the background are expanded to full orthogroups, and the sets
are counted per orthogroup (which OrthoGather always does for expanded sets), so
only the annotations of orthologues in the other five species are available.

Parts (run one per process, or all):

  ecoli   E. coli K-12 hidden. For 40 biological processes with experimental
          evidence in E. coli (EXP, IDA, IPI, IMP, IGI, IEP and the high-
          throughput codes, propagated by is_a and part_of; 15-80 proteins, depth
          >= 4, pairwise Jaccard < 0.5), the foreground is the process's proteins
          ("pure") or those plus as many random E. coli proteins ("noisy"), and
          the background is the 4,403 E. coli proteins of the run. A process is
          recovered if it is significant, or a descendant is, or an ancestor at
          most two levels up with depth >= 3. Reference: the same foregrounds with
          E. coli's annotations, per protein, not expanded.
  null    The same set-up with random foregrounds of 40 E. coli proteins
          (100 replicates): a replicate is a false positive if any term has
          FDR < 0.05.
  example The paper's lists (306 decreased, 185 increased, the 491 together;
          background of 3,181) with M. smegmatis hidden, against the published
          results (M. smegmatis annotated, per protein).

Usage:  python docs/validation/expansion_benchmark.py [ecoli|null|example ...]
"""
from __future__ import annotations

import random
import sys
import time

import _harness as h
import pandas as pd

EX = h.EXAMPLE / "input_dataset"
EXPERIMENTAL = {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "HTP", "HDA", "HMP", "HGI", "HEP"}


def species_proteins(ws, prefix):
    sp = next(s for s in ws.species if s.startswith(prefix))
    out = set()
    for f in ("Orthogroups.tsv", "Orthogroups_UnassignedGenes.tsv"):
        for cell in pd.read_csv(ws.folder / f, sep="\t", dtype=str)[sp].dropna():
            out.update(e.split("|")[1] for e in cell.split(", "))
    return sorted(out)


def significant(ws, fg, expand, counting):
    status, js = ws.foreground(fg, expand=expand)
    if status != 200:
        return {"status": status, "sig": {}}
    status, js = ws.enrich(counting_mode=counting)
    return {"status": status, "mode": (js.get("counting") or {}).get("mode"),
            "sig": {t["GO"]: (t["name"], round(t["p_fdr_bh"], 4)) for t in h.terms(js)
                    if t["p_fdr_bh"] < 0.05}}


def related(dag, t, p):
    """How significant term t recovers process p, or None."""
    if t == p:
        return "exact"
    if t not in dag or p not in dag:
        return None
    if p in dag[t].get_all_upper():
        return "descendant"
    if t in dag[p].get_all_upper() and dag[t].depth >= max(3, dag[p].depth - 2):
        return "close ancestor"
    return None


def recovery(dag, p, sig):
    if p in sig:
        return "exact"
    kinds = {related(dag, t, p) for t in sig}
    return next((k for k in ("descendant", "close ancestor") if k in kinds), "no")


def part_ecoli():
    dag = h.og.ensure_godag(h.og.GO_ROOT_OBO)
    truth = h.ExampleWorkspace("ecoli_annotated")
    base = species_proteins(truth, "Escherichia")
    base_set = set(base)
    eco_file = next(f for sp, f in truth.mapping.items() if sp.startswith("Escherichia"))
    sets = {}
    for line in open(truth.goa_dir / eco_file):
        if line.startswith("!"):
            continue
        c = line.rstrip("\n").split("\t")
        if (c[6] not in EXPERIMENTAL or c[8] != "P" or "NOT" in c[3] or c[1] not in base_set
                or c[4] not in dag):
            continue
        for g in {c[4]} | dag[c[4]].get_all_upper():
            sets.setdefault(g, set()).add(c[1])
    candidates = [g for g, s in sets.items() if 15 <= len(s) <= 80 and dag[g].depth >= 4
                  and dag[g].namespace == "biological_process"]
    rng = random.Random(21)
    rng.shuffle(candidates)
    chosen = []
    for g in candidates:
        if all(len(sets[g] & sets[k]) / len(sets[g] | sets[k]) < 0.5 for k in chosen):
            chosen.append(g)
        if len(chosen) == 40:
            break
    hidden = h.ExampleWorkspace("ecoli_hidden", hide="Escherichia")
    truth.background_once(base)
    hidden.background_once(base, expand=True)
    rows = []
    for variant in ("pure", "noisy"):
        for g in chosen:
            fg = sorted(sets[g])
            if variant == "noisy":
                fg = fg + rng.sample(sorted(base_set - sets[g]), len(fg))
            ref = significant(truth, fg, False, "per_protein")
            exp = significant(hidden, fg, True, "per_orthogroup")
            rows.append({"variant": variant, "GO": g, "name": dag[g].name, "proteins": len(sets[g]),
                         "annotated_per_protein": recovery(dag, g, ref["sig"]),
                         "hidden_expanded": recovery(dag, g, exp["sig"]),
                         "hidden_expanded_mode": exp.get("mode"),
                         "hidden_expanded_n_significant": len(exp["sig"])})
            print(variant, g, rows[-1]["name"][:45], rows[-1]["annotated_per_protein"],
                  rows[-1]["hidden_expanded"], flush=True)
    summary = {}
    for variant in ("pure", "noisy"):
        rs = [r for r in rows if r["variant"] == variant]
        for col in ("annotated_per_protein", "hidden_expanded"):
            summary[f"{variant}/{col}"] = {k: sum(r[col] == k for r in rs)
                                           for k in ("exact", "descendant", "close ancestor", "no")}
            summary[f"{variant}/{col}"]["recovered"] = sum(r[col] != "no" for r in rs)
    h.write_result("expansion_benchmark/ecoli", {"processes": len(chosen), "background": len(base),
                                                 "summary": summary, "rows": rows})
    print(summary, flush=True)


def part_null(replicates=100):
    hidden = h.ExampleWorkspace("ecoli_hidden_null", hide="Escherichia")
    base = species_proteins(hidden, "Escherichia")
    hidden.background_once(base, expand=True)
    rng = random.Random(2027)
    hits, seen, modes = 0, {}, {}
    for i in range(replicates):
        r = significant(hidden, rng.sample(base, 40), True, "per_orthogroup")
        modes[r.get("mode")] = modes.get(r.get("mode"), 0) + 1
        hits += bool(r["sig"])
        for name, _ in r["sig"].values():
            seen[name] = seen.get(name, 0) + 1
        if i % 10 == 9:
            print("null", i + 1, hits, flush=True)
    h.write_result("expansion_benchmark/null", {
        "replicates": replicates, "foreground_size": 40, "background": len(base),
        "with_a_significant_term": hits, "rate": hits / replicates, "mode_applied": modes,
        "most_frequent_terms": sorted(seen.items(), key=lambda x: -x[1])[:8]})


def part_example():
    bg = h.read_list(EX / "background_3181.txt")
    lists = {"decreased": h.read_list(EX / "foreground_down-regulated_306.txt"),
             "increased": h.read_list(EX / "foreground_up-regulated_185.txt")}
    lists["all_491"] = lists["decreased"] + lists["increased"]
    published = h.ExampleWorkspace("msm_annotated")
    published.background_once(bg)
    hidden = h.ExampleWorkspace("msm_hidden", hide="smegmatis")
    hidden.background_once(bg, expand=True)
    out = {}
    for arm, fg in lists.items():
        pub = significant(published, fg, False, "per_protein")
        hid = significant(hidden, fg, True, "per_orthogroup")
        out[arm] = {"published_terms": sorted(v[0] for v in pub["sig"].values()),
                    "msm_hidden_expanded_terms": sorted(v[0] for v in hid["sig"].values()),
                    "published_terms_recovered": sorted(pub["sig"][g][0] for g in pub["sig"] if g in hid["sig"]),
                    "mode": hid.get("mode")}
        print(arm, len(pub["sig"]), "published;", len(hid["sig"]), "with M. smegmatis hidden;",
              len(out[arm]["published_terms_recovered"]), "of the published recovered", flush=True)
    h.write_result("expansion_benchmark/example", out)


if __name__ == "__main__":
    parts = sys.argv[1:] or ["ecoli", "null", "example"]
    t0 = time.time()
    for part in parts:
        {"ecoli": part_ecoli, "null": part_null, "example": part_example}[part]()
    print(f"done in {time.time() - t0:.0f} s")
