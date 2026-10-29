# Changelog

Notable changes to OrthoGather. Versions are tagged `vMAJOR.MINOR.PATCH`, and every release since
1.1.1 is archived on Zenodo (all versions:
[10.5281/zenodo.18510910](https://doi.org/10.5281/zenodo.18510910)).

## 2.2.1 (not released yet)

Fixes from the blind study of 2.2.0 (October 2026). An analysis of proteomes with UniProt accessions
gives exactly the same results as in 2.2.0: the worked example still gives 21 and 1 enriched terms
with the GOA files of July 2026 (23 and 1 with those of October), and 66 analyses of the example and
of the study's *Bacillus subtilis* data, in every counting, expansion, background and evidence
setting, return the same terms, counts, p- and q-values. No part of the statistical method changes.

### Fixed
- Expansion with identifiers that are not UniProt accessions: proteomes from UniParc or from a lab's
  own FASTA have bare identifiers in the orthogroups (`UPI…`, `IS27_00398`), and the expansion only
  read `db|ACC|NAME` cells, so it found no orthogroup and the run stopped at "Foreground missing".
  It now reads both forms, as per-orthogroup counting and the UpSet plots already did.
- An expansion that finds no orthogroup is an error that names the identifiers, not a success.
  Loading a foreground or background replaces it, so after a failed load the server holds none, and
  "Foreground missing" and "Background missing" give the reason of the failed load.
- The GO page runs only with the sets it shows. Ticking "Use all GOA files" no longer empties the
  background box; changing a box or an option marks that set as not loaded and disables Run until it
  is loaded again; and the server refuses a run whose sets are not the ones it loaded.
- The counting no longer switches back to "Per protein" on its own when expansion is removed, and a
  line above Run says what the run will use.
- Provenance: an External Upload or the Preselected Dataset no longer shows the UniProt release and
  OrthoFinder version of the last New Analysis; the history snapshot of a New Analysis records that
  analysis, not the one open while it ran; and a run opened from the history shows its own
  provenance (or "not recorded for this run" when 2.2.0 saved another run's).
- Species matching on the GO page uses the proteome each species was downloaded from when the
  analysis knows it, and compares names as whole words: "IS27" is no longer matched to "Influenza A
  virus (A/Memphis/27/1983)". The table shows the proteome ID of each match. The 47 species of the
  Preselected Dataset match as before.
- The lineage cache of the taxonomic tree is kept in `~/.orthogather/`; the copy bundled in
  `static/Proteomes_json/` is read but no longer modified.
- The provenance stamps of a New Analysis are kept in `run_provenance/`, out of `Proteomas/`, which
  OrthoFinder reads: every run warned that `proteome_provenance.json` "is not a FASTA file".
- The OrthoFinder log on the page no longer shows the user's folders: paths inside the
  application's folder are relative and the home folder is `~`.
- The Data provenance panel of the GO page is refreshed when the GOA download finishes, instead of
  saying "not downloaded" until the page is reloaded.
- Figure 2 counts proteomes, and says how many species they are: the Preselected Dataset has 47
  proteomes of 35 species, not "47 species".
- The summary of the UpSet filter reads as one sentence instead of one line per piece.

### Added
- The results Excel lists the proteins (or orthogroups, and the pasted identifiers behind each) of
  every term, in new columns after the existing ones.
- Error codes (`ERR_…`) for every error of the Gene Ontology page.
- Provenance: the smallest q a per-orthogroup run can reach (the floor set by the number of
  permutations, explained in `docs/ADVANCED.md`), and the SHA-256 of each GOA file. Each history run
  keeps the fingerprint of the GOA files used with it, and the page says when a new download differs.

### Removed
- Code and files nothing used: the legacy `/download` and `/download_upset_data` routes (the
  application uses `/stream_download` and `/download_figure_data`), three unused helpers in
  `app.py`, the empty `orthogather/routes` package, 29 error-catalogue entries that were never
  raised (some with outdated hints; a test now checks that every entry is used), an unused image
  and two outdated end-to-end scripts in `tools/`.
- The guided Conda scripts (`installers/install_orthogather_mac.sh`,
  `installers/install_orthogather_wsl.sh`) and the Conda launchers (`installers/start_orthogather.sh`,
  `installers/Start_Orthogather.command`): they repeated what the installers and the Conda
  commands of the README and the installation guide do.

## 2.2.0 (2026-10-22)

Fixes from the October 2026 audit and review. The default analysis (per-protein counting against a
pasted background, as in the paper) gives exactly the same results as 2.1.0 and 2.1.1: the worked
example still gives 21 and 1 enriched terms with the same q-values. A fresh installation of 2.1.x
picked up statsmodels 0.15, with which every GO enrichment fails; update to this version.

### Fixed
- Proteome download: proteomes other than reference proteomes are no longer in UniProtKB, so their
  download came back empty. They are now downloaded from UniParc, with UniParc identifiers; the
  download log says so, the number of sequences is checked against UniProt's count, and the
  provenance file records where each proteome came from. Such proteomes join the orthogroups but have
  no GO annotation, and the GOA table no longer offers them the file of another proteome of their taxon.
- Per-orthogroup counting: an orthogroup is in the foreground when it contains a foreground
  protein, so large families came out enriched by chance (77% of random foregrounds in a
  simulation). Its p-values now come from a permutation test that shuffles the foreground among the
  background proteins (`p_hypergeom` keeps the statistic), and proteins in no orthogroup count as
  units of their own instead of being dropped. Identifiers are read from both `db|ACC|NAME` and bare
  FASTA headers.
- "Use all GOA files": the universe is the annotated proteome of the species the foreground comes
  from, not of every species with a GOA file; pooling species made any function commoner in the
  foreground's species look enriched (42.5% of random foregrounds). The provenance sheet records
  the background used.
- "Single-copy only" removed every orthogroup: it looked for the single-copy list in a folder that
  was never set. It now reads the active analysis (OrthoFinder's list, or the gene counts), and an
  expansion that leaves no single-copy orthogroup is reported instead of returning an empty set.
- OrthoFinder: a run that fails, or whose output is incomplete, is reported as failed and is not
  saved; results left by an earlier attempt are removed before each run, so they can no longer be
  taken for the new one. A missing OrthoFinder installation gives a clear message.
- Pasted identifiers: the foreground, the background and the UniProt filter of Figures 5 and 6
  read FASTA headers, with or without their sequences, as the Gene Ontology page said they did;
  lower-case accessions are converted to upper case and isoform suffixes are removed with a
  warning. All of these used to be dropped in silence. The results list every pasted foreground
  identifier that did not enter the test with the reason (not found, not in the background, no GO
  annotation, left out by the expansion), and the coverage note no longer advises expanding to
  orthogroups.
- Expanded sets are always counted per orthogroup. Counted per protein, every paralogue of a family
  was a separate observation, and random foregrounds gave a significant term every time; the
  "Per protein" option is disabled while either set is expanded, and the results say why.
- "Use all GOA files" counted per orthogroup is the whole proteome of the foreground's species in
  the analysis, each protein taking part through its orthogroup, with the annotations of every GOA
  file: the same as pasting that proteome as the background and expanding it. It now works for a
  species without a GOA file (it used to fall back to per-protein counting).
- Per-orthogroup counting: the population is limited to the orthogroups of the measured proteins;
  orthogroups that no measured protein belongs to inflated the population counts.
- OrthoXML: when most identifiers in an uploaded file are not UniProt accessions (OMA, OrthoDB and
  Ensembl write their own), the results page says that GO enrichment and the protein filter will
  not find them.
- Clearer messages when nothing can be tested: a species without a GOA file, or a background
  without annotations, now points to per-orthogroup counting or expansion.
- Gene Ontology page, per-orthogroup counting: the coverage banner showed the proteins of the
  expanded sets, and for a species without a GOA file it read "0% of your foreground ... with GO
  annotations" while the test ran on most of it. It now shows the pasted proteins that entered the
  test and the orthogroups they were counted as.
- The run summary keeps the number of significant terms when notes or warnings are shown, and a run
  that fails hides the results of the previous one instead of leaving them on screen.
- "Single-copy only" acts when an expanded set is loaded; changed afterwards, it was ignored without
  a word. The run now asks to load the sets again, and the option is available only while a set is
  expanded.
- A foreground or background that cannot be loaded shows the reason (for example, that none of its
  orthogroups is single-copy) instead of "Error saving Foreground".
- Per-orthogroup counting: the evidence codes shown for a term count the annotated background
  proteins of its orthogroups (they counted every member, and missed proteins in no orthogroup).
- The `Provenance` sheet of the results file also records whether each set was expanded, the
  orthogroup filter, the display threshold, the maximum number of terms and the GOATOOLS version.
- `installers/install_orthogather_wsl.sh` installs from `environment.yml`; it installed unpinned
  packages.
- The installers, and the Windows updater, install the latest published release instead of the
  tip of the `main` branch, so every installation is a tested version archived on Zenodo. The
  Windows updater also brings the Conda environment to that release's versions.
- Installation: GOATOOLS 1.6.4 fails with statsmodels 0.15, which a new installation picked up,
  so every GO enrichment of a fresh installation stopped with an error. The dependencies in
  `environment.yml` and `requirements.txt` are now pinned to the versions the tests and the worked
  example were verified with, statsmodels 0.14.6 included; the pinned environment installs on
  macOS (Apple silicon and Intel) and Linux.

### Documentation
- README: the example's peak memory is about 1.7 GB, of which about 1.1 GB is the application's
  baseline (it said about 1 GB).
- README, `docs/ADVANCED.md`, the tutorial and the Gene Ontology page describe per-orthogroup
  counting, expansion and "Use all GOA files" as they now work: expanding the foreground tests the
  pasted proteins through their orthogroups, and expanding the background is what brings in the
  annotations of orthologues.
- Tutorial: the annotation overview counts proteins with a GO term (it described the earlier
  species-level estimate), and the list of outgoing connections includes the taxonomy lookup, the
  catalogue update check and the plotting libraries.
- Home page: 28,475 is the number of taxa with a GO annotation file (it said species). The species
  picker says that a non-reference proteome has no GO annotation.

### Validation
- `docs/validation/`: scripts and results that check the statistics on data where the answer is
  known, with every input in the repository (the GOA files of the worked example are included):
  the 35 numbers of the worked example, random foregrounds for every setting, a species with its
  annotations hidden (35 of 40 *E. coli* processes recovered through orthologues), and every
  combination of the Gene Ontology settings (1,296, no failure).
- GitHub Actions runs the test suite and the worked-example check on Linux and macOS on every change.

### Tests
- `tests/test_enrichment_safeguards.py`: calibration and power of the per-orthogroup permutation
  test, identifier parsing, GOA files per species, single-copy orthogroups and OrthoFinder failures.
- `tests/test_review_input_ids.py`: reading pasted identifiers and FASTA text, and the reason
  reported for each foreground identifier that is not tested.
- `tests/test_review_expansion_counting.py`: expanded sets counted per orthogroup, and "Use all
  GOA files" equal to the expanded proteome, with and without a GOA file.
- `tests/test_review_orthoxml_ids.py`: the note for OrthoXML files without UniProt accessions.
- `tests/test_review_final_screen.py`: the per-orthogroup banner, the orthogroup filter changed after
  loading, and the per-orthogroup evidence breakdown.
- `tests/test_go_combinations.py`: 144 combinations of the Gene Ontology settings through the real
  routes, each checked against the rules every analysis must meet (the full 1,296 with
  `OG_FULL_MATRIX=1`).

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
