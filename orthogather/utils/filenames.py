"""
Descriptive filenames for every download OrthoGather offers.

The naming convention:

    orthogather_<artifact>_<context>_<YYYY-MM-DD>.<ext>

Where:
  - artifact = what's in the file ("GOenrichment-chart", "figure3-upset-OGs", ...)
  - context  = the things that change between runs and matter to the user
               when they have several files on disk (species count, namespace
               filter, evidence preset, etc.). Joined with underscores.
  - date     = ISO date (YYYY-MM-DD) so files sort naturally and the user
               doesn't have to wonder when a download came out of OrthoGather.
  - ext      = png, svg, csv, tsv, json, xlsx, ...

Empty/None context parts are skipped. The helper sanitises slashes and
whitespace so it's safe to hand directly to a Content-Disposition header.
"""
from __future__ import annotations

import datetime
import re
from typing import Iterable, Optional


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(s: str) -> str:
    """Lowercase + ASCII-safe slug. Keeps dots / underscores / dashes."""
    if not s:
        return ""
    out = _UNSAFE.sub("-", str(s)).strip("-_.")
    return out


def descriptive_filename(artifact: str,
                          ext: str,
                          *,
                          context: Optional[Iterable[str]] = None,
                          date: Optional[str] = None) -> str:
    """Return ``orthogather_<artifact>_<context...>_<date>.<ext>``.

    Parameters
    ----------
    artifact : str
        What the file represents (e.g. ``"GOenrichment-chart"``).
        Required.
    ext : str
        File extension, without the leading dot (e.g. ``"png"``).
    context : iterable of str, optional
        Extra slugs to embed, in order. Empty / None entries are skipped.
        Examples: ``["47species", "evidence-all", "BP"]``.
    date : str, optional
        ISO date (``"2026-05-26"``). Defaults to today.

    Examples
    --------
    >>> descriptive_filename("GOenrichment-chart", "png",
    ...     context=["47species", "evidence-all"], date="2026-05-26")
    'orthogather_GOenrichment-chart_47species_evidence-all_2026-05-26.png'
    >>> descriptive_filename("figure1", "csv", date="2026-05-26")
    'orthogather_figure1_2026-05-26.csv'
    """
    parts = ["orthogather", _slug(artifact)]
    for c in (context or []):
        s = _slug(c)
        if s:
            parts.append(s)
    parts.append(date or datetime.date.today().isoformat())
    stem = "_".join(p for p in parts if p)
    return f"{stem}.{_slug(ext)}"
