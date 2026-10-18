# OrthoGather: advanced notes

This page collects details that most users do not need: the enrichment test settings, OrthoFinder
thread settings, the guided install scripts, disk use, the repository layout, the error codes and
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

There are three evidence presets. All keeps every annotation. Non-IEA (called "curated" in the
exported files) keeps EXP, IDA, IPI, IMP, IGI, IEP, TAS, IC, IBA and the high-throughput codes
HTP, HEP, HDA, HMP and HGI; besides IEA, it therefore also drops ISS, ISO, ISA, ISM, IGC, RCA, NAS,
IBD, IKR, IRD and ND. Experimental only keeps EXP, IDA, IPI, IMP, IGI, IEP and the high-throughput
codes.

Counting can be per protein or per orthogroup. With per-protein counting, an orthogroup with ten
members contributes ten observations to a term, which overstates the evidence when the sets are
expanded to full orthogroups; per-orthogroup counting counts each orthogroup once. The Orthogroups
setting (all, or single-copy only) affects only expansion.

The `Provenance` worksheet of each results file records the evidence codes, the counting mode, the
test, the FDR threshold, the minimum depth, the term-size limits and the sizes of the foreground
and background. It does not record whether either set was expanded, the single-copy filter, the
background type, the maximum number of terms shown, the display threshold or the GOATOOLS version,
so report these in your methods.

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

## Guided install scripts

As an alternative to the Conda commands in the README, two scripts check the prerequisites and
create the `orthogather` environment:

```bash
./installers/install_orthogather_mac.sh      # macOS, needs Conda
bash installers/install_orthogather_wsl.sh   # WSL, needs Micromamba
```

The macOS script builds the environment from `environment.yml`; the WSL script installs the
packages explicitly. The WSL script checks `/proc/version` for a WSL kernel and stops on native
Linux, so on Linux use the Conda commands in the README. Conda can be installed through
[Miniforge](https://github.com/conda-forge/miniforge); Micromamba is a separate program, not part of
Miniforge.

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
| `installers/` | The macOS and Windows installers and the guided install scripts (see [installers/README.md](../installers/README.md)) |
| `docs/` | The installation guide (PDF and HTML) and this page |
| `tests/`, `tools/` | The test suite and maintenance scripts (catalogue building, end-to-end checks, tutorial screenshots) |
| `environment.yml`, `requirements*.txt` | Conda environment and pip requirements |
| `CITATION.cff`, `.zenodo.json` | Citation metadata for GitHub and Zenodo |

## Error codes

Many errors shown by OrthoGather carry a stable code (`ERR_...`), a message and a hint; the rest
are shown as plain messages. The codes are defined in `orthogather/utils/error_catalog.py` (about
65 entries). Backend routes call `respond_error("ERR_CODE", where=..., detail=...)`, and the
frontend shows the response as a notification through `static/js/og-errors.js`. The categories are
`input`, `state`, `data`, `network`, `external`, `not-found` and `system`; the severities are
`error`, `warning` and `info`.

To add an error, add an `ErrorSpec` with a code starting with `ERR_` to `error_catalog.py` and
reference it from the route. `tests/test_error_catalog.py` checks that every code used in `app.py`
exists in the catalogue. Errors that escape the routes are caught by global handlers for 404, 500
and unhandled exceptions, which return JSON for API requests and `templates/error.html` for pages.

When reporting a problem, quote the `ERR_` code in the
[issue](https://github.com/CarlosVivasR/OrthoGather/issues).

## Test suite

The repository has 101 tests covering species matching, taxonomy, the error catalogue, OrthoXML
import, catalogue building, file names and provenance. The enrichment statistics have no automated
test; the worked example in [`example_analysis/`](../example_analysis/) is the reference for
checking them.

```bash
conda activate orthogather
pip install -r requirements-dev.txt   # pytest, selenium, webdriver-manager
pytest tests/ -v
```

`requirements-dev.txt` also installs what `tools/capture_tutorial_screenshots.py` needs to
regenerate the tutorial screenshots with a headless Chrome.
