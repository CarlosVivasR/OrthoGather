"""
Species catalogue: loading the UniProt proteome catalogue from disk, matching
user-supplied species names against it, and expanding common abbreviations
("E. coli" → "Escherichia coli").

The matcher has three tiers (in order of preference):
  1. Strain match  — prefix matches `base_norm` AND contains `strain_norm`.
  2. Base-only     — first proteome whose normalised label starts with `base_norm`.
  3. Substring     — first proteome whose label contains `base_norm` anywhere
                     (catches non-standard orderings like "Coli, Escherichia"
                     that occasionally appear in Excel exports).

The module-level caches (`_proteomes_cache`, `_match_species_cache`) are
*read-only* in user-facing code; they only ever grow with idempotent values,
so they're safe under Flask's multi-request model.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import shutil
from typing import List

import pandas as pd

from orthogather.utils.parsing import normalize


# ---------------------------------------------------------------------------
# Alias table — most common scientific abbreviations.
# Keys are normalised to lowercase without dots/whitespace ("ecoli");
# values are the canonical "Genus species" expansion.
# ---------------------------------------------------------------------------
SPECIES_ALIAS_MAP = {
    "ecoli":            "Escherichia coli",
    "scerevisiae":      "Saccharomyces cerevisiae",
    "spombe":           "Schizosaccharomyces pombe",
    "bsubtilis":        "Bacillus subtilis",
    "athaliana":        "Arabidopsis thaliana",
    "dmelanogaster":    "Drosophila melanogaster",
    "celegans":         "Caenorhabditis elegans",
    "mmusculus":        "Mus musculus",
    "hsapiens":         "Homo sapiens",
    "rnorvegicus":      "Rattus norvegicus",
    "drerio":           "Danio rerio",
    "ggallus":          "Gallus gallus",
    "xlaevis":          "Xenopus laevis",
    "xtropicalis":      "Xenopus tropicalis",
    "ppatens":          "Physcomitrium patens",  # was Physcomitrella; UniProt renamed the genus
    "osativa":          "Oryza sativa",
    "zmays":            "Zea mays",
    "styphimurium":     "Salmonella typhimurium",
    "senterica":        "Salmonella enterica",
    "paeruginosa":      "Pseudomonas aeruginosa",
    "mtuberculosis":    "Mycobacterium tuberculosis",
    "saureus":          "Staphylococcus aureus",
    "lmonocytogenes":   "Listeria monocytogenes",
    "hpylori":          "Helicobacter pylori",
    "cjejuni":          "Campylobacter jejuni",
    "vcholerae":        "Vibrio cholerae",
    "ypestis":          "Yersinia pestis",
    "ngonorrhoeae":     "Neisseria gonorrhoeae",
    "nmeningitidis":    "Neisseria meningitidis",
    "spneumoniae":      "Streptococcus pneumoniae",
    "spyogenes":        "Streptococcus pyogenes",
    "tbrucei":          "Trypanosoma brucei",
    "tcruzi":           "Trypanosoma cruzi",
    "pfalciparum":      "Plasmodium falciparum",
    "lmajor":           "Leishmania major",
    "cmerolae":         "Cyanidioschyzon merolae",
    "creinhardtii":     "Chlamydomonas reinhardtii",
    "dictyostelium":    "Dictyostelium discoideum",
    "ddiscoideum":      "Dictyostelium discoideum",
    "neurosporacrassa": "Neurospora crassa",
    "ncrassa":          "Neurospora crassa",
    "aniger":           "Aspergillus niger",
    "anidulans":        "Emericella nidulans",  # UniProt names A. nidulans by its teleomorph
    "afumigatus":       "Aspergillus fumigatus",
    "calbicans":        "Candida albicans",
}


def expand_species_alias(fullname):
    """Expand abbreviations such as 'E. coli' / 'E.coli' / 'E coli' into the
    full genus name via :data:`SPECIES_ALIAS_MAP`. Returns the expanded name
    or the input unchanged when no alias applies.

    Examples
    --------
    >>> expand_species_alias('E. coli')
    'Escherichia coli'
    >>> expand_species_alias('E.coli K-12')
    'Escherichia coli K-12'
    >>> expand_species_alias('Escherichia coli')   # already full
    'Escherichia coli'
    """
    if not fullname:
        return fullname
    stripped = fullname.strip()
    # Match: single letter, then either '.' (with optional spaces) or whitespace,
    # then a species epithet. Anything after that is treated as trailing strain.
    m = re.match(r"^([A-Za-z])(?:\.\s*|\s+)([A-Za-z][A-Za-z\-]+)(\s+.*)?$", stripped)
    if not m:
        return fullname
    abbrev_letter, epithet, trailing = m.group(1), m.group(2), m.group(3) or ""
    key = (abbrev_letter + epithet).lower()
    expanded = SPECIES_ALIAS_MAP.get(key)
    if expanded:
        return (expanded + trailing).strip()
    return fullname


def split_species_name(fullname):
    """Split a species name into (base, strain) where base is the binomial
    ("Genus species") and strain is everything after.

    Applies :func:`expand_species_alias` first so "E. coli K-12" becomes
    ("Escherichia coli", "K-12") rather than ("E. coli", "K-12").
    """
    fullname = expand_species_alias(fullname)
    parts = fullname.split()
    base = " ".join(parts[:2]) if len(parts) >= 2 else fullname
    strain = " ".join(parts[2:]) if len(parts) > 2 else ""
    # Match the run of capital letters preceding the first digit so that
    # "Acinetobacter baumannii AB5075" yields strain "AB5075" rather than "B5075".
    match = re.search(r"[A-Z]+[0-9]", fullname)
    if match:
        strain = fullname[match.start():]
    return base.strip(), strain.strip()


def extract_species_names_from_tsv(path):
    """Return the species columns from an Orthogroups.tsv (or compatible)
    file. The first column is the orthogroup ID and is dropped."""
    df = pd.read_csv(path, sep='\t', nrows=0)
    return list(df.columns[1:])


# ---------------------------------------------------------------------------
# Catalogue loader + species matcher with the module-level caches.
# ---------------------------------------------------------------------------
_proteomes_cache = None


def ensure_catalogue_present(json_path):
    """Seed the raw catalogue JSON from the committed ``.gz`` baseline if absent.

    The 166 MB ``proteomes_list.json`` is no longer stored in Git (no more LFS).
    What ships in the repo is ``proteomes_list.json.gz`` (~13 MB); the raw JSON is
    a derived, git-ignored artefact decompressed on first launch. This makes a
    fresh clone self-contained and offline — no ``git lfs pull``, no network.

    Idempotent and safe: if the raw JSON already exists (e.g. a newer catalogue
    was downloaded from a GitHub release) it is left untouched — the ``.gz`` seed
    never clobbers a fresher copy. Returns ``json_path`` for convenient chaining.
    """
    if os.path.exists(json_path):
        return json_path
    gz_path = json_path + ".gz"
    if not os.path.exists(gz_path):
        return json_path  # nothing to seed from; caller handles the missing file
    tmp_path = json_path + ".seed.tmp"
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with gzip.open(gz_path, "rb") as src, open(tmp_path, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)  # 1 MiB chunks
        os.replace(tmp_path, json_path)  # atomic
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    return json_path


def load_proteomes(json_path):
    """Load and cache the UniProt proteome catalogue.

    The catalogue is ~843 K entries (~166 MB on disk). Loading + normalising
    once at startup turns subsequent :func:`match_species` calls from O(N×M)
    string ops into O(N×M) plain comparisons (~50× faster). The catalogue
    is read-only after load, so the cache is safe under Flask's thread model.

    Seeds the raw JSON from the ``.gz`` baseline first (see
    :func:`ensure_catalogue_present`) so importing without going through
    ``app.py``'s ``__main__`` (tests, helper scripts) still finds the file.
    """
    global _proteomes_cache
    if _proteomes_cache is None:
        ensure_catalogue_present(json_path)
        with open(json_path, "r") as f:
            _proteomes_cache = json.load(f)
        # Pre-normalise every label once
        for p in _proteomes_cache:
            p["_norm_label"] = normalize(p["label"])
    return _proteomes_cache


_match_species_cache = {}


def invalidate_caches():
    """Drop the in-memory catalogue + match caches so the next
    :func:`load_proteomes` rebuilds from the file on disk.

    Call this after the catalogue file changes (e.g. a release update). Resetting
    the importing module's own globals is NOT enough — the caches live here, so
    invalidation must happen here too.
    """
    global _proteomes_cache, _match_species_cache
    _proteomes_cache = None
    _match_species_cache = {}


def match_species(species_list, proteomes):
    """Match every species in ``species_list`` against the catalogue.

    Result is memoised by the ``tuple(species_list)`` so repeat warm hits to
    /resultado_goa with the same selection skip the O(N×M) scan entirely.

    Returns a list of dicts: ``{"original": str, "base": str, "strain": str,
    "match": <proteome dict | None>}``.
    """
    cache_key = tuple(species_list)
    cached = _match_species_cache.get(cache_key)
    if cached is not None:
        return cached
    matches = []
    for original in species_list:
        base, strain = split_species_name(original)
        base_norm = normalize(base)
        strain_norm = normalize(strain)
        # Tier 1 (strain match): prefix matches `base_norm` AND contains `strain_norm`
        # Tier 2 (base-only):    first prefix candidate
        # Tier 3 (substring):    `base_norm` appears anywhere in the label
        matched = None
        first_candidate = None
        substring_candidate = None
        for p in proteomes:
            norm = p.get("_norm_label") or normalize(p["label"])
            if norm.startswith(base_norm):
                if first_candidate is None:
                    first_candidate = p
                if strain_norm and strain_norm in norm:
                    matched = p
                    break
            elif substring_candidate is None and base_norm and base_norm in norm:
                substring_candidate = p
        if matched is None:
            matched = first_candidate or substring_candidate
        matches.append({
            "original": original,
            "base": base,
            "strain": strain,
            "match": matched,
        })
    _match_species_cache[cache_key] = matches
    return matches


def invalidate_catalogue_caches():
    """Drop both the proteomes cache and the species-match cache.

    Called from /catalog/update when the on-disk catalogue is refreshed and
    from the test suite between cases.
    """
    global _proteomes_cache
    _proteomes_cache = None
    _match_species_cache.clear()
