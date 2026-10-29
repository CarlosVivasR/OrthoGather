"""The run uses the sets the page shows (blind study, 29-Oct-2026).

Ticking "Use all GOA files" emptied the background box; with the box empty the
page validated nothing, kept Run enabled, and the run used the background loaded
before. The page now keeps the box, marks a set as not loaded whenever its box
or options change, and sends what it shows with the run; the server refuses to
run when that is not what it loaded.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_review_nonuniprot_ids import REF, three_species  # noqa: F401  (fixture)

HTML = (Path(__file__).resolve().parent.parent / "templates" / "resultado_goa.html").read_text()


def _fg(ids, expand=False, sc=False):
    return {"uniprot_ids": ids, "use_orthogroups": expand, "single_copy_only": sc}


def _bg(ids, expand=False, sc=False, all_goa=False):
    return {"background_choice": "5" if all_goa else "4", "custom_uniprot_ids": [] if all_goa else ids,
            "use_orthogroups": expand, "single_copy_only": sc}


def _load(c, fg, bg):
    assert c.post("/foreground_analysis", json=fg).status_code == 200
    assert c.post("/background_analysis", json=bg).status_code == 200


def test_run_with_the_loaded_sets(three_species):
    c = three_species
    fg, bg = _fg(REF[:30]), _bg(REF)
    _load(c, fg, bg)
    r = c.post("/gene_ontology_analysis", json={"sets": {"foreground": fg, "background": bg}})
    assert r.status_code == 200, r.get_json()


def test_background_changed_after_loading_is_refused(three_species):
    c = three_species
    fg, bg = _fg(REF[:30]), _bg(REF)
    _load(c, fg, bg)
    # The page now shows "Use all GOA files", but that background was never loaded.
    r = c.post("/gene_ontology_analysis",
               json={"sets": {"foreground": fg, "background": _bg([], all_goa=True)}})
    assert r.status_code == 400
    js = r.get_json()
    assert "background" in js["message"] and "not the one loaded" in js["message"]
    assert "Load background" in js["hint"]


def test_foreground_changed_after_loading_is_refused(three_species):
    c = three_species
    fg, bg = _fg(REF[:30]), _bg(REF)
    _load(c, fg, bg)
    r = c.post("/gene_ontology_analysis",
               json={"sets": {"foreground": _fg(REF[:30], expand=True), "background": bg}})
    assert r.status_code == 400
    assert "foreground" in r.get_json()["message"]


def test_same_sets_written_differently_are_accepted(three_species):
    # The fingerprint is taken on the identifiers as read, not on the raw text.
    c = three_species
    _load(c, _fg(REF[:30]), _bg(REF))
    fg_text = [f">tr|{a}|{a}_SPREF" for a in REF[:30]]
    r = c.post("/gene_ontology_analysis",
               json={"sets": {"foreground": _fg(fg_text, sc=True), "background": _bg(REF)}})
    assert r.status_code == 200, r.get_json()


def test_runs_without_sets_are_not_checked(three_species):
    # Callers of the API that do not send the sets work as before.
    c = three_species
    _load(c, _fg(REF[:30]), _bg(REF))
    assert c.post("/gene_ontology_analysis", json={}).status_code == 200


def test_page_keeps_the_background_box_and_tracks_stale_sets():
    goa = re.search(r'useGOACheck\.addEventListener\("change".*?\}\);', HTML, re.S)
    assert goa and 'bgTextArea.value = ""' not in goa.group(0)
    assert "function markStale(" in HTML
    assert "sets: currentSets()" in HTML
