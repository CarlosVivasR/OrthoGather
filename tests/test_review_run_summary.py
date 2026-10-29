"""The GO page does not change the counting on its own, and says what the run
will use before it runs (blind study, 29-Oct-2026).

Loading a set without expansion after an expanded one switched "Per
orthogroup" back to "Per protein" without a word, and the user only learnt it
from the results.
"""
from __future__ import annotations

import re
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "templates" / "resultado_goa.html").read_text()


def _function(name):
    m = re.search(rf"function {name}\(\) \{{.*?\n      \}}\n", HTML, re.S)
    assert m, name
    return m.group(0)


def test_unexpanding_keeps_the_counting_that_is_ticked():
    body = _function("updateCountingWarning")
    # Expansion still forces per orthogroup, as the server does...
    assert "perOrthogroup.checked = true;" in body
    # ...but nothing ticks "Per protein" back when the expansion goes.
    assert "perProtein.checked = true" not in body
    assert "countingBeforeExpansion" not in HTML


def test_the_page_states_the_effective_settings_before_running():
    assert re.search(r'<p id="go-run-summary"[^>]*aria-live="polite"', HTML)
    body = _function("updateRunSummary")
    assert "Will run:" in body
    for what in ("counting", "evidence", "foreground", "background"):
        assert what in body
    # Refreshed whenever a set or a setting changes.
    assert "updateRunSummary();" in _function("updateRunState")
    assert "updateRunSummary();" in _function("updateCountingWarning")
