"""
Species catalogue: loading the UniProt proteome catalogue from disk, matching
user-supplied species names against it, and expanding common abbreviations
("E. coli" → "Escherichia coli").

The matcher has four tiers (in order of preference):
  0. Proteome ID   — the catalogue entry of the proteome the species was
                     downloaded from, when the analysis knows it.
  1. Strain match  — label starts with the base name AND contains `strain_norm`.
  2. Base-only     — first proteome whose label starts with the base name.
  3. Synonym       — first proteome whose label contains the base name elsewhere
                     (UniProt keeps former names in parentheses, as in
                     "Mycolicibacterium smegmatis (...) (Mycobacterium smegmatis)").
Names are compared as whole words: "IS27" no longer matches "Influenza A virus
(A/Memphis/27/1983)", nor "... H37Rv" the strain "H37RvSiena".

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
    if len(parts) >= 3 and parts[0].lower() == "candidatus":
        # "Candidatus" is a status, not the genus: the binomial is the next two
        # words. UniProt labels write it or not ("Pelagibacter ubique (strain
        # HTCC1062)"); the base read as "Candidatus Pelagibacter" matched
        # another species of the genus.
        parts = parts[1:]
        fullname = " ".join(parts)
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
_proteome_index = {}


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
    _proteome_index.clear()


def _words(text):
    """Lower-case alphanumeric words: 'Escherichia coli (strain K12)' ->
    ['escherichia', 'coli', 'strain', 'k12']. Underscores separate words."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _has_words(label, words, at_start):
    """Whether ``words`` appear as consecutive whole words of ``label``, at its
    start if ``at_start``."""
    lw, n = _words(label), len(words)
    starts = [0] if at_start else range(len(lw) - n + 1)
    return bool(n) and any(lw[i:i + n] == words for i in starts)


def _by_proteome_id(proteomes):
    key = id(proteomes)
    if key not in _proteome_index:
        _proteome_index.clear()
        _proteome_index[key] = {p.get("Proteome Id"): p for p in proteomes if p.get("Proteome Id")}
    return _proteome_index[key]


def match_species(species_list, proteomes, proteome_ids=None):
    """Match every species in ``species_list`` against the catalogue.

    ``proteome_ids`` maps a species name to the UniProt proteome it was
    downloaded from, when the analysis knows it; that entry is used directly.

    Result is memoised by the species list and the IDs, so repeat warm hits to
    /resultado_goa with the same selection skip the O(N×M) scan entirely.

    Returns a list of dicts: ``{"original": str, "base": str, "strain": str,
    "match": <proteome dict | None>, "method": "proteome_id" | "name" | None}``.
    """
    proteome_ids = proteome_ids or {}
    cache_key = (tuple(species_list), tuple(sorted(proteome_ids.items())))
    cached = _match_species_cache.get(cache_key)
    if cached is not None:
        return cached
    index = _by_proteome_id(proteomes) if proteome_ids else {}
    matches = []
    for original in species_list:
        base, strain = split_species_name(original)
        base_norm = normalize(base)
        strain_norm = normalize(strain)
        base_words = _words(base)
        # Tier 0 (proteome ID): the entry of the proteome the species came from
        # Tier 1 (strain match): label starts with the base AND contains `strain_norm`
        # Tier 2 (base-only):    first label that starts with the base
        # Tier 3 (synonym):      the base appears elsewhere in the label
        # The normalised strings are a fast filter; the words decide.
        matched = index.get(proteome_ids.get(original))
        method = "proteome_id" if matched else None
        first_candidate = None
        synonym_candidate = None
        for p in ([] if matched else proteomes):
            norm = p.get("_norm_label") or normalize(p["label"])
            if norm.startswith(base_norm) and _has_words(p["label"], base_words, at_start=True):
                if first_candidate is None:
                    first_candidate = p
                if strain_norm and strain_norm in norm:
                    matched = p
                    break
            elif (synonym_candidate is None and base_norm and base_norm in norm
                  and _has_words(p["label"], base_words, at_start=False)):
                synonym_candidate = p
        if matched is None:
            matched = first_candidate or synonym_candidate
        matches.append({
            "original": original,
            "base": base,
            "strain": strain,
            "match": matched,
            "method": method or ("name" if matched else None),
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
    _proteome_index.clear()
