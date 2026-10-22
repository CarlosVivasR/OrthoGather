# OrthoGather: advanced notes

This page collects details that most users do not need: the enrichment test settings, OrthoFinder
thread settings, disk use, the repository layout, the error codes and
the test suite. For installation and use, see the [README](../README.md) and the
[installation guide](Installation_guide.pdf).

## Enrichment test

GOATOOLS reads the GOA annotations and propagates them through the ontology. OrthoGather then
computes a one-sided Fisher's exact test for over-representation with SciPy and applies the
Benjamini–Hochberg correction itself:

- Annotations are propagated to parent terms through `is_a` and `part_of` (the True Path Rule).
- Annotations carrying the `NOT` qualifier are discarded.
- Terms annotated to fewer than 10 or more than 500 proteins of the annotated background are
  excluded, the limits used by clusterProfiler and WebGestalt.
- Biological Process, Cellular Component and Molecular Function share a single annotated
  background, as in PANTHER's over-representation test, and Benjamini–Hochberg correction is
  applied once across all three.
- The minimum GO depth is applied before the correction. It is not only a display setting: raising
  it shrinks the set of tested terms and so changes every q-value.
- The foreground is restricted to proteins that are annotated and present in the background. An
  identifier that carries GO terms but was not detected in the experiment is left out, because it
  is not in the background.
- Pasted identifiers are read before the test. A FASTA header (`>sp|P0A6F5|CH60_ECOLI …`, or
  `sp|P0A6F5|CH60_ECOLI` followed by a description) gives its accession and the sequence lines
  are skipped; accessions are converted to upper case; an isoform suffix (`P00350-2`) is removed,
  with a warning, because GOA files annotate the canonical accession; duplicates are dropped.
  Identifiers that are not UniProt accessions keep their case. The results list each pasted
  foreground identifier that did not enter the test, with the reason: not found in the analysis,
  not in the background, no GO annotation, or left out by the orthogroup expansion.

There are three evidence presets. All keeps every annotation. Non-IEA (called "curated" in the
exported files) keeps EXP, IDA, IPI, IMP, IGI, IEP, TAS, IC, IBA and the high-throughput codes
HTP, HEP, HDA, HMP and HGI; besides IEA, it therefore also drops ISS, ISO, ISA, ISM, IGC, RCA, NAS,
IBD, IKR, IRD and ND. Experimental only keeps EXP, IDA, IPI, IMP, IGI, IEP and the high-throughput
codes.

Counting can be per protein or per orthogroup. With per-protein counting, an orthogroup with ten
members contributes ten observations to a term, which overstates the evidence when the sets are
expanded to full orthogroups; per-orthogroup counting counts each orthogroup once, with the union of
the annotations of its background members, and counts each annotated protein that is in no
orthogroup as a unit of its own. When the foreground or the background is expanded, counting is
always per orthogroup: per protein, a family would count once per paralogue, and in a benchmark
with random foregrounds that gave a significant term in every replicate. Counted per orthogroup,
the foreground is always the pasted proteins, each through its orthogroup, so expanding the
foreground only sets the counting; expanding the background is what gives each orthogroup the
annotations of its members in the other species. An orthogroup is in the foreground when it contains a foreground
protein, so a family of many detected paralogues is more likely to be there by chance than a pair.
The p-values of this mode therefore come from a permutation test: the foreground labels are
shuffled among the background proteins as pasted (before any expansion; with **Use all GOA files**,
the proteome of the foreground's species in the analysis), each shuffle is collapsed to orthogroups in
the same way (a pasted protein with no annotation of its own takes part through the annotations of
its orthogroup, which is what expansion adds), and the observed hypergeometric p-value (exported as `p_hypergeom`) is compared with
the shuffled ones. The number of shuffles is 2m/α, between 5,000 and 50,000, where m is the number
of terms in the correction family; the seed is fixed, so a run is reproducible. The Orthogroups
setting (all, or single-copy only) affects only expansion, and is applied when a set is loaded.

With **Use all GOA files**, the universe is the annotated proteome of the species the foreground
proteins belong to, not of every species in the analysis: with a foreground from one species, a
pooled universe makes any function that is commoner in that species look enriched. Counted per
orthogroup, the universe is the whole proteome of that species in the analysis, each protein taking
part through its orthogroup, and the orthogroups carry the annotations of every GOA file. That is
the same as pasting the proteome as the background and expanding it, and it works the same for a
species with a complete, a partial or no GOA file.

The `Provenance` worksheet of each results file records the data versions (UniProt, GOA, the GO
ontology, OrthoFinder and GOATOOLS) and every setting of the run: the evidence codes, the counting
mode, whether each set was expanded and with which orthogroups, the background, the test, the FDR
and display thresholds, the maximum number of terms shown, the minimum depth, the term-size limits
and the sizes of the foreground and background.

## OrthoFinder thread settings

OrthoGather runs OrthoFinder with `-og`, which stops after orthogroup inference and skips the gene
and species trees. It reads the number of logical CPUs and sets the sequence-search threads (`-t`)
to that number and the analysis threads (`-a`) to a quarter of it, with a minimum of one: `-t 10
-a 2` with 10 logical CPUs, `-t 8 -a 2` on a 4-core laptop with 8 threads. The analysis phase is
limited by memory, so more analysis threads rarely help. This ratio is OrthoGather's default, not
an OrthoFinder recommendation.

To leave CPUs free for other work, set the thread counts when starting the application:

```bash
ORTHOGATHER_OF_THREADS=6 ORTHOGATHER_OF_ANALYSIS_THREADS=1 python app.py
```


## Disk use

The proteome catalogue ships compressed in the repository
(`static/Proteomes_json/proteomes_list.json.gz`, 20 MB) and is unpacked on first launch to a
260 MB JSON file. With the ontology and the repository itself, OrthoGather takes about 350 MB
before any analysis, plus the downloaded proteomes. The Conda environment adds about 2 GB. The
application checks GitHub for a newer catalogue and offers to update it.

## Repository layout

| Path | Contents |
|---|---|
| `app.py` | The Flask application: routes, analysis steps and exports |
| `orthogather/` | Core modules: catalogue, GOA parsing, OrthoXML import, history, error codes |
| `templates/`, `static/` | Web pages, styles, scripts and images. `static/Orthogroups.zip` holds the Preselected Dataset, `static/Proteomes_json/` the proteome catalogue and `static/vendor/` the bundled UpSetJS and its licence |
| `go-basic.obo` | The Gene Ontology release used for enrichment, read by the application from the repository root |
| `example_analysis/` | The worked example from the paper, as exported by the application |
| `installers/` | The macOS and Windows installers (see [installers/README.md](../installers/README.md)) |
| `docs/` | The installation guide (PDF and HTML) and this page |
| `tests/`, `tools/` | The test suite and maintenance scripts (catalogue building, end-to-end checks, tutorial screenshots) |
| `environment.yml`, `requirements*.txt` | Conda environment and pip requirements |
| `CITATION.cff`, `.zenodo.json` | Citation metadata for GitHub and Zenodo |

## Error codes

Many errors shown by OrthoGather carry a stable code (`ERR_...`), a message and a hint; the rest
are shown as plain messages. The codes are defined in `orthogather/utils/error_catalog.py` (36
entries). Backend routes call `respond_error("ERR_CODE", where=..., detail=...)`, and the
frontend shows the response as a notification through `static/js/og-errors.js`. The categories are
`input`, `state`, `data`, `network`, `external`, `not-found` and `system`; the severities are
`error`, `warning` and `info`.

To add an error, add an `ErrorSpec` with a code starting with `ERR_` to `error_catalog.py` and
reference it from the route. `tests/test_error_catalog.py` checks that every code used in `app.py`
exists in the catalogue, and that every catalogued code is used. Errors that escape the routes are caught by global handlers for 404, 500
and unhandled exceptions, which return JSON for API requests and `templates/error.html` for pages.

When reporting a problem, quote the `ERR_` code in the
[issue](https://github.com/CarlosVivasR/OrthoGather/issues).

## Test suite

The repository has 165 tests covering species matching, taxonomy, the error catalogue, OrthoXML
import, catalogue building, file names, provenance, pasted identifiers, local security, the
per-orthogroup permutation test (its calibration on random foregrounds and its power), the GOA files
per species, single-copy orthogroups, failed OrthoFinder runs, and every combination of the Gene
Ontology settings through the real routes (`tests/test_go_combinations.py`: the counting mode applied,
the notes that explain it, Fisher p-values equal to SciPy's and a Benjamini-Hochberg correction that
reproduces). The worked example is checked number by number by
`docs/validation/verify_example.py`; [`docs/validation/`](validation/) also holds the calibration of
every setting on random foregrounds and the benchmark of expansion with a species' annotations
hidden. GitHub Actions runs the tests and the example check on Linux and macOS on every change.

```bash
conda activate orthogather
pip install -r requirements-dev.txt   # pytest, selenium, webdriver-manager
pytest tests/ -v
```

`requirements-dev.txt` also installs what `tools/capture_tutorial_screenshots.py` needs to
regenerate the tutorial screenshots with a headless Chrome.
