"""
Tests for the catalogue de-LFS / refresh machinery:

  - ``ensure_catalogue_present`` seeds the raw JSON from the .gz baseline when
    the raw file is missing, and NEVER clobbers an existing (fresher) raw file.
  - ``tools/build_catalogue.py`` parses EBI's proteome2taxid table and refreshes
    ``file_url`` by an exact taxid join (the root-cause fix for stale GOA 404s).
"""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_build_module():
    """Import tools/build_catalogue.py by path (it lives outside the package)."""
    path = REPO_ROOT / "tools" / "build_catalogue.py"
    spec = importlib.util.spec_from_file_location("build_catalogue", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# ensure_catalogue_present
# --------------------------------------------------------------------------- #
def test_ensure_seeds_from_gz_when_missing(tmp_path):
    from orthogather.core.catalogue import ensure_catalogue_present

    json_path = tmp_path / "proteomes_list.json"
    payload = [{"label": "X", "taxon_id": "1", "file_url": "NA"}]
    with gzip.open(str(json_path) + ".gz", "wt") as f:
        json.dump(payload, f)

    assert not json_path.exists()
    ensure_catalogue_present(str(json_path))
    assert json_path.exists()
    assert json.loads(json_path.read_text()) == payload


def test_ensure_does_not_clobber_existing(tmp_path):
    from orthogather.core.catalogue import ensure_catalogue_present

    json_path = tmp_path / "proteomes_list.json"
    fresh = [{"label": "FRESH", "taxon_id": "9", "file_url": "NA"}]
    stale = [{"label": "STALE", "taxon_id": "9", "file_url": "NA"}]
    json_path.write_text(json.dumps(fresh))
    with gzip.open(str(json_path) + ".gz", "wt") as f:
        json.dump(stale, f)

    ensure_catalogue_present(str(json_path))
    # The pre-existing (potentially newer) file must survive untouched.
    assert json.loads(json_path.read_text()) == fresh


def test_ensure_noop_when_nothing_to_seed(tmp_path):
    from orthogather.core.catalogue import ensure_catalogue_present

    json_path = tmp_path / "proteomes_list.json"
    # No .json and no .gz — must not raise; caller handles the missing file.
    ensure_catalogue_present(str(json_path))
    assert not json_path.exists()


# --------------------------------------------------------------------------- #
# build_catalogue: parse + refresh
# --------------------------------------------------------------------------- #
def test_parse_taxid_map_basic():
    mod = _load_build_module()
    text = "\n".join([
        "E. coli\t562\t1.E_coli.goa",
        "Yeast\t559292\t2.S_cerevisiae.goa",
        "dup name\t562\t99.other.goa",   # duplicate taxid → first wins
        "bad line with no tabs",          # malformed → skipped
    ])
    m = mod.parse_taxid_map(text)
    assert m == {"562": "1.E_coli.goa", "559292": "2.S_cerevisiae.goa"}


def test_refresh_join_by_taxid():
    mod = _load_build_module()
    catalogue = [
        {"taxon_id": "562", "file_url": "https://old/STALE.goa"},   # → refreshed
        {"taxon_id": "999", "file_url": "https://old/GONE.goa"},    # → NA (no GOA)
        {"taxon_id": "559292", "file_url": "NA"},                   # → newly resolved
        {"taxon_id": "562", "file_url": mod.GOA_BASE + "1.E_coli.goa"},  # unchanged
    ]
    taxid_map = {"562": "1.E_coli.goa", "559292": "2.S_cerevisiae.goa"}
    stats = mod.refresh(catalogue, taxid_map)

    assert catalogue[0]["file_url"] == mod.GOA_BASE + "1.E_coli.goa"
    assert catalogue[1]["file_url"] == "NA"
    assert catalogue[2]["file_url"] == mod.GOA_BASE + "2.S_cerevisiae.goa"
    assert catalogue[3]["file_url"] == mod.GOA_BASE + "1.E_coli.goa"

    assert stats["total"] == 4
    assert stats["resolved"] == 3          # entries 0, 2, 3
    assert stats["newly_resolved"] == 1    # entry 2 (NA → url)
    assert stats["newly_na"] == 1          # entry 1 (url → NA)
    assert stats["unchanged"] == 1         # entry 3


# --------------------------------------------------------------------------- #
# build_catalogue (full mode): proteome parsing + GOA index parsing
# --------------------------------------------------------------------------- #
def test_parse_proteome_reference_by_membership():
    """type is reference IFF the upid is in the authoritative reference set — NOT
    by substring-matching proteomeType (which mislabels 'Representative proteome')."""
    mod = _load_build_module()
    ref_ids = {"UP000000211"}  # a reference proteome whose proteomeType is "Representative proteome"
    obj_ref = {
        "id": "UP000000211", "proteomeType": "Representative proteome",
        "modified": "2024-01-01", "proteinCount": 1234,
        "taxonomy": {"scientificName": "Some bacterium", "taxonId": 211},
    }
    obj_non = {
        "id": "UP000999999", "proteomeType": "Reference and representative proteome",
        "modified": "2024-02-02", "proteinCount": 10,
        "taxonomy": {"scientificName": "Other org", "taxonId": 999},
    }
    e1 = mod._parse_proteome(obj_ref, ref_ids)
    e2 = mod._parse_proteome(obj_non, ref_ids)
    assert e1["type"] == "reference"        # in set, despite "Representative …" string
    assert e1["label"] == "Some bacterium [UP000000211]"
    assert e1["taxon_id"] == "211"
    assert e1["proteome_version"] == "2024-01-01"
    assert e1["protein_count"] == 1234
    assert e2["type"] == "non-reference"    # not in set, despite "Reference …" string


def test_goa_index_parsing():
    mod = _load_build_module()
    html = (
        '<tr><td><a href="18.E_coli_MG1655.goa">18.E_coli_MG1655.goa</a></td>'
        '<td align="right">2026-04-30 15:28  </td><td align="right">9.3M</td></tr>\n'
        '<tr><td><a href="71242.S_cerevisiae_ATCC_204508.goa">x</a></td>'
        '<td align="right">2026-05-01 02:10  </td><td align="right">23M</td></tr>'
    )
    rows = {fname: (date, size) for fname, date, size in mod._GOA_ROW.findall(html)}
    assert rows["18.E_coli_MG1655.goa"] == ("2026-04-30", "9.3M")
    assert rows["71242.S_cerevisiae_ATCC_204508.goa"] == ("2026-05-01", "23M")
