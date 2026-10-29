"""The summary of the UpSet filter reads as one sentence (video review,
29-Oct-2026).

The result banner is a flex column, so the loose icon, bold counts and text of
its first sentence each became a line: "468 of 491" / "UniProt IDs found ·" /
"431" / ...
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "templates" / "resultado.html").read_text()
CSS = (ROOT / "static" / "css" / "pages" / "results.css").read_text()


def test_summary_sentences_are_one_block_each():
    summary = HTML[HTML.index("// Build the result banner"):HTML.index("const inputNotes")]
    assert "let html = '<div class=\"upset-filter-summary\">" in summary
    assert "orthogroups in the filtered figures</div>'" in summary
    partial = HTML[HTML.index("let banner = "):HTML.index("if (fallback.length)")]
    assert "<div class=\"upset-filter-summary\">" in partial and "</div>" in partial


def test_unassigned_block_has_a_style():
    assert re.search(r"\.upset-unassigned\s*\{", CSS)
