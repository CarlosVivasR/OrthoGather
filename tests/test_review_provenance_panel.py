"""The Data provenance panel of the GO page follows the GOA download (video
review, 29-Oct-2026).

The panel was rendered with the page and nothing refreshed it, so after
"Download GOA files" it still said "not downloaded in this analysis" until the
page was reloaded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tests.test_review_nonuniprot_ids import three_species  # noqa: F401  (fixture)

HTML = (Path(__file__).resolve().parent.parent / "templates" / "resultado_goa.html").read_text()


def test_panel_route_renders_the_current_provenance(three_species):
    c = three_species
    before = c.get("/provenance_panel").get_data(as_text=True)
    assert 'class="provenance"' in before and "not downloaded in this analysis" in before
    with c.session_transaction() as s:
        folder = s["folder_path"]
    with open(f"{folder}/goa_provenance.json", "w") as f:
        json.dump({"downloaded_at": "2026-10-29T20:00:00+00:00", "n_files": 1,
                   "data_generated": "2026-10-11"}, f)
    after = c.get("/provenance_panel").get_data(as_text=True)
    assert "not downloaded in this analysis" not in after and "2026-10-11" in after


def test_page_refreshes_the_panel_after_the_download():
    assert "function refreshProvenancePanel(" in HTML
    done = HTML[HTML.index('if (!finalEvent || !finalEvent.success)'):]
    assert re.search(r"refreshProvenancePanel\(\)", done[:3000])
