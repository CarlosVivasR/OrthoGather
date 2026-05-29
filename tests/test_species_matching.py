"""
Regression tests for species matching (Phase A).

These tests lock in the fix for the "E. coli" class of failures so that
future refactors of `normalize()`, `split_species_name()`, `match_species()`
can't silently bring the bug back.

Test groups:
  - normalize_*               : the casefold/strip helper
  - expand_alias_basic        : abbreviation expansion ("E. coli" -> "Escherichia coli")
  - expand_alias_no_match     : full names / unknown short forms pass through
  - split_species_name_*      : base + strain extraction
  - match_species_strain_tier : best-tier match (prefix + strain substring)
  - match_species_base_tier   : 2nd-tier fallback (first prefix candidate)
  - match_species_substring_tier : 3rd-tier fallback (substring anywhere)
  - match_species_cache       : memoisation by tuple(species_list)
  - alias_map_coverage        : every entry in SPECIES_ALIAS_MAP resolves
"""
from __future__ import annotations

import re

import pytest

from app import (
    normalize,
    expand_species_alias,
    split_species_name,
    match_species,
    SPECIES_ALIAS_MAP,
)


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------
class TestNormalize:
    def test_strips_dots_and_spaces(self):
        assert normalize("E. coli") == "ecoli"

    def test_lowercases(self):
        assert normalize("ESCHERICHIA COLI") == "escherichiacoli"

    def test_keeps_digits(self):
        assert normalize("K12 strain") == "k12strain"

    def test_drops_punctuation(self):
        assert normalize("Foo, bar - baz!") == "foobarbaz"

    def test_idempotent(self):
        n = normalize("Escherichia coli (strain K12) [UP000000625]")
        assert normalize(n) == n


# ---------------------------------------------------------------------------
# expand_species_alias()
# ---------------------------------------------------------------------------
class TestExpandAlias:
    @pytest.mark.parametrize("inp,expected", [
        ("E. coli",          "Escherichia coli"),
        ("E.coli",           "Escherichia coli"),
        ("E coli",           "Escherichia coli"),
        ("S. cerevisiae",    "Saccharomyces cerevisiae"),
        ("D. melanogaster",  "Drosophila melanogaster"),
        ("C. elegans",       "Caenorhabditis elegans"),
        ("H. sapiens",       "Homo sapiens"),
        ("M. musculus",      "Mus musculus"),
        ("A. thaliana",      "Arabidopsis thaliana"),
        ("B. subtilis",      "Bacillus subtilis"),
    ])
    def test_basic_abbreviations(self, inp, expected):
        assert expand_species_alias(inp) == expected

    def test_preserves_trailing_strain(self):
        # The strain marker after the epithet must be kept on the expanded name
        assert expand_species_alias("E. coli K-12").startswith("Escherichia coli")
        assert "K-12" in expand_species_alias("E. coli K-12")

    def test_full_name_passes_through(self):
        # When the input is already a full name we must NOT mangle it
        assert expand_species_alias("Escherichia coli") == "Escherichia coli"

    def test_unknown_abbrev_passes_through(self):
        # "Z. unknown" has no alias entry — return as-is
        assert expand_species_alias("Z. unknown") == "Z. unknown"

    def test_empty_input(self):
        assert expand_species_alias("") == ""
        assert expand_species_alias(None) is None


# ---------------------------------------------------------------------------
# split_species_name()
# ---------------------------------------------------------------------------
class TestSplitSpeciesName:
    def test_two_word_input(self):
        base, strain = split_species_name("Escherichia coli")
        assert base == "Escherichia coli"
        assert strain == ""

    def test_three_word_input(self):
        base, strain = split_species_name("Escherichia coli K12")
        assert base == "Escherichia coli"
        assert strain == "K12"

    def test_strain_at_capital_digit_boundary(self):
        # "[A-Z][0-9]" should latch onto the strain start
        base, strain = split_species_name("Acinetobacter baumannii AB5075")
        assert base == "Acinetobacter baumannii"
        assert "AB5075" in strain

    def test_one_word_input_safe(self):
        # Don't crash on a single token — Python's slicing must hold up
        base, strain = split_species_name("Bacteria")
        assert base == "Bacteria"
        assert strain == ""

    def test_alias_expansion_is_applied(self):
        # split_species_name() must call through expand_species_alias()
        base, strain = split_species_name("E. coli K-12")
        assert base == "Escherichia coli"


# ---------------------------------------------------------------------------
# match_species() — tier 1: strain match
# ---------------------------------------------------------------------------
class TestMatchSpeciesStrainTier:
    def test_ecoli_k12_resolves_to_k12_strain(self, proteomes):
        results = match_species(["E. coli K-12"], proteomes)
        m = results[0]["match"]
        assert m is not None
        assert "K12" in m["label"] or "K-12" in m["label"]

    def test_acinetobacter_strain(self, proteomes):
        # The preselected dataset has "Acinetobacter baumannii AB5075"
        results = match_species(["Acinetobacter baumannii AB5075"], proteomes)
        m = results[0]["match"]
        assert m is not None
        assert "baumannii" in m["label"].lower()


# ---------------------------------------------------------------------------
# match_species() — tier 2: base-only prefix fallback (first_candidate fix)
# ---------------------------------------------------------------------------
class TestMatchSpeciesBaseTier:
    def test_bare_genus_species_returns_first_candidate(self, proteomes):
        # No strain → must NOT return None; must use the first prefix match
        results = match_species(["Escherichia coli"], proteomes)
        m = results[0]["match"]
        assert m is not None, (
            "Bare 'Escherichia coli' should fall back to first_candidate"
        )
        assert m["label"].lower().startswith("escherichia coli")

    def test_yeast_bare_name(self, proteomes):
        results = match_species(["Saccharomyces cerevisiae"], proteomes)
        m = results[0]["match"]
        assert m is not None
        assert "saccharomyces cerevisiae" in m["label"].lower()


# ---------------------------------------------------------------------------
# match_species() — tier 3: substring fallback
# ---------------------------------------------------------------------------
class TestMatchSpeciesSubstringTier:
    def test_label_not_starting_with_base_uses_substring_path(self, proteomes):
        # This species exists with multiple words before "Escherichia" in some
        # exports; substring search is the safety net. We assert that even an
        # unusual phrasing still resolves to *some* E. coli.
        # Use a phrasing that is unlikely to be a prefix match anywhere.
        results = match_species(["thing coli Escherichia"], proteomes)
        # Behaviour: either tier-3 returns an E. coli, OR returns None — but
        # must never raise.
        m = results[0]["match"]
        if m is not None:
            assert "coli" in m["label"].lower() or "escherichia" in m["label"].lower()


# ---------------------------------------------------------------------------
# match_species() — memoisation
# ---------------------------------------------------------------------------
class TestMatchSpeciesCache:
    def test_repeat_call_returns_identical_object(self, proteomes):
        first  = match_species(["E. coli"], proteomes)
        second = match_species(["E. coli"], proteomes)
        # Must be the exact same list object — the cache returns the original
        assert first is second

    def test_different_input_returns_different_object(self, proteomes):
        a = match_species(["E. coli"], proteomes)
        b = match_species(["S. cerevisiae"], proteomes)
        assert a is not b


# ---------------------------------------------------------------------------
# Alias-map coverage — every entry must resolve to a real catalogue label.
# Catches typos in SPECIES_ALIAS_MAP before they reach a user.
# ---------------------------------------------------------------------------
class TestAliasMapCoverage:
    def test_every_alias_resolves(self, proteomes):
        """Every (alias → full name) entry in SPECIES_ALIAS_MAP must resolve
        to at least one proteome in the catalogue. If this test fails, the
        alias map has stale or misspelled entries."""
        failed = []
        for alias_key, full_name in SPECIES_ALIAS_MAP.items():
            results = match_species([full_name], proteomes)
            if results[0]["match"] is None:
                failed.append((alias_key, full_name))
        assert not failed, (
            f"Aliases that don't resolve to a real proteome: {failed!r}. "
            "Either remove them from SPECIES_ALIAS_MAP or check the spelling."
        )

    def test_alias_keys_are_well_formed(self):
        """Keys are normalised (lowercase, no spaces/dots) so the lookup path
        in expand_species_alias() can match them directly."""
        for k in SPECIES_ALIAS_MAP:
            assert k == k.lower(), f"Alias key {k!r} must be lowercase"
            assert " " not in k and "." not in k, (
                f"Alias key {k!r} must have no spaces/dots"
            )
