"""
Tests for the unified error catalog.

Covers:
  - Every entry validates (codes start with ERR_, valid categories/severities,
    sensible HTTP codes).
  - Every error code referenced from app.py exists in the catalog (so we never
    ship a respond_error("ERR_TYPO") at runtime).
  - lookup() returns the ERR_UNEXPECTED fallback for unknown codes.
  - respond_error() builds the expected JSON shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from orthogather.utils.error_catalog import (
    ERRORS, ErrorSpec, VALID_CATEGORIES, VALID_SEVERITIES, lookup,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCatalogShape:
    def test_at_least_50_errors(self):
        """We catalogued ~58. Guard against accidental deletions."""
        assert len(ERRORS) >= 50

    def test_every_code_starts_with_err(self):
        for code in ERRORS:
            assert code.startswith("ERR_"), f"Code {code!r} must start with ERR_"

    def test_every_entry_is_an_errorspec(self):
        for code, entry in ERRORS.items():
            assert isinstance(entry, ErrorSpec), f"{code} is not an ErrorSpec"

    def test_categories_are_valid(self):
        for code, entry in ERRORS.items():
            assert entry.category in VALID_CATEGORIES, (
                f"{code}: category {entry.category!r} not in {VALID_CATEGORIES!r}"
            )

    def test_severities_are_valid(self):
        for code, entry in ERRORS.items():
            assert entry.severity in VALID_SEVERITIES, (
                f"{code}: severity {entry.severity!r} not in {VALID_SEVERITIES!r}"
            )

    def test_http_codes_are_sane(self):
        for code, entry in ERRORS.items():
            assert 100 <= entry.http_code <= 599, (
                f"{code}: http_code {entry.http_code} out of HTTP range"
            )

    def test_message_and_hint_present(self):
        for code, entry in ERRORS.items():
            assert entry.message.strip(), f"{code}: empty message"
            assert entry.hint.strip(),    f"{code}: empty hint"

    def test_hints_are_actionable(self):
        """A hint should not just say 'try again' — it should be specific."""
        for code, entry in ERRORS.items():
            lower = entry.hint.lower()
            assert lower != "try again.", (
                f"{code}: hint must be more specific than 'try again'"
            )


class TestLookup:
    def test_known_code_returns_spec(self):
        spec = lookup("ERR_NO_UNIPROT_IDS")
        assert spec.message == "No UniProt IDs provided"
        assert spec.category == "input"

    def test_unknown_code_returns_unexpected(self):
        spec = lookup("ERR_THIS_DOES_NOT_EXIST_X42")
        assert spec is ERRORS["ERR_UNEXPECTED"]

    def test_empty_code_returns_unexpected(self):
        spec = lookup("")
        assert spec is ERRORS["ERR_UNEXPECTED"]


class TestAppPyReferences:
    """Every ERR_* code referenced from app.py must exist in the catalog.

    This is the key test that keeps the catalog and the code in sync: if
    someone calls respond_error("ERR_TYPO"), this test fails immediately.
    """

    @pytest.fixture(scope="class")
    def referenced_codes(self):
        text = (REPO_ROOT / "app.py").read_text()
        # Pull every ERR_xxx_yyy reference (uppercase + underscores + digits)
        pattern = re.compile(r"\bERR_[A-Z][A-Z0-9_]+\b")
        return set(pattern.findall(text))

    def test_every_reference_is_in_catalog(self, referenced_codes):
        missing = [c for c in referenced_codes if c not in ERRORS]
        # Allow only catalog-internal codes that we *intentionally* dont define
        # (none right now)
        assert not missing, (
            f"app.py references error codes that are NOT in the catalog: "
            f"{sorted(missing)!r}. Add them to orthogather/utils/error_catalog.py."
        )


class TestRespondError:
    """End-to-end shape of respond_error()'s JSON output."""

    def test_returns_flask_response_and_status(self, monkeypatch):
        # We need a Flask app context to call jsonify()
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            from orthogather.utils.responses import respond_error
            resp, status = respond_error("ERR_NO_UNIPROT_IDS")
            assert status == 400
            data = resp.get_json()
            assert data["success"] is False
            assert data["error_code"] == "ERR_NO_UNIPROT_IDS"
            assert data["category"] == "input"
            assert data["severity"] == "error"
            assert "Paste at least one UniProt accession" in data["hint"]

    def test_detail_is_appended(self):
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            from orthogather.utils.responses import respond_error
            resp, _ = respond_error("ERR_LOAD_ANALYSIS_FAILED", detail="bad zip")
            data = resp.get_json()
            assert ": bad zip" in data["message"]

    def test_http_code_override(self):
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            from orthogather.utils.responses import respond_error
            resp, status = respond_error("ERR_NO_UNIPROT_IDS", http_code=422)
            assert status == 422

    def test_unknown_code_falls_back_to_unexpected(self):
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            from orthogather.utils.responses import respond_error
            resp, status = respond_error("ERR_NONEXISTENT_AT_ALL")
            data = resp.get_json()
            assert data["error_code"] == "ERR_NONEXISTENT_AT_ALL"
            # The fallback ERR_UNEXPECTED spec is used for the message/hint
            assert "unexpected error" in data["message"].lower()
            assert status == 500
