# OrthoGather — worked example

Every file here was produced by OrthoGather v1.0.0 from the example dataset
described in **Supplementary File S1** of the manuscript, and is the
application's own export: nothing has been edited, renamed or reformatted by
hand. Each artifact has its own folder holding every format the application
offers for it.

## Source dataset

Giddey, A. D., de Kock, E., Nakedi, K. C. et al. (2017).
*A temporal proteome dynamics study reveals the molecular basis of induced
phenotypic resistance in Mycobacterium smegmatis at sub-lethal rifampicin
concentrations.* Scientific Reports 7:43858.
<https://doi.org/10.1038/srep43858>

Protein identifiers were taken from that paper's supplementary material and
standardised to UniProt accessions. Because proteins that increase and proteins
that decrease in abundance describe opposite biological responses, the 491
differentially expressed proteins were split by direction and analysed as two
independent foregrounds against a common background.

## Contents

### `input_dataset/`

| File | Contents |
|---|---|
| `foreground_down-regulated_306.txt` | 306 proteins less abundant after rifampicin |
| `foreground_up-regulated_185.txt` | 185 proteins more abundant after rifampicin |
| `background_3181.txt` | the 3,181 proteins detected in the study |
| `Example_dataset_Foreground_Background.xlsx` | the same lists as a workbook |

### `0_run_metadata/`

`provenance/` — software and database versions of this run, in text and JSON.
`citation/` — BibTeX and RIS entries for this exact run.
`taxonomy-tree/` — taxonomic dendrogram of the six species, in Newick format.

### `1_orthofinder/`

OrthoFinder output for the six species, as downloaded from the run summary:
`Orthogroups.tsv`, `Orthogroups.GeneCount.tsv`,
`Orthogroups_UnassignedGenes.tsv`, `Orthogroups.txt`. **5,949 orthogroups.**

### `2_comparative_analysis/`

One folder per figure, each with the image as exported by the application (PNG
and SVG) and the underlying data (XLSX, CSV, TSV, JSON). The data files list,
for every species intersection, the orthogroups and the UniProt accessions they
contain, one worksheet per intersection.

| Folder | Figure |
|---|---|
| `figure1_protein-distribution` | proteins per orthogroup |
| `figure2_orthogroup-sharing` | orthogroups by number of species |
| `figure3_upset-orthogroups` | UpSet, orthogroups, three species |
| `figure4_upset-proteins` | UpSet, proteins, three species |
| `figure5_upset-orthogroups-filtered` | the same, restricted to the 430 orthogroups that contain a foreground protein |
| `figure6_upset-proteins-filtered` | the same, for proteins |

### `3_go_annotation/`

`annotation-coverage-per-orthogroup/` — GO annotation coverage per orthogroup
(XLSX, and zipped CSV and TSV). Worksheets: Meta, Initial Groups, Filtered
Groups, Removed Groups, Groups of Interest, Species & GOA Map.
**4,638 of the 5,949 orthogroups contain at least one annotated protein.**
`annotation-coverage-histogram/` — the coverage histogram as exported.

### `4_go_enrichment/`

One folder per direction of change, each split into `chart/` (PNG, SVG),
`results/` (XLSX, zipped CSV and TSV) and `table/` (CSV, TSV, JSON).

| Folder | Result |
|---|---|
| `down-regulated_306/` | 306 submitted, 250 annotated, tested against the 2,470-protein annotated universe. **21 enriched terms** (20 BP, 1 MF). |
| `up-regulated_185/` | 185 submitted, 162 annotated. **1 enriched term**; the chart and the table also carry the two terms at FDR 0.059. |

Both runs used all evidence codes, per-protein counting, all orthogroups, a
one-sided Fisher exact test, minimum GO depth 2, term sizes of 10–500
background proteins, and Benjamini–Hochberg correction applied once across the
three namespaces (613 terms in the correction family). Every parameter is
recorded in the `Provenance` worksheet of each results file.

## Reproducing this analysis

Install OrthoGather, select the six species listed in Supplementary File S1, run
OrthoFinder, then open the Gene Ontology module and paste the foreground and
background lists from `input_dataset/`. GO annotation files are downloaded by
the application from the EBI GOA repository; that repository is updated monthly,
so a later run may differ slightly from the results here. The Gene Ontology
release and the GOA generation date in each `Provenance` worksheet identify the
exact versions used:

| | |
|---|---|
| OrthoGather | 1.0.0 |
| OrthoFinder | 2.5.5 |
| GOATOOLS | 1.6.4 |
| UniProt release | 2026_02 |
| Proteome catalogue | 2026-06-03 |
| Gene Ontology | releases/2026-07-26 |
| EBI GOA proteomes generated | 2026-07-28 |
