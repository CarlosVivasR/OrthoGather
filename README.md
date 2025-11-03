# 🧬 OrthoGather: a local platform for orthology-based proteome comparison and Gene Ontology enrichment

**OrthoGather** — compare proteomes with **[OrthoFinder](https://github.com/davidemms/OrthoFinder)** and discover function with **[GOATOOLS](https://github.com/tanghaibao/goatools)** — all in a local web app.  
Download **UniProt** proteomes, run **OrthoFinder 3.0.1b1**, perform **GO enrichment**, and export figures/Excel.  
*Requires Python 3.7.*

---

## 🌍 What is OrthoGather?

**OrthoGather** is a local web interface that bridges **orthology inference** with **functional interpretation**. It lets you:

- Run **OrthoFinder 3.0.1b1** locally and explore orthogroups across species.
- Perform **Gene Ontology enrichment** with **GOATOOLS**.
- Produce **publication-ready figures** and **tables** for downstream analysis.
- Keep everything **private/offline** on your machine (no data leaves your computer).

---

## 🧩 Overview

**OrthoGather** unifies **orthology-based proteome comparison** with **functional interpretation**.  
It streamlines the path from species selection to results you can read, share, and reuse: run **OrthoFinder 3.0.1b1**, explore orthogroups across species, and perform **Gene Ontology** enrichment with **GOATOOLS**.  
The app operates entirely on your machine — favoring **privacy**, **reproducibility**, and **quick iteration**.

---
## 🔽 Download and Installation

To install **OrthoGather**, first clone the repository and move into the project folder:

```bash
git clone https://github.com/CarlosVivasR/OrthoGather.git
cd OrthoGather
```

The installation process depends on your operating system. Each method automatically configures the required environment and dependencies, but you can consult installation_guide.pdf for a complete explanation of every step and additional troubleshooting details.

### 🧩 macOS (Intel / Rosetta)

Run the following command to install OrthoGather on macOS systems with Intel chips, or using Rosetta mode on Apple Silicon:
```bash
./install_orthogather_mac.sh
```

This script will:
- Check that you are running in Intel (Rosetta) mode.
- Create a dedicated environment named orthogather37 with Python 3.7.
- Install all required dependencies (Flask, GOATOOLS, OrthoFinder, etc.).
- Verify that OrthoGather is correctly installed and ready to use.

⚠️ Note:
Conda must be installed on macOS before running this script (e.g., via Miniforge, Anaconda, or Miniconda).
The installation guide (installation_guide.pdf) includes step-by-step instructions on how to install Conda and enable Rosetta mode properly.

Once completed, remember to open your terminal in Rosetta mode and activate the environment each time you want to use the tool:
```bash
conda activate orthogather37
python app.py
```
### 🧬 Linux / WSL (Windows Subsystem for Linux)

For Linux or WSL users, run the following command:
```bash
./install_orthogather_wsl.sh
```

The script will automatically:
- Detect if you are running inside a WSL or Linux environment.
- Check if Micromamba is installed — if not, it will display the command to install it manually and prompt you to restart the terminal.
- Create the environment orthogather37 with Python 3.7.
- Install all required dependencies and verify the OrthoFinder installation.
- After installation, activate the environment and start the tool:
``` bash
micromamba activate orthogather37
python app.py
```

For a comprehensive explanation of the setup process, including dependency management, configuration tips, and troubleshooting on both macOS and WSL/Linux, please refer to the detailed installation_guide.pdf included in this repository.

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

## 💡 Why it helps

A substantial share of proteins across organisms remain **under-annotated or misannotated**, which makes it difficult to reason about function from any single species alone.  
**OrthoGather** is motivated by that gap: it leverages **orthogroups** to transfer functional signal from well-annotated proteins to those with limited or noisy annotations — moving beyond “who shares what?” toward **“what biology does this imply?”**.

Starting from any **UniProt-associated proteome** set, **orthology** provides the evolutionary context; **Gene Ontology enrichment** provides the functional readout; and both are brought together in **one local interface**.

The tool builds on reliable components — orthology inference with **[OrthoFinder](https://github.com/davidemms/OrthoFinder)**, GO annotations (**GOA**) when available, enrichment analysis with **[GOATOOLS](https://github.com/tanghaibao/goatools)**, and intersection visualisation with **[UpSetPlot](https://upsetplot.readthedocs.io/en/stable/)** — and turns these pieces into a cohesive, **orthogroup-centric** workflow.

You select species, download proteomes, run **OrthoFinder** with live logs, and immediately explore the standard `Orthogroups/` output interactively.  
You can define a **foreground/background** from pasted UniProt IDs or from **all downloaded GOA**, and you may optionally **expand your sets by orthogroups** to propagate evidence from better-annotated orthologs.  
An **annotation-coverage panel** helps you judge whether there is enough GO support before running statistics.

Everything runs locally, producing **figures** and **tables** that are easy to reuse and share.

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
