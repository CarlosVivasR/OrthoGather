"""Combinations of the Gene Ontology settings, through the real routes.

A synthetic analysis with the hard cases: three species (spB with a complete GOA
file, spC annotated at about 40%, spD without one), paralogue families of unequal
size, single-species orthogroups, proteins in no orthogroup, and IEA, curated and
experimental evidence. For each measured species, every combination of

    foreground   a signal list, and the same list pasted in mixed formats
    background   pasted, pasted and expanded, "Use all GOA files"
    expansion    of the foreground: no / yes
    counting     per protein / per orthogroup
    evidence     all / experimental

is run (48 analyses per species) and checked against rules every analysis must
meet: the counting mode applied and the notes that explain it, the accounting of
the pasted identifiers, possible counts, Fisher p-values equal to SciPy's, a
Benjamini-Hochberg correction that reproduces, the results file and the
response agreeing. Equivalences between analyses are checked too.

With OG_FULL_MATRIX=1 the same test runs the full matrix: six foreground lists
(adding a paralogue family, a random list, a single identifier, and identifiers
of another species and unknown ones), the single-copy filter on and off, and the
three evidence settings, 1,296 combinations in all. docs/validation/
combinations_matrix.py runs it and keeps the summary (OG_MATRIX_OUT).
"""
from __future__ import annotations

import itertools
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import fisher_exact

T_SIGNAL = "GO:0006412"           # translation
T_PARALOG = "GO:0030497"          # fatty acid elongation, carried by large families
T_REG = "GO:0006355"              # regulation of DNA-templated transcription
OTHERS = ["GO:0055085", "GO:0006508", "GO:0005975", "GO:0006260", "GO:0006281", "GO:0000160"]
MF = ["GO:0003677", "GO:0005524", "GO:0016491"]
CC = ["GO:0005886", "GO:0005737"]
CODES = ["IEA"] * 7 + ["IBA", "TAS"] + ["IDA", "EXP"]

FULL = os.environ.get("OG_FULL_MATRIX") == "1"
FG_NAMES = (("signal", "paralog", "random", "messy", "tiny", "outside") if FULL
            else ("signal", "messy"))
SINGLE_COPY = (False, True) if FULL else (False,)
EVIDENCE = ("all", "curated", "experimental") if FULL else ("all", "experimental")

NOTE_FORCED = "so it was counted per orthogroup"
NOTE_DONT = "Do not rely on these results"
NOTE_FALLBACK = "Per-orthogroup counting was not possible"


def _gaf(acc, go, code, aspect, qualifier=""):
    return "\t".join(["UniProtKB", acc, acc, qualifier, go, "PMID:0", code, "", aspect, "", "",
                      "protein", "taxon:1", "20261020", "UniProt", "", ""]) + "\n"


def _world(tmp_path, monkeypatch, seed=7):
    """Write the synthetic analysis and point the app at it."""
    import app as og
    from orthogather.core import goa as og_goa
    from orthogather.core import single_copy as og_sc
    from orthogather.core.excel import generate_go_excel

    rng = random.Random(seed)
    folder, goa_dir, results = tmp_path / "analysis", tmp_path / "GOA", tmp_path / "results"
    for d in (folder, goa_dir, results):
        d.mkdir()
    species = ["spB", "spC", "spD"]
    goa = {"spB": [], "spC": []}
    ogs, members = [], defaultdict(list)

    def annotate(sp, acc, bp):
        if sp == "spD" or (sp == "spC" and rng.random() > 0.4):
            return
        goa[sp].append(_gaf(acc, bp, rng.choice(CODES), "P"))
        goa[sp].append(_gaf(acc, rng.choice(MF), rng.choice(CODES), "F"))
        if rng.random() < 0.5:
            goa[sp].append(_gaf(acc, rng.choice(CC), rng.choice(CODES), "C"))
        if rng.random() < 0.03:
            goa[sp].append(_gaf(acc, T_SIGNAL, "IDA", "P", "NOT"))

    def new_og(per_sp, bp):
        ogs.append(per_sp)
        for sp, accs in per_sp.items():
            members[sp].extend(accs)
            for a in accs:
                annotate(sp, a, bp)

    for i in range(250):                                  # one copy per species
        new_og({sp: [f"{sp[-1]}{i:05d}"] for sp in species},
               T_SIGNAL if i < 50 else OTHERS[i % len(OTHERS)])
    k = 1000
    for i in range(60):                                   # paralogue families
        per = {}
        for sp, hi in (("spB", 8), ("spC", 3), ("spD", 6)):
            c = rng.randint(1, hi)
            per[sp] = [f"{sp[-1]}{k + j:05d}" for j in range(c)]
            k += c
        new_og(per, T_PARALOG if i < 30 else T_REG)
    for i in range(20):                                   # spD only
        new_og({"spD": [f"D{k:05d}", f"D{k + 1:05d}"]}, OTHERS[i % 6]); k += 2
    for i in range(20):                                   # spB and spC only
        new_og({"spB": [f"B{k:05d}"], "spC": [f"C{k + 1:05d}"]}, OTHERS[i % 6]); k += 2
    unassigned = {sp: [f"{sp[-1]}{90000 + j:05d}" for j in range(30)] for sp in species}
    for sp, accs in unassigned.items():
        for j, a in enumerate(accs):
            annotate(sp, a, OTHERS[j % 6])

    def cell(accs, sp):
        return ", ".join(f"tr|{a}|{a}_{sp.upper()}" for a in accs)
    pd.DataFrame([{"Orthogroup": f"OG{i:07d}", **{sp: cell(per.get(sp, []), sp) for sp in species}}
                  for i, per in enumerate(ogs)]).to_csv(folder / "Orthogroups.tsv", sep="\t", index=False)
    pd.DataFrame([{"Orthogroup": f"OG{i:07d}", **{sp: len(per.get(sp, [])) for sp in species},
                   "Total": sum(len(v) for v in per.values())}
                  for i, per in enumerate(ogs)]).to_csv(folder / "Orthogroups.GeneCount.tsv",
                                                        sep="\t", index=False)
    ua, n = [], len(ogs)
    for sp, accs in unassigned.items():
        for a in accs:
            ua.append({"Orthogroup": f"OG{n:07d}", **{s: (cell([a], s) if s == sp else "")
                                                      for s in species}})
            n += 1
    pd.DataFrame(ua).to_csv(folder / "Orthogroups_UnassignedGenes.tsv", sep="\t", index=False)
    mapping = {}
    for sp, lines in goa.items():
        (goa_dir / f"9.{sp}.goa").write_text("!gaf-version: 2.2\n" + "".join(lines))
        mapping[sp] = f"9.{sp}.goa"
    (folder / "goa_mapping.json").write_text(json.dumps(mapping))

    monkeypatch.setattr(og, "RESULTS_FOLDER", str(results))
    monkeypatch.setattr(og, "GOA_DOWNLOAD_FOLDER", str(goa_dir))
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    og_sc.invalidate_single_copy_cache()
    id2gos = og_goa.build_id2gos_from_goa_folder(str(goa_dir), limit_files=list(mapping.values()))
    generate_go_excel(str(folder / "Orthogroups.tsv"), mapping,
                      str(results / "Gene_Ontology_Analysis.xlsx"), annotated_ids=set(id2gos))

    def client():
        c = og.app.test_client()
        with c.session_transaction() as s:
            s["folder_path"], s["species"], s["modo"] = str(folder), species, "upload"
        return c
    return client, results, members, unassigned, ogs


def _lists(sp, members, unassigned, ogs, rng):
    letter = sp[-1]
    proteome = members[sp] + unassigned[sp]
    signal = [f"{letter}{i:05d}" for i in range(30)]
    signal += rng.sample([p for p in proteome if p not in signal], 20)
    messy = ([f">sp|{signal[0]}|X_{sp.upper()} protein OS=Synthetic", "MKVLAAGLLLA",
              signal[1].lower(), f"{signal[2]}-2", signal[3], signal[3]] + signal[4:]
             + ["", "P99999", "Q0ZZZ9", unassigned[sp][0]])
    other = "spB" if sp != "spB" else "spC"
    lists = {"signal": signal, "messy": messy,
             "paralog": [a for per in ogs[250:280] for a in per.get(sp, [])],
             "random": rng.sample(proteome, 50),
             "tiny": [signal[0]],
             "outside": rng.sample(proteome, 10) + rng.sample(members[other], 5)
                        + ["P11111", "Q22222", "A0A0A0A0A0", "X99999", "O12345"]}
    return {k: lists[k] for k in FG_NAMES}, proteome + ["P11111", "Q22222", "O54321"]


def _fisher(sc, sn, pc, pn):
    return fisher_exact([[sc, sn - sc], [pc - sc, pn - pc - sn + sc]], alternative="greater")[1]


def _bh(p, m):
    p = np.asarray(p, float)
    order = np.argsort(p)
    q = np.minimum.accumulate((p[order] * m / np.arange(1, len(p) + 1))[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def _check(ctx, r, c, results):
    """The rules every analysis must meet. Returns the failures and a summary."""
    from orthogather.utils.parsing import parse_identifier_list
    js = r.get_json() or {}
    if r.status_code == 400:
        return ([] if js.get("hint") else ["400 without a hint"]), {"http400": js.get("message")}
    if r.status_code != 200:
        return [f"HTTP {r.status_code}: {js.get('message')}"], None
    f = []
    counting, warn = js["counting"], js.get("warnings") or []
    expanded = ctx["fg_expand"] or ctx["bg"] == "custom_exp"
    req = ctx["counting"]
    fell_back = any(NOTE_FALLBACK in w for w in warn)
    if counting["mode_requested"] != req:
        f.append("mode_requested is not the mode asked for")
    if expanded and counting["mode"] != "per_orthogroup" and not fell_back:
        f.append("expanded but not counted per orthogroup, with no fallback note")
    if not expanded and counting["mode"] != req and not fell_back:
        f.append("not expanded and the mode asked for was not applied")
    if any(NOTE_FORCED in w for w in warn) != (expanded and req == "per_protein"
                                                and counting["mode"] == "per_orthogroup"):
        f.append("the 'counted per orthogroup' note does not match what was done")
    if any(NOTE_DONT in w for w in warn) != (expanded and counting["mode"] == "per_protein"):
        f.append("the 'Do not rely' warning does not match what was done")
    if len(set(warn)) != len(warn):
        f.append("repeated warnings")
    ids = js["input_ids"]
    parsed = list(dict.fromkeys(parse_identifier_list(ctx["fg_list"])["ids"]))
    untested = [u["id"] for u in ids["untested"]]
    if ids["pasted"] != len(parsed):
        f.append("number of pasted identifiers is wrong")
    if len(set(untested)) != len(untested) or not set(untested) <= set(parsed):
        f.append("the untested table repeats identifiers or lists ones not pasted")
    if any(u["reason"] not in ids["labels"] for u in ids["untested"]):
        f.append("an untested reason has no label")
    if counting["foreground_units"] > counting["background_units"]:
        f.append("more foreground than background units")
    rows = [t for k in ("bp_results", "cc_results", "mf_results") for t in js.get(k) or []]
    for t in rows:
        sc, sn, pc, pn = t["study_count"], t["study_n"], t["pop_count"], t["pop_n"]
        if not (0 <= sc <= sn <= pn and sc <= pc <= pn and 10 <= pc <= 500):
            f.append(f"impossible counts for {t['GO']}")
        if t["p_fdr_bh"] + 1e-12 < t["p_uncorrected"] or not 0 <= t["p_fdr_bh"] <= 1:
            f.append(f"q-value below p or outside [0, 1] for {t['GO']}")
        if bool(t.get("significant")) != (t["p_fdr_bh"] < 0.05):
            f.append(f"'significant' flag wrong for {t['GO']}")
        hyp = t["p_uncorrected"] if counting["mode"] == "per_protein" else t.get("p_hypergeom")
        if hyp is None or abs(hyp - _fisher(sc, sn, pc, pn)) > 1e-9 * max(1.0, hyp) + 1e-12:
            f.append(f"Fisher p-value differs from SciPy for {t['GO']}")
    xl = pd.ExcelFile(results / "go_enrichment_report.xlsx")
    prov = dict(zip(*xl.parse("Provenance")[["key", "value"]].T.values))
    x = [rec for sh in ("BP", "MF", "CC") for rec in xl.parse(sh).to_dict("records")
         if "p_uncorrected" in rec]
    m = int(prov.get("Terms in correction family", len(x)) or 0)
    if x and np.max(np.abs(_bh([rec["p_uncorrected"] for rec in x], m)
                           - np.array([rec["p_fdr_bh"] for rec in x]))) > 1e-9:
        f.append("Benjamini-Hochberg does not reproduce the q-values")
    if {rec["GO"] for rec in x if rec["p_fdr_bh"] < 0.05} != {t["GO"] for t in rows if t["p_fdr_bh"] < 0.05}:
        f.append("the results file and the response differ")
    if c.get("/download_go_enrichment_excel").status_code != 200:
        f.append("results file download failed")
    key = sorted((t["GO"], t["study_count"], t["pop_count"], t["pop_n"], round(t["p_fdr_bh"], 12))
                 for t in rows)
    return f, {"mode": counting["mode"], "rows": key, "untested": sorted(untested)}


@pytest.mark.parametrize("measured", ["spB", "spC", "spD"])
def test_go_setting_combinations(tmp_path, monkeypatch, measured):
    client, results, members, unassigned, ogs = _world(tmp_path, monkeypatch)
    fg_lists, bg_list = _lists(measured, members, unassigned, ogs, random.Random(11))
    failures, out, refused = [], {}, Counter()
    c = client()
    for fg_name, bg, fg_expand, sc in itertools.product(fg_lists, ("custom", "custom_exp", "allgoa"),
                                                        (False, True), SINGLE_COPY):
        fg_list = fg_lists[fg_name]
        r1 = c.post("/foreground_analysis", json={"uniprot_ids": fg_list, "use_orthogroups": fg_expand,
                                                  "single_copy_only": sc})
        r2 = c.post("/background_analysis", json={
            "background_choice": "5" if bg == "allgoa" else "4",
            "custom_uniprot_ids": [] if bg == "allgoa" else bg_list,
            "use_orthogroups": bg == "custom_exp", "single_copy_only": sc})
        if r1.status_code == 400 and fg_expand and sc:
            # Expanding to single-copy orthogroups only can leave nothing; that is refused.
            refused[r1.get_json()["message"]] += 1
            continue
        assert r1.status_code == 200 and r2.status_code == 200, (fg_name, bg, fg_expand, sc)
        for counting, evidence in itertools.product(("per_protein", "per_orthogroup"), EVIDENCE):
            ctx = dict(fg=fg_name, bg=bg, fg_expand=fg_expand, sc=sc, counting=counting,
                       evidence=evidence, fg_list=fg_list)
            r = c.post("/gene_ontology_analysis", json={
                "counting_mode": counting, "evidence_preset": evidence,
                "p_value": 0.05, "display_p_value": 1.0, "min_depth": 2})
            fails, summary = _check(ctx, r, c, results)
            failures += [f"{fg_name}/{bg}/fg_expand={fg_expand}/sc={sc}/{counting}/{evidence}: {x}"
                         for x in fails]
            out[(fg_name, bg, fg_expand, sc, counting, evidence)] = summary

    def get(*k):
        v = out.get(k)
        return v if v and "rows" in v else None
    for fg_name, bg, fg_expand, sc, ev in itertools.product(
            fg_lists, ("custom", "custom_exp", "allgoa"), (False, True), SINGLE_COPY, EVIDENCE):
        pp = get(fg_name, bg, fg_expand, sc, "per_protein", ev)
        po = get(fg_name, bg, fg_expand, sc, "per_orthogroup", ev)
        if (fg_expand or bg == "custom_exp") and pp and po and pp["mode"] == "per_orthogroup" \
                and pp["rows"] != po["rows"]:
            failures.append(f"{fg_name}/{bg}/{fg_expand}/{sc}/{ev}: expanded per protein != per orthogroup")
        if sc and not fg_expand and bg != "custom_exp":
            for cm in ("per_protein", "per_orthogroup"):
                a, b = get(fg_name, bg, False, False, cm, ev), get(fg_name, bg, False, True, cm, ev)
                if a and b and a["rows"] != b["rows"]:
                    failures.append(f"{fg_name}/{bg}/{cm}/{ev}: single-copy changes an unexpanded analysis")
    # A list from another species as well pools both proteomes (with a warning), so it is left out.
    for fg_name, fg_expand, ev in itertools.product([n for n in fg_lists if n != "outside"],
                                                    (False, True), EVIDENCE):
        a = get(fg_name, "allgoa", fg_expand, False, "per_orthogroup", ev)
        b = get(fg_name, "custom_exp", fg_expand, False, "per_orthogroup", ev)
        if (a and b and a["rows"] != b["rows"]) or ((a is None) != (b is None)):
            failures.append(f"{fg_name}/{fg_expand}/{ev}: 'Use all GOA files' per orthogroup "
                            f"!= the proteome pasted and expanded")
    # The same settings in a new session, background loaded first, give the same results.
    c2 = client()
    c2.post("/background_analysis", json={"background_choice": "4", "custom_uniprot_ids": bg_list,
                                          "use_orthogroups": True})
    c2.post("/foreground_analysis", json={"uniprot_ids": fg_lists["messy"], "use_orthogroups": True})
    r = c2.post("/gene_ontology_analysis", json={"counting_mode": "per_protein", "evidence_preset": "all",
                                                 "p_value": 0.05, "display_p_value": 1.0, "min_depth": 2})
    _, again = _check(dict(fg="messy", bg="custom_exp", fg_expand=True, counting="per_protein",
                           evidence="all", fg_list=fg_lists["messy"]), r, c2, results)
    first = out[("messy", "custom_exp", True, False, "per_protein", "all")]
    if (again or {}).get("rows") != first.get("rows"):
        failures.append("a new session gives different results")

    analysed = [v for v in out.values() if v and "rows" in v]
    if os.environ.get("OG_MATRIX_OUT"):
        summary_path = Path(os.environ["OG_MATRIX_OUT"]) / f"{measured}.json"
        summary_path.write_text(json.dumps({
            "measured_species": measured,
            "combinations": len(out) + sum(refused.values()) * 2 * len(EVIDENCE),
            "analysed": len(analysed),
            "refused_by_design": dict(refused),
            "answered_400": Counter(v["http400"] for v in out.values() if v and "http400" in v),
            "modes_applied": Counter(f"{k[1]}|fg_expand={k[2]}|{k[4]} -> {v['mode']}"
                                     for k, v in out.items() if v and "rows" in v),
            "failures": failures}, indent=1) + "\n")
    assert not failures, "\n".join(failures[:30])
    assert len(analysed) >= (16 if measured == "spD" else 40)
