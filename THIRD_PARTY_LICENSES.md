# Third-party components and data

OrthoGather is released under the GNU General Public License, version 3 or later (see
[LICENSE](LICENSE)). It includes, loads or depends on the components below, each under its own
licence.

## Included in this repository

| Component | Location | Licence |
|---|---|---|
| UpSetJS (`@upsetjs/bundle` 1.11.0), © 2021 Samuel Gratzl | `static/vendor/upsetjs.umd.production.min.js` | GNU AGPL v3 for academic and private use; commercial licence otherwise. Full text: [`static/vendor/LICENSE-upsetjs.md`](static/vendor/LICENSE-upsetjs.md) |
| Gene Ontology (`go-basic.obo`, release 2026-07-26) | repository root | CC BY 4.0 ([geneontology.org](https://geneontology.org/docs/go-citation-policy/)) |
| Proteome catalogue derived from UniProt | `static/Proteomes_json/` | CC BY 4.0 ([uniprot.org](https://www.uniprot.org/help/license)) |
| Preselected Dataset: orthogroups inferred from UniProt proteomes | `static/Orthogroups.zip` | CC BY 4.0 (UniProt data) |
| Worked example input lists, from Giddey et al. (2017), *Sci. Rep.* 7:43858 | `example_analysis/input_dataset/` | CC BY 4.0 |

## Loaded from public CDNs by the web interface

| Component | Licence |
|---|---|
| Plotly.js 2.35.2 | MIT |
| D3 7.9.0 | ISC |
| three.js 0.170.0 | MIT |
| Font Awesome Free 6.5.1 | Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT |
| Inter, JetBrains Mono and Fraunces (Google Fonts) | SIL Open Font License 1.1 |

## Installed as dependencies

| Component | Licence |
|---|---|
| OrthoFinder 2.5.5 | GNU GPL v3 |
| GOATOOLS | BSD 2-Clause |
| SciPy, NumPy, pandas | BSD 3-Clause |
| Flask, Flask-Session | BSD 3-Clause |
| requests | Apache 2.0 |
| openpyxl | MIT |

## Data downloaded at run time

| Data | Licence |
|---|---|
| UniProt proteomes | CC BY 4.0 |
| EBI GOA annotation files | CC BY 4.0 |
| Taxonomic lineages, from the UniProt taxonomy service (based on NCBI Taxonomy) | CC BY 4.0 |
