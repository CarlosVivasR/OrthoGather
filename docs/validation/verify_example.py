"""Check every number of the worked example that the paper and Supplementary
File S1 quote, and compare the regenerated exports with the published ones in
example_analysis/.

The example is rebuilt from the repository: the OrthoFinder export in
example_analysis/1_orthofinder/ and the GOA files of 28 July 2026 in
docs/validation/data/. Each check prints OK or FAIL; the exit status is 1 if
any check fails.

Usage:  python docs/validation/verify_example.py
"""
from __future__ import annotations

import glob
import sys

import _harness as h
import pandas as pd
from orthogather.core.excel import compute_annotation_distribution
from orthogather.core.figures import generate_figure_1, generate_figure_2
from orthogather.core.goa import build_id2gos_from_goa_folder
from orthogather.core.single_copy import get_single_copy_orthogroups

EX = h.EXAMPLE
checks = []


def check(where, claim, expected, observed):
    checks.append({"where": where, "claim": claim, "expected": expected, "observed": observed,
                   "ok": expected == observed})


ws = h.ExampleWorkspace()
folder = ws.folder
species = ws.species
gc = pd.read_csv(folder / "Orthogroups.GeneCount.tsv", sep="\t")
ua = pd.read_csv(folder / "Orthogroups_UnassignedGenes.tsv", sep="\t")
sp_cols = [c for c in gc.columns if c not in ("Orthogroup", "Total")]

# ----------------------------------------------------------------- OrthoFinder (S1 Fig. S3)
check("Paper/S1", "orthogroups", 5949, len(gc))
check("S1 Fig. S3", "single-copy orthogroups", 393, len(get_single_copy_orthogroups(str(folder))))
check("S1 Fig. S3", "species-specific orthogroups", 778, int(((gc[sp_cols] > 0).sum(axis=1) == 1).sum()))
check("S1", "unassigned genes", 6289, int(ua[sp_cols].notna().sum().sum()))
assigned, unassigned = gc[sp_cols].sum(), ua[sp_cols].notna().sum()
pct = assigned / (assigned + unassigned) * 100
check("S1 Fig. S3", "mean % assigned (range)", "80.4 (75.1–85.7)",
      f"{pct.mean():.1f} ({pct.min():.1f}–{pct.max():.1f})")
check("S1", "proteins in the run", 32219, int(assigned.sum() + unassigned.sum()))

# ----------------------------------------------------------------- Figures 1 and 2
f1 = generate_figure_1(gc.copy())
pub1 = pd.read_csv(glob.glob(str(EX / "2_comparative_analysis/figure1_protein-distribution/*.csv"))[0])
check("example_analysis", "figure 1 data identical", True,
      list(zip(f1["xs"], f1["ys"])) == list(zip(pub1.iloc[:, 0], pub1.iloc[:, 1])))
f2 = generate_figure_2(gc.copy())
pub2 = pd.read_csv(glob.glob(str(EX / "2_comparative_analysis/figure2_orthogroup-sharing/*.csv"))[0])
check("example_analysis", "figure 2 data identical", True,
      list(zip(f2["xs"], f2["ys"])) == list(zip(pub2.iloc[:, 0], pub2.iloc[:, 1])))

# ----------------------------------------------------------------- UpSet plots (real routes)
sel = [s for s in species if s.startswith(("Mycolicibacterium", "Mycobacteroides", "Escherichia"))]
msm, mab, eco = (next(s for s in sel if s.startswith(p))
                 for p in ("Mycolicibacterium", "Mycobacteroides", "Escherichia"))
up = ws.client.post("/upset_data", json={"species": sel}).get_json()
og_c = {frozenset(c["sets"]): c["cardinality"] for c in up["fig3"]["combinations"]}
pr_c = {frozenset(c["sets"]): c["cardinality"] for c in up["fig4"]["combinations"]}
check("S1", "Msm-only orthogroups / proteins", (447, 817), (og_c[frozenset([msm])], pr_c[frozenset([msm])]))
check("S1", "shared by all three: orthogroups / proteins", (1024, 4599),
      (og_c[frozenset(sel)], pr_c[frozenset(sel)]))
check("S1", "Mab ∩ Msm: orthogroups / proteins", (1699, 4709),
      (og_c[frozenset([msm, mab])], pr_c[frozenset([msm, mab])]))
for fig, key in (("3", "fig3"), ("4", "fig4")):
    pub = pd.read_csv(glob.glob(str(EX / f"2_comparative_analysis/figure{fig}_*/*.csv"))[0])
    mine = {c["name"].replace(" ∩ ", " + "): c["cardinality"] for c in up[key]["combinations"]}
    check("example_analysis", f"figure {fig} data identical", True,
          all(mine.get(r["species"]) == r.iloc[-1] for _, r in pub.iterrows()) and len(mine) == len(pub))

fg_down = h.read_list(EX / "input_dataset/foreground_down-regulated_306.txt")
fg_up = h.read_list(EX / "input_dataset/foreground_up-regulated_185.txt")
ids = fg_down + fg_up
fl = ws.client.post("/upset_data_filtered", json={"species": sel, "uniprot_ids": ids}).get_json()
check("Paper/S1", "IDs mapped / orthogroups / unassigned", (467, 430, 24),
      (len(fl["ids_found"]), fl["n_orthogroups"], len(fl["ids_unassigned"])))
for fig, key in (("5", "fig5"), ("6", "fig6")):
    pub = pd.read_csv(glob.glob(str(EX / f"2_comparative_analysis/figure{fig}_*/*.csv"))[0])
    mine = {c["name"].replace(" ∩ ", " + "): c["cardinality"] for c in fl[key]["combinations"]}
    check("example_analysis", f"figure {fig} data identical", True,
          all(mine.get(r["species"]) == r.iloc[-1] for _, r in pub.iterrows()) and len(mine) == len(pub))

# Table S3: filtered orthogroups found only in Msm
og = pd.read_csv(folder / "Orthogroups.tsv", sep="\t")


def accessions(cell):
    return [] if pd.isna(cell) else [e.split("|")[1] if e.count("|") >= 2 else e
                                     for e in str(cell).split(", ")]


msm_only = [o for c in fl["fig5"]["combinations"] if c["sets"] == [msm] for o in c["elems"]]
rows = og[og["Orthogroup"].isin(msm_only)]
idset = set(ids)
prot = [(r["Orthogroup"], a) for _, r in rows.iterrows() for a in accessions(r[msm])]
fg_per_og = {o: sum(1 for oo, a in prot if oo == o and a in idset) for o in msm_only}
size_per_og = {o: sum(1 for oo, _ in prot if oo == o) for o in msm_only}
multi = [o for o, n in fg_per_og.items() if n > 1]
check("S1", "Msm-only filtered orthogroups / proteins", (28, 71), (len(msm_only), len(prot)))
check("S1 Table S3", "foreground proteins among them", 35, sum(fg_per_og.values()))
check("S1 Table S3", "OGs with >1 foreground protein (proteins)", (5, 12),
      (len(multi), sum(fg_per_og[o] for o in multi)))
check("S1 Table S3", "OGs with a single foreground protein", 23, sum(1 for n in fg_per_og.values() if n == 1))
check("S1 Table S3", "OGs only foreground / mixed", (13, 15),
      (sum(1 for o in msm_only if fg_per_og[o] == size_per_og[o]),
       sum(1 for o in msm_only if fg_per_og[o] < size_per_og[o])))

# ----------------------------------------------------------------- GO coverage (Fig. 3A–B, S6B)
dist = compute_annotation_distribution(str(ws.results / "Gene_Ontology_Analysis.xlsx"))
nz = dist["stats_nonzero"]
check("Paper/S1", "orthogroups with ≥1 annotated protein (%)", "4638 (78.0%)",
      f"{nz['n']} ({nz['n'] / len(gc) * 100:.1f}%)")
check("Paper/S1", "mean / median coverage among annotated", "93.8 / 100",
      f"{nz['mean']:.1f} / {nz['median']:.0f}")
check("S1", "orthogroups with no annotated protein", 1311, dist["n_zero_og"])

# ----------------------------------------------------------------- GO enrichment
bg = h.read_list(EX / "input_dataset/background_3181.txt")
ws.background_once(bg)
res = {}
for arm, fg in (("down", fg_down), ("up", fg_up), ("all", ids)):
    ws.foreground(fg)
    status, js = ws.enrich(display_p_value=0.10)
    assert status == 200, js
    rows_ = h.terms(js)
    res[arm] = {"sig": [t for t in rows_ if t["significant"]], "all": rows_, "stats": js["annotation_stats"]}
d = res["down"]
check("Paper/S1", "decreased: enriched terms (BP, MF, CC)", (21, 20, 1, 0),
      (len(d["sig"]), *[sum(1 for t in d["sig"] if t["namespace"] == ns)
                        for ns in ("biological_process", "molecular_function", "cellular_component")]))
annotated = set(build_id2gos_from_goa_folder(str(ws.goa_dir), limit_files=list(ws.mapping.values())))
check("S1", "decreased: annotated & tested / carrying a GO annotation", (250, 251),
      (d["stats"]["with_annotations"], sum(1 for p in set(fg_down) if p in annotated)))
check("S1", "population (annotated background)", 2470, d["stats"]["background_annotated"])
check("S1", "increased: annotated & tested", 162, res["up"]["stats"]["with_annotations"])
check("Paper/S1", "increased: enriched terms", 1, len(res["up"]["sig"]))
near = {t["name"]: round(t["p_fdr_bh"], 2) for t in res["up"]["all"] if not t["significant"]}
check("S1", "increased: translation & protein biosynthetic process at FDR 0.06",
      {"translation": 0.06, "protein biosynthetic process": 0.06},
      {k: near.get(k) for k in ("translation", "protein biosynthetic process")})
check("Paper/S1", "491 together: one term, protein maturation", ["protein maturation"],
      [t["name"] for t in res["all"]["sig"]])
ws.foreground(fg_down)
d5 = [t for t in h.terms(ws.enrich(min_depth=5, display_p_value=0.05)[1]) if t["significant"]]
d2 = {t["GO"] for t in d["sig"]}
check("S1", "depth ≥ 5: 14 of the 21 kept + phospholipid metabolic process",
      (14, ["phospholipid metabolic process"]),
      (len({t["GO"] for t in d5} & d2), sorted(t["name"] for t in d5 if t["GO"] not in d2)))
groups = {}
for t in d["sig"]:
    groups.setdefault(frozenset(t["study_items"]), []).append(t["name"])
negreg = [k for k, v in groups.items()
          if any(n.startswith("negative regulation of macromolecule biosynthetic") for n in v)]
transc = [k for k, v in groups.items() if "negative regulation of DNA-templated transcription" in v]
check("S1", "negative-regulation terms: one group of 13 proteins, 11 with transcription terms", (13, 11),
      (len(negreg[0]) if negreg else None, len(transc[0]) if transc else None))

# The enrichment exports against the published ones (terms, counts, p and q)
for arm, folder_name in (("down", "down-regulated_306"), ("up", "up-regulated_185")):
    f = glob.glob(str(EX / "4_go_enrichment" / folder_name / "results" / "*.xlsx"))[0]
    pub = pd.concat([pd.read_excel(f, sheet_name=s) for s in ("BP", "CC", "MF")])
    mine = {t["GO"]: t for t in res[arm]["all"]}
    same = all(g in mine and int(mine[g]["study_count"]) == int(r["study_count"])
               and int(mine[g]["pop_count"]) == int(r["pop_count"])
               and abs(mine[g]["p_fdr_bh"] - float(r["p_fdr_bh"])) < 1e-12
               for g, r in pub.set_index("GO").iterrows())
    check("example_analysis", f"GO results file ({folder_name}) identical", True, same)

n_ok = sum(c["ok"] for c in checks)
for c in checks:
    print(("OK  " if c["ok"] else "FAIL"),
          f'[{c["where"]}] {c["claim"]}: expected {c["expected"]}, got {c["observed"]}')
print(f"\n{n_ok}/{len(checks)} checks passed")
h.write_result("verify_example", {"passed": n_ok, "total": len(checks), "checks": checks})
sys.exit(0 if n_ok == len(checks) else 1)
