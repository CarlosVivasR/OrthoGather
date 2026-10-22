"""Random foregrounds: how often does each setting report a significant term
when there is nothing to find?

On the worked example (3,181 proteins detected, OrthoFinder run of 5 August
2026, GOA files of 28 July 2026), foregrounds of 306 proteins (the size of the
decreased set) are drawn at random from the universe each setting tests
against, and analysed with that setting. A random draw has no biology behind
it, so a calibrated test reports a significant term (FDR < 0.05) in about 5% of
the draws or fewer: false discovery rate control bounds that rate at 5% when no
term is truly enriched.

The universe is the 3,181 detected proteins for a pasted background. With "Use
all GOA files" it is M. smegmatis' annotated proteome counted per protein, and
its whole proteome in the analysis counted per orthogroup.

One more setting is not a calibration but a warning: detected_vs_proteome draws
from the 3,181 detected proteins and tests them against the whole annotated
proteome ("Use all GOA files"). Detected proteins are not a random part of the
proteome, so this setting finds "enrichment" in random sets of detected
proteins; it is why the experiment's own background should be pasted.

Settings:
  per_protein            the paper's setting: pasted background, per protein
  per_orthogroup         pasted background, per orthogroup (permutation p-values)
  expanded               foreground and background expanded to full orthogroups
  all_goa_per_protein    "Use all GOA files", per protein
  all_goa_per_orthogroup "Use all GOA files", per orthogroup
  msm_hidden_expanded    M. smegmatis' GOA file left out, both sets expanded: a
                         species without annotation, through its orthologues
  msm_hidden_all_goa     the same species without annotation, "Use all GOA files"
  detected_vs_proteome   see above

Each setting writes results/null_calibration/<setting>.json; settings can run
in parallel processes.

Usage:  python docs/validation/null_calibration.py [--replicates 100] [--only SETTING ...]
"""
from __future__ import annotations

import argparse
import math
import random
import time
from collections import Counter

import _harness as h

SETTINGS = {
    "per_protein":            dict(hide=None, bg="pasted", expand=False, counting="per_protein"),
    "per_orthogroup":         dict(hide=None, bg="pasted", expand=False, counting="per_orthogroup"),
    "expanded":               dict(hide=None, bg="pasted", expand=True, counting="per_orthogroup"),
    "all_goa_per_protein":    dict(hide=None, bg="all_goa", expand=False, counting="per_protein"),
    "all_goa_per_orthogroup": dict(hide=None, bg="all_goa", expand=False, counting="per_orthogroup"),
    "msm_hidden_expanded":    dict(hide="smegmatis", bg="pasted", expand=True, counting="per_orthogroup"),
    "msm_hidden_all_goa":     dict(hide="smegmatis", bg="all_goa", expand=False, counting="per_orthogroup"),
    "detected_vs_proteome":   dict(hide=None, bg="all_goa", expand=False, counting="per_protein",
                                   draw="detected"),
}


def universe(ws, s, detected):
    """The proteins a random foreground is drawn from for setting s."""
    if s["bg"] == "pasted" or s.get("draw") == "detected":
        return detected
    import pandas as pd
    msm = next(sp for sp in ws.species if "smegmatis" in sp)
    proteome = set()
    for f in ("Orthogroups.tsv", "Orthogroups_UnassignedGenes.tsv"):
        for cell in pd.read_csv(ws.folder / f, sep="\t", dtype=str)[msm].dropna():
            proteome.update(e.split("|")[1] for e in cell.split(", "))
    if s["counting"] == "per_orthogroup":
        return sorted(proteome)
    annotated = set(h.og_goa.build_id2gos_from_goa_folder(
        str(ws.goa_dir), limit_files=[f for sp, f in ws.mapping.items() if "smegmatis" in sp]))
    return sorted(proteome & annotated)


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--only", nargs="*", help="run only these settings")
    args = ap.parse_args()

    background = h.read_list(h.EXAMPLE / "input_dataset/background_3181.txt")
    workspaces = {}
    for name, s in SETTINGS.items():
        if args.only and name not in args.only:
            continue
        rng = random.Random(args.seed)                    # the same draws for every setting
        ws = workspaces.get(s["hide"]) or workspaces.setdefault(
            s["hide"], h.ExampleWorkspace(f"null_{s['hide'] or 'all'}", hide=s["hide"]))
        ws.new_session()
        ws.background_once(None if s["bg"] == "all_goa" else background,
                           all_goa=s["bg"] == "all_goa", expand=s["expand"])
        pool = universe(ws, s, background)
        hits, done, modes, seen, statuses = 0, 0, Counter(), Counter(), Counter()
        t0 = time.time()
        for _ in range(args.replicates):
            fg = rng.sample(pool, 306)
            status, js = ws.foreground(fg, expand=s["expand"])
            assert status == 200, js
            status, js = ws.enrich(counting_mode=s["counting"])
            statuses[status] += 1
            if status != 200:
                continue
            done += 1
            modes[js["counting"]["mode"]] += 1
            sig = [t["name"] for t in h.terms(js) if t["p_fdr_bh"] < 0.05]
            hits += bool(sig)
            seen.update(set(sig))
        result = {
            "setting": name, **s, "drawn_from": len(pool), "foreground_size": 306,
            "replicates": args.replicates, "seed": args.seed, "analysed": done, "http_status": dict(statuses), "mode_applied": dict(modes),
            "with_a_significant_term": hits, "rate": round(hits / done, 4) if done else None,
            "wilson_95ci": wilson(hits, done), "most_frequent_terms": seen.most_common(5),
            "seconds": round(time.time() - t0)}
        print(f"{name:24s} {hits:4d}/{done:<4d} = {hits / max(done, 1):6.1%}  95% CI {wilson(hits, done)}  "
              f"mode {dict(modes)}", flush=True)
        h.write_result(f"null_calibration/{name}", result)


if __name__ == "__main__":
    main()
