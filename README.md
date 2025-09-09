# OrthoGather
OrthoGather: compare proteomes with [OrthoFinder] and discover function with [GOATOOLS]—all in a local web app. Download UniProt proteomes, run OrthoFinder 3.0.1b1, perform GO enrichment (Biological Process / Cellular Component / Molecular Function), and export figures/Excel. Python 3.7.

## What is OrthoGather?
OrthoGather is a local web interface that bridges orthology inference with functional interpretation. It lets you:
- Run **OrthoFinder 3.0.1b1** locally and explore **orthogroups** across species.
- Perform **Gene Ontology enrichment** (BP/CC/MF) with **GOATOOLS** (Fisher + FDR).
- Produce **publication-ready figures (PNG)** and **tables (Excel/CSV)** for downstream analysis.
- Keep everything **private/offline** on your machine (no data leaves your computer).

## Overview
OrthoGather unifies orthology-based proteome comparison with functional interpretation. It streamlines the path from species selection to results you can read, share, and reuse: run **OrthoFinder 3.0.1b1**, explore **orthogroups** across species, and perform **Gene Ontology enrichment** with **GOATOOLS** (BP/CC/MF; Fisher + FDR). The app operates entirely on your machine—favoring privacy, reproducibility, and quick iteration.

## Input flows
You can start an analysis in three ways:
- **New Analysis** — Select organisms from a UniProt catalog, download proteomes, and run OrthoFinder locally with live logs. This creates a clean, self-contained workspace for your study.
- **Preselected Dataset** — A ready-to-use example that lets you explore the full workflow immediately (ideal for demos or teaching).
- **External Data Upload** — Upload a `.zip` with previously generated OrthoFinder results from another system to reuse completed analyses without recomputation.

Regardless of the entry point, OrthoGather focuses downstream steps on the standard **Orthogroups** output, keeping only what is needed for analysis and export.

## Analysis routes
Once orthogroups are available (generated or uploaded), you can take either route—or both—in any order.

### 1) Comparative Orthogroup Analysis
This module helps you examine the presence and distribution of orthogroups across a user-defined subset of species and, optionally, narrow the scope to proteins of interest via UniProt IDs.

- **Subset by species**: pick two or more species to create a focused comparison set (useful for clades, model–non-model contrasts, or custom panels).
- **Two UpSet plots** ([UpSetPlot]):
  - **Species combinations** — number of orthogroups unique/shared across species combinations (presence/absence patterns).
  - **Protein contribution** — how many proteins each combination contributes, clarifying the magnitude behind intersections.
- **Optional protein-level filter**: restrict orthogroups to those containing specific UniProt IDs (e.g., differentially expressed proteins, pathway members, or candidate families). This enables practical tasks like locating functional orthologs for a protein of interest across species.

Exports include publication-ready figures (PNG) and tables (Excel/CSV) summarizing orthogroup membership and intersections.

### 2) Gene Ontology Enrichment Analysis
This module turns orthogroup-level findings into functional hypotheses.

- **GOA download** (per species) and an **annotation coverage** panel (4-in-1) to gauge how well proteins are annotated before enrichment.
- **Define sets**:
  - **Foreground** — paste UniProt IDs for the set to be tested.
  - **Background** — paste UniProt IDs **or** use “all species with GOA” from your selection.
  - **Include complete orthogroups** (optional) — expand IDs to all members of their orthogroups to capture functionally related proteins.
- **Run enrichment** with **GOATOOLS** (BP/CC/MF; Fisher + FDR), then review significant terms and download detailed results.

Outputs include the enrichment figure and structured tables in Excel/CSV for downstream exploration.

## Why it helps
A substantial share of proteins across organisms remain **under-annotated** or **misannotated**, which makes it difficult to reason about function from any single species alone. OrthoGather is motivated by that gap: it leverages orthogroups to transfer functional signal from well-annotated proteins to those with limited or noisy annotations, so you can move beyond “who shares what?” toward “what biology does this imply?” Starting from any UniProt-associated proteome set, orthology provides the evolutionary context; Gene Ontology enrichment provides the functional readout; and both are brought together in one place you can actually use.

The tool builds on reliable components—orthology inference with [OrthoFinder], GO annotations (GOA) when available, enrichment analysis with [GOATOOLS], and intersection visualisation with [UpSetPlot]—but it does something different: it turns these pieces into a cohesive, orthogroup-centric workflow. You select species, download proteomes, run OrthoFinder with live logs, and immediately explore the standard *Orthogroups/* output interactively. You can define a foreground/background from pasted UniProt IDs or from all downloaded GOA, and you may optionally expand your sets by orthogroups to propagate evidence from better-annotated orthologs. An annotation-coverage panel helps you judge whether there is enough GO support before running statistics. Everything runs locally, producing figures (PNG) and tables (Excel/CSV) that are easy to reuse and share.

Looking ahead, OrthoGather is designed to grow: near-term additions include GO DAG visualisation, richer summary plots, faster foreground/background iteration, and light batch workflows—while keeping the same local, reproducible, and privacy-preserving design. In short, the focus is to make it straightforward to formulate **testable functional hypotheses** from orthogroup presence/absence, exploit **well-annotated orthologs** to illuminate **under-annotated or misannotated** proteins, and obtain immediate, visual answers to “who shares what?” across your species panels—all with publication-ready outputs and no cloud dependency.

### References & attributions
- OrthoFinder — phylogenetic orthology inference platform. See papers linked in their README. [OrthoFinder]  
- GOATOOLS — Gene Ontology enrichment and utilities. [GOATOOLS]  
- UpSetPlot — UpSet plots in Python (set-intersection visualisation). [UpSetPlot]

[OrthoFinder]: https://github.com/davidemms/OrthoFinder
[GOATOOLS]: https://github.com/tanghaibao/goatools
[UpSetPlot]: https://github.com/jnothman/UpSetPlot
