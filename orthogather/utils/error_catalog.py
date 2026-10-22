"""
OrthoGather error catalogue — single source of truth.

Every error the app raises (input validation, missing data, network failures,
unexpected exceptions) is keyed by a stable code in this module. Routes call
:func:`respond_error` with the code; the frontend reads the code from the
response and renders a consistent banner with the message and the suggested
fix.

How to add a new error
----------------------

When you add a feature, add the error here FIRST, then reference it from your
route. Never write a raw `respond(False, "ad-hoc message")` again — that's
what this catalogue exists to prevent.

::

    ERRORS["ERR_FEATURE_MUST_FAIL"] = ErrorSpec(
        message="Short human-readable summary of what went wrong.",
        hint="One-sentence concrete action the user can take to fix it.",
        category="input",          # input | state | data | network | system | not-found
        severity="error",          # error | warning | info
        http_code=400,             # HTTP status code
    )

Then in your route::

    from orthogather.utils.responses import respond_error
    return respond_error("ERR_FEATURE_MUST_FAIL", where="my_endpoint")

If you need to embed dynamic info (a filename, a count, …) you can pass
``extra={"detail": "..."}`` and the frontend will append it to the message.

Conventions
-----------
- Every code starts with ``ERR_``.
- Messages are 1 line, no trailing dot, no exclamation marks.
- Hints are 1-2 sentences, must be actionable ("Click X first" / "Paste at
  least one ID" / "Check your network connection"), not "Try again".
- Severity is "error" for things blocking the user, "warning" for degraded
  operation, "info" for purely informational.
- Categories help the frontend group / icon errors and help us search logs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Spec dataclass — the registry stores one of these per error code.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ErrorSpec:
    message:   str
    hint:      str
    category:  str = "system"
    severity:  str = "error"
    http_code: int = 400

    def to_dict(self) -> dict:
        return asdict(self)


# Valid values — used by the test suite to keep the catalogue consistent.
VALID_CATEGORIES = {"input", "state", "data", "network", "system", "not-found", "external"}
VALID_SEVERITIES = {"error", "warning", "info"}


# ---------------------------------------------------------------------------
# The catalogue. Grouped by category for readability; order has no semantic
# meaning at runtime.
# ---------------------------------------------------------------------------
ERRORS: Dict[str, ErrorSpec] = {

    # =========================================================================
    # INPUT — user typed / pasted / selected something invalid
    # =========================================================================

    "ERR_NO_UNIPROT_IDS": ErrorSpec(
        message="No UniProt IDs provided",
        hint="Paste at least one UniProt accession (e.g. P12345) into the textarea before submitting.",
        category="input",
    ),

    "ERR_EMPTY_ID_LIST": ErrorSpec(
        message="The UniProt ID list is empty after trimming",
        hint="Make sure the IDs are separated by spaces, commas, or new lines and none are blank.",
        category="input",
    ),

    "ERR_NO_FILTER_IDS": ErrorSpec(
        message="No UniProt IDs provided for the filter",
        hint="Paste at least one UniProt accession to filter the UpSet by. Leaving the box empty would match every orthogroup.",
        category="input",
    ),

    "ERR_TOO_FEW_SPECIES": ErrorSpec(
        message="Pick at least 2 species",
        hint="UpSet plots compare two or more species. Tick more chips in the species picker.",
        category="input",
    ),

    "ERR_TOO_FEW_SPECIES_FILTERED": ErrorSpec(
        message="Pick at least 2 species before filtering",
        hint="Generate Figures 3 & 4 first (with ≥ 2 species), then come back and filter by UniProt IDs.",
        category="input",
    ),

    "ERR_SPECIES_NOT_IN_ANALYSIS": ErrorSpec(
        message="One or more species are not in the loaded analysis",
        hint="Use the species picker to choose names from the chip list — typing a species manually can mismatch.",
        category="input",
    ),

    "ERR_NO_MATCHING_ORTHOGROUPS": ErrorSpec(
        message="None of the pasted UniProt IDs were found",
        hint="Double-check the IDs (case-sensitive) and the species selection — IDs from species not in the analysis won't match.",
        category="input",
        severity="warning",
    ),

    "ERR_SPECIES_LIMIT_REACHED": ErrorSpec(
        message="Species limit reached",
        hint="OrthoGather is tuned for ≤ 50 species on a local desktop. Remove a chip first, or split the analysis in two and use /compare.",
        category="input",
        severity="warning",
    ),

    "ERR_SPECIES_NEAR_LIMIT": ErrorSpec(
        message="Approaching the species limit",
        hint="OrthoFinder runtime grows quadratically with species count. Past ~50 species, expect long runs on a typical laptop.",
        category="input",
        severity="info",
    ),

    "ERR_REPRODUCE_TRUNCATED": ErrorSpec(
        message="Pre-fill truncated at the species limit",
        hint="The saved run had more than 50 species; OrthoGather only pre-filled the first 50. Remove any you don't need and add others manually.",
        category="input",
        severity="warning",
    ),

    "ERR_TAXONOMY_FETCH_FAILED": ErrorSpec(
        message="Could not fetch NCBI lineage from UniProt",
        hint="The taxonomic tree needs internet for first-time fetches. Cached entries still work offline. Check your network and try again, or remove the offending species.",
        category="state",
        severity="warning",
    ),

    "ERR_TAXONOMY_INVALID_TAXID": ErrorSpec(
        message="Invalid or unknown taxon ID",
        hint="The selected species has an invalid NCBI taxon ID. It will appear under 'Unknown lineage' in the tree. Use the Fix field on the species table to re-resolve it.",
        category="input",
        severity="warning",
    ),

    "ERR_TAXONOMY_NO_SPECIES": ErrorSpec(
        message="No species provided for the taxonomy tree",
        hint="Add at least one species before requesting the taxonomic tree.",
        category="input",
        severity="warning",
    ),

    # =========================================================================
    # STATE — wrong order of operations / session not ready
    # =========================================================================

    "ERR_NO_ACTIVE_ANALYSIS": ErrorSpec(
        message="No active analysis in this browser session",
        hint="Open a result page first: pick Preselected, New Analysis, or History → Open.",
        category="state",
    ),

    "ERR_FOREGROUND_MISSING": ErrorSpec(
        message="Foreground proteins are missing from the session",
        hint="Load a foreground (paste UniProt IDs + click 'Load foreground') before running GO enrichment.",
        category="state",
    ),

    # =========================================================================
    # DATA — required file or sheet missing on disk
    # =========================================================================

    "ERR_GO_ANALYSIS_EXCEL_MISSING": ErrorSpec(
        message="GO analysis Excel file not found",
        hint="Click 'Download GOA files' first so OrthoGather can build Gene_Ontology_Analysis.xlsx.",
        category="data",
        http_code=404,
    ),

    "ERR_EXCEL_NOT_GENERATED": ErrorSpec(
        message="The Excel file does not exist yet",
        hint="Run the GO analysis first (Foreground → Background → Run GO enrichment).",
        category="data",
        http_code=404,
    ),

    "ERR_ENRICHMENT_EXCEL_MISSING": ErrorSpec(
        message="GO enrichment Excel not available",
        hint="Run 'Run GO enrichment' on the GO page before downloading the report.",
        category="data",
        http_code=404,
    ),

    "ERR_MALFORMED_EXCEL": ErrorSpec(
        message="Malformed Gene Ontology Excel file",
        hint="Re-generate the Excel by clicking 'Download GOA files' again. The file likely got corrupted mid-write.",
        category="data",
        http_code=500,
    ),

    "ERR_LOAD_ANALYSIS_FAILED": ErrorSpec(
        message="Could not load the analysis data from disk",
        hint="The Orthogroups.tsv may be unreadable. Try re-uploading or re-running the OrthoFinder analysis.",
        category="data",
        http_code=500,
    ),

    # =========================================================================
    # NETWORK / EXTERNAL — UniProt, GitHub, EBI down or unreachable
    # =========================================================================

    "ERR_GITHUB_TIMEOUT": ErrorSpec(
        message="GitHub API timed out",
        hint="Check your network connection and try again in a few minutes.",
        category="external",
        severity="warning",
        http_code=200,   # graceful — UI shows status without breaking page
    ),

    "ERR_GITHUB_UNREACHABLE": ErrorSpec(
        message="Could not reach GitHub",
        hint="OrthoGather uses GitHub to check for catalogue updates. Either you're offline or the GitHub API is degraded.",
        category="external",
        severity="warning",
        http_code=200,
    ),

    "ERR_GITHUB_RATE_LIMIT": ErrorSpec(
        message="GitHub API rate-limit reached",
        hint="Wait a few minutes and click 'Check for updates' again. The limit resets within the hour.",
        category="external",
        severity="warning",
        http_code=200,
    ),

    "ERR_GITHUB_BAD_STATUS": ErrorSpec(
        message="GitHub returned an unexpected response",
        hint="The check failed but OrthoGather still works locally. Skip the update for now and try again later.",
        category="external",
        severity="warning",
        http_code=200,
    ),

    # =========================================================================
    # COMPUTATIONAL — internal pipeline failure
    # =========================================================================

    "ERR_GO_FIGURE_FAILED": ErrorSpec(
        message="Could not generate the annotation-distribution figure",
        hint="Make sure the GOA Excel was built without warnings (check the status banner after 'Download GOA files').",
        category="system",
        http_code=500,
    ),

    "ERR_UPSET_COMPUTE_FAILED": ErrorSpec(
        message="Could not compute UpSet data",
        hint="The selected species may have produced an empty intersection. Try a different combination, or refresh the page to re-load the dataset.",
        category="system",
        http_code=500,
    ),

    "ERR_FILTERED_UPSET_FAILED": ErrorSpec(
        message="Filtered UpSet computation failed",
        hint="Some UniProt IDs may not be present in the dataset. Verify the IDs are correctly formatted and belong to the loaded species.",
        category="system",
        http_code=500,
    ),

    # =========================================================================
    # NOT-FOUND — explicit 404 for missing resources
    # =========================================================================

    "ERR_RUN_NOT_FOUND": ErrorSpec(
        message="Run not found",
        hint="The run may have been deleted from disk. Pick a different one from the History page.",
        category="not-found",
        http_code=404,
    ),

    "ERR_RUN_READ_FAILED": ErrorSpec(
        message="Could not read run metadata",
        hint="The meta.json or one of the per-run TSVs is unreadable. Delete the run from History and re-create it.",
        category="data",
        http_code=500,
    ),

    "ERR_NO_RUNS_FOUND": ErrorSpec(
        message="No runs found in your history",
        hint="Run an analysis first (New Analysis or Preselected) — completed runs land in ~/.orthogather/runs/.",
        category="not-found",
        http_code=404,
    ),

    # =========================================================================
    # FRONTEND — JS-only conditions (referenced by og-errors.js)
    # =========================================================================

    "ERR_EXPORT_PNG_FAILED": ErrorSpec(
        message="Could not export the figure as PNG",
        hint="Some browser extensions (e.g. ad blockers) interfere with canvas rendering. Try in a private window, or use SVG instead.",
        category="system",
        http_code=500,
    ),

    "ERR_EXPORT_SVG_FAILED": ErrorSpec(
        message="Could not export the figure as SVG",
        hint="Refresh the page and try again — the chart hadn't finished rendering. If the issue persists, see the browser console.",
        category="system",
        http_code=500,
    ),

    "ERR_GENERATE_FIRST": ErrorSpec(
        message="Generate the figure first",
        hint="Click Generate (or run the enrichment) before downloading — there's no figure to export yet.",
        category="state",
        severity="info",
        http_code=400,
    ),

    "ERR_UPSETJS_NOT_LOADED": ErrorSpec(
        message="The UpSetJS bundle failed to load",
        hint="Refresh the page. UpSetJS is served from /static/vendor/ — if it persists, the file may be missing from the install.",
        category="external",
        severity="warning",
        http_code=503,
    ),

    # =========================================================================
    # CATCH-ALL — unhandled exceptions, 404 page, 500 page
    # =========================================================================

    "ERR_NOT_FOUND_404": ErrorSpec(
        message="Page not found",
        hint="Check the URL — OrthoGather may have moved or removed that endpoint. Use the navigation to find what you need.",
        category="not-found",
        http_code=404,
    ),

    "ERR_UNEXPECTED": ErrorSpec(
        message="An unexpected error occurred",
        hint="This is a bug — please open an issue at github.com/CarlosVivasR/OrthoGather/issues with the steps you took, and include the error code shown.",
        category="system",
        http_code=500,
    ),
}


# ---------------------------------------------------------------------------
# Self-check (run on import, dev-mode safety net).
# ---------------------------------------------------------------------------
def _validate_catalogue() -> None:
    for code, spec in ERRORS.items():
        if not code.startswith("ERR_"):
            raise ValueError(f"Error code {code!r} must start with 'ERR_'.")
        if spec.category not in VALID_CATEGORIES:
            raise ValueError(
                f"{code}: category {spec.category!r} not in {VALID_CATEGORIES!r}"
            )
        if spec.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"{code}: severity {spec.severity!r} not in {VALID_SEVERITIES!r}"
            )
        if not (100 <= spec.http_code <= 599):
            raise ValueError(f"{code}: http_code {spec.http_code} out of range")
        if not spec.message or not spec.hint:
            raise ValueError(f"{code}: message and hint are required")


_validate_catalogue()


def lookup(code: str) -> ErrorSpec:
    """Return the spec for ``code`` or the ERR_UNEXPECTED fallback."""
    return ERRORS.get(code) or ERRORS["ERR_UNEXPECTED"]
