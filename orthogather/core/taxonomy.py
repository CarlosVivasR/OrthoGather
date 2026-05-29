"""NCBI taxonomy lineages + tree building for OrthoGather (Point 11).

The pipeline turns a set of selected species (each with a UniProt
``taxon_id``) into:

1. **Per-species lineage** (kingdom → phylum → class → order → family →
   genus → species) fetched from UniProt's taxonomy REST endpoint and
   cached locally. The cache carries metadata (``fetched_at``,
   ``source``, ``source_release``) so a reviewer can verify exactly what
   data was used and when.
2. **A nested taxonomy tree** combining all selected species under their
   shared lineage. Identical NCBI ancestor → shared internal node. The
   algorithm is fully deterministic; same input → same tree byte-for-byte.
3. **Newick** export so the same tree can be opened in iTOL, FigTree,
   Dendroscope or any phylogeny viewer.

All functions here are pure (no Flask, no globals). The Flask layer wraps
them in an HTTP endpoint elsewhere.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UNIPROT_TAXONOMY_URL = "https://rest.uniprot.org/taxonomy/{taxon_id}.json"

# Cache lives next to the proteomes catalog so it ships with the repo for
# the preselected dataset, and grows in place for user-added species.
DEFAULT_CACHE_PATH = Path("static") / "Proteomes_json" / "taxonomy_lineage.json"

# Ranks we KEEP in the rendered tree. Anything outside this set is dropped
# because it bloats the visualization without helping the user distinguish
# species:
#   - "no rank" intermediates ("cellular organisms",
#     "Mycobacterium tuberculosis complex", "Bacillus subtilis group", …)
#   - "kingdom" (NCBI added Bacillati/Pseudomonadati clades in 2024; for
#     bacterial datasets these add visual noise without information)
#   - "subspecies" / "strain" — the user's display-name leaf already
#     carries strain-level distinction; nesting two more redundant labels
#     above it just causes label collisions.
STRUCTURAL_RANKS = (
    "domain",
    "superkingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species",
)


def _filter_lineage(lineage):
    """Keep only entries whose rank is in STRUCTURAL_RANKS. Preserves order."""
    return [l for l in lineage
            if (l.get("rank") or "").lower() in STRUCTURAL_RANKS]

_NEWICK_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _load_cache(cache_path: Path) -> dict:
    """Load the cache JSON. Returns the full envelope (with ``_meta`` and
    ``entries`` keys). Initialises a fresh envelope if the file is missing
    or unreadable.
    """
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "entries" in data:
                return data
        except (OSError, json.JSONDecodeError) as e:
            logging.warning(
                f"[taxonomy] Cache at {cache_path} unreadable ({e}); starting fresh."
            )
    return {
        "_meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema": "orthogather.taxonomy.cache.v1",
            "description": (
                "Per-taxon_id NCBI lineages, fetched from UniProt REST. "
                "Each entry has fetched_at + source + source_release so the "
                "data backing a published tree can be audited."
            ),
        },
        "entries": {},
    }


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp, cache_path)


# ---------------------------------------------------------------------------
# UniProt fetch
# ---------------------------------------------------------------------------

def _fetch_uniprot_lineage(taxon_id: str, *, timeout: float = 8.0,
                            session: requests.Session | None = None) -> dict:
    """Hit UniProt's REST taxonomy endpoint for one taxon_id and return the
    normalised lineage. Raises ``ValueError`` for bad taxon_ids and
    ``requests.RequestException`` for network errors (callers catch both
    and surface them via the error catalog).
    """
    url = UNIPROT_TAXONOMY_URL.format(taxon_id=taxon_id)
    s = session or requests.Session()
    resp = s.get(url, timeout=timeout, headers={"Accept": "application/json"})
    if resp.status_code == 404:
        raise ValueError(f"Taxon ID {taxon_id} not found at UniProt")
    resp.raise_for_status()
    payload = resp.json()

    # UniProt's /taxonomy/{id}.json returns:
    #   - Top-level fields = the LEAF (e.g. strain or species itself)
    #   - `lineage` = ancestors in ROOT-first order, EXCLUDING the leaf
    # We normalise to a single ordered list [root → leaf] of dicts:
    #   {"taxon_id": int, "name": str, "rank": str}
    # (Verified against real UniProt responses, see /tmp curl on 2026-05-26.)
    lineage = []
    for anc in payload.get("lineage", []) or []:
        lineage.append({
            "taxon_id": anc.get("taxonId"),
            "name": anc.get("scientificName") or "Unknown",
            "rank": anc.get("rank") or "no rank",
        })
    # Append the leaf taxon itself last (so it sits at the deepest position).
    lineage.append({
        "taxon_id": payload.get("taxonId"),
        "name": payload.get("scientificName") or f"taxon_{taxon_id}",
        "rank": payload.get("rank") or "no rank",
    })

    # Try to detect the UniProt release the data came from. They expose it
    # via the `X-UniProt-Release` response header on some endpoints. Be
    # defensive: if missing, fall back to the date.
    release = (resp.headers.get("X-UniProt-Release")
               or resp.headers.get("x-uniprot-release")
               or datetime.now(timezone.utc).strftime("%Y_%m"))

    return {
        "scientific_name": payload.get("scientificName"),
        "lineage": lineage,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "UniProt REST taxonomy",
        "source_release": release,
    }


# ---------------------------------------------------------------------------
# Public API: get_lineage (with caching)
# ---------------------------------------------------------------------------

def get_lineage(taxon_id: str | int, *,
                cache_path: Path | str = DEFAULT_CACHE_PATH,
                fetcher: Callable[[str], dict] | None = None,
                session: requests.Session | None = None) -> dict:
    """Return the full lineage entry for one taxon_id.

    Lazy + cached: first call hits UniProt and writes to cache; subsequent
    calls return the cached entry instantly.

    Parameters
    ----------
    taxon_id : str or int
        The NCBI taxonomy ID (UniProt uses the same numbering).
    cache_path : Path or str
        Where to read/write the cache. Defaults to the bundled location.
    fetcher : callable, optional
        Test seam — swap in to bypass the real UniProt call.
    session : requests.Session, optional
        Reuse a session across many calls (faster TCP + keep-alive).

    Returns
    -------
    dict
        ``{scientific_name, lineage, fetched_at, source, source_release}``.

    Raises
    ------
    ValueError
        ``taxon_id`` is not a positive integer string or wasn't found.
    requests.RequestException
        Network failure and not in cache.
    """
    tid = str(taxon_id).strip()
    if not tid or not tid.isdigit():
        raise ValueError(f"Invalid taxon_id: {taxon_id!r} (expected positive integer)")

    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    if tid in cache["entries"]:
        return cache["entries"][tid]

    fetch_fn = fetcher or (lambda t: _fetch_uniprot_lineage(t, session=session))
    entry = fetch_fn(tid)
    cache["entries"][tid] = entry
    _save_cache(cache_path, cache)
    return entry


def get_lineages_bulk(species_with_taxids: Iterable[tuple[str, str]], *,
                      cache_path: Path | str = DEFAULT_CACHE_PATH,
                      fetcher: Callable[[str], dict] | None = None,
                      polite_delay_s: float = 0.12,
                      ) -> dict[str, dict]:
    """Resolve lineages for many species in one call.

    Reads cache once, fetches only the missing taxon_ids (sequentially with
    a small polite delay so we don't hammer UniProt), writes the cache once
    at the end. Much faster than calling ``get_lineage`` in a loop because
    cache I/O is amortized.

    Returns a dict ``{taxon_id: lineage_entry}`` for every input pair that
    resolved successfully. Failures are logged and skipped (the tree
    builder will mark those species as "Unknown lineage").
    """
    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    out: dict[str, dict] = {}
    dirty = False

    fetch_fn = fetcher or _fetch_uniprot_lineage
    session = requests.Session()

    for _, tid in species_with_taxids:
        tid = str(tid).strip()
        if not tid.isdigit():
            logging.warning(f"[taxonomy] Skipping invalid taxon_id {tid!r}")
            continue
        if tid in cache["entries"]:
            out[tid] = cache["entries"][tid]
            continue
        try:
            entry = (fetch_fn(tid) if fetcher
                     else _fetch_uniprot_lineage(tid, session=session))
            cache["entries"][tid] = entry
            out[tid] = entry
            dirty = True
            time.sleep(polite_delay_s)
        except (ValueError, requests.RequestException) as e:
            logging.warning(f"[taxonomy] Lineage fetch failed for taxon_id={tid}: {e}")

    if dirty:
        _save_cache(cache_path, cache)
    return out


# ---------------------------------------------------------------------------
# Tree building
# ---------------------------------------------------------------------------

def build_taxonomy_tree(species_with_taxids: Iterable[tuple[str, str]], *,
                        lineages: dict[str, dict] | None = None,
                        ) -> dict:
    """Build a nested taxonomy tree from a set of selected species.

    Algorithm (deterministic, side-effect-free):

    1. For each (display_name, taxon_id), walk down its full NCBI lineage
       level by level starting from a synthetic ROOT.
    2. At each level, find or create a child node keyed by the level's
       scientific name. Existing nodes are reused so species sharing an
       ancestor end up under the same internal node.
    3. The species itself attaches as a leaf at the bottom, carrying its
       display_name, taxon_id, rank, and full lineage string for tooltips.
    4. Output is a plain dict tree directly consumable by D3's
       ``d3.hierarchy()`` on the frontend.

    Parameters
    ----------
    species_with_taxids : iterable of (display_name, taxon_id)
    lineages : dict, optional
        Pre-fetched lineages keyed by taxon_id (from ``get_lineages_bulk``).
        If omitted, lineages are looked up on demand via the default cache.

    Returns
    -------
    dict
        ``{name, rank, children: [...]}`` nested structure. Leaves carry
        ``{name, rank: 'Species', taxon_id, lineage, leaf: True}``.

    Notes
    -----
    Species whose lineage couldn't be resolved are attached under a single
    ``"Unknown lineage"`` sibling at the root, so the user can see them
    and the tree doesn't silently drop them.
    """
    if lineages is None:
        pairs = list(species_with_taxids)
        lineages = get_lineages_bulk(pairs)
        # Re-pair iter
        species_with_taxids = pairs

    # Internal mutable tree node structure:
    #   {"name": str, "rank": str, "children_by_name": {name: node}, "leaves": [leaf_dict]}
    def _new_node(name: str, rank: str) -> dict:
        return {"name": name, "rank": rank,
                "children_by_name": {}, "leaves": []}

    root = _new_node("ROOT", "")
    unknown = _new_node("Unknown lineage", "")

    for display_name, taxon_id in species_with_taxids:
        tid = str(taxon_id).strip()
        entry = lineages.get(tid)
        if not entry:
            unknown["leaves"].append({
                "name": display_name,
                "rank": "Species",
                "taxon_id": tid,
                "leaf": True,
                "lineage": "Unknown",
            })
            continue

        # Filter lineage to structural ranks only (drops noise like "no rank"
        # intermediates and the new NCBI kingdoms). The full lineage is kept
        # for the tooltip string so the user can still see everything.
        filtered_lineage = _filter_lineage(entry["lineage"])

        node = root
        for level in filtered_lineage:
            level_name = level["name"]
            level_rank = level["rank"]
            if level_name not in node["children_by_name"]:
                node["children_by_name"][level_name] = _new_node(level_name, level_rank)
            node = node["children_by_name"][level_name]
        # Attach species as a leaf at the deepest level. We use the user-
        # facing display name (e.g. "E. coli K12") rather than the UniProt
        # scientific name so the tree matches what the user picked.
        # Tooltip shows the full unfiltered lineage so power users still
        # see every NCBI level.
        full_lineage_str = "; ".join(l["name"] for l in entry["lineage"])
        node["leaves"].append({
            "name": display_name,
            "rank": "Species",
            "taxon_id": tid,
            "leaf": True,
            "lineage": full_lineage_str,
        })

    if unknown["leaves"]:
        root["children_by_name"]["Unknown lineage"] = unknown

    # Convert to the public shape (children as list, leaves merged in).
    def _to_public(node: dict) -> dict:
        out: dict[str, Any] = {"name": node["name"], "rank": node["rank"]}
        kids: list[dict] = [_to_public(c) for c in node["children_by_name"].values()]
        for leaf in node["leaves"]:
            kids.append(dict(leaf))
        if kids:
            out["children"] = kids
        return out

    return _to_public(root)


def trim_to_lca(tree: dict) -> dict:
    """Drop top levels with a single child until we hit a branching point.

    Saves visual space: if every species is under "cellular organisms →
    Bacteria", we don't need to render those two levels — start at the
    first node where the tree actually branches.

    Always leaves at least one named node at the root (won't return an
    empty dict).
    """
    node = tree
    while (len(node.get("children", [])) == 1
           and not any(c.get("leaf") for c in node.get("children", []))):
        # one child and it's an internal node → safe to descend
        node = node["children"][0]
    return node


# ---------------------------------------------------------------------------
# Newick export
# ---------------------------------------------------------------------------

def _newick_safe(name: str) -> str:
    """Make a name Newick-safe: replace whitespace with underscores and
    strip characters Newick treats specially (parens, commas, colons,
    semicolons). Single-quote wrap if the name still contains weird chars.
    """
    safe = _NEWICK_NAME_RE.sub("_", name.strip())
    return safe or "unnamed"


def to_newick(tree: dict, *, include_internal_labels: bool = True) -> str:
    """Convert a tree dict (as built by ``build_taxonomy_tree``) into a
    Newick string. Branch lengths are omitted (this is a taxonomic, not
    phylogenetic, tree).
    """
    def _walk(node: dict) -> str:
        children = node.get("children", [])
        if not children:
            return _newick_safe(node["name"])
        parts = [_walk(c) for c in children]
        label = _newick_safe(node["name"]) if include_internal_labels else ""
        return f"({','.join(parts)}){label}"

    return _walk(tree) + ";"


# ---------------------------------------------------------------------------
# Convenience summary for the UI
# ---------------------------------------------------------------------------

def summarize_diversity(tree: dict) -> dict:
    """Count how many distinct phyla / classes / families / species the
    tree contains. Used by the frontend to populate the summary cards.
    """
    counts: dict[str, set[str]] = {
        "phylum": set(), "class": set(), "order": set(),
        "family": set(), "genus": set(), "species": set(),
    }
    n_leaves = 0

    def _walk(node: dict) -> None:
        nonlocal n_leaves
        rank = (node.get("rank") or "").lower()
        if rank in counts:
            counts[rank].add(node["name"])
        if node.get("leaf"):
            n_leaves += 1
        for c in node.get("children", []):
            _walk(c)

    _walk(tree)
    return {
        "n_leaves": n_leaves,
        "n_phyla":   len(counts["phylum"]),
        "n_classes": len(counts["class"]),
        "n_orders":  len(counts["order"]),
        "n_families": len(counts["family"]),
        "n_genera":  len(counts["genus"]),
        "phyla":   sorted(counts["phylum"]),
        "classes": sorted(counts["class"]),
    }
