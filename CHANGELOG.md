# Changelog

Notable changes to OrthoGather. Versions are tagged `vMAJOR.MINOR.PATCH`, and every release since
1.1.1 is archived on Zenodo (all versions:
[10.5281/zenodo.18510910](https://doi.org/10.5281/zenodo.18510910)).

## 2.1.1 (2026-10-18)

Text and documentation corrections; the analyses are unchanged and give the same results as
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
- Gene Ontology enrichment corrected. The foreground and the background are both restricted to
  the annotated background, so the two sides of the test are symmetric, and the annotated and
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
