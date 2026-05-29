"""
Unit tests for orthogather.utils.filenames.descriptive_filename.
"""
import datetime

import pytest

from orthogather.utils.filenames import descriptive_filename


class TestDescriptiveFilename:
    def test_minimal(self):
        out = descriptive_filename("foo", "png", date="2026-05-26")
        assert out == "orthogather_foo_2026-05-26.png"

    def test_with_context(self):
        out = descriptive_filename("GOenrichment-chart", "png",
                                    context=["47species", "evidence-all"],
                                    date="2026-05-26")
        assert out == "orthogather_GOenrichment-chart_47species_evidence-all_2026-05-26.png"

    def test_skips_empty_context_entries(self):
        out = descriptive_filename("foo", "csv", context=["", None, "5species"],
                                    date="2026-05-26")
        assert out == "orthogather_foo_5species_2026-05-26.csv"

    def test_sanitises_unsafe_characters(self):
        # Slashes and exclamations are not allowed in filenames; underscores OK
        out = descriptive_filename("weird/name with!@", "csv", date="2026-05-26")
        assert "/" not in out
        assert "!" not in out
        assert "@" not in out
        assert out.endswith(".csv")
        assert out.startswith("orthogather_")

    def test_default_date_is_today(self):
        out = descriptive_filename("foo", "png")
        today = datetime.date.today().isoformat()
        assert today in out

    def test_keeps_dots_dashes_underscores_in_artifact(self):
        out = descriptive_filename("figure1.protein-distribution_v2", "csv",
                                    date="2026-05-26")
        # dots and dashes preserved, no double underscores
        assert "figure1.protein-distribution_v2" in out

    def test_extension_sanitised(self):
        # Even a malicious ext like "png; rm -rf /" gets sanitised
        out = descriptive_filename("foo", "png; rm -rf /", date="2026-05-26")
        assert out.startswith("orthogather_foo_2026-05-26.")
        # only safe chars in the extension
        ext = out.rsplit(".", 1)[1]
        assert all(c.isalnum() or c in "_-." for c in ext)
