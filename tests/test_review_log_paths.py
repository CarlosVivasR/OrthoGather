"""The OrthoFinder log on the page does not show the user's folders (video
review, 29-Oct-2026).

Each line of OrthoFinder's output went to the page as written, so its paths
showed the user's home folder (/Users/<name>/...) in screenshots and videos.
"""
from __future__ import annotations

import io
import os


class _FakeOrthoFinder:
    """Prints a banner and two paths, then fails, so the route stops there."""

    def __init__(self, *args, **kwargs):
        cwd, home = os.getcwd(), os.path.expanduser("~")
        self.stdout = io.StringIO(
            "OrthoFinder version 2.5.5 Copyright (C) 2014 David Emms\n"
            f"Results:\n    {cwd}/Proteomas/OrthoFinder/Results_Oct29/\n"
            f"Log written to {home}/elsewhere/log.txt\n")
        self.returncode = 1

    def wait(self):
        return 1


def test_orthofinder_log_hides_the_home_folder(tmp_path, monkeypatch):
    import app as og
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Proteomas").mkdir()
    (tmp_path / "run_provenance").mkdir()
    (tmp_path / ".orthogather_sessions").mkdir()
    monkeypatch.setattr(og.subprocess, "Popen", _FakeOrthoFinder)
    body = og.app.test_client().get("/stream_orthofinder").get_data(as_text=True)
    home = os.path.expanduser("~")
    assert home not in body
    assert "data: Proteomas/OrthoFinder/Results_Oct29/" in body.replace("    ", "")
    assert "~/elsewhere/log.txt" in body
    # The version is still read from the banner.
    stamp = (tmp_path / "run_provenance" / "orthofinder_provenance.json").read_text()
    assert '"2.5.5"' in stamp
