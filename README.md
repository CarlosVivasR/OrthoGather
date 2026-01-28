# 🧬 OrthoGather: a local platform for orthology-based proteome comparison and Gene Ontology enrichment

**OrthoGather** — compare proteomes with **OrthoFinder** and discover function with **GOATOOLS** — all in a local web application.  
Download **UniProt** proteomes, run **OrthoFinder**, perform **Gene Ontology enrichment**, and export publication-ready figures and tables.  
*Requires Python 3.7.*

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

## 🔽 Download and Installation


To install **OrthoGather**, first clone the repository and move into the project folder:

```bash
git clone https://github.com/CarlosVivasR/OrthoGather.git
cd OrthoGather
```

The installation process depends on your operating system. Each method automatically configures the required environment and dependencies, but you can consult [installation_guide.pdf](Installation_guide.pdf) for a complete explanation of every step and additional troubleshooting details.

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
