"""How do the results of the worked example change with the analysis settings?

The paper's lists (306 decreased, 185 increased, the 491 together; GOA files of
28 July 2026) are analysed with the published settings (per protein, all
evidence codes, one universe for the three ontologies, minimum depth 2, the
3,181 detected proteins as background) and with one setting changed at a time.
For each, the significant terms (FDR < 0.05, over-represented) are recorded.
This is Table S6 of Supplementary File S1.

Parts (run one per process, or all):

  table   Every row of Table S6: one analysis setting changed at a time; the
          whole annotated proteome as background ("Use all GOA files"); and
          both sets expanded to full orthogroups, with and without the
          M. smegmatis GOA file. Terms that cannot apply to a mycobacterium
          (the nucleus, membrane-bounded organelles, the flagellum and
          flagellar motility, with their descendants over is_a and part_of)
          are listed apart. Writes sensitivity_example.json.
  seeds   The rows counted per orthogroup, again with seeds 1-50 of the
          permutation: terms close to the threshold can change with the seed.
          Rows can be named after the part, to run them in parallel. Writes
          sensitivity_seeds/<row>.json.

Usage:  python docs/validation/sensitivity_example.py [table] [seeds [row ...]]
"""
from __future__ import annotations

import functools
import sys
import time

import _harness as h
from orthogather.core import og_permutation as og_perm

EX = h.EXAMPLE / "input_dataset"
SETTINGS = {
    "published": {},
    "per_ontology_universe": {"universe_scope": "per_ontology"},
    "non_iea_evidence": {"evidence_preset": "curated"},
    "experimental_evidence": {"evidence_preset": "experimental"},
    "per_orthogroup": {"counting_mode": "per_orthogroup"},
    "two_sided_test": {"test_direction": "two-sided"},
    "min_depth_5": {"min_depth": 5},
}
# Background rows: (workspace, background, expanded). "hidden" leaves the
# M. smegmatis GOA file out, as for a species without annotation.
BACKGROUNDS = {
    "whole_proteome_background": ("annotated", {"all_goa": True}, False),
    "expanded": ("annotated", {"expand": True}, True),
    "expanded_without_msm_goa": ("hidden", {"expand": True}, True),
}
SEED_ROWS = ("per_orthogroup", "expanded", "expanded_without_msm_goa")
NOT_IN_MYCOBACTERIA = {"GO:0005634": "nucleus", "GO:0043227": "membrane-bounded organelle",
                       "GO:0009288": "bacterial-type flagellum",
                       "GO:0001539": "cilium or flagellum-dependent cell motility"}


def read_lists():
    down = h.read_list(EX / "foreground_down-regulated_306.txt")
    up = h.read_list(EX / "foreground_up-regulated_185.txt")
    return {"decreased_306": down, "increased_185": up, "all_491": down + up}


def ancestors(dag, go):
    """The term and its ancestors over is_a and part_of, as the enrichment propagates."""
    seen, stack = {go}, [dag[go]]
    while stack:
        t = stack.pop()
        for p in list(t.parents) + list(getattr(t, "relationship", {}).get("part_of", ())):
            if p.item_id not in seen:
                seen.add(p.item_id)
                stack.append(p)
    return seen


def significant(js, dag):
    rows = [t for t in h.terms(js) if t["p_fdr_bh"] < 0.05 and t.get("direction") != "depleted"]
    return {"n": len(rows),
            "terms": sorted((t["name"], round(t["p_fdr_bh"], 4)) for t in rows),
            "not_applicable": sorted(t["name"] for t in rows
                                     if t["GO"] in dag and ancestors(dag, t["GO"]) & set(NOT_IN_MYCOBACTERIA))}


def workspaces(bg):
    return {"annotated": h.ExampleWorkspace("sensitivity"),
            "hidden": h.ExampleWorkspace("sensitivity_hidden", hide="smegmatis"), "bg": bg}


def run_row(ws, row, fg):
    """One analysis of a row of Table S6 for one list."""
    if row in SETTINGS:
        w = ws["annotated"]
        w.background_once(ws["bg"])
        w.foreground(fg)
        return w.enrich(**SETTINGS[row])
    name, extra, expand = BACKGROUNDS[row]
    w = ws[name]
    w.background_once(None if extra.get("all_goa") else ws["bg"], **extra)
    w.foreground(fg, expand=expand)
    return w.enrich(counting_mode="per_orthogroup" if expand else "per_protein")


def part_table(dag, ws):
    out = {name: {} for name in read_lists()}
    for row in list(SETTINGS) + list(BACKGROUNDS):
        for name, fg in read_lists().items():
            status, js = run_row(ws, row, fg)
            assert status == 200, js
            out[name][row] = significant(js, dag)
            print(f"{name:14s} {row:26s} {out[name][row]['n']:3d}", flush=True)
    h.write_result("sensitivity_example", out)


def part_seeds(dag, ws, rows):
    pvalues = og_perm.permutation_pvalues
    for row in rows:
        out = {"seeds": "1-50", "application_seed": 20261020}
        for name, fg in read_lists().items():
            n, sets = {}, []
            for seed in range(1, 51):
                og_perm.permutation_pvalues = functools.partial(pvalues, seed=seed)
                try:
                    status, js = run_row(ws, row, fg)
                finally:
                    og_perm.permutation_pvalues = pvalues
                assert status == 200, js
                sig = significant(js, dag)
                n[seed] = sig["n"]
                sets.append({t for t, _ in sig["terms"]})
            out[name] = {"n_by_seed": n, "min": min(n.values()), "max": max(n.values()),
                         "in_every_seed": sorted(set.intersection(*sets)),
                         "in_some_seed": sorted(set.union(*sets))}
            print(row, name, out[name]["min"], out[name]["max"], flush=True)
        h.write_result(f"sensitivity_seeds/{row}", out)


def main(args):
    args = args or ["table", "seeds"]
    dag = h.og.ensure_godag(h.og.GO_ROOT_OBO)
    ws = workspaces(h.read_list(EX / "background_3181.txt"))
    t0 = time.time()
    if "table" in args:
        part_table(dag, ws)
    if "seeds" in args:
        rows = args[args.index("seeds") + 1:] or list(SEED_ROWS)
        part_seeds(dag, ws, rows)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
