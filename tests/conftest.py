"""
Shared pytest fixtures for the OrthoGather test suite.

The proteomes catalogue is ~843 K entries and ~1 s to load — we share it
across all tests via a session-scoped fixture so the suite stays fast.

We also clear `_match_species_cache` between tests because `match_species()`
memoises by `tuple(species_list)`. Without this, test order would influence
which path inside `match_species()` is exercised, and a failing test would
leave bad data in the cache for subsequent tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo root importable so `from app import …` works regardless of
# where pytest is invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def proteomes():
    """The full UniProt proteome catalogue, loaded once per test session."""
    from app import load_proteomes, JSON_PATH
    return load_proteomes(JSON_PATH)


@pytest.fixture(autouse=True)
def _clear_match_species_cache():
    """Reset the module-level match-species cache before every test so order
    of test execution can't introduce false negatives."""
    from app import _match_species_cache
    _match_species_cache.clear()
    yield
    _match_species_cache.clear()
