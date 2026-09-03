"""
Gene Ontology Annotation (GOA / GAF) loader + evidence-code presets.

This module owns the raw GAF parser. It deliberately does NOT depend on
Flask or any global state: callers pass in the folder path and (optionally)
a set of evidence codes to keep.

GAF format reference (GO Consortium spec, 17 columns, 0-indexed):
    1 = DB Object ID  (the protein accession we use as the gene ID)
    4 = GO ID
    6 = Evidence Code (EXP, IDA, ..., IEA, ISS, ...)
    8 = Aspect        (P = BP, F = MF, C = CC)
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Evidence-code presets used by /gene_ontology_analysis.
#   http://geneontology.org/docs/guide-go-evidence-codes/
#
# - 'all'          : accept every annotation (default; closest to legacy
#                    behaviour, includes IEA which is ~95% of any GOA file).
# - 'curated'      : human-curated annotations: experimental + traceable author
#                    statement (TAS) + curator statement (IC) + PAINT-derived
#                    IBA + high-throughput. Excludes IEA, the computational-
#                    analysis codes (ISS/ISO/ISA/ISM/IGC/RCA) and NAS: a
#                    non-traceable author statement cannot be traced back to a
#                    source, so it is deliberately not treated as curated here.
# - 'experimental' : strictest, experimental + high-throughput experimental only.
#
# The full high-throughput family is HTP, HEP, HDA, HMP and HGI — all five are
# included wherever "high-throughput" is claimed above.
#
# templates/resultado_goa.html shows these lists to the user code-by-code in the
# "Evidence quality" popover. Keep the two in sync when editing either.
# ---------------------------------------------------------------------------
EVIDENCE_PRESETS = {
    "all":          None,  # no filter
    "curated":      {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP", "TAS", "IC",
                     "IBA", "HTP", "HEP", "HDA", "HMP", "HGI"},
    "experimental": {"EXP", "IDA", "IPI", "IMP", "IGI", "IEP",
                     "HTP", "HEP", "HDA", "HMP", "HGI"},
}


def _open_gaf(path: Path):
    """Open a .gaf / .goa file (or .gz variant) as text. Caller must close it."""
    if str(path).endswith(".gz"):
        import gzip
        return gzip.open(str(path), "rt", encoding="utf-8", errors="replace")
    return open(str(path), "rt", encoding="utf-8", errors="replace")


def build_id2gos_from_goa_folder(goa_folder: str,
                                 limit_files: Optional[List[str]] = None,
                                 evidence_codes: Optional[set] = None,
                                 return_evidence: bool = False
                                 ) -> Dict[str, List[str]]:
    """Read every .goa/.gaf (incl. .gz) in ``goa_folder`` and build the
    gene → list[GO IDs] mapping that GOATOOLS needs.

    Parameters
    ----------
    goa_folder : str
        Path to folder containing the GOA / GAF files.
    limit_files : list[str] | None
        If provided, only files whose name matches the list are read.
    evidence_codes : set[str] | None
        If provided, only annotations whose evidence code (GAF col 7) belongs
        to this set are kept. Use :data:`EVIDENCE_PRESETS` for ready-made choices.
        When ``None``, no filter is applied (legacy behaviour).
    return_evidence : bool
        When ``True``, additionally returns a per-(gene, GO) breakdown of
        evidence codes — used for the interactive-table chips. Return becomes
        a tuple ``(id2gos, evidence_map)``.

    Returns
    -------
    dict[str, list[str]] or tuple
        Mapping of ``gene_id`` → sorted list of GO IDs (one dict per call).
    """
    folder = Path(goa_folder)
    if not folder.exists():
        raise FileNotFoundError(f"GOA folder not found: {goa_folder}")

    # ── Cache lookup ─────────────────────────────────────────────────────
    # Key includes every input that affects the parser's output: the file
    # names + mtimes + sizes, the limit_files filter, the evidence filter,
    # and whether the caller asked for the evidence_map. If GOA files get
    # re-downloaded, mtime changes and we transparently re-parse.
    try:
        cache_key = _goa_cache_key(folder, limit_files, evidence_codes, return_evidence)
    except OSError:
        cache_key = None
    if cache_key is not None and _id2gos_cache["key"] == cache_key:
        logging.info(f"[INFO] id2gos cache HIT ({len(_id2gos_cache['id2gos'])} genes)")
        if return_evidence:
            return _id2gos_cache["id2gos"], _id2gos_cache["evidence_map"]
        return _id2gos_cache["id2gos"]

    patterns = ["*.goa", "*.gaf", "*.goa.gz", "*.gaf.gz"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    files = sorted(files)

    if limit_files:
        limit_set = set(limit_files)
        files = [f for f in files if f.name in limit_set]

    if not files:
        raise FileNotFoundError("No GOA/GAF files found in GOA folder.")

    id2gos = defaultdict(set)       # gene -> set(GO)
    evidence_map: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    ns_totals = {"BP": 0, "CC": 0, "MF": 0}
    total_read = 0

    aspect_to_ns = {"P": "BP", "F": "MF", "C": "CC"}

    for f in files:
        try:
            logging.info(f"HMS:{datetime.timedelta(0)}  reading annotations: {f.name}")
            per_file_counts = {"BP": 0, "CC": 0, "MF": 0}
            with _open_gaf(f) as fh:
                for line in fh:
                    if not line or line.startswith("!"):
                        continue
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) < 9:
                        continue
                    gene_id = cols[1].strip()
                    go_id   = cols[4].strip()
                    ev      = cols[6].strip()
                    aspect  = cols[8].strip()
                    if not gene_id or not go_id or not go_id.startswith("GO:"):
                        continue
                    if evidence_codes is not None and ev not in evidence_codes:
                        continue
                    ns = aspect_to_ns.get(aspect)
                    if ns is None:
                        continue
                    if go_id not in id2gos[gene_id]:
                        per_file_counts[ns] += 1
                    id2gos[gene_id].add(go_id)
                    if return_evidence:
                        evidence_map[gene_id][go_id].add(ev)

            total_read += 1
            for k in ns_totals:
                ns_totals[k] += per_file_counts[k]
            logging.info(f"{per_file_counts['BP']} GO in BP, "
                         f"{per_file_counts['CC']} in CC, "
                         f"{per_file_counts['MF']} in MF")
        except Exception as e:
            logging.warning(f"[WARN] Could not read {f.name}: {e}")

    if total_read == 0:
        raise ValueError("No GO annotations could be read from the .goa/.gaf files.")

    logging.info(
        f"TOTAL files read: {total_read}. "
        f"Loaded GO -> BP:{ns_totals['BP']}, CC:{ns_totals['CC']}, MF:{ns_totals['MF']} "
        f"(evidence filter: {sorted(evidence_codes) if evidence_codes else 'NONE'})"
    )

    out = {gid: sorted(gos) for gid, gos in id2gos.items()}
    ev_out = None
    if return_evidence:
        ev_out = {g: {go: sorted(codes) for go, codes in d.items()}
                  for g, d in evidence_map.items()}

    # ── Cache store ─────────────────────────────────────────────────────
    # Save under the same key we tried above. Subsequent identical calls
    # (same files + same evidence filter) will hit the cache and skip the
    # 3-4 s GAF parse entirely.
    if cache_key is not None:
        _id2gos_cache["key"] = cache_key
        _id2gos_cache["id2gos"] = out
        _id2gos_cache["evidence_map"] = ev_out

    if return_evidence:
        return out, ev_out
    return out


# ---------------------------------------------------------------------------
# Module-level caches — drastically reduce per-run cost of /gene_ontology_analysis.
#
# Why this matters
# ----------------
# Profile on a typical bacterial dataset (16 species, 64k proteins) showed:
#   - ensure_godag()                : 2.9 s,  +82 MB per call
#   - build_id2gos_from_goa_folder() : 3.6 s,  +30 MB per call
# Both inputs (the OBO file and the .goa files) are STABLE during a session.
# Without caching, every GO run re-parses ~115 MB of data and adds 110 MB of
# heap that the GC may not reclaim promptly. After 3 GO runs (a common case
# when tweaking thresholds), the Python process easily hits 1 GB and the OS
# starts paging — that's the "ordenador laggea" symptom.
#
# Cache strategy
# --------------
# Both caches key on the source file's mtime + path. If the user updates the
# OBO or downloads new GOA files, the mtime changes and the cache misses
# transparently. Single-process Flask, no thread safety required.
# ---------------------------------------------------------------------------

_godag_cache = {"path": None, "mtime": None, "godag": None}
_id2gos_cache = {"key": None, "id2gos": None, "evidence_map": None}


def read_obo_metadata(path: str) -> dict:
    """Read the version header of a GO ``.obo`` file without parsing the whole
    ontology. Returns ``{"data_version": ..., "format_version": ...}`` (values
    may be ``None`` if absent or the file is unreadable).

    The ``data-version`` (e.g. ``releases/2024-09-08``) pins which GO release
    produced an enrichment result — essential provenance, since the ontology
    changes over time. Only the first ~30 header lines are scanned; the term
    stanzas that follow are never touched, so this is effectively free.
    """
    meta = {"data_version": None, "format_version": None}
    try:
        p = Path(path)
        if not p.exists():
            return meta
        with open(p, encoding="utf-8", errors="replace") as fh:
            for _ in range(30):
                line = fh.readline()
                if not line or line.startswith("[Term]"):
                    break
                if line.startswith("data-version:"):
                    meta["data_version"] = line.split(":", 1)[1].strip()
                elif line.startswith("format-version:"):
                    meta["format_version"] = line.split(":", 1)[1].strip()
    except Exception as e:  # pragma: no cover - defensive, provenance is best-effort
        logging.warning(f"[provenance] could not read OBO metadata: {e}")
    return meta


def read_goa_header(path: str) -> dict:
    """Read the metadata header of a GOA/GAF annotation file without parsing
    the (huge) body. Returns ``{"date_generated": ..., "go_version": ...,
    "gaf_version": ...}`` (values may be ``None``).

    EBI/UniProt stamp every ``.goa`` file with the date the annotations were
    *generated* (e.g. ``2026-04-30``) — distinct from when OrthoGather
    downloaded them. That generated date is the real EBI data version and is
    what makes a GO result reproducible. Only the leading ``!`` comment lines
    are scanned; the first data row stops the read.
    """
    meta = {"date_generated": None, "go_version": None, "gaf_version": None}
    try:
        p = Path(path)
        if not p.exists():
            return meta
        with open(p, encoding="utf-8", errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line or not line.startswith("!"):
                    break
                low = line.lower()
                if low.startswith("!date-generated:"):
                    meta["date_generated"] = line.split(":", 1)[1].strip()
                elif low.startswith("!go-version:"):
                    meta["go_version"] = line.split(":", 1)[1].strip()
                elif low.startswith("!gaf-version:"):
                    meta["gaf_version"] = line.split(":", 1)[1].strip()
    except Exception as e:  # pragma: no cover - defensive, provenance is best-effort
        logging.warning(f"[provenance] could not read GOA header: {e}")
    return meta


def ensure_godag(path: str):
    """Load (and cache) the GO basic OBO file.

    Cached on the (resolved_path, mtime) of the OBO file. The OBO doesn't
    change during a Flask process lifetime in practice, so this becomes a
    free dict lookup after the first call — saving ~3 s and ~82 MB per
    subsequent GO run.

    Raises :class:`FileNotFoundError` if the file is missing — callers
    surface that to the user via :func:`respond`.
    """
    from goatools.obo_parser import GODag
    obo_path = Path(path)
    if not obo_path.exists():
        raise FileNotFoundError(
            f"Cannot find OBO file at {path}. It must be located next to app.py."
        )
    mtime = obo_path.stat().st_mtime
    resolved = str(obo_path.resolve())
    if (_godag_cache["path"] == resolved
            and _godag_cache["mtime"] == mtime
            and _godag_cache["godag"] is not None):
        logging.info(f"[INFO] GODag cache HIT for {obo_path.name}")
        return _godag_cache["godag"]

    logging.info(f"[INFO] GODag cache MISS — loading from {path} ...")
    godag = GODag(path, prt=None)
    _godag_cache["path"] = resolved
    _godag_cache["mtime"] = mtime
    _godag_cache["godag"] = godag
    return godag


def _goa_cache_key(folder: Path, limit_files, evidence_codes, return_evidence):
    """Build a stable cache key from the inputs that would change the parser's output."""
    files_signature = tuple(sorted(
        (f.name, f.stat().st_mtime, f.stat().st_size)
        for f in folder.iterdir()
        if f.is_file() and (f.suffix in (".goa", ".gaf") or f.name.endswith((".goa.gz", ".gaf.gz")))
    ))
    limit_t = tuple(sorted(limit_files)) if limit_files else None
    ev_t    = tuple(sorted(evidence_codes)) if evidence_codes else None
    return (files_signature, limit_t, ev_t, bool(return_evidence))
