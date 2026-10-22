# Contributing to OrthoGather

OrthoGather is maintained by its authors at University College Dublin. Bug reports, questions and
suggestions are welcome through the
[issue tracker](https://github.com/CarlosVivasR/OrthoGather/issues).

## Reporting a problem

Use the **Bug report** form. The most useful details are:

- the OrthoGather version, shown in the sidebar of the application;
- your operating system and how you installed OrthoGather (macOS installer, Windows installer or
  Conda);
- the error code, if the message starts with `ERR_` (the codes are listed in
  `orthogather/utils/error_catalog.py`);
- what you did, what you expected and what happened instead;
- the provenance file of the analysis (`provenance.txt`, downloadable from the results pages),
  if the problem concerns a result;
- on Windows, the installer log in `%LOCALAPPDATA%\OrthoGather\install-log.txt` if installation
  failed.

The [installation guide](docs/Installation_guide.pdf) has a troubleshooting section that covers the
most common installation problems.

## Suggesting a feature

Use the **Feature request** form and describe the analysis or workflow the feature would make
possible.

## Working on the code

```bash
git clone https://github.com/CarlosVivasR/OrthoGather.git
cd OrthoGather
conda env create -f environment.yml
conda activate orthogather
pip install -r requirements-dev.txt
pytest tests/
python app.py
```

- Work on a branch and open a pull request against `main`; the pull-request template lists the
  checks. `main` is the development version; users install published releases (see below).
- Run `pytest tests/` before opening the pull request. GitHub Actions runs the same tests on Linux
  and macOS, in the pinned environment of `environment.yml`, on every push and pull request,
  together with `python docs/validation/verify_example.py`, which must report 35/35: the numbers
  of the worked example that the paper quotes.
- Changes to the Gene Ontology analysis should also pass the full combinations matrix
  (`OG_FULL_MATRIX=1 pytest tests/test_go_combinations.py`, about 8 minutes); the other checks of
  the statistics are described in [docs/validation/](docs/validation/).
- Changes that alter scientific output (orthogroups, enrichment statistics or exported values)
  must be stated in the pull request and in [CHANGELOG.md](CHANGELOG.md), with the reason, and
  must not change the worked example unless that is the point of the change.
- Add new changes under an `## Unreleased` heading at the top of the CHANGELOG.
- To change a dependency, update both `environment.yml` and `requirements.txt`, with exact
  versions, and check that the tests and the worked example still pass.
- New user-facing errors should use a code from `orthogather/utils/error_catalog.py`; see
  [docs/ADVANCED.md](docs/ADVANCED.md#error-codes).
- Update the README, the installation guide or `docs/ADVANCED.md` when a change affects them.

Releases follow `vMAJOR.MINOR.PATCH`: a patch for corrections that leave results unchanged, a minor
version for new features or corrected results, a major version for incompatible changes. The steps
(version numbers, tag, installer zips, GitHub release and Zenodo) are in
[installers/README.md](installers/README.md#releasing).

## Licence

By contributing, you agree that your contributions are released under the GNU General Public
License, version 3 or later, the licence of OrthoGather.
