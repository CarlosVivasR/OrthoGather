[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18510911.svg)](https://doi.org/10.5281/zenodo.18510911)

# 🧬 OrthoGather: a local platform for orthology-based proteome comparison and Gene Ontology enrichment

**OrthoGather** — compare proteomes with **OrthoFinder** and discover function with **GOATOOLS** — all in a local web application.  
Download **UniProt** proteomes, run **OrthoFinder**, perform **Gene Ontology enrichment**, and export publication-ready figures and tables.  
*Requires Python 3.11 and OrthoFinder 2.5.5 (runs natively on Apple Silicon, Intel macOS, Linux, and WSL — no Rosetta needed).*

---

## 🧩 Overview

**OrthoGather** is a local web application that integrates **orthology inference** with **functional interpretation** for comparative proteome and proteomics analyses.

It enables users to:
- Download reference proteomes from **UniProt** and infer orthogroups using **OrthoFinder**.
- Explore shared and species-specific orthogroups through interactive **UpSet plots**.
- Perform **Gene Ontology (GO) enrichment** with **GOATOOLS**, leveraging orthogroup relationships to propagate functional information across species.
- Generate **publication-ready figures** and **Excel tables** for downstream analysis.

All analyses run **locally**, favouring **privacy**, **reproducibility**, and **rapid iteration**, and are particularly useful when working with **poorly annotated or non-model organisms**.

---

## 💡 Why it helps

A substantial fraction of proteins across organisms remain **under-annotated or inconsistently annotated**, which complicates functional interpretation and cross-species comparisons. This is particularly limiting in proteomics experiments involving non-model species or clinical isolates.

**OrthoGather** addresses this gap by exploiting **orthogroup relationships** to transfer functional information from well-annotated proteins to those with limited annotation. By combining orthology-based comparison with Gene Ontology enrichment in a single workflow, the platform moves beyond identifying shared proteins toward inferring **shared and species-specific biological functions**.

Starting from any **UniProt-associated proteome set**, orthology provides evolutionary context, while Gene Ontology enrichment provides a functional readout — both integrated into a single, local interface.

---

## 📖 Citation

If you use **OrthoGather** in your research, please cite:

> **Manuscript in preparation.**

This section will be updated with the bioRxiv preprint and the final journal reference once available.

---
## 🔽 Download and Installation

### Prerequisites

Before installing **OrthoGather**, please ensure that you have:

- **Git**, including **Git LFS**
  ```bash
  git lfs install
  ```
- **Conda** or **Micromamba**
- A Unix-based environment (macOS, Linux, or WSL)

### Clone the repository

To install **OrthoGather**, first clone the repository and move into the project folder:

```bash
git clone https://github.com/CarlosVivasR/OrthoGather.git
cd OrthoGather
```

### ✅ Recommended: one-line install with Conda (all platforms)

The canonical setup is a single Conda environment defined in [`environment.yml`](environment.yml).
It installs Python 3.11, OrthoFinder 2.5.5, and every Python dependency — and runs
**natively** on Apple Silicon, Intel macOS, Linux, and WSL (no Rosetta).

```bash
conda env create -f environment.yml
conda activate orthogather
python app.py
```

That's it. Every time you want to use OrthoGather, just `conda activate orthogather` and `python app.py`.

> Using **Micromamba** instead of Conda? Replace `conda` with `micromamba` in the commands above.

### 🧩 Optional: guided install scripts

If you prefer a guided installer that also checks prerequisites, run the script for your platform:

```bash
./install_orthogather_mac.sh   # macOS (Apple Silicon or Intel)
./install_orthogather_wsl.sh   # Linux / WSL
```

Both scripts create the same `orthogather` environment from `environment.yml` and verify that OrthoFinder is detected.

⚠️ **Prerequisite:** Conda or Micromamba must already be installed (e.g. via [Miniforge](https://github.com/conda-forge/miniforge)). For a step-by-step walkthrough and troubleshooting, see [installation_guide.pdf](Installation_guide.pdf).

---

## 🧬 Input flows

You can start an analysis in **three ways**:

### New Analysis
Select organisms from a UniProt catalog, download proteomes, and run **OrthoFinder** locally with live logs.  
Creates a clean, self-contained workspace for your study.

### Preselected Dataset
A ready-to-use example that lets you explore the full workflow immediately (ideal for demos or teaching).

### External Data Upload
Upload a `.zip` with previously generated **OrthoFinder** results from another system to reuse completed analyses without recomputation.

> Regardless of the entry point, OrthoGather focuses downstream steps on the standard **Orthogroups** output, keeping only what is needed for analysis and export.

#### OrthoFinder thread tuning

OrthoGather invokes OrthoFinder with `-og` (skip gene/species trees — we only need orthogroups) and **auto-detects your CPU count** for the `-t` (sequence-search) and `-a` (analysis) thread counts. On a 10-core Mac you'll see `-t 10 -a 2`; on a 4-core laptop, `-t 4 -a 1`. Override if you want to leave headroom for other work:

```bash
ORTHOGATHER_OF_THREADS=6 ORTHOGATHER_OF_ANALYSIS_THREADS=1 python app.py
```

The convention `-a ≈ -t / 4` follows OrthoFinder's own recommendation: the analysis phase is memory-bound and oversubscription hurts more than it helps.

---

## 🔬 Analysis routes

Once **orthogroups** are available (generated or uploaded), you can take either route — or both — in any order.

### 1️⃣ Comparative Orthogroup Analysis

This module helps you examine the **presence and distribution of orthogroups** across a user-defined subset of species and, optionally, narrow the scope to proteins of interest via **UniProt IDs**.

**Features:**
- **Subset by species** — pick two or more species to create a focused comparison set (useful for clades, model–non-model contrasts, or custom panels).
- **Two UpSet plots** (via **[UpSetPlot](https://upsetplot.readthedocs.io/en/stable/)**):
  - **Species combinations** — number of orthogroups unique/shared across species combinations (presence/absence patterns).
  - **Protein contribution** — how many proteins each combination contributes, clarifying the magnitude behind intersections.
- **Optional protein-level filter** — restrict orthogroups to those containing specific UniProt IDs (e.g., differentially expressed proteins, pathway members, or candidate families).

**Exports:** publication-ready **PNG** figures and **Excel/CSV** tables summarizing orthogroup membership and intersections.

### 2️⃣ Gene Ontology Enrichment Analysis

This module turns orthogroup-level findings into **functional hypotheses**.

**Workflow:**
- **GOA download (per species)** and an **annotation coverage panel (4-in-1)** to gauge how well proteins are annotated before enrichment.
- **Define sets:**
  - **Foreground** — paste UniProt IDs for the set to be tested.
  - **Background** — paste UniProt IDs or use “all species with GOA” from your selection.
  - **Include complete orthogroups (optional)** — expand IDs to all members of their orthogroups to capture functionally related proteins.
- **Run enrichment** with **[GOATOOLS](https://github.com/tanghaibao/goatools)**, then review significant terms and download detailed results.

**Outputs:** the enrichment figure and structured tables for downstream exploration.

---

## ⚠️ Error system

Every user-visible error in OrthoGather has a stable code, a clear message,
and an actionable hint. The catalogue lives in
`orthogather/utils/error_catalog.py` (~60 entries today). Backend routes call
`respond_error("ERR_CODE", where=..., detail=...)` and the frontend renders
the response as a uniform toast via `static/js/og-errors.js`.

**Adding a new error**: open `error_catalog.py`, add a new `ErrorSpec` with
a code starting with `ERR_`, then reference it from your route. The pytest
suite at `tests/test_error_catalog.py` enforces that every code referenced
from `app.py` exists in the catalogue.

Categories: `input`, `state`, `data`, `network`, `external`, `not-found`,
`system`. Severities: `error`, `warning`, `info`. The frontend toast styles
itself accordingly (red / amber / blue border, matching icon).

Global error handlers (`@app.errorhandler(404)`, `@app.errorhandler(500)`,
`@app.errorhandler(Exception)`) catch anything that escapes and render
either JSON (for `Accept: application/json` / `/api/*` paths) or the
branded `templates/error.html` page (for HTML requests).

---

## 🧪 Running the test suite

OrthoGather ships with a pytest suite that locks in the species-matching contract (see `tests/test_species_matching.py`). To run it:

```bash
conda activate orthogather
pip install -r requirements-dev.txt   # installs pytest, selenium, webdriver-manager
pytest tests/ -v
```

The same dev requirements file also installs the tools used by
`tools/capture_tutorial_screenshots.py` to regenerate the tutorial figures
(headless Chrome via Selenium).

---

## 🚀 Looking ahead

**OrthoGather** is designed to grow. Near-term additions include:

- **GO DAG visualisation**
- **Richer summary plots**
- **Faster foreground/background iteration**
- **Lightweight batch workflows**

All while keeping the same **local, reproducible, and privacy-preserving** design.

> In short: formulate testable functional hypotheses from orthogroup presence/absence, exploit well-annotated orthologs to illuminate under-annotated proteins, and obtain immediate, visual answers to “who shares what?” — **with publication-ready outputs and no cloud dependency**.

---

## 📚 References & attributions

- **OrthoFinder** — phylogenetic orthology inference platform. See papers linked in their README. **[OrthoFinder GitHub](https://github.com/davidemms/OrthoFinder)**
- **GOATOOLS** — Python library for Gene Ontology analyses. **[GOATOOLS GitHub](https://github.com/tanghaibao/goatools)**
- **UpSetPlot** — visualization of set intersections. **[UpSetPlot Docs](https://upsetplot.readthedocs.io/en/stable/)**
- **UniProt** — comprehensive resource for protein sequence and annotation. **[UniProt](https://www.uniprot.org/)**
