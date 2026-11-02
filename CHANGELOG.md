# Changelog

Notable changes to OrthoGather. Versions are tagged `vMAJOR.MINOR.PATCH`, and every release since
1.1.1 is archived on Zenodo (all versions:
[10.5281/zenodo.18510910](https://doi.org/10.5281/zenodo.18510910)).

## 2.2.1 (2026-11-02)

A maintenance release. The worked example and every analysis of proteomes with UniProt accessions give
the same results as in 2.2.0 (checked on 66 analyses in every counting, expansion, background and
evidence setting); the statistical method is unchanged.

### Highlights
- **Proteomes from any source.** Expansion and per-orthogroup counting read bare identifiers (UniParc
  `UPI…`, a lab's own FASTA) and the identifier forms of NCBI (`gnl|…`, `gi|…`), JGI and PDB headers.
  Identifiers shared by several strains or proteomes are handled consistently and reported.
- **Results you can trace.** For each term, the results Excel lists its proteins or orthogroups, which
  pasted identifiers carry the term themselves and which through their orthologues, and whether it is
  significant. The Provenance sheet adds fingerprints of the pasted lists and of the GOA files, the
  run's warnings, and the identifiers that did not enter the test, each with its reason.
- **Clearer evidence.** The evidence chips count the proteins behind each term, including their
  annotations to more specific terms.

### Improved
- Each run is tied to the sets and the analysis on screen: a set changed after loading, sets loaded
  before a new GOA download, or GO tables built for another analysis ask to be loaded again. After
  updating, download the GOA files once more for an open analysis.
- Very large orthogroups (more than about 1,200 proteins of one species) are read in full.
- Species matching uses the proteome each species came from, compares whole words and reads
  "Candidatus" names by their binomial; the match table shows the proteome ID.
- External Uploads, the Preselected Dataset and History runs show their own provenance.
- Moving between the Protein Analysis and Gene Ontology views keeps an uploaded analysis.
- Notes on what expanding only the foreground does, on why no term is significant per orthogroup, and
  on identifiers in more than one proteome or orthogroup; a line above Run says what the run will use.
- Figure 2 counts proteomes and species; the UpSet filter summary reads as one sentence; the
  OrthoFinder log shows paths relative to the application.
- Error codes for every message of the Gene Ontology page.
- The table's CSV/TSV export adds the raw and hypergeometric p-values and the significance flag.
- Application data (taxonomy cache, run records) is kept out of the installation and proteome folders.
- `tools/build_catalogue.py` follows the proteome type names that UniProt uses since release 2026_03
  for full rebuilds of the catalogue (the numbers 1, 2 and 4 still work).

### Validation and documentation
- `docs/validation/independent_check.py` recomputes the enrichment statistics without GOATOOLS or the
  application's code: identical in every setting tested.
- `docs/validation/sensitivity_example.py` runs the worked example under each analysis setting (Table
  S6 of Supplementary File S1), with seeds 1–50 for the per-orthogroup rows.
- The hidden-annotation benchmark draws its 40 *E. coli* processes in a fixed order, so every run
  regenerates the same figures: 27 of 40 recovered with the exact term, 37 and 35 (pure and
  diluted) counting close relatives.
- `expansion_benchmark.py donors` repeats the benchmark with the donors' annotations restricted by
  kind: 27, 27, 24, 19 (Non-IEA setting) and 1 (Experimental only) of 40.
- `docs/validation/clusterprofiler_check.R` tests the worked example with clusterProfiler on the same
  data: the 21 and the 1 terms are returned.
- Validation README: what recovery through orthologues depends on, how the order of a pasted
  background can move terms close to the threshold, and the scope of each check.
- `example_analysis/README.md`: how the example's foreground and background were built from the
  supplementary workbook of Giddey et al. 2017.
- The note after an OrthoXML upload, the README and the tutorial say that non-UniProt identifiers get
  annotation only through orthologues that have UniProt accessions.

### Removed
- Unused code, routes and files, and the guided Conda scripts (the installers and the README cover
  them).

## 2.2.0 (2026-10-22)

Recommended for every installation: the dependencies are now pinned, including statsmodels 0.14.6,
which GOATOOLS 1.6.4 requires. The worked example gives the same results as 2.1.0 (21 and 1 enriched
terms, same q-values); per-orthogroup and "Use all GOA files" analyses differ from 2.1.x.

### Highlights
- **Per-orthogroup counting with permutation p-values** that allow for family size; proteins in no
  orthogroup count as units of their own, and expanded sets are always counted per orthogroup.
- **Non-reference proteomes** are downloaded from UniParc, as UniProtKB no longer distributes them;
  their size is checked against UniProt and their source recorded.
- **"Use all GOA files"** takes the proteome of the foreground's species, and counted per orthogroup it
  works for a species without a GOA file.
- **Pasted lists** accept FASTA headers and sequences, lower-case accessions and isoforms, and the
  results list every identifier that did not enter the test, with its reason.
- **Validation** (`docs/validation/`): scripts and data that reproduce the worked example (35 values)
  and test random foregrounds, a species with hidden annotations and 1,296 combinations of settings;
  GitHub Actions runs the tests and the example on Linux and macOS.

### Improved
- "Single-copy only" reads the active analysis, reports when no single-copy orthogroup remains, and
  asks to load the sets again when it is changed afterwards.
- OrthoFinder runs that fail or end incomplete are reported and not saved; a missing installation
  gives a clear message.
- Per-orthogroup counting limits the population to the orthogroups of the measured proteins.
- OrthoXML uploads without UniProt accessions get a note.
- Coverage banner, run summary and error messages; the Provenance sheet also records the expansion,
  the orthogroup filter, the display threshold, the maximum number of terms and the GOATOOLS version.
- The installers install the latest published release, and the Windows updater brings the Conda
  environment to its versions.

### Documentation
- README, `docs/ADVANCED.md`, the tutorial and the Gene Ontology page describe per-orthogroup counting
  and expansion; README memory figures; the home page counts taxa with a GO annotation file.

## 2.1.1 (2026-10-18)

Not released on its own; its changes are part of 2.2.0. Text and documentation corrections; the analyses are unchanged and give the same results as
2.1.0.

### Changed
- In-app tutorial brought in line with the application and the paper: the test is one-sided;
  orthogroup expansion counts the annotations of all members and transfers none; the evidence
  preset is called Non-IEA, with the codes it keeps; the Preselected Dataset is 47 proteomes from
  35 species; the History actions are described as they work; the citation shows the current
  title.
- Gene Ontology page: the background help recommends the proteins detected in the experiment,
  and the Non-IEA description lists what it leaves out.
- Home page: the Preselected Dataset card says 47 proteomes from 35 species.

### Fixed
- The home page links "Read the docs", "Cite OrthoGather" and "Get help" now open the README,
  the citation section of the tutorial and the issue tracker.
- Citation export (BibTeX and RIS): current title of the paper, full author names, and an author
  list in BibTeX format.
- Provenance sheet of the enrichment results: the aspects are labelled BP, CC and MF.

### Documentation
- README rewritten: installation routes and requirements, the worked example with its UniProt
  proteome IDs, citation of the preprint, licence and third-party components.
- One installation guide, `docs/INSTALL.html` and `docs/Installation_guide.pdf`, replaces the
  earlier guides; it adds update, uninstall and troubleshooting instructions.
- `docs/ADVANCED.md` describes the enrichment test settings, thread settings, repository layout,
  error codes and tests.
- `CITATION.cff` gives the preprint as the preferred citation, and `.zenodo.json` links to it.
- `CONTRIBUTING.md`, `THIRD_PARTY_LICENSES.md` and this changelog added.

## 2.1.0 (2026-09-14)

Version described in the preprint (Zenodo: [10.5281/zenodo.22738813](https://doi.org/10.5281/zenodo.22738813)).

### Changed
- Gene Ontology enrichment: the foreground and the background are both restricted to the
  annotated background, so the two sides of the test are symmetric, and the annotated and
  submitted counts are both reported.
- One-sided Fisher's exact test for over-representation, replacing the two-sided GOATOOLS default.
- Annotations are propagated through `is_a` and `part_of`, and annotations with the `NOT`
  qualifier are discarded.
- Terms annotated to fewer than 10 or more than 500 background proteins are excluded before the
  Benjamini–Hochberg correction.
- A display threshold separate from the significance threshold: terms just above it are shown as
  hollow bars and not reported as findings.
- Gene Ontology updated to release 2026-07-26.
- Evidence preset "Curated" renamed "Non-IEA" (the codes it keeps are listed in
  `docs/ADVANCED.md`).

### Added
- `example_analysis/`: the complete worked example from the paper, with inputs, every export and
  provenance records.

### Installers
- Distributed as zip files, which browsers and antivirus software block less often than scripts.
- The Windows installer checks that virtualisation is available, resumes after the restart,
  retries failed downloads and writes a log to `%LOCALAPPDATA%\OrthoGather\install-log.txt`; its
  logic is tested on Windows in GitHub Actions.
- The launchers reopen a running instance instead of starting a second one, and fall back to the
  next free port when port 5000 is taken.

### Fixed
- Species count in export file names.

## 2.0.0 (2026-06-03)

### Added
- Installers for macOS and Windows that need no typed commands; on Windows, OrthoGather runs in WSL.
- Automatic updates of the proteome catalogue from GitHub releases.

### Changed
- Python 3.11 with OrthoFinder 2.5.5, running natively on Apple Silicon (Rosetta no longer needed).
- UniProt proteome catalogue refreshed: 1,013,422 proteomes from 161,743 species (UniProt release
  2026_01), with EBI GOA links and version stamps.
- The catalogue is distributed compressed (about 20 MB) and unpacked on first launch, so Git LFS
  is no longer needed.
- Faster species search; unused dependencies removed.

The proteome catalogue snapshot of 2026-06-03 was published as a separate release
(`catalogue-2026-06-03`); it contains data only.

## 1.1.2 (2026-02-25, tag `v.1.1.2`)

### Added
- Reproducible worked example (`example_analysis/`) with its input dataset, outputs and README.

### Changed
- Minor documentation updates.

## 1.1.1 (2026-02-10)

### Added
- `CITATION.cff` with authorship and citation information.

### Changed
- Code improvements.

## 1.0.1 (2026-02-08)

Maintenance release.

## 1.0.0 (2026-02-06)

First public release.
