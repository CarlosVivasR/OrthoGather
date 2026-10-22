"""Shared set-up for the validation scripts.

The scripts drive OrthoGather's real HTTP routes through Flask's test client.
Before the application is imported, HOME and the working directory are moved to
a temporary folder, so a run never touches the analysis history, the session
files or the data folders of an installation.

Two kinds of workspace:

- ExampleWorkspace: the worked example of the paper, rebuilt from files in the
  repository (the OrthoFinder export in example_analysis/1_orthofinder/ and the
  EBI GOA files of 28 July 2026 in docs/validation/data/). One species' GOA file
  can be left out, to test what the application does for a species without
  annotation.
- SyntheticWorkspace: an analysis written from Python dictionaries, for the
  combinations matrix.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data" / "goa_2026-07-28"
EXAMPLE = REPO / "example_analysis"
RESULTS = Path(__file__).resolve().parent / "results"

WORK = Path(os.environ.get("OG_VALIDATION_WORKDIR") or tempfile.mkdtemp(prefix="og_validation_"))
WORK.mkdir(parents=True, exist_ok=True)
(WORK / "home").mkdir(exist_ok=True)
os.environ["HOME"] = str(WORK / "home")
os.environ["ORTHOGATHER_CLEAN_PROTEOMAS"] = "0"
os.chdir(WORK)
sys.path.insert(0, str(REPO))

import pandas as pd                                   # noqa: E402

import app as og                                      # noqa: E402
from orthogather.core import goa as og_goa            # noqa: E402
from orthogather.core import single_copy as og_sc     # noqa: E402
from orthogather.core.excel import generate_go_excel  # noqa: E402

GO_SETTINGS = {"p_value": 0.05, "min_depth": 2}


def clear_caches():
    og._ID2GOS_CACHE.clear()
    og_goa._id2gos_cache.update({"key": None, "id2gos": None, "evidence_map": None})
    og_goa._by_file_cache.update({"key": None, "value": None})
    og_sc.invalidate_single_copy_cache()


def terms(js):
    """Every term row of a /gene_ontology_analysis response."""
    return [t for k in ("bp_results", "cc_results", "mf_results") for t in (js or {}).get(k) or []]


def read_list(path):
    return [line.strip() for line in open(path) if line.strip()]


def gaf_line(acc, go, code="IEA", aspect="P", qualifier=""):
    """A minimal GAF 2.2 line (17 columns)."""
    return "\t".join(["UniProtKB", acc, acc, qualifier, go, "PMID:0", code, "", aspect, "", "",
                      "protein", "taxon:1", "20261020", "UniProt", "", ""])


class _Workspace:
    """An analysis folder, its GOA files and its results, with a client whose
    session points at them."""

    _n = 0

    def _make_dirs(self, name):
        _Workspace._n += 1
        self.root = WORK / f"{_Workspace._n:03d}_{name}"
        shutil.rmtree(self.root, ignore_errors=True)
        self.folder, self.goa_dir, self.results = (self.root / "analysis", self.root / "GOA",
                                                   self.root / "results")
        for d in (self.folder, self.goa_dir, self.results):
            d.mkdir(parents=True)

    mode = "upload"

    def _finish(self, mapping):
        (self.folder / "goa_mapping.json").write_text(json.dumps(mapping))
        self.mapping = mapping
        self.species = list(pd.read_csv(self.folder / "Orthogroups.tsv", sep="\t", nrows=0).columns[1:])
        self.activate()
        if mapping:
            id2gos = og_goa.build_id2gos_from_goa_folder(str(self.goa_dir),
                                                         limit_files=list(mapping.values()))
            generate_go_excel(str(self.folder / "Orthogroups.tsv"), mapping,
                              str(self.results / "Gene_Ontology_Analysis.xlsx"),
                              annotated_ids=set(id2gos))
        self.new_session()

    def activate(self):
        og.RESULTS_FOLDER = str(self.results)
        og.GOA_DOWNLOAD_FOLDER = str(self.goa_dir)
        clear_caches()

    def new_session(self):
        self.client = og.app.test_client()
        with self.client.session_transaction() as s:
            s.update(folder_path=str(self.folder), species=self.species, modo=self.mode)
        self._loaded = {}

    # ------------------------------------------------------------------ routes
    def foreground(self, ids, expand=False, single_copy=False):
        self.activate()
        r = self.client.post("/foreground_analysis", json={
            "uniprot_ids": ids, "use_orthogroups": expand, "single_copy_only": single_copy})
        return r.status_code, r.get_json() or {}

    def background(self, ids=None, all_goa=False, expand=False, single_copy=False):
        self.activate()
        key = (tuple(ids or ()), all_goa, expand, single_copy)
        r = self.client.post("/background_analysis", json={
            "background_choice": "5" if all_goa else "4",
            "custom_uniprot_ids": [] if all_goa else list(ids or []),
            "use_orthogroups": expand, "single_copy_only": single_copy})
        self._loaded["background"] = key
        return r.status_code, r.get_json() or {}

    def background_once(self, ids=None, all_goa=False, expand=False):
        """Load the background unless the same one is already loaded."""
        if self._loaded.get("background") != (tuple(ids or ()), all_goa, expand, False):
            status, js = self.background(ids, all_goa, expand)
            assert status == 200, js

    def enrich(self, **settings):
        self.activate()
        body = dict(GO_SETTINGS)
        body.update(settings)
        r = self.client.post("/gene_ontology_analysis", json=body)
        return r.status_code, r.get_json() or {}


class ExampleWorkspace(_Workspace):
    """The worked example (OrthoFinder run of 5 August 2026, GOA files of
    28 July 2026), optionally with one species' GOA file left out."""

    mode = "generated"

    def __init__(self, name="example", hide=None):
        self._make_dirs(name)
        zips = sorted((EXAMPLE / "1_orthofinder").glob("*.zip"))
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(self.folder)
        mapping = json.loads((DATA / "goa_mapping.json").read_text())
        if hide:
            mapping = {sp: f for sp, f in mapping.items() if hide not in sp}
        for fn in mapping.values():
            with gzip.open(DATA / f"{fn}.gz", "rb") as src, open(self.goa_dir / fn, "wb") as dst:
                shutil.copyfileobj(src, dst)
        self._finish(mapping)


class SyntheticWorkspace(_Workspace):
    """An analysis written from dictionaries.

    orthogroups : {orthogroup: {species: [accessions]}}
    unassigned  : {species: [accessions in no orthogroup]}
    goa_lines   : {species: [GAF lines]}; a species without an entry has no GOA file
    """

    def __init__(self, name, orthogroups, unassigned=None, goa_lines=None):
        self._make_dirs(name)
        species = sorted({sp for per in orthogroups.values() for sp in per}
                         | set(unassigned or {}) | set(goa_lines or {}))

        def cell(accs, sp):
            return ", ".join(f"tr|{a}|{a}_{sp[:5].upper()}" for a in accs)
        rows = [{"Orthogroup": og_id, **{sp: cell(per.get(sp, []), sp) for sp in species}}
                for og_id, per in orthogroups.items()]
        counts = [{"Orthogroup": og_id, **{sp: len(per.get(sp, [])) for sp in species},
                   "Total": sum(len(v) for v in per.values())} for og_id, per in orthogroups.items()]
        pd.DataFrame(rows, columns=["Orthogroup"] + species).to_csv(
            self.folder / "Orthogroups.tsv", sep="\t", index=False)
        pd.DataFrame(counts, columns=["Orthogroup"] + species + ["Total"]).to_csv(
            self.folder / "Orthogroups.GeneCount.tsv", sep="\t", index=False)
        ua, k = [], len(orthogroups)
        for sp, accs in (unassigned or {}).items():
            for a in accs:
                ua.append({"Orthogroup": f"OG{k:07d}", **{s: (cell([a], s) if s == sp else "")
                                                          for s in species}})
                k += 1
        pd.DataFrame(ua, columns=["Orthogroup"] + species).to_csv(
            self.folder / "Orthogroups_UnassignedGenes.tsv", sep="\t", index=False)
        mapping = {}
        for sp, lines in (goa_lines or {}).items():
            fn = f"{_Workspace._n}_{sp}.goa"
            (self.goa_dir / fn).write_text("!gaf-version: 2.2\n" + "".join(
                line if line.endswith("\n") else line + "\n" for line in lines))
            mapping[sp] = fn
        self._finish(mapping)


def write_result(name, payload):
    path = RESULTS / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str) + "\n")
    return path
