"""Tests for orthogather.core.taxonomy.

Covers the pure functions (build_taxonomy_tree, trim_to_lca, to_newick,
summarize_diversity) against fixtures, plus the cache behaviour of
get_lineage with a fetcher stub (no network calls in tests).
"""
from __future__ import annotations

import json
import pytest

from orthogather.core.taxonomy import (
    build_taxonomy_tree,
    get_lineage,
    get_lineages_bulk,
    summarize_diversity,
    to_newick,
    trim_to_lca,
)


# ---------------------------------------------------------------------------
# Fixtures: real NCBI lineages, hand-curated for 5 reference species.
# Same data UniProt would return — just inlined so tests are offline.
# ---------------------------------------------------------------------------

E_COLI_K12 = {
    "scientific_name": "Escherichia coli (strain K12)",
    "lineage": [
        {"taxon_id": 131567, "name": "cellular organisms", "rank": "no rank"},
        {"taxon_id": 2,      "name": "Bacteria",            "rank": "superkingdom"},
        {"taxon_id": 1224,   "name": "Pseudomonadota",      "rank": "phylum"},
        {"taxon_id": 1236,   "name": "Gammaproteobacteria", "rank": "class"},
        {"taxon_id": 91347,  "name": "Enterobacterales",    "rank": "order"},
        {"taxon_id": 543,    "name": "Enterobacteriaceae",  "rank": "family"},
        {"taxon_id": 561,    "name": "Escherichia",         "rank": "genus"},
        {"taxon_id": 562,    "name": "Escherichia coli",    "rank": "species"},
    ],
    "fetched_at": "2026-05-26T22:00:00Z",
    "source": "mock",
    "source_release": "test",
}

E_COLI_O157 = {
    **E_COLI_K12,
    "scientific_name": "Escherichia coli O157:H7",
}

B_SUBTILIS = {
    "scientific_name": "Bacillus subtilis subsp. subtilis str. 168",
    "lineage": [
        {"taxon_id": 131567, "name": "cellular organisms", "rank": "no rank"},
        {"taxon_id": 2,      "name": "Bacteria",           "rank": "superkingdom"},
        {"taxon_id": 1239,   "name": "Bacillota",          "rank": "phylum"},
        {"taxon_id": 91061,  "name": "Bacilli",            "rank": "class"},
        {"taxon_id": 1385,   "name": "Bacillales",         "rank": "order"},
        {"taxon_id": 186817, "name": "Bacillaceae",        "rank": "family"},
        {"taxon_id": 1386,   "name": "Bacillus",           "rank": "genus"},
        {"taxon_id": 1423,   "name": "Bacillus subtilis",  "rank": "species"},
    ],
    "fetched_at": "2026-05-26T22:00:00Z",
    "source": "mock",
    "source_release": "test",
}

M_TUBERCULOSIS = {
    "scientific_name": "Mycobacterium tuberculosis H37Rv",
    "lineage": [
        {"taxon_id": 131567, "name": "cellular organisms", "rank": "no rank"},
        {"taxon_id": 2,      "name": "Bacteria",            "rank": "superkingdom"},
        {"taxon_id": 201174, "name": "Actinomycetota",      "rank": "phylum"},
        {"taxon_id": 1760,   "name": "Actinomycetes",       "rank": "class"},
        {"taxon_id": 85007,  "name": "Mycobacteriales",     "rank": "order"},
        {"taxon_id": 1762,   "name": "Mycobacteriaceae",    "rank": "family"},
        {"taxon_id": 1763,   "name": "Mycobacterium",       "rank": "genus"},
        {"taxon_id": 1773,   "name": "Mycobacterium tuberculosis", "rank": "species"},
    ],
    "fetched_at": "2026-05-26T22:00:00Z",
    "source": "mock",
    "source_release": "test",
}

HUMAN = {
    "scientific_name": "Homo sapiens",
    "lineage": [
        {"taxon_id": 131567, "name": "cellular organisms", "rank": "no rank"},
        {"taxon_id": 2759,   "name": "Eukaryota",          "rank": "superkingdom"},
        {"taxon_id": 33208,  "name": "Metazoa",            "rank": "kingdom"},
        {"taxon_id": 7711,   "name": "Chordata",           "rank": "phylum"},
        {"taxon_id": 40674,  "name": "Mammalia",           "rank": "class"},
        {"taxon_id": 9443,   "name": "Primates",           "rank": "order"},
        {"taxon_id": 9604,   "name": "Hominidae",          "rank": "family"},
        {"taxon_id": 9605,   "name": "Homo",               "rank": "genus"},
        {"taxon_id": 9606,   "name": "Homo sapiens",       "rank": "species"},
    ],
    "fetched_at": "2026-05-26T22:00:00Z",
    "source": "mock",
    "source_release": "test",
}

FIXTURE_LINEAGES = {
    "83333":  E_COLI_K12,
    "83334":  E_COLI_O157,
    "224308": B_SUBTILIS,
    "83332":  M_TUBERCULOSIS,
    "9606":   HUMAN,
}


# ---------------------------------------------------------------------------
# build_taxonomy_tree
# ---------------------------------------------------------------------------

def test_single_species_builds_full_chain():
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333")], lineages=FIXTURE_LINEAGES
    )
    # The ROOT has one child (Bacteria, since "cellular organisms" is "no
    # rank" and gets filtered out), which descends through Phylum / Class
    # / ... / Species, with the user-facing leaf at the bottom.
    n = tree
    seen_names = []
    while "children" in n and n["children"]:
        n = n["children"][0]
        seen_names.append(n["name"])
    # "cellular organisms" must NOT appear (it's no-rank, filtered out)
    assert "cellular organisms" not in seen_names
    assert seen_names[0] == "Bacteria"
    assert "Pseudomonadota" in seen_names
    assert "Escherichia coli" in seen_names
    assert seen_names[-1] == "E. coli K12"
    assert n["leaf"] is True
    assert n["taxon_id"] == "83333"


def test_sister_species_share_ancestors():
    """Two E. coli strains should share every internal node down to the
    species level."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"), ("E. coli O157:H7", "83334")],
        lineages=FIXTURE_LINEAGES,
    )
    trimmed = trim_to_lca(tree)
    # Both strains share lineage all the way to "Escherichia coli", so the
    # LCA after trim should land at Escherichia coli with 2 leaves below it.
    assert trimmed["name"] == "Escherichia coli"
    assert {c["name"] for c in trimmed["children"]} == {"E. coli K12", "E. coli O157:H7"}
    for c in trimmed["children"]:
        assert c["leaf"] is True


def test_distantly_related_species_branch_at_root():
    """E. coli (Bacteria) and Human (Eukaryota) share no STRUCTURAL ancestor —
    only the 'cellular organisms' no-rank parent, which we drop from the
    rendered tree. So the LCA after trimming is the synthetic ROOT with two
    superkingdoms as immediate children."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"), ("Human", "9606")],
        lineages=FIXTURE_LINEAGES,
    )
    trimmed = trim_to_lca(tree)
    assert trimmed["name"] == "ROOT"
    kids = {c["name"] for c in trimmed["children"]}
    assert "Bacteria" in kids
    assert "Eukaryota" in kids


def test_three_bacteria_share_bacterial_root():
    """E. coli, B. subtilis, M. tuberculosis share down to Bacteria."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"),
         ("B. subtilis 168", "224308"),
         ("M. tuberculosis H37Rv", "83332")],
        lineages=FIXTURE_LINEAGES,
    )
    trimmed = trim_to_lca(tree)
    assert trimmed["name"] == "Bacteria"
    phyla = {c["name"] for c in trimmed["children"]}
    assert phyla == {"Pseudomonadota", "Bacillota", "Actinomycetota"}


def test_unknown_taxid_attaches_under_unknown_lineage():
    """A taxon_id with no lineage in the cache should not silently drop;
    it must show up under an 'Unknown lineage' node so the user sees it."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"),
         ("MysteryBug", "999999")],   # not in FIXTURE_LINEAGES
        lineages=FIXTURE_LINEAGES,
    )
    # Walk the tree, look for "Unknown lineage" subtree
    def find_node(node, name):
        if node.get("name") == name:
            return node
        for c in node.get("children", []):
            r = find_node(c, name)
            if r:
                return r
        return None
    unknown = find_node(tree, "Unknown lineage")
    assert unknown is not None
    assert unknown["children"][0]["name"] == "MysteryBug"
    assert unknown["children"][0]["lineage"] == "Unknown"


def test_deterministic_byte_for_byte():
    """Same input → same tree, byte-for-byte. Critical for reproducibility."""
    pairs = [("E. coli K12", "83333"), ("B. subtilis 168", "224308")]
    tree1 = build_taxonomy_tree(pairs, lineages=FIXTURE_LINEAGES)
    tree2 = build_taxonomy_tree(pairs, lineages=FIXTURE_LINEAGES)
    assert json.dumps(tree1, sort_keys=True) == json.dumps(tree2, sort_keys=True)


# ---------------------------------------------------------------------------
# trim_to_lca
# ---------------------------------------------------------------------------

def test_trim_stops_at_first_branching():
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"), ("B. subtilis 168", "224308")],
        lineages=FIXTURE_LINEAGES,
    )
    trimmed = trim_to_lca(tree)
    # ROOT → cellular organisms → Bacteria → [Pseudomonadota, Bacillota]
    # → first branching is at Bacteria.
    assert trimmed["name"] == "Bacteria"
    assert len(trimmed["children"]) == 2


def test_trim_keeps_node_with_only_leaf_child():
    """Don't descend through a level whose single child is a LEAF
    (otherwise we'd lose the species)."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333")], lineages=FIXTURE_LINEAGES
    )
    trimmed = trim_to_lca(tree)
    # Should descend down to Escherichia coli (the species level), whose
    # single child is the leaf "E. coli K12". Trim stops there.
    assert trimmed["name"] == "Escherichia coli"
    assert len(trimmed["children"]) == 1
    assert trimmed["children"][0]["leaf"] is True


# ---------------------------------------------------------------------------
# to_newick
# ---------------------------------------------------------------------------

def test_newick_ends_with_semicolon():
    tree = build_taxonomy_tree([("E. coli K12", "83333")], lineages=FIXTURE_LINEAGES)
    nwk = to_newick(trim_to_lca(tree))
    assert nwk.endswith(";")


def test_newick_contains_leaf_names():
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"), ("B. subtilis 168", "224308")],
        lineages=FIXTURE_LINEAGES,
    )
    nwk = to_newick(trim_to_lca(tree))
    assert "E._coli_K12" in nwk
    assert "B._subtilis_168" in nwk
    # Internal-node labels appear too
    assert "Pseudomonadota" in nwk
    assert "Bacillota" in nwk


def test_newick_parens_balanced():
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"),
         ("B. subtilis 168", "224308"),
         ("M. tuberculosis H37Rv", "83332")],
        lineages=FIXTURE_LINEAGES,
    )
    nwk = to_newick(trim_to_lca(tree))
    assert nwk.count("(") == nwk.count(")")


# ---------------------------------------------------------------------------
# summarize_diversity
# ---------------------------------------------------------------------------

def test_diversity_counts_three_phyla_for_three_bacteria():
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"),
         ("B. subtilis 168", "224308"),
         ("M. tuberculosis H37Rv", "83332")],
        lineages=FIXTURE_LINEAGES,
    )
    s = summarize_diversity(trim_to_lca(tree))
    assert s["n_leaves"] == 3
    assert s["n_phyla"] == 3
    assert sorted(s["phyla"]) == ["Actinomycetota", "Bacillota", "Pseudomonadota"]


def test_diversity_counts_on_full_tree_not_trimmed():
    """Diversity counts must come from the FULL tree, not the trimmed one,
    because trim_to_lca collapses single-child levels (so a 2-E.-coli tree
    loses Pseudomonadota in the trimmed version even though that's still
    the phylum of both strains)."""
    tree = build_taxonomy_tree(
        [("E. coli K12", "83333"), ("E. coli O157:H7", "83334")],
        lineages=FIXTURE_LINEAGES,
    )
    # Summarize the FULL tree (real prod usage: backend reports both).
    s = summarize_diversity(tree)
    assert s["n_leaves"] == 2
    assert s["n_phyla"] == 1   # both in Pseudomonadota
    assert s["n_genera"] == 1  # both in Escherichia
    # And confirm the trimmed tree DOES strip the now-redundant levels:
    trimmed = trim_to_lca(tree)
    assert trimmed["name"] == "Escherichia coli"


# ---------------------------------------------------------------------------
# get_lineage caching
# ---------------------------------------------------------------------------

def test_get_lineage_uses_cache(tmp_path):
    """Once a taxon_id is fetched, subsequent calls don't re-fetch."""
    cache_path = tmp_path / "lineage_cache.json"
    calls = {"n": 0}

    def fake_fetcher(tid):
        calls["n"] += 1
        return FIXTURE_LINEAGES["83333"]

    # First call — fetcher invoked once
    r1 = get_lineage("83333", cache_path=cache_path, fetcher=fake_fetcher)
    assert calls["n"] == 1
    assert r1["scientific_name"].startswith("Escherichia coli")

    # Second call — should hit cache, fetcher NOT invoked again
    r2 = get_lineage("83333", cache_path=cache_path, fetcher=fake_fetcher)
    assert calls["n"] == 1
    assert r2 == r1


def test_get_lineage_rejects_invalid_taxid(tmp_path):
    cache_path = tmp_path / "lineage_cache.json"
    with pytest.raises(ValueError):
        get_lineage("not-a-number", cache_path=cache_path, fetcher=lambda t: None)
    with pytest.raises(ValueError):
        get_lineage("", cache_path=cache_path, fetcher=lambda t: None)


def test_get_lineages_bulk_writes_cache_once(tmp_path):
    """Bulk fetch should batch cache writes (not save after every entry)."""
    cache_path = tmp_path / "lineage_cache.json"
    fetched = []

    def fake_fetcher(tid):
        fetched.append(tid)
        return FIXTURE_LINEAGES.get(tid, FIXTURE_LINEAGES["83333"])

    pairs = [("E. coli", "83333"), ("B. subtilis", "224308"), ("M. tb", "83332")]
    out = get_lineages_bulk(pairs, cache_path=cache_path,
                             fetcher=fake_fetcher, polite_delay_s=0)
    assert set(out.keys()) == {"83333", "224308", "83332"}
    assert len(fetched) == 3

    # Cache file should now have all three entries
    with open(cache_path) as f:
        data = json.load(f)
    assert set(data["entries"].keys()) == {"83333", "224308", "83332"}


def test_get_lineages_bulk_skips_invalid_taxids(tmp_path):
    """Invalid taxon_ids are logged + skipped, not raised."""
    cache_path = tmp_path / "lineage_cache.json"
    pairs = [("OK", "83333"), ("Bad", "not-int"), ("OK2", "224308")]
    out = get_lineages_bulk(
        pairs, cache_path=cache_path,
        fetcher=lambda t: FIXTURE_LINEAGES.get(t, FIXTURE_LINEAGES["83333"]),
        polite_delay_s=0,
    )
    assert "83333" in out
    assert "224308" in out
    assert "not-int" not in out
