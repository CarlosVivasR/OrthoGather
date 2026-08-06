"""
Persistent OrthoFinder-run history at ``~/.orthogather/runs/<id>/``.

This module owns all the disk I/O for saved runs:
  - parsing OrthoFinder's stats files into a summary dict
  - detecting technical issues (empty proteomes, 0% coverage)
  - snapshotting a freshly-finished run into the history folder
  - listing saved runs
  - loading a run for /compare
  - generating BibTeX / RIS citation strings

Everything is pure I/O — no Flask. Routes call these and surface the result.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import time
import zipfile
from pathlib import Path

import pandas as pd

from orthogather.config import HISTORY_DIR, PROTEOMES_FOLDER, SESSION_FILE_DIR
from orthogather.core.figures import generate_figure_1, generate_figure_2


def parse_orthofinder_stats(results_dir) -> dict:
    """Parse OrthoFinder's Statistics_PerSpecies.tsv + Statistics_Overall.tsv
    into the dict the run summary card needs."""
    results_dir = Path(results_dir)
    stats_dir = results_dir / "Comparative_Genomics_Statistics"
    per_species_path = stats_dir / "Statistics_PerSpecies.tsv"
    overall_path     = stats_dir / "Statistics_Overall.tsv"

    summary = {
        "ok": False,
        "total_orthogroups": None,
        "single_copy_orthogroups": None,
        "species_specific_orthogroups": None,
        "mean_pct_in_og": None,
        "min_pct_in_og":  None,
        "max_pct_in_og":  None,
        "n_species": None,
        "species": []
    }

    if not per_species_path.exists():
        return summary
    rows = per_species_path.read_text().splitlines()
    if len(rows) < 2:
        return summary

    species_names = [s.strip() for s in rows[0].split('\t')[1:] if s.strip()]
    data = {name: {} for name in species_names}
    for raw in rows[1:]:
        cells = raw.split('\t')
        if not cells:
            continue
        metric = cells[0].strip()
        for i, val in enumerate(cells[1:]):
            if i >= len(species_names):
                break
            data[species_names[i]][metric] = val.strip()

    def _num(d, key):
        v = d.get(key, '')
        if not v:
            return None
        try:
            return float(v) if '.' in v else int(v)
        except ValueError:
            return None

    for sp in species_names:
        d = data[sp]
        summary["species"].append({
            "name": sp,
            "n_proteins":   _num(d, "Number of genes"),
            "n_in_og":      _num(d, "Number of genes in orthogroups"),
            "pct_in_og":    _num(d, "Percentage of genes in orthogroups"),
            "n_unassigned": _num(d, "Number of unassigned genes"),
        })

    pcts = [s["pct_in_og"] for s in summary["species"] if s["pct_in_og"] is not None]
    if pcts:
        summary["mean_pct_in_og"] = round(sum(pcts) / len(pcts), 1)
        summary["min_pct_in_og"]  = round(min(pcts), 1)
        summary["max_pct_in_og"]  = round(max(pcts), 1)

    if overall_path.exists():
        for raw in overall_path.read_text().splitlines():
            parts = raw.split('\t')
            if len(parts) < 2:
                continue
            k, v = parts[0].strip(), parts[1].strip()
            try:
                if k == "Number of orthogroups":
                    summary["total_orthogroups"] = int(v)
                elif k == "Number of single-copy orthogroups":
                    summary["single_copy_orthogroups"] = int(v)
                elif k == "Number of species-specific orthogroups":
                    summary["species_specific_orthogroups"] = int(v)
                elif k == "Number of species":
                    summary["n_species"] = int(v)
            except ValueError:
                pass

    summary["ok"] = bool(summary["species"])
    return summary


def detect_technical_issues(summary: dict) -> list:
    """Flag concrete technical problems (NOT biological — distance / divergence
    are normal). Used by the run-summary card to warn the user about likely
    bad inputs."""
    issues = []
    for sp in summary.get("species", []):
        n   = sp.get("n_proteins") or 0
        pct = sp.get("pct_in_og") or 0
        if n < 50:
            issues.append({
                "species": sp["name"], "kind": "empty_proteome",
                "detail": f"only {n} proteins — likely a truncated or corrupt FASTA"
            })
        elif pct == 0:
            issues.append({
                "species": sp["name"], "kind": "zero_coverage",
                "detail": "0% of proteins assigned to an orthogroup — proteome may be incompatible with the others"
            })
    return issues


def snapshot_run(results_dir, run_id: str, duration_s: float, species_ids=None,
                 provenance=None) -> dict:
    """Copy essential OrthoFinder outputs to ``~/.orthogather/runs/<run_id>/``
    and write a ``meta.json`` describing the run.

    Parameters
    ----------
    results_dir : str | Path
        OrthoFinder's output directory.
    run_id : str
        Stable id for the run (used as folder name and citation key).
    duration_s : float
        How long the OrthoFinder run took.
    species_ids : list[str] | None
        Optional list of UniProt proteome IDs the user picked. Stored in
        ``meta.json`` so /history/<id>/reproduce can pre-fill the picker.
    """
    results_dir = Path(results_dir)
    dest = HISTORY_DIR / run_id
    dest.mkdir(parents=True, exist_ok=True)

    keep = [
        results_dir / "Orthogroups" / "Orthogroups.tsv",
        results_dir / "Orthogroups" / "Orthogroups.txt",
        results_dir / "Orthogroups" / "Orthogroups.GeneCount.tsv",
        results_dir / "Orthogroups" / "Orthogroups_UnassignedGenes.tsv",
        results_dir / "Orthogroups" / "Orthogroups_SingleCopyOrthologues.txt",
        results_dir / "Comparative_Genomics_Statistics" / "Statistics_PerSpecies.tsv",
        results_dir / "Comparative_Genomics_Statistics" / "Statistics_Overall.tsv",
    ]
    for src in keep:
        if src.exists():
            shutil.copy2(src, dest / src.name)

    summary = parse_orthofinder_stats(results_dir)
    issues  = detect_technical_issues(summary)
    meta = {
        "id": run_id,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(duration_s, 1),
        "species": [{"name": s["name"]} for s in summary.get("species", [])],
        "species_ids": list(species_ids or []),
        "summary": summary,
        "issues":  issues,
        "name": None,
        "provenance": provenance,
    }
    with open(dest / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # Re-create the Orthogroups.zip inside the saved run so /cargar_carpeta
    # can re-use it directly.
    zip_path = dest / "Orthogroups.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for filename in ("Orthogroups.tsv", "Orthogroups.txt",
                         "Orthogroups.GeneCount.tsv",
                         "Orthogroups_UnassignedGenes.tsv"):
            p = dest / filename
            if p.exists():
                zipf.write(p, arcname=filename)

    return meta


def cleanup_temp_run() -> None:
    """Delete the temporary OrthoFinder workspace (input FASTAs + the
    ``OrthoFinder/`` intermediates dir) but PRESERVE the run outputs the next
    steps depend on: ``Orthogroups.zip`` (consumed by Protein Analysis / Gene
    Ontology via ``/cargar_carpeta?modo=generated``) and the ``*_provenance.json``
    stamps (copied into the analysis folder by ``_render_result_and_cache``).
    Keeps ``Proteomas/`` itself so subsequent runs work.

    Previously this wiped *every* file, including ``Orthogroups.zip`` — which
    made clicking "Protein Analysis" right after a run redirect to home, because
    the generated-mode handler could no longer find the zip."""
    proteomes_path = Path(PROTEOMES_FOLDER)
    if not proteomes_path.exists():
        return
    keep = {"Orthogroups.zip", "proteome_provenance.json", "orthofinder_provenance.json"}
    for entry in proteomes_path.iterdir():
        if entry.name in keep:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        except Exception:
            pass


# =====================================================================
# Disk hygiene — automatic pruning to keep a long-lived install healthy
# =====================================================================
# Without these, prolonged use accumulates:
#   - ~30-100 MB per saved analysis under ~/.orthogather/runs/<id>/
#   - one .orthogather_sessions file per browser per visit (kilobytes,
#     but they pile up to thousands over months)
#   - leftover Proteomas/ working dir if OrthoFinder crashed mid-run
#
# These functions are safe to call on every Flask startup — they no-op
# when nothing needs cleaning.

def _dir_size_bytes(path: Path) -> int:
    """Sum byte size of every file under ``path`` (recursive)."""
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except (OSError, PermissionError):
            pass
    return total


def prune_history(max_runs: int = 20) -> dict:
    """Keep only the ``max_runs`` most recent runs under ``HISTORY_DIR``.

    Older runs are deleted whole (including their orthogroups.zip and
    figures). Returns a summary ``{"kept": int, "removed": int,
    "freed_mb": float}`` for logging.
    """
    if not HISTORY_DIR.exists() or max_runs < 1:
        return {"kept": 0, "removed": 0, "freed_mb": 0.0}

    # Collect (run_dir, mtime) pairs — sort by mtime descending so we keep
    # the newest. We use mtime rather than meta.created_at so untrusted /
    # malformed meta.json files don't accidentally protect old runs.
    runs = []
    for d in HISTORY_DIR.iterdir():
        if d.is_dir():
            try:
                runs.append((d, d.stat().st_mtime))
            except OSError:
                pass
    runs.sort(key=lambda t: t[1], reverse=True)

    to_remove = runs[max_runs:]
    freed = 0
    removed = 0
    for d, _ in to_remove:
        try:
            freed += _dir_size_bytes(d)
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
        except Exception as e:
            logging.warning(f"[hygiene] Could not prune {d.name}: {e}")

    return {"kept": min(len(runs), max_runs),
            "removed": removed,
            "freed_mb": round(freed / 1024 / 1024, 1)}


def prune_old_sessions(max_age_days: int = 14) -> dict:
    """Delete Flask filesystem-session files older than ``max_age_days``.

    Flask-Session writes one file per browser session under
    ``SESSION_FILE_DIR``. They never expire by default. After a few months
    you can easily have thousands of stale entries.
    """
    sess_dir = Path(SESSION_FILE_DIR)
    if not sess_dir.exists() or max_age_days < 0:
        return {"removed": 0, "freed_mb": 0.0}

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    freed = 0
    for f in sess_dir.iterdir():
        try:
            st = f.stat()
            if st.st_mtime < cutoff:
                freed += st.st_size
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    return {"removed": removed,
            "freed_mb": round(freed / 1024 / 1024, 1)}


def disk_usage_report() -> dict:
    """Return current size of the main runtime directories. Used for the
    startup log so the user can see if anything is bloating."""
    from orthogather.config import GOA_DOWNLOAD_FOLDER, RESULTS_FOLDER
    return {
        "history_mb":   round(_dir_size_bytes(HISTORY_DIR) / 1024 / 1024, 1),
        "sessions_mb":  round(_dir_size_bytes(Path(SESSION_FILE_DIR)) / 1024 / 1024, 1),
        "proteomas_mb": round(_dir_size_bytes(Path(PROTEOMES_FOLDER)) / 1024 / 1024, 1),
        "goa_mb":       round(_dir_size_bytes(Path(GOA_DOWNLOAD_FOLDER)) / 1024 / 1024, 1),
        "results_mb":   round(_dir_size_bytes(Path(RESULTS_FOLDER)) / 1024 / 1024, 1),
    }


def run_startup_hygiene() -> None:
    """One-shot disk-cleanup pass intended to run when Flask starts.

    Controlled by env vars (all optional; sensible defaults):
      - ORTHOGATHER_MAX_HISTORY       (int, default 20): how many runs to keep
      - ORTHOGATHER_SESSION_TTL_DAYS  (int, default 14): expire stale sessions
      - ORTHOGATHER_CLEAN_PROTEOMAS   (bool, default 1): clear leftover
                                        Proteomas working dir from prior crashes

    Always logs the disk usage AFTER cleanup so users can monitor growth.
    """
    def _env_int(name, default):
        try:    return int(os.environ.get(name, default))
        except (ValueError, TypeError): return default
    def _env_bool(name, default):
        return os.environ.get(name, str(default)).strip().lower() not in ("0", "false", "no", "off")

    max_history   = _env_int("ORTHOGATHER_MAX_HISTORY", 20)
    session_ttl   = _env_int("ORTHOGATHER_SESSION_TTL_DAYS", 14)
    clean_temp    = _env_bool("ORTHOGATHER_CLEAN_PROTEOMAS", True)

    hist = prune_history(max_history)
    sess = prune_old_sessions(session_ttl)
    if clean_temp:
        cleanup_temp_run()

    if hist["removed"] or sess["removed"]:
        logging.info(
            f"[hygiene] Pruned history ({hist['removed']} runs, "
            f"{hist['freed_mb']} MB freed), "
            f"sessions ({sess['removed']} files, {sess['freed_mb']} MB freed)"
        )
    else:
        logging.info("[hygiene] Nothing to prune at startup.")

    usage = disk_usage_report()
    logging.info(
        f"[hygiene] Disk usage now — "
        f"history: {usage['history_mb']} MB · "
        f"sessions: {usage['sessions_mb']} MB · "
        f"Proteomas: {usage['proteomas_mb']} MB · "
        f"GOAfiles: {usage['goa_mb']} MB · "
        f"results: {usage['results_mb']} MB"
    )


def list_history() -> list:
    """Return list of saved runs, newest first. Skips folders without a
    valid ``meta.json``."""
    runs = []
    if not HISTORY_DIR.exists():
        return runs
    for d in HISTORY_DIR.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path) as f:
                runs.append(json.load(f))
        except Exception:
            continue
    runs.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return runs


def build_citation_context(run_id: str):
    """Return a dict with the values needed to render BibTeX / RIS, or
    ``None`` if the run doesn't exist."""
    meta_path = HISTORY_DIR / run_id / "meta.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        return None
    created = (meta.get("created_at") or "")[:10]
    year = created[:4] or datetime.datetime.utcnow().strftime("%Y")
    species = meta.get("summary", {}).get("species") or meta.get("species") or []
    n_species = len(species)
    title = meta.get("name") or f"OrthoGather analysis of {n_species} proteomes"
    return {
        "run_id": run_id,
        "year": year,
        "date": created,
        "title": title,
        "n_species": n_species,
        "species_names": [s.get("name", "") for s in species],
        "n_orthogroups": (meta.get("summary", {}) or {}).get("total_orthogroups", 0),
    }


def bibtex_for_run(ctx: dict) -> str:
    """Render BibTeX for a run context dict (output of :func:`build_citation_context`)."""
    key = f"orthogather{ctx['run_id']}"
    species_block = ", ".join(s.replace("_", " ") for s in ctx["species_names"][:6])
    if len(ctx["species_names"]) > 6:
        species_block += f", and {len(ctx['species_names']) - 6} more"
    return (
        # The OrthoGather tool itself — cite alongside your analysis run.
        f"@article{{VivasRodriguez2026OrthoGather,\n"
        f"  author  = {{Carlos Vivas-Rodriguez, David Matallanas, Colm J. Ryan, "
        f"Siobhán McClean, Olivier Dennler, Joanna Drabińska}},\n"
        f"  title   = {{{{OrthoGather}}: a local platform for orthology-based proteome "
        f"and proteomics comparisons and Gene Ontology enrichment}},\n"
        f"  journal = {{bioRxiv}},\n"
        f"  year    = {{2026}},\n"
        f"  doi     = {{10.64898/2026.01.30.702851}},\n"
        f"}}\n\n"
        f"@misc{{{key},\n"
        f"  title        = {{{ctx['title']}}},\n"
        f"  author       = {{OrthoGather user}},\n"
        f"  year         = {{{ctx['year']}}},\n"
        f"  howpublished = {{Local analysis with OrthoGather (run {ctx['run_id']})}},\n"
        f"  note         = {{Species: {species_block}. {ctx['n_orthogroups']} orthogroups. "
        f"Pipeline: OrthoFinder + UniProt proteomes. Generated on {ctx['date']}.}},\n"
        f"}}\n\n"
        f"@article{{emms2019orthofinder,\n"
        f"  title   = {{OrthoFinder: phylogenetic orthology inference for comparative genomics}},\n"
        f"  author  = {{Emms, David M and Kelly, Steven}},\n"
        f"  journal = {{Genome Biology}},\n"
        f"  volume  = {{20}},\n"
        f"  pages   = {{238}},\n"
        f"  year    = {{2019}},\n"
        f"  doi     = {{10.1186/s13059-019-1832-y}},\n"
        f"}}\n\n"
        f"@article{{uniprot2023,\n"
        f"  title   = {{UniProt: the Universal Protein Knowledgebase in 2023}},\n"
        f"  author  = {{{{The UniProt Consortium}}}},\n"
        f"  journal = {{Nucleic Acids Research}},\n"
        f"  volume  = {{51}},\n"
        f"  number  = {{D1}},\n"
        f"  pages   = {{D523--D531}},\n"
        f"  year    = {{2023}},\n"
        f"  doi     = {{10.1093/nar/gkac1052}},\n"
        f"}}\n"
    )


def ris_for_run(ctx: dict) -> str:
    """Render RIS for a run context dict."""
    species_block = ", ".join(s.replace("_", " ") for s in ctx["species_names"][:6])
    if len(ctx["species_names"]) > 6:
        species_block += f", and {len(ctx['species_names']) - 6} more"
    return (
        # Record 1: the OrthoGather tool (cite alongside your run).
        "TY  - JOUR\n"
        "TI  - OrthoGather: a local platform for orthology-based proteome and "
        "proteomics comparisons and Gene Ontology enrichment\n"
        "AU  - Carlos Vivas-Rodriguez\n"
        "AU  - David Matallanas\n"
        "AU  - Colm J. Ryan\n"
        "AU  - Siobhán McClean\n"
        "AU  - Olivier Dennler\n"
        "AU  - Joanna Drabińska\n"
        "PY  - 2026\n"
        "JO  - bioRxiv\n"
        "DO  - 10.64898/2026.01.30.702851\n"
        "ER  - \n"
        # Record 2: this specific analysis run (data).
        "TY  - DATA\n"
        f"TI  - {ctx['title']}\n"
        "AU  - OrthoGather user\n"
        f"PY  - {ctx['year']}\n"
        f"DA  - {ctx['date']}\n"
        f"AB  - OrthoGather run {ctx['run_id']}. Species: {species_block}. "
        f"{ctx['n_orthogroups']} orthogroups. Pipeline: OrthoFinder + UniProt proteomes.\n"
        "PB  - OrthoGather (local)\n"
        "ER  - \n"
        # Record 3: OrthoFinder.
        "TY  - JOUR\n"
        "TI  - OrthoFinder: phylogenetic orthology inference for comparative genomics\n"
        "AU  - Emms, David M\n"
        "AU  - Kelly, Steven\n"
        "PY  - 2019\n"
        "JO  - Genome Biology\n"
        "VL  - 20\n"
        "SP  - 238\n"
        "DO  - 10.1186/s13059-019-1832-y\n"
        "ER  - \n"
        # Record 4: UniProt.
        "TY  - JOUR\n"
        "TI  - UniProt: the Universal Protein Knowledgebase in 2023\n"
        "AU  - The UniProt Consortium\n"
        "PY  - 2023\n"
        "JO  - Nucleic Acids Research\n"
        "VL  - 51\n"
        "IS  - D1\n"
        "SP  - D523\n"
        "EP  - D531\n"
        "DO  - 10.1093/nar/gkac1052\n"
        "ER  - \n"
    )


def load_run_for_compare(run_id: str) -> dict:
    """Read everything /compare needs for a single run: meta + Fig 1 data + Fig 2 data.

    Returns one of:
      - dict with the run payload (success).
      - ``{"_error": "missing", "id": ...}``      — meta.json absent.
      - ``{"_error": "pre-feature", "id": ...}``  — meta.json present but
                                                     GeneCount.tsv missing.
      - ``{"_error": "read-failed", "id": ...}``  — files exist but unparseable.
    """
    run_dir = HISTORY_DIR / run_id
    meta_path = run_dir / "meta.json"
    gene_count_path = run_dir / "Orthogroups.GeneCount.tsv"
    if not meta_path.exists():
        return {"_error": "missing", "id": run_id}
    if not gene_count_path.exists():
        return {"_error": "pre-feature", "id": run_id}
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        df = pd.read_csv(gene_count_path, sep="\t")
    except Exception as e:
        logging.error(f"[/compare] Could not load run {run_id}: {e}")
        return {"_error": "read-failed", "id": run_id, "detail": str(e)}
    fig1 = generate_figure_1(df)
    fig2 = generate_figure_2(df)
    summary = meta.get("summary") or {}
    return {
        "id": run_id,
        "name": meta.get("name") or f"{len(summary.get('species', []))} species",
        "created_at": meta.get("created_at", ""),
        "duration_s": meta.get("duration_s", 0),
        "summary": summary,
        "fig1": fig1,
        "fig2": fig2,
    }
