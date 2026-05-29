"""Tests for provenance version capture.

Covers read_obo_metadata (the GO ontology version header reader) against
temp OBO fixtures. The OrthoFinder version is captured from a live run
banner in app.py and the GO ontology version from the OBO header — both
feed build_provenance() so results are reproducible.
"""
from __future__ import annotations

from orthogather.core.goa import read_obo_metadata, read_goa_header


def _write_obo(path, header_lines):
    path.write_text(
        "\n".join(header_lines)
        + "\n\n[Term]\nid: GO:0008150\nname: biological_process\n"
    )
    return str(path)


def test_read_obo_metadata_parses_versions(tmp_path):
    obo = _write_obo(
        tmp_path / "go-basic.obo",
        ["format-version: 1.2", "data-version: releases/2024-09-08"],
    )
    meta = read_obo_metadata(obo)
    assert meta["data_version"] == "releases/2024-09-08"
    assert meta["format_version"] == "1.2"


def test_read_obo_metadata_missing_header(tmp_path):
    obo = _write_obo(tmp_path / "go-basic.obo", ["format-version: 1.2"])
    meta = read_obo_metadata(obo)
    assert meta["format_version"] == "1.2"
    assert meta["data_version"] is None


def test_read_obo_metadata_missing_file(tmp_path):
    meta = read_obo_metadata(str(tmp_path / "does-not-exist.obo"))
    assert meta == {"data_version": None, "format_version": None}


def test_read_obo_metadata_stops_at_terms(tmp_path):
    # A data-version appearing only *after* a [Term] stanza must not be picked
    # up — the reader scans the header only.
    obo = tmp_path / "go-basic.obo"
    obo.write_text(
        "format-version: 1.2\n\n[Term]\nid: GO:1\ndata-version: bogus\n"
    )
    meta = read_obo_metadata(str(obo))
    assert meta["data_version"] is None


# ---------------------------------------------------------------------------
# read_goa_header — the real EBI data version lives in the .goa file header.
# ---------------------------------------------------------------------------

GOA_HEADER = (
    "!gaf-version: 2.2\n"
    "!generated-by: UniProt\n"
    "!date-generated: 2026-04-30\n"
    "!GO-version: http://purl.obolibrary.org/obo/go/releases/2026-04-27/extensions/go-plus.ofn\n"
    "UniProtKB\tA0A385XJ53\tinsA9\tinvolved_in\tGO:0006313\tGO_REF:0000002\tIEA\t"
    "InterPro:IPR003220\tP\tprotein\ttaxon:83333\t20260428\tInterPro\t\t\n"
)


def test_read_goa_header_parses_version(tmp_path):
    f = tmp_path / "x.goa"
    f.write_text(GOA_HEADER)
    h = read_goa_header(str(f))
    assert h["date_generated"] == "2026-04-30"
    assert h["gaf_version"] == "2.2"
    assert "releases/2026-04-27" in h["go_version"]


def test_read_goa_header_stops_at_first_data_row(tmp_path):
    # A "!"-prefixed line appearing after a data row must not be read.
    f = tmp_path / "x.goa"
    f.write_text(
        "!date-generated: 2026-04-30\n"
        "UniProtKB\tP1\tg\tinvolved_in\tGO:1\tREF\tIEA\tx\tP\tp\ttaxon:1\t1\tX\t\t\n"
        "!date-generated: bogus\n"
    )
    h = read_goa_header(str(f))
    assert h["date_generated"] == "2026-04-30"


def test_read_goa_header_missing_file(tmp_path):
    h = read_goa_header(str(tmp_path / "nope.goa"))
    assert h == {"date_generated": None, "go_version": None, "gaf_version": None}
