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
  checks.
- Run `pytest tests/` before opening the pull request.
- Changes that alter scientific output (orthogroups, enrichment statistics or exported values)
  must be stated in the pull request and in [CHANGELOG.md](CHANGELOG.md), with the reason.
- New user-facing errors should use a code from `orthogather/utils/error_catalog.py`; see
  [docs/ADVANCED.md](docs/ADVANCED.md#error-codes).
- Update the README, the installation guide or `docs/ADVANCED.md` when a change affects them.

Releases and installer builds follow the steps in [installers/README.md](installers/README.md).

## Licence

By contributing, you agree that your contributions are released under the GNU General Public
License, version 3 or later, the licence of OrthoGather.
