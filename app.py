import os
import io
import gzip
import zipfile
import shutil
import re
import time
import socket
import threading
import webbrowser
import json
import requests
import subprocess
import secrets
import traceback
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Set
import numpy as np
import pandas as pd
# matplotlib + seaborn were removed 2026-05-26 (Point 10 of the post-review
# plan). Every figure in OrthoGather is now interactive Plotly, rendered
# client-side. The few server-side image writes that remained have been
# migrated to JSON payloads — see /generate_go_image, /upset_data, and
# /gene_ontology_analysis.
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, session, jsonify, send_from_directory, Response, stream_with_context
)
from flask_session import Session
from goatools.obo_parser import GODag
from goatools.anno.gaf_reader import GafReader
from goatools.goea.go_enrichment_ns import GOEnrichmentStudy
from collections import defaultdict

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Refactor 2026-05-26 (Point 2 of the post-review plan):
# - Paths/constants moved to orthogather.config
# - respond() moved to orthogather.utils.responses
# - parse_uniprot_block / normalize moved to orthogather.utils.parsing
# - find_free_port / open_browser moved to orthogather.utils.network
# Imported back here so the existing routes + the pytest suite (which uses
# `from app import …`) keep working unchanged.
# ---------------------------------------------------------------------------
from orthogather.config import (
    BASE_DIR, STATIC_FOLDER, PROTEOMES_FOLDER, GOA_DOWNLOAD_FOLDER,
    RESULTS_FOLDER, JSON_PATH, GO_ROOT_OBO, HISTORY_DIR, SESSION_FILE_DIR,
    ORTHOGATHER_VERSION,
)
from orthogather.utils.responses import respond, respond_error
from orthogather.utils.parsing import normalize, parse_uniprot_block
from orthogather.utils.network import find_free_port, open_browser

# ------------------------
# App
# ------------------------
app = Flask(__name__)
app.secret_key = os.getenv("ORTHOGATHER_SECRET") or secrets.token_hex(32)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = SESSION_FILE_DIR
app.config["SESSION_PERMANENT"] = False
Session(app)


@app.url_defaults
def _static_cache_bust(endpoint, values):
    """Append each static file's mtime as ``?v=`` so browsers refetch CSS/JS the
    moment it changes and otherwise serve from cache. Replaces hand-bumped
    ``?v=N`` query strings, which silently served stale assets when forgotten
    (e.g. an old og-base.js whose setButtonLoading swapped text instead of
    showing the spinner)."""
    if endpoint != "static":
        return
    filename = values.get("filename")
    if not filename:
        return
    try:
        values["v"] = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
    except OSError:
        pass

# ------------------------
# Global variables
# ------------------------
# Module-level mutable globals were removed 2026-05-26. Every route now reads
# fresh data from disk via `load_folder_data(session['folder_path'])` and
# passes the resulting dataframes explicitly to its helpers. This makes the
# app safe under multi-worker deployments (gunicorn, Docker) — previously
# two concurrent requests could clobber each other's `gene_count_df`.


def load_folder_data(folder_path):
    logging.info(f"Files in folder '{folder_path}':")
    try:
        logging.info(os.listdir(folder_path))
    except Exception as e:
        logging.warning(f"[WARN] Could not list '{folder_path}': {e}")

    gene_count_path = os.path.join(folder_path, 'Orthogroups.GeneCount.tsv')
    orthogroups_path = os.path.join(folder_path, 'Orthogroups.tsv')
    single_copy_path = os.path.join(folder_path, 'Orthogroups_SingleCopyOrthologues.txt')
    unassigned_path  = os.path.join(folder_path, 'Orthogroups_UnassignedGenes.tsv')

    # 👉 Only these two are mandatory
    if not os.path.exists(gene_count_path):
        raise FileNotFoundError(f"File not found: {gene_count_path}")
    if not os.path.exists(orthogroups_path):
        raise FileNotFoundError(f"File not found: {orthogroups_path}")

    # Mandatory loads
    gene_count_df  = pd.read_csv(gene_count_path, sep='\t')
    orthogroups_df = pd.read_csv(orthogroups_path, sep='\t')

    # Optional loads
    single_copy_df = None
    if os.path.exists(single_copy_path):
        try:
            single_copy_df = pd.read_csv(single_copy_path, sep='\t')
        except Exception as e:
            logging.warning(f"[WARN] Could not read SingleCopy (continuing): {e}")
    else:
        logging.warning(f"[WARN] Optional file not found (continuing): {single_copy_path}")

    unassigned_df = None
    if os.path.exists(unassigned_path):
        try:
            unassigned_df = pd.read_csv(unassigned_path, sep='\t')
        except Exception as e:
            logging.warning(f"[WARN] Could not read Unassigned (continuing): {e}")
    else:
        logging.warning(f"[WARN] Optional file not found (continuing): {unassigned_path}")

    return gene_count_df, orthogroups_df, single_copy_df, unassigned_df

def delete_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

def create_plots_directory():
    if not os.path.exists(os.path.join('static', 'plots')):
        os.makedirs(os.path.join('static', 'plots'))

# Figure-1/2 data builders moved to orthogather.core.figures (English names).
# Spanish aliases kept here so the existing route handlers don't have to be
# touched in this commit — they'll be renamed in Step 5.
from orthogather.core.figures import generate_figure_1, generate_figure_2
generar_figura_1 = generate_figure_1
generar_figura_2 = generate_figure_2

# Legacy matplotlib UpSet/Excel helpers removed 2026-05-24 — replaced by
# /upset_data (JSON) + UpSetJS frontend + /download_figure_data.
# See git log for the deleted functions.


def read_orthogroups_data(zip_path):
    """Read and return the contents of the Orthogroups.tsv file from a ZIP archive."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        with zip_ref.open('Orthogroups.tsv') as file:
            return pd.read_csv(file, sep='\t')


# Species catalogue + matching moved to orthogather.core.catalogue
from orthogather.core.catalogue import (
    SPECIES_ALIAS_MAP, expand_species_alias, split_species_name,
    extract_species_names_from_tsv, load_proteomes, match_species,
    ensure_catalogue_present, invalidate_caches,
    _match_species_cache, _proteomes_cache,
)

# Excel writer + annotation-distribution figure + clear_goa_dir helper moved
# to orthogather.core.excel — re-imported below for the existing routes.
from orthogather.core.excel import (
    generate_go_excel, clear_goa_dir,
)

# History module: parse stats, snapshot runs, list, compare, citations.
# Routes still use the old `_underscored` names; aliases below keep them happy
# until Step 5 renames the call sites.
from orthogather.core.history import (
    parse_orthofinder_stats   as _parse_orthofinder_stats,
    detect_technical_issues   as _detect_technical_issues,
    cleanup_temp_run          as _cleanup_temp_run,
    list_history              as _list_history,
    build_citation_context    as _build_citation_context,
    bibtex_for_run            as _bibtex_for_run,
    ris_for_run               as _ris_for_run,
    load_run_for_compare      as _load_run_for_compare,
    run_startup_hygiene       as _run_startup_hygiene,
    disk_usage_report         as _disk_usage_report,
)
from orthogather.core import history as _history_mod

# Point 13 — startup disk hygiene. Prunes history > N runs, expires stale
# Flask sessions, and sweeps leftover Proteomas/ working dirs from prior
# crashes. Controlled by ORTHOGATHER_MAX_HISTORY / SESSION_TTL_DAYS /
# CLEAN_PROTEOMAS env vars (see history.run_startup_hygiene docstring).
# Without this, prolonged use of the tool eats disk indefinitely.
try:
    _run_startup_hygiene()
except Exception as _e:
    logging.warning(f"[hygiene] startup pass failed (non-fatal): {_e}")


def _snapshot_run(results_dir, run_id, duration_s):
    """Backward-compat wrapper: pulls species_ids out of session and forwards
    to the pure function in orthogather.core.history."""
    species_ids = list(session.get('species_ids') or [])
    return _history_mod.snapshot_run(results_dir, run_id, duration_s,
                                     species_ids=species_ids,
                                     provenance=build_provenance())


def _orthofinder_thread_settings() -> tuple:
    """Resolve OrthoFinder ``-t`` (sequence-search) and ``-a`` (analysis)
    thread counts from the host's CPU count, with env-var override.

    Why this exists
    ---------------
    Hard-coding ``-t 8 -a 8`` over-subscribes on 4-core laptops (kernel
    context-switching murders Diamond's throughput) and wastes silicon on
    16/32-core workstations. OrthoFinder's own docs recommend ``-t`` near the
    physical core count and ``-a`` lower (the analysis phase is memory-bound
    and benefits very little from extra threads).

    Returns
    -------
    (t, a) : tuple[int, int]
        ``-t`` = detected cores (sequence-search parallelism, Diamond).
        ``-a`` = max(1, cores // 4) (analysis phase, capped to avoid memory
        pressure). Both can be overridden via the environment variables
        ``ORTHOGATHER_OF_THREADS`` and ``ORTHOGATHER_OF_ANALYSIS_THREADS``.
    """
    cores = os.cpu_count() or 4
    t_default = max(1, cores)
    a_default = max(1, cores // 4)

    def _as_pos_int(env_name: str, fallback: int) -> int:
        raw = os.environ.get(env_name)
        if not raw:
            return fallback
        try:
            v = int(raw)
            return v if v >= 1 else fallback
        except ValueError:
            logging.warning(
                f"Ignoring non-integer {env_name}={raw!r}; using {fallback}"
            )
            return fallback

    t = _as_pos_int("ORTHOGATHER_OF_THREADS", t_default)
    a = _as_pos_int("ORTHOGATHER_OF_ANALYSIS_THREADS", a_default)
    return t, a





# GOA / GAF parsing + evidence presets moved to orthogather.core.goa
from orthogather.core.goa import (
    EVIDENCE_PRESETS, _open_gaf, build_id2gos_from_goa_folder, ensure_godag as _ensure_godag,
    read_obo_metadata, read_goa_header,
)
from orthogather.core import single_copy as _sc_mod
from orthogather.core.single_copy import (
    _single_copy_cache, invalidate_single_copy_cache,
)


def ensure_godag(path=GO_ROOT_OBO):
    """Backward-compat wrapper that defaults to the module-level GO_ROOT_OBO."""
    return _ensure_godag(path)


def get_single_copy_orthogroups() -> set:
    """Backward-compat wrapper. The new module needs the upload root passed
    explicitly; we read it from app.config here and forward."""
    return _sc_mod.get_single_copy_orthogroups(app.config.get('UPLOAD_FOLDER'))


############################################################################################################
############################################################################################################
###############################################   @APP ROUTE     ###########################################
############################################################################################################
############################################################################################################

# ---------------------------------------------------------------------------
# Global error handlers — every uncaught exception, 404, 500 lands here.
# JSON requests (Accept: application/json or path starts with /api/) get a
# JSON response shaped like respond_error(); HTML requests get error.html.
# This means the user NEVER sees a raw Werkzeug traceback.
# ---------------------------------------------------------------------------
from orthogather.utils.error_catalog import lookup as _err_lookup


def _wants_json() -> bool:
    """Heuristic: was this request expecting JSON?"""
    if request.is_json:
        return True
    if request.path.startswith("/api/"):
        return True
    accept = request.accept_mimetypes
    return accept.best_match(["application/json", "text/html"]) == "application/json"


def _render_error_page(code: str, status: int, detail: str = None):
    spec = _err_lookup(code)
    if _wants_json():
        return respond_error(code, http_code=status, detail=detail)
    return render_template(
        "error.html",
        error_code=code,
        message=spec.message + (f": {detail}" if detail else ""),
        hint=spec.hint,
        category=spec.category,
        severity=spec.severity,
        detail=detail,
    ), status


@app.errorhandler(404)
def _handle_404(e):
    return _render_error_page("ERR_NOT_FOUND_404", 404)


@app.errorhandler(500)
def _handle_500(e):
    logging.exception("[500] unhandled internal server error")
    return _render_error_page("ERR_UNEXPECTED", 500, detail=str(e) if app.debug else None)


@app.errorhandler(Exception)
def _handle_exception(e):
    # Re-raise HTTPExceptions so they flow to their dedicated handlers (404,
    # 405, etc.) instead of becoming generic 500s.
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    logging.exception("[unhandled] %r", e)
    return _render_error_page(
        "ERR_UNEXPECTED", 500,
        detail=str(e) if app.debug else None,
    )


@app.route('/')
def index():
    # Feed the home-page "catalogue scope" stats from the live manifest so they
    # never drift out of date (they used to be hardcoded and went stale).
    m = _read_catalog_manifest() or {}
    return render_template(
        'index.html',
        proteome_count=m.get('proteome_count') or 1013422,
        goa_taxa_count=m.get('goa_taxa_count') or 28475,
    )


@app.route('/favicon.ico')
def favicon():
    """Browsers request /favicon.ico unconditionally even when the HTML
    declares <link rel="icon" href="…">; serve the existing static file
    from there too so DevTools doesn't show a 404."""
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'images'),
        '1-a668dcaa1.ico',
        mimetype='image/x-icon'
    )


@app.route('/reanalyze')
def reanalyze():
    """Redirects to the point where Figures 1 and 2 were generated."""
    # If the figures have already been generated, redirect the user to that view
    if 'figuras_generadas' in session:
        plot_url_1 = session['plot_url_1']
        plot_url_2 = session['plot_url_2']
        folder_path = session.get('folder_path', '')
        species = list(session.get('species', []))  # Retrieve species from the dataframe
        return render_template('resultado.html', 
                               plot_url_1=plot_url_1, 
                               plot_url_2=plot_url_2, 
                               species=species, 
                               folder_path=folder_path)
    # If no data exists, redirect to the home page
    return redirect(url_for('index'))

import os, zipfile, shutil
from flask import flash, redirect, url_for, render_template, request, session

@app.route('/cargar_carpeta', methods=['POST', 'GET'])
def cargar_carpeta():
    """
    Supported inputs:
      - POST + file (mode=upload): ZIP uploaded -> extracted into static/data_folder/upload
      - POST + mode=generated:     uses Proteomas/Orthogroups.zip -> extracted into static/data_folder/generated
      - GET  + filename=Orthogroups.zip (&mode=preselected|generated):
                                    preselected = static/Orthogroups.zip
                                    generated   = Proteomas/Orthogroups.zip
      - POST + especies[]=...      (from resultado.html) generates Figures 4 and 5
    """
    # Globals removed — every reader re-loads via load_folder_data(session['folder_path']).

    def _clean_dir(path: str):
        os.makedirs(path, exist_ok=True)
        for entry in os.listdir(path):
            p = os.path.join(path, entry)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.unlink(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p)
            except Exception as e:
                logging.warning(f"[WARN] Could not delete {p}: {e}")

    def _render_result_and_cache(folder_path, mode_flag):
        """
        Loads DataFrames, generates Figures 1 and 2, stores results in session, and renders resultado.html.
        Minimum requirements: Orthogroups.GeneCount.tsv and Orthogroups.tsv
        (SingleCopy and Unassigned files are optional for Figures 1 and 2).
        """
        try:
            # Log for debugging
            try:
                logging.info(f"[INFO] Contents of '{folder_path}': {os.listdir(folder_path)}")
            except Exception as _e:
                logging.warning(f"[WARN] Could not list '{folder_path}': {_e}")

            # --- Minimum required files
            req_gene = os.path.join(folder_path, 'Orthogroups.GeneCount.tsv')
            req_og   = os.path.join(folder_path, 'Orthogroups.tsv')
            missing = [p for p in (req_gene, req_og) if not os.path.exists(p)]
            if missing:
                for p in missing:
                    logging.error(f"[ERROR] Missing: {p}")
                flash("Missing required files (Orthogroups.GeneCount.tsv and Orthogroups.tsv are mandatory).")
                return redirect(url_for('index'))

            # --- Optional files warning (continue even if missing)
            for opt in ('Orthogroups_SingleCopyOrthologues.txt',
                        'Orthogroups_UnassignedGenes.tsv',
                        'Orthogroups.txt'):
                p = os.path.join(folder_path, opt)
                if not os.path.exists(p):
                    logging.warning(f"[WARN] Optional file not found (continuing): {p}")

            # Load and generate figures
            gene_count_df_, orthogroups_df_, single_copy_df_, unassigned_df_ = load_folder_data(folder_path)
            # Fresh upload → invalidate single-copy cache (will be lazily reloaded
            # by /foreground_analysis / /background_analysis if needed)
            invalidate_single_copy_cache()

            plot_url_1 = generar_figura_1(gene_count_df_)
            plot_url_2 = generar_figura_2(gene_count_df_)

            # Cache results in session
            session['figuras_generadas'] = True
            session['plot_url_1'] = plot_url_1
            session['plot_url_2'] = plot_url_2
            session['folder_path'] = folder_path
            session['species'] = list(gene_count_df_.columns[1:])
            session['modo'] = mode_flag
            # Carry the run-step provenance stamps (UniProt release + OrthoFinder
            # version) from Proteomas/ into the analysis folder so they survive
            # into build_provenance + the saved run snapshot. Only present for the
            # 'generated' flow (downloaded proteomes); uploads have none, which is
            # correct.
            for _prov_name in ("proteome_provenance.json", "orthofinder_provenance.json"):
                try:
                    _src = os.path.join(PROTEOMES_FOLDER, _prov_name)
                    if os.path.exists(_src):
                        shutil.copy2(_src, os.path.join(folder_path, _prov_name))
                except Exception as _e:
                    logging.warning(f"[provenance] could not copy {_prov_name}: {_e}")
            # Drop the GO-page taxonomic cache. It's keyed by the previous
            # analysis's species list and is read by /api/session_species_taxids
            # in preference to session['species'] — leaving it stale here makes
            # the Protein Analysis taxonomic tree show the wrong species set.
            session.pop('species_matches', None)
            session.pop('species_detected', None)

            return render_template(
                'resultado.html',
                plot_url_1=plot_url_1,
                plot_url_2=plot_url_2,
                species=list(gene_count_df_.columns[1:]),
                folder_path=folder_path
            )

        except Exception as e:
            logging.error(f"[ERROR] _render_result_and_cache(mode={mode_flag}, path={folder_path}) -> {e}")
            flash(f"Error preparing results ({mode_flag}): {e}")
            return redirect(url_for('index'))

    # -------------------------
    # POST
    # -------------------------
    if request.method == 'POST':

        # --- A) UPLOAD: manually uploaded file. Accept either an OrthoFinder
        # ZIP (the historical input) or an OrthoXML file (.xml / .orthoxml)
        # produced by OrthoDB, OMA, eggNOG, OrthoFinder, etc. — see Point 9
        # of the post-review plan.
        if 'file' in request.files:
            folder = request.files['file']
            if folder.filename == '':
                flash('No file selected.')
                return redirect(url_for('index'))
            lower = folder.filename.lower()
            is_zip = lower.endswith('.zip')
            is_xml = lower.endswith('.xml') or lower.endswith('.orthoxml')
            if not (is_zip or is_xml):
                flash('Upload must be a .zip (OrthoFinder output) '
                      'or .xml / .orthoxml (Quest-for-Orthologs standard).')
                return redirect(url_for('index'))

            folder_path = os.path.join('static', 'data_folder', 'upload')
            _clean_dir(folder_path)
            saved_path = os.path.join(folder_path, folder.filename)
            folder.save(saved_path)

            if is_zip:
                try:
                    with zipfile.ZipFile(saved_path, 'r') as zip_ref:
                        zip_ref.extractall(folder_path)
                except Exception as e:
                    logging.error(f"[ERROR] Unzipping uploaded ZIP: {e}")
                    flash(f"Error extracting the uploaded ZIP: {e}")
                    return redirect(url_for('index'))
            else:
                # OrthoXML path — parse and write OrthoFinder-compatible TSVs
                from orthogather.core.orthoxml import (
                    parse_orthoxml, write_orthofinder_tsvs,
                )
                try:
                    og_df, gc_df, xml_meta = parse_orthoxml(saved_path)
                    write_orthofinder_tsvs(og_df, gc_df, folder_path)
                    # Stash the OrthoXML provenance in the session so the
                    # reproducibility manifest (Point 4) can pick it up.
                    session['source_format'] = 'orthoxml'
                    session['orthoxml_meta'] = xml_meta
                    logging.info(
                        f"[upload] OrthoXML parsed: {xml_meta['n_orthogroups']} OGs, "
                        f"{xml_meta['n_species']} species, "
                        f"origin={xml_meta.get('origin', '?')}"
                    )
                except (FileNotFoundError, ValueError) as e:
                    logging.error(f"[ERROR] OrthoXML parse failed: {e}")
                    flash(f"Could not parse OrthoXML: {e}")
                    return redirect(url_for('index'))

            return _render_result_and_cache(folder_path, 'upload')

        # --- B) GENERATED: ZIP generated by OrthoFinder
        if request.form.get('modo') == 'generated':
            folder_path = os.path.join('static', 'data_folder', 'generated')
            _clean_dir(folder_path)

            zip_src = os.path.join('Proteomas', 'Orthogroups.zip')
            if not os.path.isfile(zip_src):
                flash('File Proteomas/Orthogroups.zip not found. Please run OrthoFinder first.')
                return redirect(url_for('index'))

            try:
                with zipfile.ZipFile(zip_src, 'r') as zip_ref:
                    zip_ref.extractall(folder_path)
            except Exception as e:
                logging.error(f"[ERROR] Unzipping generated ZIP: {e}")
                flash(f"Error extracting generated ZIP: {e}")
                return redirect(url_for('index'))

            return _render_result_and_cache(folder_path, 'generated')

        # --- C) Legacy POST handler for matplotlib UpSet figures has been
        # retired. Figures 3/4/5 are now generated client-side via UpSetJS
        # + Plotly using /upset_data (JSON) and /download_upset_data.
        # Any old form submit will fall through to the GET re-render below.

    # -------------------------
    # GET (preselected / generated / upload)
    # -------------------------
    if request.method == 'GET':
        # A) preselected / generated -> extract from given ZIP
        if request.args.get('filename') == 'Orthogroups.zip':
            modo_arg = request.args.get('modo', 'preselected')
            try:
                if modo_arg == 'generated':
                    zip_src = os.path.join('Proteomas', 'Orthogroups.zip')
                    folder_path = os.path.join('static', 'data_folder', 'generated')
                else:
                    zip_src = os.path.join('static', 'Orthogroups.zip')
                    folder_path = os.path.join('static', 'data_folder')

                _clean_dir(folder_path)

                with zipfile.ZipFile(zip_src, 'r') as zip_ref:
                    zip_ref.extractall(folder_path)

                return _render_result_and_cache(folder_path, modo_arg)

            except Exception as e:
                logging.error(f"[ERROR] GET cargar_carpeta (mode={modo_arg}): {e}")
                flash(f"Error processing file (mode={modo_arg}): {e}")
                return redirect(url_for('index'))

        # B) upload -> reuse already extracted folder from upload flow
        if request.args.get('modo') == 'upload':
            try:
                folder_path = os.path.join('static', 'data_folder', 'upload')
                if not os.path.isdir(folder_path):
                    flash('No upload data prepared. Please upload a ZIP first.')
                    return redirect(url_for('index'))

                # Do not clean or extract anything here: it’s already unpacked by the upload POST
                return _render_result_and_cache(folder_path, 'upload')

            except Exception as e:
                logging.error(f"[ERROR] GET cargar_carpeta (mode=upload): {e}")
                flash(f"Error preparing upload: {e}")
                return redirect(url_for('index'))

    # -------------------------
    # Re-render if figures already exist
    # -------------------------
    if session.get('figuras_generadas'):
        return render_template(
            'resultado.html',
            plot_url_1=session.get('plot_url_1'),
            plot_url_2=session.get('plot_url_2'),
            species=session.get('species', []),
            folder_path=session.get('folder_path', '')
        )

    return redirect(url_for('index'))

# ════════════════════════════════════════════════════════════════════════════
# UpSet data endpoints (Innovation #4 — UpSetJS migration)
#
# Backend stops generating PNGs for Figures 3/4/5. Instead it returns the raw
# combination / count data as JSON; the frontend renders Figures 4 & 5 with
# UpSetJS (@upsetjs/bundle, MIT) and Figure 3 with Plotly. This makes the
# figures interactive, exportable as JSON/CSV/Excel by the user, and a fraction
# of the size on the wire (KB vs MB).
# ════════════════════════════════════════════════════════════════════════════

def _build_upset_payload(gene_count_df, species_selected, orthogroup_subset=None,
                         fig_keys=("fig3", "fig4")):
    """Compute UpSet figures in one pass.

    Args:
      gene_count_df:      the full GeneCount dataframe (one row per orthogroup).
      species_selected:   list of species (column names) to include.
      orthogroup_subset:  optional iterable of Orthogroup IDs. When provided,
                          only those orthogroups feed the UpSet — used by the
                          UniProt-ID filter (Figures 5 & 6).
      fig_keys:           (key_orthogroups, key_proteins). Defaults to fig3/fig4
                          for the always-on upsets; the filtered endpoint passes
                          ("fig5", "fig6") so the JSON stays unambiguous.

    Returns a dict with the two figure keys + a 'species' echo + 'n_orthogroups'
    so the frontend can show "Filtered: N orthogroups" banner.

    Combinations are sorted by degree ascending, ties broken by descending
    count — same convention as upsetplot's sort_by='degree'.
    """
    # Filter to rows where at least one selected species has a protein.
    df = gene_count_df.copy()
    if orthogroup_subset is not None:
        subset = set(orthogroup_subset)
        # gene_count_df has 'Orthogroup' as a column (first one) — match by it.
        df = df[df["Orthogroup"].isin(subset)]
    df = df[(df[species_selected] > 0).any(axis=1)]

    # Walk each orthogroup once and bucket it into (a) the per-species sets
    # it belongs to, and (b) the unique combination of species it represents.
    # We need the actual Orthogroup IDs (not just counts) because UpSetJS's
    # hover logic computes overlap between a hovered set's elements and each
    # combination's elements — without real IDs the highlights are nonsensical.
    sets_og_ids = {sp: [] for sp in species_selected}   # species -> [OG IDs]
    combo_og_ids = {}                                   # combo tuple -> [OG IDs]
    combo_prot_counts = {}                              # combo tuple -> Σ proteins (selected species only)
    set_protein_sum = {sp: 0 for sp in species_selected}
    # Per-combination per-species protein contribution. Powers the
    # "fraction of this bar that comes from species X" highlight on Figure 4.
    combo_species_proteins = {}                         # combo tuple -> {species: Σ proteins from that species}

    sub = df[["Orthogroup"] + list(species_selected)]
    for row in sub.itertuples(index=False, name=None):
        og_id = row[0]
        values = row[1:]
        combo = tuple(sp for sp, v in zip(species_selected, values) if v > 0)
        if not combo:
            continue
        # Add to each member species' set
        for sp, v in zip(species_selected, values):
            if v > 0:
                sets_og_ids[sp].append(og_id)
                set_protein_sum[sp] += int(v)
        # Add to its exclusive combination bucket
        combo_og_ids.setdefault(combo, []).append(og_id)
        combo_prot_counts[combo] = combo_prot_counts.get(combo, 0) + int(sum(values))
        # Per-species contribution inside this combo
        cps = combo_species_proteins.setdefault(combo, {})
        for sp, v in zip(species_selected, values):
            if v > 0:
                cps[sp] = cps.get(sp, 0) + int(v)

    set_cardinality = {sp: len(sets_og_ids[sp]) for sp in species_selected}

    # ─── Figure 3: UpSet of orthogroup counts ─────────────────────────────
    fig3_combinations = []
    for combo, ids in combo_og_ids.items():
        fig3_combinations.append({
            "name": " ∩ ".join(combo),
            "sets": list(combo),
            "cardinality": len(ids),
            "elems": ids,
        })
    fig3_combinations.sort(key=lambda c: (len(c["sets"]), -c["cardinality"]))

    # ─── Figure 4: UpSet of protein counts ────────────────────────────────
    # Same OG IDs (combinations are identical), but cardinality = protein sum.
    # Also carries species_proteins so the frontend can highlight the exact
    # fraction of each bar that comes from the hovered species.
    fig4_combinations = []
    for combo, n_prot in combo_prot_counts.items():
        fig4_combinations.append({
            "name": " ∩ ".join(combo),
            "sets": list(combo),
            "cardinality": int(n_prot),
            "elems": combo_og_ids[combo],   # Same OG IDs as the orthogroup view
            "species_proteins": dict(combo_species_proteins.get(combo, {})),
        })
    fig4_combinations.sort(key=lambda c: (len(c["sets"]), -c["cardinality"]))

    sets3 = [{"name": sp, "cardinality": set_cardinality[sp], "elems": sets_og_ids[sp]}
             for sp in species_selected]
    sets4 = [{"name": sp, "cardinality": set_protein_sum[sp], "elems": sets_og_ids[sp]}
             for sp in species_selected]

    key_og, key_prot = fig_keys
    return {
        "species": list(species_selected),
        "n_orthogroups": int(len(df)),
        key_og: {
            "title": "UpSet — orthogroups shared across species",
            "sets": sets3,
            "combinations": fig3_combinations,
        },
        key_prot: {
            "title": "UpSet — proteins shared across species",
            "sets": sets4,
            "combinations": fig4_combinations,
        },
    }


# UniProt ID → orthogroup matcher.
# The Orthogroups.tsv stores proteins as comma-space-separated strings with
# various formats (sp|P12345|... , tr|Q9XX12|... , bare P12345, etc.).
# Substring match on the raw cell is robust to all of them and ~100× faster
# than per-protein parsing (Series.str.contains is C-vectorised).
def _find_orthogroups_with_ids(orthogroups_df, species_selected, uniprot_ids):
    """Return (matched_orthogroups, ids_found, ids_not_found).

    matched_orthogroups: list of Orthogroup IDs that contain ANY of the queried
                        UniProt IDs in their selected-species columns.
    ids_found:          subset of `uniprot_ids` that appeared at least once.
    ids_not_found:      subset of `uniprot_ids` that did NOT appear anywhere.
    """
    # Concatenate the selected species columns into one big haystack per row.
    cols = [c for c in species_selected if c in orthogroups_df.columns]
    if not cols:
        return [], [], list(uniprot_ids)
    # NaN safety: missing cells become empty strings.
    joined = orthogroups_df[cols].fillna("").astype(str).agg("|".join, axis=1)

    # Compile a single regex with word-boundary-ish guard so 'P123' doesn't
    # match 'P12345'. UniProt IDs are alphanumeric — surround by non-alnum.
    if not uniprot_ids:
        return [], [], []
    # Sort by length descending so longer IDs are tried first when overlapping.
    ids_sorted = sorted({str(i).strip() for i in uniprot_ids if str(i).strip()},
                        key=len, reverse=True)
    pattern = re.compile(r"(?<![A-Za-z0-9])(" +
                         "|".join(re.escape(i) for i in ids_sorted) +
                         r")(?![A-Za-z0-9])")

    matched_ogs = []
    found = set()
    for idx, hay in zip(orthogroups_df["Orthogroup"], joined):
        hits = pattern.findall(hay)
        if hits:
            matched_ogs.append(idx)
            found.update(hits)

    not_found = [i for i in ids_sorted if i not in found]
    return matched_ogs, sorted(found), not_found


@app.route('/upset_data', methods=['POST'])
def upset_data():
    """Return JSON for Figures 3/4/5 — replaces the matplotlib PNG generation.
    Body: { species: [name, name, ...] } with ≥2 species."""
    data = request.get_json(silent=True) or {}
    species_selected = data.get("species", [])
    if not isinstance(species_selected, list) or len(species_selected) < 2:
        return respond_error("ERR_TOO_FEW_SPECIES", where="upset_data")

    folder_path = session.get('folder_path', '')
    if not folder_path or not os.path.isdir(folder_path):
        return respond_error("ERR_NO_ACTIVE_ANALYSIS", where="upset_data")

    try:
        gene_count_df_, orthogroups_df_, _, _ = load_folder_data(folder_path)
    except Exception as e:
        logging.error(f"[/upset_data] Could not load data: {e}")
        return respond_error("ERR_LOAD_ANALYSIS_FAILED", where="upset_data", detail=str(e))

    # Defensive: make sure every requested species actually exists in the dataframe.
    missing = [sp for sp in species_selected if sp not in gene_count_df_.columns]
    if missing:
        return respond_error("ERR_SPECIES_NOT_IN_ANALYSIS", where="upset_data",
                              detail=", ".join(missing))

    try:
        payload = _build_upset_payload(gene_count_df_, species_selected)
    except Exception as e:
        logging.error(f"[/upset_data] Computation failed: {e}")
        return respond_error("ERR_UPSET_COMPUTE_FAILED", where="upset_data", detail=str(e))

    # Remember the species selection so /download_upset_data can re-export
    # without the client having to send it again.
    session['upset_species_selected'] = species_selected
    return jsonify({"ok": True, **payload})


@app.route('/upset_data_filtered', methods=['POST'])
def upset_data_filtered():
    """Same as /upset_data but restricted to orthogroups that contain at least
    one of the provided UniProt IDs.

    Body: { species: [name, name, ...], uniprot_ids: [id, id, ...] }
    Returns: { ok, species, n_orthogroups, fig5, fig6, ids_found, ids_not_found }
    """
    data = request.get_json(silent=True) or {}
    species_selected = data.get("species", [])
    raw_ids = data.get("uniprot_ids", [])

    if not isinstance(species_selected, list) or len(species_selected) < 2:
        return respond_error("ERR_TOO_FEW_SPECIES_FILTERED", where="upset_data_filtered")
    if not isinstance(raw_ids, list) or not raw_ids:
        return respond_error("ERR_NO_FILTER_IDS", where="upset_data_filtered")

    # Sanitise the IDs: strip whitespace, drop empties, de-duplicate.
    uniprot_ids = sorted({str(i).strip() for i in raw_ids if str(i).strip()})
    if not uniprot_ids:
        return respond_error("ERR_EMPTY_ID_LIST", where="upset_data_filtered")

    folder_path = session.get('folder_path', '')
    if not folder_path or not os.path.isdir(folder_path):
        return respond_error("ERR_NO_ACTIVE_ANALYSIS", where="upset_data_filtered")

    try:
        gene_count_df_, orthogroups_df_, _, _ = load_folder_data(folder_path)
    except Exception as e:
        logging.error(f"[/upset_data_filtered] Could not load data: {e}")
        return respond_error("ERR_LOAD_ANALYSIS_FAILED",
                              where="upset_data_filtered", detail=str(e))

    missing = [sp for sp in species_selected if sp not in gene_count_df_.columns]
    if missing:
        return respond_error("ERR_SPECIES_NOT_IN_ANALYSIS",
                              where="upset_data_filtered",
                              detail=", ".join(missing))

    # Run the UniProt → orthogroup matcher.
    try:
        matched_ogs, ids_found, ids_not_found = _find_orthogroups_with_ids(
            orthogroups_df_, species_selected, uniprot_ids
        )
    except Exception as e:
        logging.error(f"[/upset_data_filtered] Matcher failed: {e}")
        return respond_error("ERR_FILTERED_UPSET_FAILED",
                              where="upset_data_filtered", detail=str(e))

    if not matched_ogs:
        # Special case: not an error, just no hits. Return a warning-level JSON
        # so the frontend can surface a clear "no matches" notice with the IDs.
        return jsonify({
            "ok": False,
            "success": False,                # so OG.fetchJSON catches it
            "error_code": "ERR_NO_MATCHING_ORTHOGROUPS",
            "severity": "warning",
            "category": "input",
            "message": f"None of the {len(uniprot_ids)} UniProt IDs were found in the selected species' orthogroups",
            "hint":    "Double-check the IDs (case-sensitive) or pick a broader species selection.",
            "ids_found": [],
            "ids_not_found": uniprot_ids,
        }), 200

    # Build Figures 5 + 6 from the filtered subset.
    try:
        payload = _build_upset_payload(
            gene_count_df_, species_selected,
            orthogroup_subset=matched_ogs,
            fig_keys=("fig5", "fig6"),
        )
    except Exception as e:
        logging.error(f"[/upset_data_filtered] Computation failed: {e}")
        return respond_error("ERR_FILTERED_UPSET_FAILED",
                              where="upset_data_filtered", detail=str(e))

    # Remember selection + matched OGs so /download_figure_data can export figs 5/6.
    session['upset_species_selected']    = species_selected
    session['upset_filtered_orthogroups'] = matched_ogs

    return jsonify({
        "ok": True,
        "ids_found":     ids_found,
        "ids_not_found": ids_not_found,
        "n_ids_searched": len(uniprot_ids),
        **payload,
    })


def _build_figure_dataframe(fig, folder_path, species_selected, filtered_ogs=None):
    """Build the tidy DataFrame for a given figure (1..6). Returns (df, base_filename).

    fig in {1,2}            → figures 1 & 2 (per-OG counts, no species needed).
    fig in {3,4}            → figures 3 & 4 (UpSet of every orthogroup).
    fig in {5,6}            → figures 5 & 6 (UpSet filtered by UniProt IDs).
                              `filtered_ogs` must be the list of matched
                              orthogroup IDs from the previous /upset_data_filtered call.
    Raises ValueError on bad input."""
    if fig in ('1', '2'):
        # Figures 1 & 2 are computed from gene_count_df only — no species selection needed.
        gene_count_df_, _, _, _ = load_folder_data(folder_path)
        if fig == '1':
            data = generar_figura_1(gene_count_df_)
            if not data:
                raise ValueError("Figure 1 data could not be computed.")
            df_out = pd.DataFrame({
                "proteins_per_orthogroup": data["xs"],
                "n_orthogroups":           data["ys"],
            })
            base = "figure1-protein-distribution"
        else:
            data = generar_figura_2(gene_count_df_)
            if not data:
                raise ValueError("Figure 2 data could not be computed.")
            df_out = pd.DataFrame({
                "n_species_sharing": data["xs"],
                "n_orthogroups":     data["ys"],
            })
            base = "figure2-orthogroup-sharing"
        return df_out, base

    if fig in ('3', '4'):
        if not species_selected:
            raise ValueError("No UpSet data in session. Generate the figures first.")
        gene_count_df_, _, _, _ = load_folder_data(folder_path)
        payload = _build_upset_payload(gene_count_df_, species_selected)
        if fig == '3':
            df_out = pd.DataFrame([{
                "combination":   c["name"],
                "n_species":     len(c["sets"]),
                "species":       " + ".join(c["sets"]),
                "n_orthogroups": c["cardinality"],
            } for c in payload["fig3"]["combinations"]])
            base = "figure3-upset-orthogroups"
        else:
            df_out = pd.DataFrame([{
                "combination": c["name"],
                "n_species":   len(c["sets"]),
                "species":     " + ".join(c["sets"]),
                "n_proteins":  c["cardinality"],
            } for c in payload["fig4"]["combinations"]])
            base = "figure4-upset-proteins"
        return df_out, base

    if fig in ('5', '6'):
        if not species_selected:
            raise ValueError("No UpSet data in session. Generate the figures first.")
        if not filtered_ogs:
            raise ValueError("No UniProt-filtered orthogroups in session — "
                             "run the filtered UpSet (Figs 5 & 6) first.")
        gene_count_df_, _, _, _ = load_folder_data(folder_path)
        payload = _build_upset_payload(
            gene_count_df_, species_selected,
            orthogroup_subset=filtered_ogs,
            fig_keys=("fig5", "fig6"),
        )
        if fig == '5':
            df_out = pd.DataFrame([{
                "combination":   c["name"],
                "n_species":     len(c["sets"]),
                "species":       " + ".join(c["sets"]),
                "n_orthogroups": c["cardinality"],
            } for c in payload["fig5"]["combinations"]])
            base = "figure5-upset-orthogroups-filtered"
        else:
            df_out = pd.DataFrame([{
                "combination": c["name"],
                "n_species":   len(c["sets"]),
                "species":     " + ".join(c["sets"]),
                "n_proteins":  c["cardinality"],
            } for c in payload["fig6"]["combinations"]])
            base = "figure6-upset-proteins-filtered"
        return df_out, base

    raise ValueError(f"Unknown figure '{fig}'. Valid values: 1, 2, 3, 4, 5, 6.")


@app.route('/download_figure_data')
def download_figure_data():
    """Download Figure 1/2/3/4 underlying data in xlsx / csv / tsv / json.
    Query params: ?fig=1|2|3|4&format=xlsx|csv|tsv|json
    Figures 1-2 are always available after a /cargar_carpeta render.
    Figures 3-4 require the user to have called /upset_data first."""
    fig = request.args.get('fig', '').strip()
    fmt = request.args.get('format', '').strip().lower()
    if fig not in ('1', '2', '3', '4', '5', '6'):
        return (f"Unknown figure '{fig}'. Valid values: 1, 2, 3, 4, 5, 6."), 400
    if fmt not in ('xlsx', 'csv', 'tsv', 'json'):
        return (f"Unsupported format '{fmt}'. Valid values: xlsx, csv, tsv, json."), 400

    folder_path = session.get('folder_path', '')
    if not folder_path:
        return ("No analysis loaded in this browser session. Open a result page "
                "first (e.g. /cargar_carpeta or History → Open) and then try the "
                "download again."), 400
    species_selected = session.get('upset_species_selected') or []
    filtered_ogs     = session.get('upset_filtered_orthogroups') or []

    try:
        df_out, base = _build_figure_dataframe(
            fig, folder_path, species_selected,
            filtered_ogs=filtered_ogs,
        )
    except ValueError as ve:
        return str(ve), 400
    except Exception as e:
        return f"Could not rebuild data: {e}", 500

    # Descriptive filename: include species count when relevant + ISO date so
    # the user can tell several downloads apart on disk.
    from orthogather.utils.filenames import descriptive_filename
    context = []
    if fig in ('3', '4', '5', '6') and species_selected:
        context.append(f"{len(species_selected)}species")
    if fig in ('5', '6') and filtered_ogs:
        context.append(f"{len(filtered_ogs)}OGs-filtered")
    dl_name = descriptive_filename(base, fmt, context=context)

    if fmt == 'json':
        return Response(
            df_out.to_json(orient='records', indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename="{dl_name}"'},
        )
    if fmt == 'csv':
        return Response(
            df_out.to_csv(index=False),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{dl_name}"'},
        )
    if fmt == 'tsv':
        return Response(
            df_out.to_csv(index=False, sep='\t'),
            mimetype='text/tab-separated-values',
            headers={'Content-Disposition': f'attachment; filename="{dl_name}"'},
        )
    # xlsx
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_out.to_excel(writer, sheet_name=f"Figure {fig}", index=False)
        meta_rows = [
            {"key": "Generated",   "value": datetime.datetime.utcnow().isoformat() + "Z"},
            {"key": "Source",      "value": "OrthoGather figure data export"},
            {"key": "Figure",      "value": f"Figure {fig}"},
            {"key": "Total rows",  "value": len(df_out)},
        ]
        if fig in ('3', '4'):
            meta_rows.append({"key": "Species selected", "value": ", ".join(species_selected)})
        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="README", index=False)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=dl_name,
    )


# Backwards-compat alias for the old endpoint name. Same params, but
# /download_upset_data only ever served figs 3-4 (formerly 4-5).
@app.route('/download_upset_data')
def download_upset_data_compat():
    return download_figure_data()


# Legacy Flask endpoints removed 2026-05-24 (no frontend caller):
#   /create_excel, /download_excel, /download/<filename>,
#   /generate_new_figures, /create_excel_proteome_filtrado
# Replaced by /upset_data + /download_figure_data (JSON-first architecture).


@app.route("/1-seleccion_especies")
def species_selection_page():
    # URL kept Spanish ("/1-seleccion_especies") because it's bookmarked +
    # screenshotted in the tutorial. Template filename also Spanish for the
    # same reason. Only the Python function name got anglicised.
    return render_template("1-seleccion_especies.html")

@app.route("/download", methods=["POST"])
def download_proteomes():
    proteome_ids = request.json.get("proteome_ids", [])

    if not proteome_ids:
        logging.error("❌ No proteomes received from frontend.")
        return jsonify({"error": "No proteomes provided."}), 400

    logging.info("🔁 Cleaning Proteomes folder...")
    for f in os.listdir(PROTEOMES_FOLDER):
        path = os.path.join(PROTEOMES_FOLDER, f)
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            logging.error(f"❌ Error deleting {path}: {e}")

    descargados = []
    errores = []
    vacios = []

    for pid in proteome_ids:
        logging.info(f"\n🔍 Processing {pid}...")

        # METADATA
        url_metadata = f"https://rest.uniprot.org/proteomes/{pid}"
        try:
            r_meta = requests.get(url_metadata)
            if r_meta.status_code != 200:
                raise Exception(f"Metadata HTTP {r_meta.status_code}")
            metadata = r_meta.json()
        except Exception as e:
            logging.error(f"❌ Failed to download metadata for {pid}: {e}")
            errores.append(f"{pid} (metadata failed: {e})")
            continue

        # File name
        organism_name = metadata.get("taxonomy", {}).get("scientificName", "Unknown_organism")
        safe_name = re.sub(r"[^\w\-_\.() ]", "_", organism_name).replace(" ", "_")
        filename = f"{safe_name}.fasta"
        filepath = os.path.join(PROTEOMES_FOLDER, filename)

        # FASTA
        fasta_url = f"https://rest.uniprot.org/uniprotkb/stream?format=fasta&compressed=false&query=(proteome:{pid})"
        try:
            r_fasta = requests.get(fasta_url)
            if r_fasta.status_code != 200:
                raise Exception(f"FASTA HTTP {r_fasta.status_code}")
            with open(filepath, "w") as f:
                f.write(r_fasta.text)
            logging.info(f"📁 Saved to: {filepath}")
        except Exception as e:
            logging.error(f"❌ Failed to save FASTA for {pid}: {e}")
            errores.append(f"{pid} (fasta failed: {e})")
            continue

        # Size verification
        if os.path.getsize(filepath) == 0:
            os.remove(filepath)
            logging.warning(f"⚠️ Empty file removed: {filename}")
            vacios.append(filename)
        else:
            descargados.append(filename)

    logging.info("\n✅ DOWNLOAD COMPLETED")
    logging.info(f"✔️ Downloaded: {descargados}")
    logging.warning(f"⚠️ Empty: {vacios}")
    logging.error(f"❌ Errors: {errores}")

    return jsonify({
        "descargados": descargados,
        "vacios": vacios,
        "errores": errores
    })

# ----------------------------------------------------------------------------
# Catalogue manifest & GitHub-Releases-based update mechanism
# ----------------------------------------------------------------------------
#
# We store a small manifest next to proteomes_list.json that records WHEN the
# catalogue was published and WHERE it came from. The UI shows this info and
# offers a 'Check for updates' button that hits the GitHub Releases API of
# this project's repo, looking for a newer .json asset and offering to
# download it with a progress bar.
# ----------------------------------------------------------------------------

CATALOG_MANIFEST_PATH = str(BASE_DIR / "static" / "Proteomes_json" / "proteomes_list.manifest.json")
GITHUB_OWNER = "CarlosVivasR"
GITHUB_REPO = "OrthoGather"


def _read_catalog_manifest():
    """Return the local catalogue manifest, building a fallback from file mtime if missing."""
    if os.path.exists(CATALOG_MANIFEST_PATH):
        try:
            with open(CATALOG_MANIFEST_PATH) as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Could not read catalogue manifest: {e}")

    # Fallback synthesised from the file on disk
    if os.path.exists(JSON_PATH):
        mtime = os.path.getmtime(JSON_PATH)
        try:
            size = os.path.getsize(JSON_PATH)
        except OSError:
            size = 0
        return {
            "version": "bundled",
            "downloaded_at": datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat(),
            "source_url": None,
            "size_bytes": size,
            "proteome_count": None,
            "is_fallback": True,
        }
    return None


def _write_catalog_manifest(manifest: dict):
    try:
        os.makedirs(os.path.dirname(CATALOG_MANIFEST_PATH), exist_ok=True)
        with open(CATALOG_MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        logging.error(f"Could not write catalogue manifest: {e}")


def build_provenance():
    """Reproducibility record for the active analysis: which proteome catalogue
    snapshot + GOA download + OrthoGather version produced it. Surfaced at the
    bottom of results pages, embedded in exports, and stored with saved runs —
    so a result can always be traced to its data versions (reviewer ask)."""
    manifest = _read_catalog_manifest() or {}
    catalogue = {
        "version":        manifest.get("version"),
        "downloaded_at":  manifest.get("downloaded_at"),
        "proteome_count": manifest.get("proteome_count"),
        "is_fallback":    manifest.get("is_fallback", False),
    }
    # Read a provenance stamp written either into the active analysis folder or,
    # during the OrthoFinder run (before folder_path exists), into Proteomas/.
    # Checking both means the history snapshot — taken mid-run — captures them too.
    def _load_prov(name):
        for base in (session.get("folder_path"), PROTEOMES_FOLDER):
            if not base:
                continue
            p = os.path.join(base, name)
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        return json.load(f)
                except Exception as e:
                    logging.warning(f"[provenance] could not read {name}: {e}")
        return None

    goa      = _load_prov("goa_provenance.json")
    proteome = _load_prov("proteome_provenance.json")
    of_prov  = _load_prov("orthofinder_provenance.json") or {}
    # GO ontology release (data-version from the OBO header) — pins which GO
    # snapshot the enrichment ran against. Read lazily; header-only, so cheap.
    ontology = read_obo_metadata(GO_ROOT_OBO)
    return {
        "orthogather_version": ORTHOGATHER_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode":         session.get("modo"),
        "catalogue":    catalogue,
        "goa":          goa,
        # UniProt release that produced the proteome sequences (None for
        # externally uploaded orthogroups — that version is unknown to us).
        "proteome":     proteome,
        "ontology":     ontology,
        # The OrthoFinder release that produced the orthogroups, captured from
        # its run banner. None when results were uploaded externally (the
        # producing version is genuinely unknown in that case).
        "orthofinder_version": of_prov.get("version"),
    }


@app.context_processor
def _inject_provenance():
    """Make ``provenance()`` callable from any template (lazy — only runs when
    a template actually invokes it)."""
    return {"provenance": build_provenance}


@app.context_processor
def _inject_sidebar_context():
    """Globals the navigation sidebar needs on every page: the live History run
    count (for the pill) and the OrthoGather version (brand sub-label). Kept
    cheap and failure-tolerant so a bad read never breaks page rendering."""
    try:
        count = len(_list_history())
    except Exception:
        count = 0
    return {"history_count": count, "orthogather_version": ORTHOGATHER_VERSION}


def build_provenance_text(prov=None) -> str:
    """Render the provenance record as a human-readable plain-text block, ready
    to paste into a paper's Methods section."""
    p = prov or build_provenance()
    cat = p.get("catalogue") or {}
    g = p.get("goa") or {}
    pr = p.get("proteome") or {}
    onto = p.get("ontology") or {}
    j = lambda v: ", ".join(v) if isinstance(v, list) else (v if v not in (None, "") else "—")
    return "\n".join([
        "OrthoGather — analysis provenance",
        "=" * 42,
        f"OrthoGather version  : {p.get('orthogather_version') or '—'}",
        f"Generated at         : {p.get('generated_at') or '—'}",
        f"Analysis mode        : {p.get('mode') or '—'}",
        "",
        "Proteome data (UniProt)",
        f"  release            : {j(pr.get('release'))}",
        f"  release date       : {j(pr.get('release_date'))}",
        f"  source             : {pr.get('source') or '—'}",
        "",
        "OrthoFinder",
        f"  version            : {p.get('orthofinder_version') or '— (externally supplied orthogroups)'}",
        "",
        "Gene Ontology ontology",
        f"  release (OBO)      : {onto.get('data_version') or '—'}",
        "",
        "GOA annotations (EBI)",
        f"  data generated     : {j(g.get('data_generated')) if g else '—'}",
        f"  GO-version         : {j(g.get('go_version')) if g else '—'}",
        f"  downloaded at      : {(g.get('downloaded_at') if g else None) or '—'}",
        f"  files              : {(g.get('n_files') if g else None) if g else '—'}",
        f"  source             : {(g.get('source') if g else None) or '—'}",
        "",
        "Proteome catalogue",
        f"  version            : {cat.get('version') or '—'}",
        f"  downloaded at      : {cat.get('downloaded_at') or '—'}",
        f"  proteome count     : {cat.get('proteome_count') or '—'}",
        "",
        "Cite: https://doi.org/10.64898/2026.01.30.702851",
        "",
    ]) + "\n"


@app.route("/download_provenance")
def download_provenance():
    """Download the reproducibility provenance (data versions) as a readable
    .txt (default) or machine-readable .json."""
    fmt = (request.args.get("fmt") or "txt").lower()
    prov = build_provenance()
    if fmt == "json":
        data = json.dumps(prov, indent=2).encode("utf-8")
        return send_file(io.BytesIO(data), mimetype="application/json",
                         as_attachment=True, download_name="orthogather-provenance.json")
    data = build_provenance_text(prov).encode("utf-8")
    return send_file(io.BytesIO(data), mimetype="text/plain",
                     as_attachment=True, download_name="orthogather-provenance.txt")


def _xlsx_to_delimited_zip(xlsx_path: str, sep: str) -> io.BytesIO:
    """Read every sheet of an .xlsx workbook and return an in-memory ZIP with
    one delimited text file per sheet (``,`` → CSV, ``\\t`` → TSV)."""
    ext = "csv" if sep == "," else "tsv"
    sheets = pd.read_excel(xlsx_path, sheet_name=None)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, df in sheets.items():
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_") or "sheet"
            zf.writestr(f"{safe}.{ext}", df.to_csv(index=False, sep=sep))
    buf.seek(0)
    return buf


@app.route("/catalog/info")
def catalog_info():
    """Return the local catalogue manifest (synthesised from file mtime if absent)."""
    manifest = _read_catalog_manifest()
    if manifest is None:
        return jsonify({"error": "No catalogue found locally"}), 404
    return jsonify(manifest)


# Cache of the gzipped slim species index, keyed by catalogue file mtime so it
# rebuilds automatically after an update. (mtime, gzipped_bytes).
_species_index_cache = {"mtime": None, "gz": None}


def _build_species_index_gz():
    """Build (and cache) the gzipped slim species index, rebuilding only when the
    catalogue file changed. Returns the gzipped bytes. Safe to call from a warm-up
    thread at startup so the first page load doesn't pay the build cost."""
    try:
        mtime = os.path.getmtime(JSON_PATH)
    except OSError:
        mtime = None
    if _species_index_cache["gz"] is None or _species_index_cache["mtime"] != mtime:
        proteomes = load_proteomes(JSON_PATH)
        slim = [
            [p.get("label", ""), p.get("Proteome Id", ""),
             1 if p.get("type") == "reference" else 0, p.get("taxon_id", "")]
            for p in proteomes
        ]
        raw = json.dumps(slim, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _species_index_cache["gz"] = gzip.compress(raw, compresslevel=6)
        _species_index_cache["mtime"] = mtime
    return _species_index_cache["gz"]


@app.route("/catalog/species_index")
def catalog_species_index():
    """Serve a SLIM, gzip-compressed projection of the catalogue for the species
    picker.

    The picker only needs four fields per proteome — label, Proteome Id, whether
    it's a reference proteome, and taxon id — but the full catalogue carries five
    more (protein_count, the two version stamps, GOA url + size). Streaming the
    whole 246 MB file to the browser is wasteful: it parses slowly (~2 s) and holds
    ~1 M nine-field objects in memory. Here we emit a compact array of
    ``[label, pid, is_reference(0/1), taxon_id]`` tuples, gzipped (~6 MB on the
    wire). The browser fetch transparently decompresses it; the picker rebuilds its
    objects from the tuples. Result: fast transfer + ~3× less parse/memory, even at
    a million proteomes. Cached and keyed by the catalogue's mtime so it refreshes
    after a catalogue update on its own."""
    resp = Response(_build_species_index_gz(), mimetype="application/json")
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Vary"] = "Accept-Encoding"
    return resp


@app.route("/catalog/check_updates")
def catalog_check_updates():
    """
    Query the GitHub Releases API for a newer catalogue.
    Returns {ok: bool, update_available: bool, local: ..., remote: ..., reason: ...}.
    """
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    try:
        r = requests.get(url, timeout=15, headers={"Accept": "application/vnd.github+json"})
    except requests.exceptions.Timeout:
        return respond_error("ERR_GITHUB_TIMEOUT", where="catalog_check_updates")
    except Exception as e:
        return respond_error("ERR_GITHUB_UNREACHABLE",
                              where="catalog_check_updates", detail=str(e))

    if r.status_code == 404:
        return jsonify({"ok": True, "update_available": False,
                        "reason": "No releases found on the repository yet."}), 200
    if r.status_code == 403:
        return respond_error("ERR_GITHUB_RATE_LIMIT", where="catalog_check_updates")
    if r.status_code != 200:
        return respond_error("ERR_GITHUB_BAD_STATUS",
                              where="catalog_check_updates",
                              detail=f"HTTP {r.status_code}")

    releases = r.json() if isinstance(r.json(), list) else []

    # Find the most recent release with a .json asset (presumed to be a catalogue)
    candidate = None
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        for asset in rel.get("assets") or []:
            name = (asset.get("name") or "").lower()
            # Catalogue assets are published gzip-compressed (.json.gz, ~20 MB vs
            # 250 MB raw); accept the plain .json form too for backward compat.
            if name.endswith(".json.gz") or name.endswith(".json"):
                candidate = {
                    "release_name": rel.get("name") or rel.get("tag_name"),
                    "release_tag": rel.get("tag_name"),
                    "published_at": rel.get("published_at"),
                    "html_url": rel.get("html_url"),
                    "asset_name": asset.get("name"),
                    "asset_url": asset.get("browser_download_url"),
                    "asset_size": asset.get("size", 0),
                }
                break
        if candidate:
            break

    if not candidate:
        return jsonify({"ok": True, "update_available": False,
                        "reason": "No catalogue release published yet on GitHub."}), 200

    # Decide if it's newer than what we have
    local = _read_catalog_manifest()
    local_iso = (local or {}).get("downloaded_at")
    update_available = True
    if local_iso and candidate["published_at"]:
        try:
            local_dt = datetime.datetime.fromisoformat(local_iso.replace("Z", "+00:00"))
            remote_dt = datetime.datetime.fromisoformat(candidate["published_at"].replace("Z", "+00:00"))
            update_available = remote_dt > local_dt
        except Exception:
            pass  # can't compare, default to assuming there is an update

    return jsonify({
        "ok": True,
        "update_available": update_available,
        "local": local,
        "remote": candidate,
    })


@app.route("/catalog/update")
def catalog_update():
    """
    Streaming download of a new catalogue from a GitHub release asset URL.
    SSE phases:
        start       { url }
        downloading { total_bytes }
        progress    { bytes_downloaded, total_bytes, percent }
        validating
        done        { manifest }
        error       { reason }
    """
    asset_url = request.args.get("url", "").strip()
    version_label = request.args.get("version", "").strip()
    release_tag = request.args.get("tag", "").strip()

    if not asset_url:
        def _no_url():
            yield _sse({"phase": "error", "reason": "Missing url parameter"})
        return Response(stream_with_context(_no_url()), mimetype="text/event-stream")

    # Safety: only allow GitHub-hosted URLs
    if not (asset_url.startswith("https://github.com/")
            or asset_url.startswith("https://api.github.com/")
            or asset_url.startswith("https://objects.githubusercontent.com/")):
        def _bad_url():
            yield _sse({"phase": "error",
                        "reason": "For safety, the URL must point to github.com."})
        return Response(stream_with_context(_bad_url()), mimetype="text/event-stream")

    def generate():
        tmp_path = JSON_PATH + ".tmp"
        try:
            yield _sse({"phase": "start", "url": asset_url})

            try:
                r = requests.get(asset_url, stream=True, timeout=30, allow_redirects=True)
            except requests.exceptions.Timeout:
                yield _sse({"phase": "error", "reason": "Download timed out."})
                return
            except Exception as e:
                yield _sse({"phase": "error", "reason": f"Network error: {e}"})
                return

            if r.status_code != 200:
                yield _sse({"phase": "error", "reason": f"Download HTTP {r.status_code}"})
                return

            total = int(r.headers.get("Content-Length", 0) or 0)
            yield _sse({"phase": "downloading", "total_bytes": total})

            downloaded = 0
            last_percent = -1
            try:
                os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MiB
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int(downloaded * 100 / total)
                            if percent != last_percent:
                                yield _sse({
                                    "phase": "progress",
                                    "bytes_downloaded": downloaded,
                                    "total_bytes": total,
                                    "percent": percent,
                                })
                                last_percent = percent
                        else:
                            # No content-length header — emit a heartbeat every 5 MB
                            if downloaded % (5 * 1024 * 1024) < 1024 * 1024:
                                yield _sse({
                                    "phase": "progress",
                                    "bytes_downloaded": downloaded,
                                    "total_bytes": 0,
                                    "percent": 0,
                                })
            except Exception as e:
                try: os.remove(tmp_path)
                except OSError: pass
                yield _sse({"phase": "error", "reason": f"Could not write the file: {e}"})
                return

            yield _sse({"phase": "validating"})

            # Catalogue assets are published gzip-compressed (~13 MB vs 166 MB).
            # Decompress in place before validating so the rest of the flow still
            # sees a raw JSON file. Detection is by asset extension (query stripped).
            if asset_url.split("?")[0].lower().endswith(".gz"):
                gunzipped = tmp_path + ".json"
                try:
                    with gzip.open(tmp_path, "rb") as src, open(gunzipped, "wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                    os.remove(tmp_path)
                    tmp_path = gunzipped
                except Exception as e:
                    for p in (tmp_path, gunzipped):
                        try: os.remove(p)
                        except OSError: pass
                    yield _sse({"phase": "error",
                                "reason": f"Could not decompress the downloaded catalogue: {e}"})
                    return

            try:
                with open(tmp_path) as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("Catalogue must be a JSON array")
                proteome_count = len(data)
                if proteome_count == 0:
                    raise ValueError("Catalogue is empty")
                # Distinct species with a GOA file — powers the home-page stat;
                # compute here so the manifest stays complete after a live update.
                goa_taxa_count = len({
                    p.get("taxon_id") for p in data
                    if p.get("file_url") not in ("NA", None, "")
                })
            except Exception as e:
                try: os.remove(tmp_path)
                except OSError: pass
                yield _sse({"phase": "error",
                            "reason": f"The downloaded file is not a valid catalogue: {e}"})
                return

            try:
                if os.path.exists(JSON_PATH):
                    os.remove(JSON_PATH)
                os.rename(tmp_path, JSON_PATH)
            except Exception as e:
                yield _sse({"phase": "error", "reason": f"Could not install the new catalogue: {e}"})
                return

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            new_manifest = {
                "version": version_label or now_iso[:10],
                "release_tag": release_tag or None,
                "downloaded_at": now_iso,
                "source_url": asset_url,
                "size_bytes": downloaded,
                "proteome_count": proteome_count,
                "goa_taxa_count": goa_taxa_count,
                "is_fallback": False,
            }
            _write_catalog_manifest(new_manifest)

            # Catalogue changed — invalidate the in-memory caches so the next
            # request rebuilds them from the new file on disk. The caches live in
            # orthogather.core.catalogue, so this must reset them there (resetting
            # app.py's imported references alone would be a no-op).
            invalidate_caches()

            yield _sse({"phase": "done", "manifest": new_manifest})
        except Exception as e:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            yield _sse({"phase": "error", "reason": str(e)})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# ----------------------------------------------------------------------------
# Streaming download (SSE) — robust replacement for the legacy /download POST.
#
# Improvements vs legacy:
#   * timeout=30s on every requests.get (legacy: no timeout, could hang ~75s)
#   * up to MAX_DOWNLOAD_ATTEMPTS per proteome with exponential backoff
#   * streams progress events so the frontend can show real-time status
#   * supports mode=retry to re-attempt only failed IDs without wiping the
#     Proteomas folder
# ----------------------------------------------------------------------------

MAX_DOWNLOAD_ATTEMPTS = 3          # total attempts per proteome
DOWNLOAD_REQUEST_TIMEOUT = 30      # seconds for each requests.get
DOWNLOAD_BACKOFF_SECONDS = (5, 10, 20)  # wait between attempts 1->2, 2->3, 3->4


def _sse(event: dict) -> str:
    """Serialise a Python dict as a single Server-Sent Event."""
    return f"data: {json.dumps(event)}\n\n"


def _safe_filename_from_metadata(metadata: dict, fallback_pid: str) -> str:
    """Build a safe FASTA filename from UniProt metadata."""
    organism_name = metadata.get("taxonomy", {}).get("scientificName") or fallback_pid
    safe_name = re.sub(r"[^\w\-_\.() ]", "_", organism_name).replace(" ", "_")
    return f"{safe_name}.fasta"


def _attempt_download_one(pid: str, attempt: int):
    """
    Try to download metadata + FASTA for one proteome.
    Yields SSE events describing progress. Returns a dict at the end:
        {"status": "saved" | "empty" | "failed", "filename": ..., "reason": ...}
    via a sentinel last event with phase="_result".
    """
    # --- Metadata ---
    yield _sse({"phase": "attempt", "pid": pid, "attempt": attempt, "step": "metadata"})
    url_metadata = f"https://rest.uniprot.org/proteomes/{pid}"
    try:
        r_meta = requests.get(url_metadata, timeout=DOWNLOAD_REQUEST_TIMEOUT)
        if r_meta.status_code != 200:
            raise RuntimeError(f"metadata HTTP {r_meta.status_code}")
        metadata = r_meta.json()
    except requests.exceptions.Timeout:
        yield _sse({"phase": "_result", "status": "failed", "reason": "metadata request timed out"})
        return
    except Exception as e:
        yield _sse({"phase": "_result", "status": "failed", "reason": f"metadata error: {e}"})
        return

    organism_name = metadata.get("taxonomy", {}).get("scientificName") or pid
    filename = _safe_filename_from_metadata(metadata, pid)
    filepath = os.path.join(PROTEOMES_FOLDER, filename)
    yield _sse({"phase": "metadata_ok", "pid": pid, "species": organism_name, "filename": filename})

    # --- FASTA ---
    yield _sse({"phase": "attempt", "pid": pid, "attempt": attempt, "step": "fasta"})
    fasta_url = f"https://rest.uniprot.org/uniprotkb/stream?format=fasta&compressed=false&query=(proteome:{pid})"
    try:
        r_fasta = requests.get(fasta_url, timeout=DOWNLOAD_REQUEST_TIMEOUT)
        if r_fasta.status_code != 200:
            raise RuntimeError(f"FASTA HTTP {r_fasta.status_code}")
        with open(filepath, "w") as f:
            f.write(r_fasta.text)
    except requests.exceptions.Timeout:
        yield _sse({"phase": "_result", "status": "failed", "reason": "FASTA request timed out"})
        return
    except Exception as e:
        yield _sse({"phase": "_result", "status": "failed", "reason": f"FASTA error: {e}"})
        return

    # UniProt stamps every REST response with the exact release that produced
    # the data (e.g. "2026_01" / "28-January-2026"). Capture it so provenance
    # records the *data* version, not just our download timestamp — the same
    # proteome ID returns different sequences across releases.
    uniprot_release = (r_fasta.headers.get("X-UniProt-Release")
                       or r_meta.headers.get("X-UniProt-Release"))
    uniprot_release_date = (r_fasta.headers.get("X-UniProt-Release-Date")
                            or r_meta.headers.get("X-UniProt-Release-Date"))

    # --- Verify ---
    try:
        size = os.path.getsize(filepath)
    except OSError:
        size = 0
    if size == 0:
        try:
            os.remove(filepath)
        except OSError:
            pass
        yield _sse({"phase": "_result", "status": "empty", "filename": filename})
        return

    yield _sse({"phase": "_result", "status": "saved", "filename": filename, "size_bytes": size,
                "species": organism_name, "uniprot_release": uniprot_release,
                "uniprot_release_date": uniprot_release_date})


@app.route("/stream_download")
def stream_download():
    """
    Streamed download endpoint (Server-Sent Events).

    Query parameters:
        ids:   comma-separated UniProt proteome IDs (e.g. UP000000625,UP000007137)
        mode:  "all" (default) — wipe Proteomas/ and download from scratch
               "retry"          — keep existing FASTAs, only fetch the listed IDs

    Event format: each event is a JSON object on a "data:" line. Phases:
        start            { total }
        proteome_start   { pid, current, total }
        attempt          { pid, attempt, step: "metadata"|"fasta" }
        metadata_ok      { pid, species, filename }
        retry_wait       { pid, attempt, seconds }
        proteome_saved   { pid, filename, size_bytes, species }
        proteome_empty   { pid, filename }
        proteome_failed  { pid, attempts, reason }
        done             { downloaded:[...], failed:[...], empty:[...] }
    """
    raw_ids = request.args.get("ids", "").strip()
    mode = request.args.get("mode", "all")

    proteome_ids = [pid.strip() for pid in raw_ids.split(",") if pid.strip()]

    # Remember the selection so the run snapshot can record exactly which
    # proteomes were used — feeds the "Reproduce this analysis" feature.
    if proteome_ids:
        session['species_ids'] = proteome_ids

    def generate():
        if not proteome_ids:
            yield _sse({"phase": "done", "downloaded": [], "failed": [], "empty": [],
                        "error": "No proteome IDs provided."})
            return

        # In "all" mode we clean the folder first; in "retry" we preserve it.
        if mode != "retry":
            try:
                os.makedirs(PROTEOMES_FOLDER, exist_ok=True)
                for entry in os.listdir(PROTEOMES_FOLDER):
                    p = os.path.join(PROTEOMES_FOLDER, entry)
                    try:
                        if os.path.isfile(p):
                            os.remove(p)
                        elif os.path.isdir(p):
                            shutil.rmtree(p)
                    except Exception as e:
                        logging.warning(f"Could not delete {p}: {e}")
            except Exception as e:
                logging.warning(f"Could not clean {PROTEOMES_FOLDER}: {e}")

        downloaded, failed, empty = [], [], []

        yield _sse({"phase": "start", "total": len(proteome_ids), "mode": mode})

        for idx, pid in enumerate(proteome_ids, start=1):
            yield _sse({"phase": "proteome_start", "pid": pid, "current": idx, "total": len(proteome_ids)})

            last_reason = "unknown"
            result = None

            for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
                if attempt > 1:
                    wait = DOWNLOAD_BACKOFF_SECONDS[min(attempt - 2, len(DOWNLOAD_BACKOFF_SECONDS) - 1)]
                    yield _sse({"phase": "retry_wait", "pid": pid, "attempt": attempt, "seconds": wait,
                                "reason": last_reason})
                    time.sleep(wait)

                # Stream the inner events from this attempt
                for ev in _attempt_download_one(pid, attempt):
                    if ev.startswith('data: {"phase": "_result"'):
                        # Final result of this attempt — parse to decide next step
                        payload = json.loads(ev[len("data: "):].strip())
                        result = payload
                        break
                    else:
                        yield ev

                if result and result.get("status") == "saved":
                    break  # success, no more attempts needed
                if result and result.get("status") == "empty":
                    break  # empty file — don't retry, just report
                # otherwise failed: keep last reason and (maybe) retry
                last_reason = (result or {}).get("reason", "unknown error")

            if result and result.get("status") == "saved":
                downloaded.append({
                    "pid": pid,
                    "filename": result.get("filename"),
                    "species": result.get("species"),
                    "size_bytes": result.get("size_bytes", 0),
                    "uniprot_release": result.get("uniprot_release"),
                    "uniprot_release_date": result.get("uniprot_release_date"),
                })
                yield _sse({"phase": "proteome_saved", "pid": pid,
                            "filename": result.get("filename"),
                            "species": result.get("species"),
                            "size_bytes": result.get("size_bytes", 0)})
            elif result and result.get("status") == "empty":
                empty.append({"pid": pid, "filename": result.get("filename")})
                yield _sse({"phase": "proteome_empty", "pid": pid, "filename": result.get("filename")})
            else:
                failed.append({"pid": pid, "attempts": MAX_DOWNLOAD_ATTEMPTS, "reason": last_reason})
                yield _sse({"phase": "proteome_failed", "pid": pid,
                            "attempts": MAX_DOWNLOAD_ATTEMPTS, "reason": last_reason})

        # Persist the UniProt release that produced these proteomes. Written to
        # PROTEOMES_FOLDER (the working dir at download time — folder_path isn't
        # set until OrthoFinder results are loaded); _render_result_and_cache
        # then copies it into folder_path so build_provenance + the snapshot
        # pick it up. Session writes don't survive a streamed response, hence a
        # file. Releases are normally uniform; we record the spread just in case.
        try:
            releases = sorted({d.get("uniprot_release") for d in downloaded if d.get("uniprot_release")})
            if releases:
                rel_dates = sorted({d.get("uniprot_release_date") for d in downloaded if d.get("uniprot_release_date")})
                with open(os.path.join(PROTEOMES_FOLDER, "proteome_provenance.json"), "w") as f:
                    json.dump({
                        "source": "UniProt (rest.uniprot.org)",
                        "release": releases[0] if len(releases) == 1 else releases,
                        "release_date": (rel_dates[0] if len(rel_dates) == 1 else rel_dates) if rel_dates else None,
                        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "n_proteomes": len(downloaded),
                    }, f)
        except Exception as e:
            logging.warning(f"[proteome] could not persist proteome_provenance.json: {e}")

        yield _sse({"phase": "done",
                    "downloaded": downloaded,
                    "failed": failed,
                    "empty": empty})

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


############################################################################################################
# Run history — snapshot + summary helpers
############################################################################################################

@app.route('/stream_orthofinder')
def stream_orthofinder():
    import zipfile
    import os

    def generate():
        start_time = time.time()
        t, a = _orthofinder_thread_settings()
        logging.info(
            f"OrthoFinder threads → -t {t} (sequence search) / -a {a} "
            f"(analysis) [host has {os.cpu_count()} CPUs]"
        )
        yield (f"data: ⚙️  Using -t {t} (sequence-search threads) and -a {a} "
               f"(analysis threads) — detected {os.cpu_count()} CPUs\n\n")
        process = subprocess.Popen(
            ["orthofinder", "-f", PROTEOMES_FOLDER,
             "-t", str(t), "-a", str(a), "-og"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        of_version = None
        for line in iter(process.stdout.readline, ''):
            stripped = line.strip()
            # Capture the exact OrthoFinder release from its banner so provenance
            # records which version produced the orthogroups. (This is the
            # endpoint the UI actually streams — /run_orthofinder is legacy.)
            if of_version is None:
                m = re.search(r"OrthoFinder version (\S+)", stripped)
                if m:
                    of_version = m.group(1)
            yield f"data: {stripped}\n\n"

        process.stdout.close()
        process.wait()

        # Persist the OrthoFinder version next to the other run outputs. Written
        # to PROTEOMES_FOLDER (folder_path isn't set until results are loaded);
        # it survives cleanup_temp_run and is copied into the analysis folder by
        # _render_result_and_cache, so build_provenance + the snapshot pick it up.
        try:
            with open(os.path.join(PROTEOMES_FOLDER, "orthofinder_provenance.json"), "w") as f:
                json.dump({"version": of_version, "source": "OrthoFinder"}, f)
        except Exception as e:
            logging.warning(f"[orthofinder] could not persist version: {e}")

        resultados_base = os.path.join(PROTEOMES_FOLDER, "OrthoFinder")
        subdirs = [d for d in os.listdir(resultados_base) if d.startswith("Results_")]
        if not subdirs:
            yield "data: ❌ No 'Results_' folder found.\n\n"
            yield "data: DONE\n\n"
            return

        latest_result = sorted(subdirs)[-1]
        results_full_path = os.path.join(resultados_base, latest_result)
        orthogroups_path = os.path.join(results_full_path, "Orthogroups")

        files_to_zip = [
            "Orthogroups.tsv",
            "Orthogroups.txt",
            "Orthogroups.GeneCount.tsv",
            "Orthogroups_UnassignedGenes.tsv"
        ]

        zip_path = os.path.join(PROTEOMES_FOLDER, "Orthogroups.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for filename in files_to_zip:
                file_path = os.path.join(orthogroups_path, filename)
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=filename)
                    yield f"data: ✔️ Added to ZIP: {filename}\n\n"
                else:
                    yield f"data: ⚠️ Missing file: {filename}\n\n"

        # ── Persist run to history (saves stats + Orthogroups.zip, drops FASTAs) ──
        try:
            run_id = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            duration = time.time() - start_time
            meta = _snapshot_run(results_full_path, run_id, duration)
            session['last_run_id'] = run_id
            yield f"data: 💾 Saved run to history ({run_id}, {len(meta.get('species', []))} species)\n\n"

            # Clean up the FASTAs + intermediates (heavy stuff we no longer need)
            _cleanup_temp_run()
            yield f"data: 🧹 Cleaned up temporary files (FASTAs + intermediates)\n\n"
        except Exception as e:
            yield f"data: ⚠️ Could not snapshot run: {e}\n\n"

        yield "data: ✅ OrthoFinder completed successfully.\n\n"
        yield "data: DONE\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ── Run summary + history endpoints ────────────────────────────────────────
@app.route('/run_summary')
def run_summary():
    """Return JSON summary for the most recent run (from history)."""
    # Try to use the session-tracked ID first; fall back to latest
    run_id = session.get('last_run_id')
    if run_id:
        meta_path = HISTORY_DIR / run_id / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                return jsonify(json.load(f))
    runs = _list_history()
    if not runs:
        return respond_error("ERR_NO_RUNS_FOUND")
    return jsonify(runs[0])


@app.route('/history')
def history_page():
    return render_template('history.html', runs=_list_history())


@app.route('/api/history')
def api_history():
    return jsonify(_list_history())


@app.route('/history/<run_id>/load')
def history_load(run_id):
    """Restore a saved run as the active analysis.

    Edge case: a run's Orthogroups.zip may be missing (interrupted snapshot,
    manual deletion, disk corruption). Instead of returning a raw JSON error
    that the browser shows as plain text, we redirect back to /history with
    a flash message so the user sees a clear explanation and can keep
    browsing their other runs.
    """
    run_dir = HISTORY_DIR / run_id
    zip_src = run_dir / "Orthogroups.zip"
    if not zip_src.exists():
        flash(
            f"This run can't be opened — its Orthogroups.zip is missing on "
            f"disk (run id: {run_id}). The metadata is still here, but the "
            f"results were not snapshotted successfully. You can delete this "
            f"entry from the menu (⋮ → Delete).",
            "error",
        )
        return redirect(url_for('history_page'))
    dest_zip = Path(PROTEOMES_FOLDER) / "Orthogroups.zip"
    shutil.copy2(zip_src, dest_zip)
    session['last_run_id'] = run_id
    # Load from the copied run zip (Proteomas/Orthogroups.zip) via the 'generated'
    # branch. Using 'preselected' here was a bug: that branch reads the bundled
    # static/Orthogroups.zip instead, so opening any saved run showed the wrong
    # (demo) species rather than the run's own.
    return redirect(url_for('cargar_carpeta', filename='Orthogroups.zip', modo='generated'))


@app.route('/history/<run_id>/delete', methods=['POST', 'DELETE'])
def history_delete(run_id):
    run_dir = HISTORY_DIR / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    return jsonify({"ok": True})


@app.route('/history/<run_id>/reproduce')
def history_reproduce(run_id):
    """Pre-fill the species picker with the same proteome IDs the user picked
    for this past run and redirect to /1-seleccion_especies. Enables a
    one-click "reproduce this analysis" flow."""
    meta_path = HISTORY_DIR / run_id / "meta.json"
    if not meta_path.exists():
        return respond_error("ERR_RUN_NOT_FOUND")
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        return respond_error("ERR_RUN_READ_FAILED")
    ids = meta.get("species_ids") or []
    if not ids:
        return ("This run was saved before the reproducibility feature was "
                "added, so the original proteome IDs are not stored. Please "
                "rerun the analysis manually."), 400
    # Session key the species selection page reads on load
    session['prefill_species_ids'] = list(ids)
    return redirect(url_for('species_selection_page'))


@app.route('/compare')
def compare_runs():
    """Side-by-side view of two saved runs. Reads /compare?a=<id>&b=<id>."""
    a_id = request.args.get("a", "").strip()
    b_id = request.args.get("b", "").strip()
    if not a_id or not b_id:
        return render_template(
            "compare.html",
            error="Pick two runs to compare. Use the Compare button on the History page.",
            runs=_list_history(),
            a=None, b=None, deltas=None,
        )
    a = _load_run_for_compare(a_id)
    b = _load_run_for_compare(b_id)

    # Surface the most actionable message for the user. Order matters:
    # "missing" (truly deleted) > "pre-feature" (data intact but old) > "read-failed".
    def _explain(run, label):
        if not run or "_error" not in run:
            return None
        rid = run.get("id", "?")
        if run["_error"] == "missing":
            return (f"Run {label} ({rid}) no longer exists on disk — it may have been "
                    f"deleted. Pick a different run from the History page.")
        if run["_error"] == "pre-feature":
            return (f"Run {label} ({rid}) was saved before the Compare feature was "
                    f"added, so it doesn't include Orthogroups.GeneCount.tsv on disk. "
                    f"Re-run that analysis (Reproduce → Run OrthoFinder) and the new "
                    f"snapshot will be compatible.")
        if run["_error"] == "read-failed":
            return (f"Run {label} ({rid}) is on disk but its files can't be read: "
                    f"{run.get('detail', '?')}.")
        return f"Run {label} ({rid}) could not be loaded."

    err_msg = _explain(a, "A") or _explain(b, "B")
    if err_msg:
        return render_template(
            "compare.html",
            error=err_msg,
            runs=_list_history(),
            a=None, b=None, deltas=None,
        )
    # Pre-compute the headline deltas so the template stays simple.
    sa, sb = a["summary"] or {}, b["summary"] or {}
    def _delta(key):
        va, vb = sa.get(key), sb.get(key)
        if va is None or vb is None: return None
        return vb - va
    deltas = {
        "total_orthogroups":        _delta("total_orthogroups"),
        "single_copy_orthogroups":  _delta("single_copy_orthogroups"),
        "species_specific_orthogroups": _delta("species_specific_orthogroups"),
        "mean_pct_in_og":           _delta("mean_pct_in_og"),
        "n_species":                _delta("n_species"),
    }
    return render_template("compare.html", a=a, b=b, deltas=deltas, error=None, runs=None)


@app.route('/history/<run_id>/cite.bib')
def history_cite_bib(run_id):
    ctx = _build_citation_context(run_id)
    if ctx is None:
        return respond_error("ERR_RUN_NOT_FOUND")
    bib = _bibtex_for_run(ctx)
    resp = Response(bib, mimetype='application/x-bibtex')
    resp.headers['Content-Disposition'] = f'attachment; filename="orthogather-{run_id}.bib"'
    return resp


@app.route('/history/<run_id>/cite.ris')
def history_cite_ris(run_id):
    ctx = _build_citation_context(run_id)
    if ctx is None:
        return respond_error("ERR_RUN_NOT_FOUND")
    ris = _ris_for_run(ctx)
    resp = Response(ris, mimetype='application/x-research-info-systems')
    resp.headers['Content-Disposition'] = f'attachment; filename="orthogather-{run_id}.ris"'
    return resp


@app.route('/api/prefill_species')
def api_prefill_species():
    """Returns (and clears) the prefill list so the species selection page can
    pre-populate chips on first load."""
    ids = session.pop('prefill_species_ids', []) or []
    return jsonify({"ids": ids})


@app.route('/history/<run_id>/rename', methods=['POST'])
def history_rename(run_id):
    meta_path = HISTORY_DIR / run_id / "meta.json"
    if not meta_path.exists():
        return respond_error("ERR_RUN_NOT_FOUND")
    new_name = (request.json or {}).get('name', '').strip() or None
    with open(meta_path) as f:
        meta = json.load(f)
    meta['name'] = new_name
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    return jsonify({"ok": True, "meta": meta})

# /generate_tree_image (ete3 phylogenetic tree route) was removed on 2026-05-25.
# Replaced 2026-05-26 by /api/taxonomy_tree (Point 11): NCBI taxonomic tree
# built from UniProt lineages, cached locally, rendered client-side with D3.
# No ete3 dependency.

@app.route('/api/disk_usage', methods=['GET'])
def api_disk_usage():
    """Return current size of every runtime directory the tool maintains.

    Useful for a 'how much is my analysis costing me' panel in the UI, and
    for the user to verify the startup-hygiene pass did its job. Sizes are
    rounded to 1 decimal MB.
    """
    return jsonify(_disk_usage_report())


@app.route('/api/session_species_taxids', methods=['GET'])
def api_session_species_taxids():
    """Resolve the active analysis's species names → taxon_ids.

    Used by the *Taxonomic tree* top button on the Protein Analysis page
    (and any other page that needs the current session's species enriched
    with NCBI taxon IDs without re-loading the catalogue client-side).

    Looks up species in the following order:
      1. ``session['species_matches']`` — already matched at /resultado_goa.
      2. ``session['species']`` — falls back to fresh match_species().

    Returns ``{"species": [{"name": <original>, "taxon_id": "<str>"}, ...]}``
    with empty taxon_id strings for species we couldn't match.
    """
    # session['species'] is `gene_count_df.columns[1:]`, which trails a "Total"
    # column (a per-row sum, not a species). Filter it out everywhere we
    # iterate over the list as if it were real species.
    def _drop_total(names):
        return [n for n in names if n != 'Total']

    matches = session.get('species_matches')
    if matches:
        matches = [m for m in matches
                   if (m.get('original') or m.get('base') or '') != 'Total']
    if not matches:
        species = _drop_total(list(session.get('species', []) or []))
        if not species:
            return jsonify({"species": []})
        try:
            proteomes = load_proteomes(JSON_PATH)
            matches = match_species(species, proteomes)
        except Exception as e:
            logging.warning(f"[taxonomy] match_species failed in session route: {e}")
            return jsonify({"species": [{"name": s, "taxon_id": ""} for s in species]})

    out = []
    for m in matches:
        name = m.get("original") or m.get("base") or ""
        tid = ""
        match_obj = m.get("match") or {}
        if isinstance(match_obj, dict):
            tid = str(match_obj.get("taxon_id") or "")
        if name:
            out.append({"name": name, "taxon_id": tid})
    return jsonify({"species": out})


@app.route('/api/taxonomy_tree', methods=['POST'])
def api_taxonomy_tree():
    """Build a taxonomic tree for a user-selected set of species.

    Request body
    ------------
    ``{"species": [{"name": <display>, "taxon_id": <ncbi_id>}, ...]}``

    Response
    --------
    ``{
        "tree":     <nested dict, d3.hierarchy()-ready>,
        "newick":   <Newick string for iTOL / FigTree export>,
        "summary":  <diversity counts: n_leaves, n_phyla, n_classes, ...>,
        "lineages": {taxon_id: {fetched_at, source, source_release}, ...}
       }``

    The first call for a given taxon_id hits UniProt's REST taxonomy
    endpoint; subsequent calls reuse the on-disk cache at
    ``static/Proteomes_json/taxonomy_lineage.json``. Failures fall under
    "Unknown lineage" rather than dropping species silently.
    """
    from orthogather.core import taxonomy as tax_mod

    payload = request.get_json(silent=True) or {}
    species = payload.get("species", []) or []
    if not species:
        return respond_error("ERR_TAXONOMY_NO_SPECIES", where="api_taxonomy_tree")

    pairs = []
    invalid = []
    for s in species:
        name = (s.get("name") or "").strip()
        tid = str(s.get("taxon_id") or "").strip()
        if not name or not tid.isdigit():
            invalid.append(s)
            continue
        pairs.append((name, tid))

    if not pairs:
        return respond_error("ERR_TAXONOMY_INVALID_TAXID",
                              where="api_taxonomy_tree",
                              detail=f"No valid (name, taxon_id) pairs in {len(species)} entries")

    try:
        lineages = tax_mod.get_lineages_bulk(pairs)
    except Exception as e:
        logging.exception("Taxonomy bulk fetch failed")
        return respond_error("ERR_TAXONOMY_FETCH_FAILED",
                              where="api_taxonomy_tree", detail=str(e))

    full_tree = tax_mod.build_taxonomy_tree(pairs, lineages=lineages)
    summary   = tax_mod.summarize_diversity(full_tree)
    trimmed   = tax_mod.trim_to_lca(full_tree)
    newick    = tax_mod.to_newick(trimmed)

    # Strip the heavy `lineage` list out of the response to keep payloads
    # small — frontend only needs the fetched_at/source metadata.
    lineage_meta = {tid: {k: v for k, v in entry.items() if k != "lineage"}
                    for tid, entry in lineages.items()}

    return respond(True, "Taxonomy tree built", where="api_taxonomy_tree",
                   payload={
                       "tree": trimmed,
                       "newick": newick,
                       "summary": summary,
                       "lineages_meta": lineage_meta,
                       "n_unresolved": len(pairs) - len(lineages),
                   })


@app.route('/tutorial')
def tutorial():
    """Long-form tutorial page — Protein Analysis + Gene Ontology walkthroughs."""
    return render_template('tutorial.html')


@app.route('/resultado_goa')
def resultado_goa():
    modo = session.get("modo")
    species = None

    # Prefer using the species list already stored in session if available
    if session.get("species"):
        species = session["species"]

    if species is None:
        # Load species according to mode
        if modo == "preselected":
            zip_path = os.path.join("static", "Orthogroups.zip")
            if not os.path.exists(zip_path):
                return (f"The preselected dataset is missing on disk (expected "
                        f"at {zip_path}). This usually means the install is "
                        f"incomplete — reinstall OrthoGather or pick another "
                        f"entry point from the home page."), 400
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open("Orthogroups.tsv") as f:
                    df = pd.read_csv(f, sep="\t", nrows=0)
                    species = list(df.columns[1:])

        elif modo == "generated":
            zip_path = os.path.join("Proteomas", "Orthogroups.zip")
            if not os.path.exists(zip_path):
                return ("The OrthoFinder output ZIP wasn't found at "
                        f"{zip_path}. This usually means the analysis hasn't "
                        f"finished yet, or it was cleaned up. Open History → "
                        f"Open on a previous run, or start a new analysis."), 400
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open("Orthogroups.tsv") as f:
                    df = pd.read_csv(f, sep="\t", nrows=0)
                    species = list(df.columns[1:])

        elif modo == "upload":
            folder_path = session.get("folder_path", "")
            if not folder_path:
                return ("No uploaded folder is currently active in this browser "
                        "session. Upload the OrthoFinder ZIP from the home page "
                        "(External Upload) first."), 400
            tsv_path = os.path.join(folder_path, "Orthogroups.tsv")
            if not os.path.exists(tsv_path):
                return (f"The uploaded folder is missing Orthogroups.tsv "
                        f"(checked at {tsv_path}). Make sure the ZIP you "
                        f"uploaded contains OrthoFinder's Orthogroups/ output."), 400
            df = pd.read_csv(tsv_path, sep="\t", nrows=0)
            species = list(df.columns[1:])

        else:
            return (f"Unknown analysis mode '{modo}'. Valid modes: preselected, "
                    f"generated, upload. Start over from the home page."), 400

    # Load available proteomes (with GOA or from the general JSON)
    proteomes = load_proteomes(JSON_PATH)

    # Automatic species matching
    species_cache = match_species(species, proteomes)

    # Save information in session
    session["species_detected"] = species
    session["species_matches"] = species_cache

    return render_template("resultado_goa.html", results=species_cache)

def _read_goa_mapping():
    """species -> downloaded GOA filename for the active analysis.

    Prefers ``session['goa_mapping']`` but falls back to the on-disk copy
    written by the streaming /download_goa_files. The download runs as a
    streamed SSE response, and Flask saves the session *before* the body
    streams, so a ``session[...] = ...`` inside the generator never persists —
    hence the JSON file alongside the orthogroups working dir.
    """
    mp = session.get("goa_mapping")
    if mp:
        return mp
    fp = session.get("folder_path")
    if fp:
        path = os.path.join(fp, "goa_mapping.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"[GOA] could not read goa_mapping.json: {e}")
    return {}


# HTTP statuses worth retrying — transient server/network conditions. A plain
# 404/403 means the file genuinely isn't at EBI (its GOA proteome set doesn't
# cover every UniProt proteome, and some entries in our catalogue are stale), so
# retrying is futile and only makes the user wait — fail fast on those instead.
_GOA_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_GOA_MAX_RETRIES = 6


def _download_goa_file(url, outpath):
    """Fetch one GOA file with retries. Returns ``(status, detail)`` where status is:

        "ok"      — saved to ``outpath``
        "missing" — deterministic 4xx (file not served by EBI); NOT retried
        "failed"  — transient errors, retries exhausted

    Transient failures back off exponentially (2s, 4s, 8s, 16s, capped at 20s)
    so flaky-network / rate-limited fetches get several genuine chances.
    """
    delay = 2
    detail = ""
    for attempt in range(1, _GOA_MAX_RETRIES + 1):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(outpath, "wb") as f:
                    f.write(r.content)
                return "ok", ""
            detail = f"HTTP {r.status_code}"
            # Deterministic client error → the file isn't there; don't retry.
            if 400 <= r.status_code < 500 and r.status_code not in _GOA_RETRYABLE_STATUS:
                return "missing", detail
        except requests.exceptions.RequestException as e:
            detail = str(e)
        if attempt < _GOA_MAX_RETRIES:
            time.sleep(min(delay, 20))
            delay *= 2
    return "failed", detail


@app.route("/download_goa_files", methods=["POST"])
def download_goa_files():
    """
    Downloads the selected GOA files from the matching table, clears GOAfiles/,
    and generates 'Gene_Ontology_Analysis.xlsx'.

    Streams Server-Sent Events so the page can show a live ``k / total`` counter
    while each species' GOA file is fetched (downloads can take a while because
    of per-file retries). SSE phases:
        start     { total }
        progress  { done, total, ok, species }   ← one per species
        excel                                     ← building the workbook
        done      { success, downloaded, failed, total }
        error     { reason }

    The species->filename mapping is persisted to ``<folder_path>/goa_mapping.json``
    (not the session) because the session can't be written mid-stream; the GO
    analysis reads it back via _read_goa_mapping().
    """
    data = request.get_json(silent=True) or {}
    species_to_url = data.get("species_to_url", {})
    # Read session-scoped paths here, in the request body — reading them inside
    # the streamed generator is fine, but doing it up-front keeps the generator
    # free of request-context assumptions.
    folder_path = session.get('folder_path')

    def generate():
        try:
            if not species_to_url:
                yield _sse({"phase": "error",
                            "reason": "No GOA URLs received. Select species with valid GOA and try again."})
                return
            if not folder_path or not os.path.exists(folder_path):
                yield _sse({"phase": "error",
                            "reason": "Working directory not prepared. Reload orthogroups (Upload/Preselected/Generated)."})
                return
            orthogroups_path = os.path.join(folder_path, 'Orthogroups.tsv')
            if not os.path.exists(orthogroups_path):
                yield _sse({"phase": "error",
                            "reason": "Orthogroups.tsv not found. Make sure orthogroups were loaded correctly."})
                return

            logging.info("[INFO] download_goa_files: cleaning GOAfiles/")
            clear_goa_dir(GOA_DOWNLOAD_FOLDER)
            os.makedirs(GOA_DOWNLOAD_FOLDER, exist_ok=True)

            total = len(species_to_url)
            yield _sse({"phase": "start", "total": total})

            downloaded, missing, failed = [], [], []
            goa_mapping = {}
            done = 0

            for species, url in species_to_url.items():
                filename = None
                if url and isinstance(url, str):
                    filename = url.split("/")[-1] or f"{normalize(species)}.goa"
                    outpath = os.path.join(GOA_DOWNLOAD_FOLDER, filename)
                    status, detail = _download_goa_file(url, outpath)
                    if status != "ok":
                        logging.warning(f"[GOA] {species}: {status} ({detail}) {url}")
                else:
                    status = "missing"

                done += 1
                if status == "ok" and filename:
                    downloaded.append(filename)
                    goa_mapping[species] = filename
                elif status == "missing":
                    missing.append(species)
                else:
                    failed.append(species)
                yield _sse({"phase": "progress", "done": done, "total": total,
                            "status": status, "species": species})

            # Persist the mapping to disk (see _read_goa_mapping for why).
            try:
                with open(os.path.join(folder_path, "goa_mapping.json"), "w") as f:
                    json.dump(goa_mapping, f)
            except Exception as e:
                logging.warning(f"[GOA] could not persist goa_mapping.json: {e}")

            # Provenance: record WHEN these GOA annotations were fetched and from
            # where, plus the real upstream data version EBI/UniProt stamps into
            # each file header (date-generated + GO-version). The download date
            # alone isn't enough — EBI regenerates the data periodically, so two
            # downloads of the "same" species months apart can differ. Read back
            # by build_provenance().
            try:
                gen_dates, go_versions = set(), set()
                for _fn in downloaded:
                    _h = read_goa_header(os.path.join(GOA_DOWNLOAD_FOLDER, _fn))
                    if _h.get("date_generated"):
                        gen_dates.add(_h["date_generated"])
                    if _h.get("go_version"):
                        go_versions.add(_h["go_version"])
                gen_sorted = sorted(gen_dates)
                gv_sorted = sorted(go_versions)
                with open(os.path.join(folder_path, "goa_provenance.json"), "w") as f:
                    json.dump({
                        "downloaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "source": "EBI GOA proteomes (ftp.ebi.ac.uk/pub/databases/GO/goa/proteomes)",
                        "n_files": len(downloaded),
                        "n_missing": len(missing),
                        "n_failed": len(failed),
                        # Real EBI data version(s): a single string when uniform,
                        # else the list so a mixed set is visible, not hidden.
                        "data_generated": (gen_sorted[0] if len(gen_sorted) == 1 else gen_sorted) or None,
                        "go_version": (gv_sorted[0] if len(gv_sorted) == 1 else gv_sorted) or None,
                    }, f)
            except Exception as e:
                logging.warning(f"[GOA] could not persist goa_provenance.json: {e}")

            yield _sse({"phase": "excel"})
            os.makedirs(RESULTS_FOLDER, exist_ok=True)
            output_excel = os.path.join(RESULTS_FOLDER, 'Gene_Ontology_Analysis.xlsx')
            try:
                excel_summary = generate_go_excel(orthogroups_path, goa_mapping, output_excel,
                                                   provenance=build_provenance())
            except Exception as e:
                logging.error(f"[GOA] Excel generation failed: {e}")
                yield _sse({"phase": "error", "reason": f"Excel generation failed: {e}"})
                return

            logging.info(f"✅ GOA Excel saved at {output_excel}")
            logging.info(f"🧬 Species (TSV) with GOA: {len(excel_summary.get('species_with_goa', []))} / {excel_summary.get('n_species_cols')}")
            if excel_summary.get("species_without_goa"):
                arr = excel_summary["species_without_goa"]
                logging.warning(f"⚠️ Without GOA (TSV): {arr[:8]}{'...' if len(arr)>8 else ''}")

            yield _sse({"phase": "done", "success": True,
                        "downloaded": len(downloaded), "missing": len(missing),
                        "failed": len(failed), "total": total,
                        "missing_species": missing, "failed_species": failed})

        except Exception as e:
            logging.error(f"[GOA] stream error: {e}")
            yield _sse({"phase": "error", "reason": f"Unexpected error: {e}"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.route("/download_go_excel")
def download_go_excel():
    output_excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
    if not os.path.exists(output_excel_path):
        return respond_error("ERR_EXCEL_NOT_GENERATED")
    # Descriptive filename: include species count + ISO date so the user can
    # tell several downloads apart on disk.
    from orthogather.utils.filenames import descriptive_filename
    species = session.get('species') or []
    ctx = [f"{len(species)}species"] if species else []
    fmt = (request.args.get("fmt") or "xlsx").lower()
    if fmt in ("csv", "tsv"):
        sep = "," if fmt == "csv" else "\t"
        buf = _xlsx_to_delimited_zip(output_excel_path, sep)
        dl_name = descriptive_filename("GOA-orthogroup-annotation", "zip", context=ctx + [fmt])
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=dl_name)
    dl_name = descriptive_filename(
        "GOA-orthogroup-annotation", "xlsx", context=ctx or None,
    )
    return send_file(output_excel_path, as_attachment=True, download_name=dl_name)

@app.route("/fix_taxid", methods=["POST"])
def fix_taxid():
    try:
        data = request.get_json(silent=True) or {}
        taxon_id = data.get("taxon_id")
        species_name = data.get("species_name")  # alternate to taxon_id
        original = data.get("original")

        if not original or (not taxon_id and not species_name):
            return respond(False, "Missing taxon_id (or species_name) and/or original name",
                           where="fix_taxid",
                           hint="Send { taxon_id, original } or { species_name, original } in the request body.",
                           code=400)

        # Load proteomes from JSON
        proteomes = load_proteomes(JSON_PATH)
        match = None
        if taxon_id:
            match = next(
                (p for p in proteomes if str(p.get("taxon_id")) == str(taxon_id)),
                None
            )
        if not match and species_name:
            # Reuse the robust matcher (handles "E. coli" etc.) — single-name match
            try:
                name_matches = match_species([species_name], proteomes)
                if name_matches and name_matches[0].get("match"):
                    match = name_matches[0]["match"]
            except Exception:
                match = None

        if not match:
            return respond(False, "No match found for Taxon ID or species name",
                           where="fix_taxid",
                           hint="Verify the taxon_id / species name against the proteomes JSON file.",
                           code=404)

        return respond(True, "Taxon fixed",
                       where="fix_taxid",
                       payload={
                           "found": True,
                           "label": match.get("label"),
                           "has_file": bool(match.get("file_url") and match["file_url"] != "NA"),
                           "file_url": match.get("file_url", "")
                       })

    except Exception as e:
        return respond(False, f"Unexpected error in fix_taxid: {e}",
                       where="fix_taxid",
                       hint="Check the proteomes JSON and the request data.",
                       code=500)

@app.route("/run_go_analysis", methods=["POST"])
def run_go_analysis():
    # Vestigial route — was the legacy entry point for the matplotlib
    # annotation-distribution PNG. The frontend no longer calls this; the
    # data is delivered as JSON by /generate_go_image and rendered with
    # Plotly client-side. Kept as a stub returning a redirect-style hint
    # for any external caller that might still hit the URL.
    return respond_error("ERR_NOT_FOUND_404",
                          where="run_go_analysis",
                          detail="This route has been replaced by /generate_go_image "
                                 "which returns the distribution data as JSON.",
                          http_code=410)

@app.route('/foreground_analysis', methods=['POST'])
def foreground_analysis():
    """Stores the foreground (pasted IDs or orthogroup-expanded IDs) in session, with detailed logs."""
    try:
        data = request.get_json(silent=True) or {}
        uniprot_ids = parse_uniprot_block(data.get('uniprot_ids', []))
        use_orthogroups = bool(data.get('use_orthogroups', False))
        single_copy_only = bool(data.get('single_copy_only', False))
        logging.info(f"[FG] Received UniProt IDs (n={len(uniprot_ids)}): {uniprot_ids}")
        logging.info(f"[FG] Use Orthogroups flag: {use_orthogroups}")
        logging.info(f"[FG] Single-copy-only flag: {single_copy_only}")

        if not uniprot_ids:
            return respond(False, "No UniProt IDs provided",
                           where="foreground_analysis",
                           hint="Paste at least one UniProt ID.",
                           code=400)

        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            logging.error(f"[FG][ERR] Gene Ontology Analysis file not found at: {excel_path}")
            return respond(False, "Gene Ontology Analysis file not found.",
                           where="foreground_analysis",
                           hint="Click 'Download GOA files' first.",
                           code=404)

        logging.info("[FG] Loading sheets from Excel file ...")
        try:
            initial_orthogroups = pd.read_excel(excel_path, sheet_name='Initial Groups')
            orthogroups_of_interest   = pd.read_excel(excel_path, sheet_name='Groups of Interest')
        except Exception as e:
            logging.error(f"[FG][ERR] Failed reading sheets: {e}")
            return respond(False, f"Malformed Excel file: {e}",
                           where="foreground_analysis",
                           hint="Re-generate the Excel using 'Download GOA files'.",
                           code=500)
        logging.info(f"[FG] Sheets loaded. Initial Groups rows={len(initial_orthogroups)}, Groups of Interest rows={len(orthogroups_of_interest)}")

        # Expand by orthogroups
        uniprot_set = set(uniprot_ids)
        selected_orthogroups = set()
        protein_set = set()

        if use_orthogroups:
            # Detect orthogroups containing any of the provided IDs
            hits_ogs = 0
            for _, row in initial_orthogroups.iterrows():
                og = row['Orthogroup']
                proteins = row[1:]
                for protein in proteins.dropna():
                    s = str(protein)
                    hits = re.findall(r'\|([^|]+)\|', s)
                    if any(uid in uniprot_set for uid in hits):
                        selected_orthogroups.add(og)
                        hits_ogs += 1
                        break
            logging.info(f"[FG] Orthogroups matched by pasted IDs: {hits_ogs}")

            # Optional: restrict to single-copy orthogroups (1:1:1... orthologs)
            if single_copy_only:
                sc_set = get_single_copy_orthogroups()
                before = len(selected_orthogroups)
                selected_orthogroups = {og for og in selected_orthogroups if og in sc_set}
                logging.info(f"[FG] Single-copy filter: {before} -> {len(selected_orthogroups)} OGs")

            # Expand IDs from 'Groups of Interest'
            exp_added = 0
            for og in selected_orthogroups:
                sub = orthogroups_of_interest[orthogroups_of_interest['Orthogroup'] == og]
                for _, row in sub.iterrows():
                    proteins = row.dropna().astype(str)
                    for protein in proteins:
                        if protein not in ('Annotation Percentage', 'Porcentaje de Anotación'):
                            ids = re.findall(r'\|([^|]+)\|', protein)
                            protein_set.update(ids)
                            exp_added += len(ids)
            logging.info(f"[FG] Expanded foreground IDs added from orthogroups: {exp_added}")

            if not selected_orthogroups:
                logging.warning("[FG][WARN] No orthogroups matched the provided UniProt IDs.")
        else:
            protein_set.update(uniprot_ids)
            # Report which orthogroups contain any of the IDs (useful info)
            hits_ogs = 0
            for _, row in initial_orthogroups.iterrows():
                og = row['Orthogroup']
                proteins = row[1:]
                for protein in proteins.dropna():
                    s = str(protein)
                    hits = re.findall(r'\|([^|]+)\|', s)
                    if any(uid in uniprot_set for uid in hits):
                        selected_orthogroups.add(og)
                        hits_ogs += 1
                        break
            logging.info(f"[FG] Orthogroups containing at least one pasted ID: {hits_ogs}")

        final_protein_list = sorted(protein_set)
        selected_orthogroups_list = sorted(selected_orthogroups)

        # Store in session
        session['foreground_proteins'] = final_protein_list
        session['selected_orthogroups'] = selected_orthogroups_list
        # Track the raw input + expansion flag so the GO results panel can show
        # "you pasted N IDs / after expansion: M proteins" to the user.
        session['foreground_original_count'] = len(uniprot_ids)
        session['foreground_used_orthogroups'] = bool(use_orthogroups)

        # Clear logs
        logging.info(f"[FG] Selected Orthogroups (n={len(selected_orthogroups_list)}): {selected_orthogroups_list}")
        logging.info(f"[FG] Final Protein List size: {len(final_protein_list)}")

        return respond(True, "Foreground analysis completed successfully",
                       where="foreground_analysis",
                       payload={"foreground_proteins": final_protein_list})
    except Exception as e:
        logging.error(f"[FG][ERR] Unexpected error: {str(e)}")
        return respond(False, f"Unexpected error: {e}",
                       where="foreground_analysis",
                       code=500)

@app.route('/background_analysis', methods=['POST'])
def background_analysis():
    """
    Defines the background for GO analysis:
      - choice '4': pasted UniProt IDs (with or without 'use_orthogroups')
      - choice '5': use ALL downloaded GOA files as background
    """
    try:
        data = request.get_json(silent=True) or {}
        choice = str(data.get('background_choice', '')).strip()
        use_orthogroups = bool(data.get('use_orthogroups', False))
        single_copy_only = bool(data.get('single_copy_only', False))
        custom_uniprot_ids = parse_uniprot_block(data.get('custom_uniprot_ids', []))

        logging.info(f"[BG] choice={choice} use_orthogroups={use_orthogroups} "
                     f"single_copy_only={single_copy_only} custom_ids={len(custom_uniprot_ids)}")
        if choice == '4' and not custom_uniprot_ids:
            return respond(False, "No UniProt IDs provided",
                           where="background_analysis",
                           hint="Paste at least one UniProt ID for the background.",
                           code=400)

        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            logging.error(f"[BG][ERR] Excel not found at: {excel_path}")
            return respond(False, "Gene Ontology Analysis file not found.",
                           where="background_analysis",
                           hint="Click 'Download GOA files' first.",
                           code=404)

        try:
            initial_orthogroups = pd.read_excel(excel_path, sheet_name='Initial Groups')
            orthogroups_of_interest   = pd.read_excel(excel_path, sheet_name='Groups of Interest')
        except Exception as e:
            logging.error(f"[BG][ERR] Failed reading sheets: {e}")
            return respond(False, f"Malformed Excel file: {e}",
                           where="background_analysis",
                           hint="Re-generate the Excel using 'Download GOA files'.",
                           code=500)

        background_ids = set()

        if choice == '4':
            if use_orthogroups:
                # Select orthogroups containing any of the custom IDs
                sel_ogs = set()
                base_set = set(custom_uniprot_ids)
                og_hits = 0
                for _, row in initial_orthogroups.iterrows():
                    og = row['Orthogroup']
                    proteins = row[1:]
                    for protein in proteins.dropna():
                        s = str(protein)
                        hits = re.findall(r'\|([^|]+)\|', s)
                        if any(uid in base_set for uid in hits):
                            sel_ogs.add(og)
                            og_hits += 1
                            break
                logging.info(f"[BG] Orthogroups matched by custom IDs: {og_hits}")
                # Optional: restrict to single-copy orthogroups
                if single_copy_only:
                    sc_set = get_single_copy_orthogroups()
                    before = len(sel_ogs)
                    sel_ogs = {og for og in sel_ogs if og in sc_set}
                    logging.info(f"[BG] Single-copy filter: {before} -> {len(sel_ogs)} OGs")
                # Expand IDs from 'Groups of Interest'
                exp_added = 0
                for og in sel_ogs:
                    sub = orthogroups_of_interest[orthogroups_of_interest['Orthogroup'] == og]
                    for _, row in sub.iterrows():
                        proteins = row.dropna().astype(str)
                        for protein in proteins:
                            if protein not in ('Annotation Percentage', 'Porcentaje de Anotación'):
                                ids = re.findall(r'\|([^|]+)\|', protein)
                                background_ids.update(ids)
                                exp_added += len(ids)
                logging.info(f"[BG] Expanded background IDs added from orthogroups: {exp_added}")
            else:
                background_ids.update(custom_uniprot_ids)
                logging.info(f"[BG] Background from pasted IDs only: n={len(background_ids)}")

        elif choice == '5':
            # Use all downloaded GOA files -> universe will be built later in /gene_ontology_analysis
            if not os.path.isdir(GOA_DOWNLOAD_FOLDER):
                logging.error(f"[BG][ERR] GOA folder not found: {GOA_DOWNLOAD_FOLDER}")
                return respond(False, "GOA download folder not found",
                               where="background_analysis",
                               hint="Download the GOA files from the species table first.",
                               code=400)

            goa_files = [f for f in os.listdir(GOA_DOWNLOAD_FOLDER)
                         if f.endswith((".gaf", ".gaf.gz", ".goa", ".goa.gz"))]
            logging.info(f"[BG] GOA files found: {len(goa_files)}")
            if not goa_files:
                return respond(False, "No GOA files found",
                               where="background_analysis",
                               hint="Click 'Download GOA files' before using this option.",
                               code=400)

            session["background_mode"] = "goa_all"
            session["background_goa_files"] = goa_files
            # background_ids left empty; will be calculated later in /gene_ontology_analysis
            session["background_ids"] = session.get("background_ids", [])
            logging.info(f"[BG] ✅ Set to ALL GOA files ({len(goa_files)})")
            return respond(True, "Background set to all GOA files",
                           where="background_analysis",
                           payload={"background_files": goa_files,
                                    "background_ids": session.get("background_ids", [])})

        else:
            return respond(False, f"Background choice '{choice}' not implemented",
                           where="background_analysis",
                           hint="Use option 4 (pasted IDs) or 5 (use GOA).",
                           code=400)

        # Save to session (option 4)
        session["background_mode"] = "ids"
        session["background_ids"] = sorted(background_ids)
        logging.info(f"[BG] ✅ Selected background IDs: {len(background_ids)}")
        return respond(True, "Background successfully stored",
                       where="background_analysis",
                       payload={"background_ids": sorted(background_ids)})
    except Exception as e:
        logging.error(f"[BG][ERR] Unexpected error: {e}")
        return respond(False, str(e), where="background_analysis", code=500)

# Cache for the parsed GOA association, keyed by (folder signature, evidence
# codes, limit_files). Reading + parsing every .goa file is the slow part of an
# enrichment run; this lets repeated runs that only change p_value / min_depth /
# counting_mode reuse the parse. The folder signature (names + mtime + size)
# means a fresh GOA download naturally invalidates it.
_ID2GOS_CACHE = {}


def _goa_folder_signature(folder):
    """A hashable fingerprint of the GOA folder: (name, mtime, size) per file.
    Changes whenever files are added/removed/re-downloaded."""
    try:
        files = []
        for pat in ("*.goa", "*.gaf", "*.goa.gz", "*.gaf.gz"):
            for f in Path(folder).glob(pat):
                st = f.stat()
                files.append((f.name, int(st.st_mtime), st.st_size))
        return tuple(sorted(files))
    except OSError:
        return None


@app.route('/gene_ontology_analysis', methods=['POST'])
def gene_ontology_analysis():
    try:
        # -------------------------------
        # FRONTEND PARAMETERS
        # -------------------------------
        data = request.get_json(silent=True) or {}
        p_value_threshold = float(data.get('p_value', 0.05))
        max_terms = data.get('max_terms')  # None or int
        min_depth = int(data.get('min_depth', 2))
        # NEW user-selectable toggles (Phase B). Defaults preserve legacy behaviour:
        #   - all evidence codes
        #   - per-protein counting
        evidence_preset = str(data.get('evidence_preset', 'all')).lower().strip()
        if evidence_preset not in EVIDENCE_PRESETS:
            evidence_preset = 'all'
        evidence_codes = EVIDENCE_PRESETS[evidence_preset]
        counting_mode = str(data.get('counting_mode', 'per_protein')).lower().strip()
        if counting_mode not in ('per_protein', 'per_orthogroup'):
            counting_mode = 'per_protein'
        # Remember what the user asked for: the per_orthogroup collapse below can
        # fall back to per_protein, and that change must be reported, not silent.
        counting_mode_requested = counting_mode
        # User-facing, non-fatal warnings accumulated during the run (silent
        # fallback, version drift, low power). Surfaced in the JSON response.
        warnings = []

        logging.info("="*80)
        logging.info(f"[GO] ▶ Starting GO Analysis")
        logging.info(f"     - p_value_threshold = {p_value_threshold}")
        logging.info(f"     - min_depth = {min_depth}")
        logging.info(f"     - max_terms = {max_terms}")
        logging.info(f"     - evidence_preset = {evidence_preset} "
                     f"({len(evidence_codes) if evidence_codes else 'no filter'} codes)")
        logging.info(f"     - counting_mode = {counting_mode}")

        # -------------------------------
        # SESSION DATA
        # -------------------------------
        foreground = session.get("foreground_proteins", [])
        background_ids = session.get("background_ids", [])
        bg_mode = session.get("background_mode")  # "goa_all" | "ids"
        goa_mapping = _read_goa_mapping()

        if not foreground:
            logging.error("[GO][ERR] ❌ Foreground missing")
            return respond(False, "Foreground missing",
                           where="gene_ontology_analysis",
                           hint="Load the foreground before running the analysis.",
                           code=400)

        logging.info(f"[GO] Foreground proteins loaded: {len(foreground)}")
        if len(foreground) < 10:
            logging.info(f"[GO] Example foreground IDs: {foreground}")

        # -------------------------------
        # BUILD id2gos FROM GOA FILES
        # -------------------------------
        limit_files = list(set(goa_mapping.values())) if goa_mapping else None
        cache_key = (
            _goa_folder_signature(GOA_DOWNLOAD_FOLDER),
            frozenset(evidence_codes) if evidence_codes else None,
            tuple(sorted(limit_files)) if limit_files else None,
        )
        cached = _ID2GOS_CACHE.get(cache_key)
        if cached is not None:
            id2gos, id2evidence = cached
            logging.info(f"[GO] id2gos cache HIT: {len(id2gos)} proteins")
        else:
            logging.info(f"[GO] Building id2gos from folder={GOA_DOWNLOAD_FOLDER} limit_files={limit_files}")
            id2gos, id2evidence = build_id2gos_from_goa_folder(
                GOA_DOWNLOAD_FOLDER,
                limit_files=limit_files,
                evidence_codes=evidence_codes,
                return_evidence=True,
            )
            # Drop entries from stale folder signatures so the cache can't grow
            # without bound across re-downloads.
            sig = cache_key[0]
            for k in [k for k in _ID2GOS_CACHE if k[0] != sig]:
                del _ID2GOS_CACHE[k]
            _ID2GOS_CACHE[cache_key] = (id2gos, id2evidence)
            logging.info(f"[GO] id2gos constructed: {len(id2gos)} proteins with GO terms")

        # -------------------------------
        # DEFINE BACKGROUND
        # -------------------------------
        if bg_mode == "goa_all":
            background_ids = sorted(id2gos.keys())
            logging.info(f"[GO] Background mode=ALL, proteins={len(background_ids)}")

        if not background_ids:
            logging.error("[GO][ERR] ❌ Background missing")
            return respond(False, "Background missing",
                           where="gene_ontology_analysis",
                           hint="Define the background before proceeding.",
                           code=400)

        bg_set = set(background_ids)
        assoc_bg = {str(g): set(gos) for g, gos in id2gos.items() if g in bg_set and gos}
        logging.info(f"[GO] assoc_bg built: {len(assoc_bg)} proteins with GO terms")

        # Detect malformed entries
        bad = [(g, type(v)) for g, v in assoc_bg.items() if not isinstance(v, set)]
        if bad:
            logging.warning(f"[GO][WARN] Found {len(bad)} non-set entries in assoc_bg. Example: {bad[:5]}")

        # Example association
        if assoc_bg:
            some_gene, some_gos = next(iter(assoc_bg.items()))
            logging.info(f"[GO] Example assoc: {some_gene} -> {list(some_gos)[:5]}")

        # -------------------------------
        # FILTER FOREGROUND
        # -------------------------------
        fg_in_bg = [g for g in foreground if g in assoc_bg]
        logging.info(f"[GO] Foreground overlap: {len(fg_in_bg)} / {len(foreground)} in background")

        # Annotation-coverage stats for the UI banner. These are computed
        # BEFORE any counting_mode collapse so the numbers reflect the actual
        # proteins (not orthogroup representatives).
        annotation_stats = {
            "original_input":   int(session.get("foreground_original_count", 0)),
            "after_expansion":  len(foreground),
            "with_annotations": len(fg_in_bg),
            "used_orthogroups": bool(session.get("foreground_used_orthogroups", False)),
            "background_size":  len(bg_set),
        }

        if not fg_in_bg:
            logging.error("[GO][ERR] ❌ Foreground has no overlap with background+GO")
            return respond(False, "Foreground IDs have no GO terms in background",
                           where="gene_ontology_analysis",
                           hint="Check that your foreground IDs have GO annotations.",
                           code=400)

        # -------------------------------
        # COUNTING MODE — per-orthogroup collapse (optional)
        # -------------------------------
        # When ``counting_mode == 'per_orthogroup'`` we replace each protein in the
        # study/population with its orthogroup representative. This mitigates
        # pseudoreplication: an OG with 10 members would otherwise contribute 10
        # near-identical observations to the enrichment statistic.
        if counting_mode == 'per_orthogroup':
            try:
                excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
                interest_df = pd.read_excel(excel_path, sheet_name='Groups of Interest')
                # Build protein -> OG map and OG -> GO union
                protein_to_og = {}
                og_to_gos = defaultdict(set)
                exclude_cols = {'Orthogroup', 'Annotation Percentage', 'Porcentaje de Anotación'}
                for _, row in interest_df.iterrows():
                    og = row.get('Orthogroup')
                    if not og:
                        continue
                    for col, val in row.items():
                        if col in exclude_cols or pd.isna(val):
                            continue
                        for pid in re.findall(r'\|([^|]+)\|', str(val)):
                            protein_to_og[pid] = og
                            if pid in assoc_bg:
                                og_to_gos[og].update(assoc_bg[pid])
                # Collapse foreground and background to OG representatives
                fg_ogs = sorted({protein_to_og[p] for p in fg_in_bg if p in protein_to_og})
                bg_ogs = sorted({og for og in og_to_gos.keys()})
                if fg_ogs and bg_ogs:
                    # Re-key the association by OG. The OG ID itself becomes the
                    # "gene" identifier passed to GOATOOLS.
                    assoc_bg = {og: og_to_gos[og] for og in bg_ogs if og_to_gos[og]}
                    bg_set = set(assoc_bg.keys())
                    fg_in_bg = [og for og in fg_ogs if og in assoc_bg]
                    logging.info(f"[GO] Per-orthogroup counting: "
                                 f"foreground OGs={len(fg_in_bg)}, "
                                 f"background OGs={len(assoc_bg)}")
                else:
                    logging.warning("[GO][WARN] per_orthogroup requested but no OG "
                                    "mapping available — falling back to per_protein.")
                    counting_mode = 'per_protein'
                    warnings.append(
                        "Requested per_orthogroup counting, but no orthogroup mapping "
                        "was available — fell back to per_protein. Pseudoreplication "
                        "was NOT corrected.")
            except Exception as e:
                logging.warning(f"[GO][WARN] per_orthogroup collapse failed ({e}); "
                                f"falling back to per_protein.")
                counting_mode = 'per_protein'
                warnings.append(
                    f"per_orthogroup collapse failed ({e}) — fell back to per_protein. "
                    f"Pseudoreplication was NOT corrected.")

        # -------------------------------
        # LOAD ONTOLOGY
        # -------------------------------
        try:
            godag = ensure_godag(GO_ROOT_OBO)
            logging.info(f"[GO] GODag loaded: {len(godag)} terms")
        except Exception as e:
            logging.error(f"[GO][ERR] ❌ GODag load failed: {e}")
            raise

        # -------------------------------
        # ENRICHMENT ANALYSIS
        # -------------------------------
        logging.info("[GO] Running GOEnrichmentStudy ...")
        # NOTE: this name re-exports the PLAIN GOEnrichmentStudy (NOT the
        # per-namespace GOEnrichmentStudyNS). Benjamini-Hochberg FDR is therefore
        # computed ONCE over BP+CC+MF pooled as a single family, before the
        # namespace split and the depth/max_terms filters below. This is a valid
        # single-experiment correction but is not per-aspect; q-values will not
        # match tools that correct each namespace separately.
        from goatools.goea.go_enrichment_ns import GOEnrichmentStudy

        try:
            goea = GOEnrichmentStudy(
                list(bg_set),   # universe
                assoc_bg,       # gene -> set(GO)
                godag,
                propagate_counts=True,  # explicit: annotations propagate up the GO DAG
                methods=['fdr_bh'],
                log=None
            )
        except Exception as e:
            logging.error("[GO][CRASH] ❌ Error initializing GOEA")
            logging.info(f"    - assoc_bg type={type(assoc_bg)} size={len(assoc_bg)}")
            sample = [(g, type(v), list(v)[:10]) for g, v in list(assoc_bg.items())[:5]]
            logging.info(f"    - Sample entries: {sample}")
            raise

        results = goea.run_study(fg_in_bg)
        logging.info(f"[GO] Raw results: {len(results)} terms")

        # -------------------------------
        # FILTER SIGNIFICANT RESULTS
        # -------------------------------
        sig = []
        for r in results:
            if r.p_fdr_bh is None or r.p_fdr_bh >= p_value_threshold:
                continue
            depth = godag[r.GO].depth if r.GO in godag else 0
            if depth >= min_depth:
                sig.append(r)

        logging.info(f"[GO] Significant after FDR<{p_value_threshold} & depth≥{min_depth}: {len(sig)}")

        # -------------------------------
        # SPLIT BY NAMESPACE
        # -------------------------------
        def top_by_ns(ns, N=None):
            arr = [r for r in sig if r.goterm.namespace == ns]
            # GO id as final tie-breaker => deterministic ordering at the max_terms
            # cutoff (terms with identical p-values no longer swap between runs).
            arr = sorted(arr, key=lambda x: (x.p_fdr_bh, x.p_uncorrected, x.GO))
            return arr[:N] if (N and isinstance(N, int)) else arr

        bp_results = top_by_ns("biological_process", max_terms)
        cc_results = top_by_ns("cellular_component", max_terms)
        mf_results = top_by_ns("molecular_function", max_terms)

        logging.info(f"[GO] Split by namespace: BP={len(bp_results)}, CC={len(cc_results)}, MF={len(mf_results)}")

        # Direction of each term from the two-sided Fisher test: 'e' = over-
        # represented (enriched), 'p' = under-represented (depleted / purified).
        # Surfaced explicitly so depleted terms are never mislabeled as enriched.
        _DIRECTION = {"e": "enriched", "p": "depleted"}
        def _direction(r):
            return _DIRECTION.get(getattr(r, "enrichment", None), "n/a")

        # NOTE (2026-05-25): the matplotlib GridSpec block that generated
        # static/plots/go_analysis_figure.png was removed here. Phase C
        # replaced it with a client-side Plotly chart + the front-end's
        # `Plotly.downloadImage` call, so the server-side PNG was no longer
        # consumed by any UI element. See git log for the original code.

        # -------------------------------
        # EXCEL OUTPUT
        # -------------------------------
        out_xlsx = os.path.join(RESULTS_FOLDER, "go_enrichment_report.xlsx")
        with pd.ExcelWriter(out_xlsx) as xw:
            for ns, res in (("BP", bp_results), ("CC", cc_results), ("MF", mf_results)):
                df = pd.DataFrame({
                    "GO": [r.GO for r in res],
                    "name": [r.name for r in res],
                    "NS": [r.goterm.namespace for r in res],
                    "Direction": [_direction(r) for r in res],
                    "-log10(FDR)": [
                        ((-float(np.log10(r.p_fdr_bh))) if (r.p_fdr_bh and r.p_fdr_bh > 0) else 0.0)
                        for r in res
                    ],
                    "study_count": [r.study_count for r in res],
                    "study_n": [r.study_n for r in res],
                    "pop_count": [r.pop_count for r in res],
                    "pop_n": [r.pop_n for r in res],
                }) if res else pd.DataFrame(columns=[
                    "GO","name","NS","Direction","-log10(FDR)","study_count","study_n","pop_count","pop_n"
                ])
                df.to_excel(xw, sheet_name=ns, index=False)
            # Provenance + run settings, so a downloaded report is reproducible.
            prov = build_provenance()
            cat = prov.get("catalogue", {}) or {}
            g = prov.get("goa", {}) or {}
            onto = prov.get("ontology", {}) or {}
            pr = prov.get("proteome", {}) or {}
            _join = lambda v: ", ".join(v) if isinstance(v, list) else v
            prov_rows = [
                ("OrthoGather version",          prov.get("orthogather_version")),
                ("Report generated at",          prov.get("generated_at")),
                ("Proteome data source",         pr.get("source")),
                ("UniProt release",              _join(pr.get("release"))),
                ("UniProt release date",         _join(pr.get("release_date"))),
                ("Proteome catalogue version",   cat.get("version")),
                ("Proteome catalogue downloaded", cat.get("downloaded_at")),
                ("Proteome count",               cat.get("proteome_count")),
                ("OrthoFinder version",          prov.get("orthofinder_version")),
                ("GO ontology version",          onto.get("data_version")),
                ("GOA data generated (EBI)",     _join(g.get("data_generated"))),
                ("GOA GO-version (EBI)",         _join(g.get("go_version"))),
                ("GOA downloaded at",            g.get("downloaded_at")),
                ("GOA source",                   g.get("source")),
                ("GOA files used",               g.get("n_files")),
                ("Evidence preset",              evidence_preset),
                ("Counting mode requested",      counting_mode_requested),
                ("Counting mode applied",        counting_mode),
                ("FDR method",                   "Benjamini-Hochberg (fdr_bh)"),
                ("FDR scope",                    "pooled across BP/CC/MF (single family); applied before depth & max_terms filters"),
                ("Annotation propagation",       "enabled (propagate_counts=True)"),
                ("FDR threshold",                p_value_threshold),
                ("Min depth",                    min_depth),
                ("Foreground units",             len(fg_in_bg)),
                ("Background units",             len(bg_set)),
            ]
            if counting_mode == 'per_orthogroup':
                prov_rows.append((
                    "Background universe note",
                    "per_orthogroup: background = orthogroups in 'Groups of Interest' "
                    "with an annotated member (not all GOA proteins)"))
            pd.DataFrame(prov_rows, columns=["key", "value"]).to_excel(
                xw, sheet_name="Provenance", index=False)
        logging.info(f"[GO] 📑 Excel generated: {out_xlsx}")

        # Version-drift guard: the OBO and the GOA files are downloaded
        # independently. If the GOA references a GO release newer/older than the
        # loaded OBO, a few terms silently drop from the testable universe.
        try:
            _obo_v = (onto or {}).get("data_version")
            _goa_v = g.get("go_version")
            if isinstance(_goa_v, list):
                _goa_v = _goa_v[0] if _goa_v else None
            if _obo_v and _goa_v and str(_obo_v) != str(_goa_v):
                warnings.append(
                    f"GO ontology version ({_obo_v}) differs from the GOA GO-version "
                    f"({_goa_v}); a few annotations referencing terms outside the loaded "
                    f"ontology may be dropped.")
        except Exception:
            pass

        # -------------------------------
        # PER-TERM EVIDENCE BREAKDOWN (for table chips in the UI)
        # -------------------------------
        # For each significant GO term, count how many evidence-code occurrences
        # appear among the foreground/study proteins that carry that term. Per-OG
        # counting collapses to OG IDs, so the evidence breakdown uses the proteins
        # that contributed to that OG.
        def evidence_breakdown_for_term(go_id, study_ids):
            counts = defaultdict(int)
            if counting_mode == 'per_orthogroup':
                # study_ids are OG IDs; pull back to constituent proteins
                # (those whose protein_to_og maps here AND that carry the term)
                proteins_for_og = defaultdict(list)
                try:
                    for p, og in protein_to_og.items():
                        proteins_for_og[og].append(p)
                except NameError:
                    pass
                for og in study_ids:
                    for p in proteins_for_og.get(og, []):
                        for ev in id2evidence.get(p, {}).get(go_id, []):
                            counts[ev] += 1
            else:
                for p in study_ids:
                    for ev in id2evidence.get(p, {}).get(go_id, []):
                        counts[ev] += 1
            return dict(counts)

        def serialise(res):
            out = []
            for r in res:
                study_items = list(r.study_items) if hasattr(r, 'study_items') else []
                out.append({
                    "GO": r.GO,
                    "name": r.name,
                    "namespace": r.goterm.namespace,
                    "depth": godag[r.GO].depth if r.GO in godag else 0,
                    "p_uncorrected": r.p_uncorrected,
                    "p_fdr_bh": r.p_fdr_bh,
                    "neg_log10_fdr": (-float(np.log10(r.p_fdr_bh))) if r.p_fdr_bh and r.p_fdr_bh > 0 else 0.0,
                    "study_count": r.study_count,
                    "study_n": r.study_n,
                    "pop_count": r.pop_count,
                    "pop_n": r.pop_n,
                    "enrichment": r.enrichment if hasattr(r, 'enrichment') else None,
                    "direction": _direction(r),
                    "study_items": study_items,
                    "evidence_breakdown": evidence_breakdown_for_term(r.GO, study_items),
                })
            return out

        # Persist the settings of THIS run so /download_go_enrichment_excel
        # can embed them in the filename ("evidence-curated", "fg1769", ...).
        session['go_settings'] = {
            "evidence_preset": evidence_preset,
            "counting_mode":   counting_mode,
            "p_value":         p_value_threshold,
            "min_depth":       min_depth,
            "max_terms":       max_terms,
        }

        # -------------------------------
        # COUNTING SUMMARY + LOW-OG NOTICE
        # -------------------------------
        # `fg_in_bg` is the study set actually handed to GOATOOLS: proteins in
        # per_protein mode, orthogroup IDs in per_orthogroup mode. When the
        # per-orthogroup collapse leaves only a handful of OGs, enrichment has no
        # power and returns nothing — which looks broken unless we explain it.
        total_sig = len(bp_results) + len(cc_results) + len(mf_results)
        foreground_units = len(fg_in_bg)
        if foreground_units and foreground_units < 5:
            warnings.append(
                f"Only {foreground_units} foreground unit(s) entered the test — "
                f"statistical power is very low; treat any result as exploratory.")
        notice = None
        if counting_mode == 'per_orthogroup' and total_sig == 0:
            notice = (
                f"Per-orthogroup counting collapsed your foreground to "
                f"{foreground_units} orthogroup{'s' if foreground_units != 1 else ''}, "
                f"too few to reach significance — so no terms came up. This is "
                f"expected when the foreground spans few orthogroups: per-protein "
                f"mode may report terms, but those are driven by paralogs within "
                f"these groups (pseudoreplication), which per-orthogroup removes."
            )

        # -------------------------------
        # FINAL RESPONSE
        # -------------------------------
        return respond(True, "GO analysis completed successfully",
                       where="gene_ontology_analysis",
                       payload={
                           "bp_results": serialise(bp_results),
                           "cc_results": serialise(cc_results),
                           "mf_results": serialise(mf_results),
                           "excel_file_path": "download_go_enrichment_excel",
                           "annotation_stats": annotation_stats,
                           "settings": session['go_settings'],
                           "counting": {
                               "mode": counting_mode,
                               "mode_requested": counting_mode_requested,
                               "foreground_units": foreground_units,
                               "background_units": len(bg_set),
                           },
                           "notice": notice,
                           "warnings": warnings,
                       })

    except Exception as e:
        logging.error(f"[GO][ERR] ❌ Unexpected error in gene_ontology_analysis: {e}")
        import traceback; traceback.print_exc()
        return respond(False, f"Unexpected error: {e}",
                       where="gene_ontology_analysis",
                       hint="Check logs and make sure OBO/GOA files exist.",
                       code=500)

@app.route("/download_go_enrichment_excel")
def download_go_enrichment_excel():
    excel_path = os.path.join(RESULTS_FOLDER, "go_enrichment_report.xlsx")
    if not os.path.exists(excel_path):
        return respond_error("ERR_ENRICHMENT_EXCEL_MISSING")
    # Descriptive filename: include foreground size + evidence preset + ISO date
    # so several enrichment downloads are distinguishable on disk.
    from orthogather.utils.filenames import descriptive_filename
    fg_size = len(session.get('foreground_proteins') or [])
    evidence_preset = session.get('go_settings', {}).get('evidence_preset')
    context = []
    if fg_size:
        context.append(f"fg{fg_size}")
    if evidence_preset:
        context.append(f"evidence-{evidence_preset}")
    fmt = (request.args.get("fmt") or "xlsx").lower()
    if fmt in ("csv", "tsv"):
        sep = "," if fmt == "csv" else "\t"
        buf = _xlsx_to_delimited_zip(excel_path, sep)
        dl_name = descriptive_filename("GOenrichment-results", "zip", context=context + [fmt])
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=dl_name)
    dl_name = descriptive_filename(
        "GOenrichment-results", "xlsx", context=context,
    )
    return send_file(excel_path, as_attachment=True, download_name=dl_name)

@app.route("/go_status")
def go_status():
    try:
        info = {
            "modo": session.get("modo"),
            "folder_path": session.get("folder_path"),
            "species_count": len(session.get("species", [])),
            "fg_count": len(session.get("foreground_proteins", [])),
            "bg_count": len(session.get("background_ids", [])),
            "goa_mapping_count": len(_read_goa_mapping()),
            "bg_mode": session.get("background_mode"),
        }
        return respond(True, "GO status", where="go_status", payload=info)
    except Exception as e:
        return respond(False, f"Unexpected error in go_status: {e}",
                       where="go_status", code=500)

# Single-slot cache for the annotation distribution, keyed by the Excel's
# mtime. The distribution is a pure function of the Excel, which only changes
# when GOA files are re-downloaded — so we recompute only then, not on every
# page (re)load that calls /generate_go_image.
_ANNOT_DIST_CACHE = {}


@app.route("/generate_go_image", methods=["POST"])
def generate_go_image():
    """
    Reads the Excel generated by /download_goa_files and returns the data
    needed to render the annotation-distribution figure CLIENT-SIDE with Plotly.

    Returns JSON with the distribution series + summary stats. Cached by Excel
    mtime so repeat calls (every results-page load) don't re-read the workbook.
    """
    try:
        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            return respond_error("ERR_GO_ANALYSIS_EXCEL_MISSING",
                                  where="generate_go_image")

        from orthogather.core.excel import compute_annotation_distribution
        try:
            mtime = os.path.getmtime(excel_path)
            cached = _ANNOT_DIST_CACHE.get("entry")
            if cached and cached[0] == (excel_path, mtime):
                data = cached[1]
            else:
                data = compute_annotation_distribution(excel_path)
                _ANNOT_DIST_CACHE["entry"] = ((excel_path, mtime), data)
        except FileNotFoundError:
            return respond_error("ERR_GO_ANALYSIS_EXCEL_MISSING",
                                  where="generate_go_image")
        except ValueError as e:
            return respond_error("ERR_MALFORMED_EXCEL",
                                  where="generate_go_image", detail=str(e))

        return respond(
            True,
            "Annotation distribution data ready",
            where="generate_go_image",
            payload={"distribution": data},
        )

    except Exception as e:
        return respond_error("ERR_GO_FIGURE_FAILED",
                              where="generate_go_image", detail=str(e))


if __name__ == "__main__":
    # Seed the raw catalogue JSON from the committed .gz baseline if missing
    # (fresh clone, no Git LFS). Decompresses once; no-op on subsequent runs.
    try:
        ensure_catalogue_present(JSON_PATH)
    except Exception as e:
        logging.warning(f"Could not seed catalogue from .gz baseline: {e}")

    # Warm the slim species-index cache in the background so the first species-page
    # load doesn't pay the one-time build (load catalogue + project + gzip ~ a few
    # seconds). Daemon thread: never blocks startup or delays shutdown.
    def _warm_species_index():
        try:
            _build_species_index_gz()
            logging.info("Species index cache warmed.")
        except Exception as e:
            logging.warning(f"Could not warm species index: {e}")
    threading.Thread(target=_warm_species_index, daemon=True).start()
    # Port: honour ORTHOGATHER_PORT if set (handy for tooling/deploys), else pick
    # a free one as before. ORTHOGATHER_NO_BROWSER=1 suppresses the auto-open tab.
    env_port = os.environ.get("ORTHOGATHER_PORT")
    port = int(env_port) if env_port and env_port.isdigit() else find_free_port()
    logging.info(f"🚀 Starting Flask on port {port}")
    if os.environ.get("ORTHOGATHER_NO_BROWSER") != "1":
        threading.Timer(1.25, open_browser, args=(port,)).start()
    app.run(debug=True, use_reloader=False, port=port)
