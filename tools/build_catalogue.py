"""
Build / refresh the OrthoGather proteome catalogue and regenerate the committed
``.gz`` baseline. Two modes:

REFRESH (default) — fast, in-place
    Rewrites every ``file_url`` against EBI's authoritative ``proteome2taxid``
    table by an EXACT taxid join. EBI renumbers/renames/removes its ``.goa``
    files over time, so URLs drift and start 404ing; the leading number in the
    filename is an *unstable* internal id, so matching on it (or on species name)
    risks grabbing the wrong strain. Joining on the stable NCBI taxid (already in
    every entry) fixes the 404s at the root with no chance of mismatching a strain.

FULL (``--full``) — slow, from scratch
    Rebuilds the entire catalogue from UniProt (ALL proteomes, every quality tier)
    + EBI GOA. Stores, per entry, the **version of the proteome** (UniProt's
    per-proteome ``modified`` date) and the **version of its GOA file** (EBI's
    last-modified date + size). Requires streaming the full UniProt proteomes JSON
    (~1 M objects, several GB) so it is paginated, retried and resumable.

The script is re-runnable. After it writes, publish ``proteomes_list.json.gz`` as
a GitHub release asset so the running app can auto-update.

USAGE
-----
    python tools/build_catalogue.py                 # fast refresh in place
    python tools/build_catalogue.py --dry-run       # refresh: print diff, write nothing
    python tools/build_catalogue.py --full          # full rebuild from UniProt + EBI
    python tools/build_catalogue.py --full --resume  # resume an interrupted full rebuild
    python tools/build_catalogue.py --full --limit 5000  # quick partial run for testing
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

REPO = Path(__file__).resolve().parent.parent
CATALOGUE_DIR = REPO / "static" / "Proteomes_json"
JSON_PATH = CATALOGUE_DIR / "proteomes_list.json"
GZ_PATH = CATALOGUE_DIR / "proteomes_list.json.gz"
MANIFEST_PATH = CATALOGUE_DIR / "proteomes_list.manifest.json"

GOA_BASE = "https://ftp.ebi.ac.uk/pub/databases/GO/goa/proteomes/"
PROTEOME2TAXID_URL = GOA_BASE + "proteome2taxid"
UNIPROT_SEARCH = "https://rest.uniprot.org/proteomes/search"

MAX_RETRIES = 5
TIMEOUT = 120


# --------------------------------------------------------------------------- #
# Generic robust GET
# --------------------------------------------------------------------------- #
def get_with_retries(url: str, session: requests.Session | None = None, expect_json=False):
    """GET with exponential backoff. Returns the Response. Raises on persistent failure
    so callers abort WITHOUT clobbering the good catalogue on disk."""
    s = session or requests
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = s.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                if expect_json:
                    r.json()  # surface malformed payloads as a retryable error
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < MAX_RETRIES:
            wait = min(2 ** attempt, 30)
            print(f"    request attempt {attempt} failed ({last}); retry in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"GET failed after {MAX_RETRIES} attempts ({url[:80]}…): {last}")


# --------------------------------------------------------------------------- #
# EBI GOA: proteome2taxid + per-file version (date/size) from the directory index
# --------------------------------------------------------------------------- #
def fetch_proteome2taxid() -> str:
    """Download EBI's proteome2taxid table. Raises on persistent failure."""
    return get_with_retries(PROTEOME2TAXID_URL).text


def parse_taxid_map(text: str) -> dict:
    """Parse ``name <TAB> taxid <TAB> filename.goa`` into ``{taxid: filename}``.

    First occurrence wins on the rare duplicate taxid; collisions/malformed lines
    are counted and reported so a surprising spike is visible, not silent.
    """
    mapping: dict[str, str] = {}
    collisions = malformed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            malformed += 1
            continue
        taxid, filename = parts[1].strip(), parts[2].strip()
        if not taxid or not filename:
            malformed += 1
            continue
        if taxid in mapping:
            collisions += 1
            continue
        mapping[taxid] = filename
    print(f"  proteome2taxid: {len(mapping)} taxids "
          f"({collisions} duplicate taxids skipped, {malformed} malformed lines)")
    return mapping


# Apache autoindex row: <a href="X.goa">…</a></td><td>DATE TIME</td><td>SIZE</td>
_GOA_ROW = re.compile(
    r'href="([^"]+\.goa)"[^>]*>.*?</a>\s*</td>\s*'
    r'<td[^>]*>\s*(\d{4}-\d{2}-\d{2})\s+[\d:]+\s*</td>\s*'
    r'<td[^>]*>\s*([\d.]+[KMGT]?|-)\s*</td>',
    re.I,
)


def fetch_goa_index() -> dict:
    """Return ``{filename.goa: {"version": 'YYYY-MM-DD', "size": '9.3M'}}`` parsed
    from EBI's directory listing — the per-file 'version' of each GOA file."""
    html = get_with_retries(GOA_BASE).text
    index = {}
    for fname, date, size in _GOA_ROW.findall(html):
        index[fname] = {"version": date, "size": (None if size == "-" else size)}
    print(f"  GOA index: {len(index)} .goa files with dates/sizes")
    return index


def build_goa_lookup() -> dict:
    """Combine proteome2taxid + the directory index into
    ``{taxid: {"url":…, "version":…, "size":…}}``."""
    taxid_map = parse_taxid_map(fetch_proteome2taxid())
    index = fetch_goa_index()
    lookup = {}
    for taxid, fname in taxid_map.items():
        meta = index.get(fname, {})
        lookup[taxid] = {
            "url": GOA_BASE + fname,
            "version": meta.get("version"),
            "size": meta.get("size"),
        }
    return lookup


# --------------------------------------------------------------------------- #
# REFRESH mode — rewrite file_url by taxid join (keeps existing entries/schema)
# --------------------------------------------------------------------------- #
def load_current_catalogue() -> list:
    if not JSON_PATH.exists() and GZ_PATH.exists():
        print(f"  raw JSON absent — seeding from {GZ_PATH.name}")
        with gzip.open(GZ_PATH, "rb") as src, open(JSON_PATH, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
    with open(JSON_PATH) as f:
        return json.load(f)


def refresh(catalogue: list, taxid_map: dict) -> dict:
    """Rewrite every ``file_url`` by exact taxid join. ``taxid_map`` is
    ``{taxid: filename}``. Returns change stats."""
    changed = newly_na = newly_resolved = resolved = unchanged = 0
    for entry in catalogue:
        taxid = str(entry.get("taxon_id", "")).strip()
        old = entry.get("file_url", "NA")
        filename = taxid_map.get(taxid)
        new = GOA_BASE + filename if filename else "NA"
        if new != "NA":
            resolved += 1
        if new == old:
            unchanged += 1
            continue
        changed += 1
        if new == "NA" and old not in ("NA", "", None):
            newly_na += 1
        elif new != "NA" and old in ("NA", "", None):
            newly_resolved += 1
        entry["file_url"] = new
    return {"total": len(catalogue), "resolved": resolved, "changed": changed,
            "unchanged": unchanged, "newly_na": newly_na, "newly_resolved": newly_resolved}


# --------------------------------------------------------------------------- #
# FULL mode — stream every UniProt proteome (paginated, retried, resumable)
# --------------------------------------------------------------------------- #
_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
JSONL_PATH = str(JSON_PATH) + ".full.jsonl"
CURSOR_PATH = str(JSON_PATH) + ".full.cursor"


def fetch_reference_upids() -> set:
    """Authoritative set of UniProt **reference** proteome ids (``proteome_type:1``).

    We classify ``type`` from membership in THIS set, not from the per-object
    ``proteomeType`` string — that string is "Reference and representative
    proteome" for some reference proteomes but plain "Representative proteome" for
    others, so a substring check silently mislabels ~33 K reference proteomes.
    """
    url = UNIPROT_SEARCH.replace("/search", "/stream") + "?query=proteome_type%3A1&format=list"
    text = get_with_retries(url).text
    ids = {line.strip() for line in text.splitlines() if line.strip()}
    print(f"  reference proteomes (proteome_type:1): {len(ids)}")
    return ids


def _parse_proteome(r: dict, reference_ids: set) -> dict:
    """Map one UniProt proteome JSON object to a catalogue entry. Stores the
    proteome's own ``modified`` date as its version. ``file_url``/GOA filled later."""
    upid = r.get("id")
    tx = r.get("taxonomy") or {}
    name = tx.get("scientificName") or ""
    taxid = tx.get("taxonId")
    # Append UniProt's common name + taxonomy synonyms in parentheses, mirroring
    # the original catalogue's label format:
    #   "Mus musculus (Mouse) [UP...]"
    #   "Mycolicibacterium smegmatis (...) (Mycobacterium smegmatis) [UP...]"
    # Critical for matching AND display: keeps user-supplied common names
    # ("Mouse", "Baker's yeast") and OLD scientific names (after UniProt genus
    # renames like Mycobacterium→Mycolicibacterium) resolving to the right
    # proteome — and therefore to the right GOA file.
    alt = []
    common = tx.get("commonName")
    if common:
        alt.append(common)
    alt.extend(s for s in (tx.get("synonyms") or []) if s)
    alt_part = "".join(f" ({a})" for a in alt)
    return {
        "label": f"{name}{alt_part} [{upid}]" if name else (upid or ""),
        "Proteome Id": upid,
        # Schema keeps "reference"/"non-reference"; reference ⇔ UniProt proteome_type:1.
        "type": "reference" if upid in reference_ids else "non-reference",
        "taxon_id": str(taxid) if taxid is not None else "",
        "protein_count": r.get("proteinCount"),
        "proteome_version": r.get("modified"),  # per-proteome version (UniProt modified date)
    }


def stream_uniprot(reference_ids: set, query="*", limit=None, resume=False):
    """Yield catalogue entries for UniProt proteomes matching ``query``, paginating
    by cursor.

    Robust + resumable: each page's entries are appended to a JSONL sidecar and the
    next-page URL is checkpointed, so an interrupted run can ``--resume`` instead of
    re-downloading several GB. Yields parsed entries (also persisted to the JSONL).
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    url = f"{UNIPROT_SEARCH}?query={quote(query)}&format=json&size=500"
    mode = "w"
    already = 0
    if resume and os.path.exists(CURSOR_PATH) and os.path.exists(JSONL_PATH):
        saved = Path(CURSOR_PATH).read_text().strip()
        if saved == "DONE":
            print("  resume: previous full fetch already complete — reusing JSONL")
            url = None
        elif saved:
            url = saved
        with open(JSONL_PATH) as f:
            for line in f:
                if line.strip():
                    already += 1
        mode = "a"
        print(f"  resume: {already} entries already fetched; continuing")

    n = already
    with open(JSONL_PATH, mode) as out:
        # Re-yield already-fetched entries (so the caller assembles the full set).
        if mode == "a":
            with open(JSONL_PATH) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass
        while url:
            resp = get_with_retries(url, session=session, expect_json=True)
            page = resp.json().get("results", [])
            if not page:
                break
            for r in page:
                entry = _parse_proteome(r, reference_ids)
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                yield entry
                n += 1
                if limit and n >= limit:
                    out.flush()
                    Path(CURSOR_PATH).write_text("DONE")
                    print(f"  reached --limit {limit}; stopping")
                    return
            out.flush()
            m = _NEXT_RE.search(resp.headers.get("Link", ""))
            url = m.group(1) if m else None
            Path(CURSOR_PATH).write_text(url or "DONE")
            if n % 20000 < 500:
                print(f"  fetched ~{n} proteomes...")
    Path(CURSOR_PATH).write_text("DONE")


def uniprot_release() -> tuple:
    """(release, release_date) read from UniProt response headers, e.g. ('2026_01', ...)."""
    r = get_with_retries(UNIPROT_SEARCH + "?query=%2A&format=list&size=1")
    return (r.headers.get("x-uniprot-release"), r.headers.get("x-uniprot-release-date"))


def build_full(types=(1, 2, 3, 4), limit=None, resume=False) -> tuple:
    """Assemble the catalogue from UniProt + EBI GOA, restricted to the given UniProt
    proteome-quality tiers (1=Reference, 2=Other/representative, 3=Redundant,
    4=Excluded). Returns (catalogue, stats).

    Redundant/Excluded tiers are near-identical duplicates and excluded low-quality
    assemblies — keeping only 1+2 yields a clean catalogue with the SAME GOA-taxon
    coverage (GOA is keyed by taxid, covered by the reference/representative tiers).
    """
    print("=== UniProt release ===")
    release, release_date = uniprot_release()
    print(f"  {release} ({release_date})")

    # UniProt query for the requested tiers, e.g. "(proteome_type:1) OR (proteome_type:2)".
    query = " OR ".join(f"(proteome_type:{t})" for t in types)
    print(f"  proteome tiers: {list(types)}  →  query: {query}")

    print("\n=== Reference proteome set (proteome_type:1) ===")
    reference_ids = fetch_reference_upids()

    print("\n=== EBI GOA lookup (taxid → url/version/size) ===")
    goa = build_goa_lookup()

    print("\n=== Stream UniProt proteomes ===")
    catalogue = []
    resolved = ref = 0
    goa_taxa = set()
    for entry in stream_uniprot(reference_ids, query=query, limit=limit, resume=resume):
        info = goa.get(entry["taxon_id"])
        if info:
            entry["file_url"] = info["url"]
            entry["goa_version"] = info["version"]
            entry["goa_size"] = info["size"]
            resolved += 1
            goa_taxa.add(entry["taxon_id"])
        else:
            entry["file_url"] = "NA"
            entry["goa_version"] = None
            entry["goa_size"] = None
        if entry["type"] == "reference":
            ref += 1
        catalogue.append(entry)

    stats = {"total": len(catalogue), "resolved": resolved, "reference": ref,
             "goa_taxa": len(goa_taxa), "types": list(types),
             "release": release, "release_date": release_date}
    return catalogue, stats


# --------------------------------------------------------------------------- #
# Shared writer
# --------------------------------------------------------------------------- #
def write_files(catalogue: list, manifest: dict) -> None:
    """Atomically write the JSON, regenerate the .gz baseline, write the manifest."""
    tmp_json = str(JSON_PATH) + ".tmp"
    with open(tmp_json, "w") as f:
        json.dump(catalogue, f, ensure_ascii=False)
    os.replace(tmp_json, JSON_PATH)
    manifest["size_bytes"] = JSON_PATH.stat().st_size

    tmp_gz = str(GZ_PATH) + ".tmp"
    with open(JSON_PATH, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    os.replace(tmp_gz, GZ_PATH)

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  wrote {JSON_PATH.name} ({manifest['size_bytes'] / 1e6:.1f} MB)")
    print(f"  wrote {GZ_PATH.name} ({GZ_PATH.stat().st_size / 1e6:.1f} MB)")
    print(f"  wrote {MANIFEST_PATH.name}")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Build/refresh the proteome catalogue.")
    ap.add_argument("--full", action="store_true",
                    help="Full rebuild from UniProt + EBI (slow; stores per-proteome and per-GOA versions).")
    ap.add_argument("--types", default="1,2",
                    help="With --full: comma-separated UniProt proteome tiers to include "
                         "(1=Reference, 2=Other/representative, 3=Redundant, 4=Excluded). "
                         "Default 1,2 — a clean catalogue with full GOA-taxon coverage.")
    ap.add_argument("--resume", action="store_true",
                    help="With --full: resume an interrupted run from its checkpoint.")
    ap.add_argument("--limit", type=int, default=None,
                    help="With --full: stop after N proteomes (for testing).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Refresh mode: compute and print the diff but write nothing.")
    args = ap.parse_args()

    if args.full:
        try:
            types = tuple(int(t) for t in args.types.split(",") if t.strip())
        except ValueError:
            print(f"ERROR: --types must be comma-separated integers, got {args.types!r}")
            return 1
        catalogue, stats = build_full(types=types, limit=args.limit, resume=args.resume)
        if not catalogue:
            print("ERROR: 0 proteomes assembled — aborting without touching the catalogue.")
            return 1
        now = _now_iso()
        manifest = {
            "version": now[:10],
            "release_tag": None,
            "downloaded_at": now,
            "refreshed_at": now,
            "source": "UniProt proteomes (REST) + EBI GOA proteomes",
            "uniprot_release": stats["release"],
            "uniprot_release_date": stats["release_date"],
            "proteome_tiers": stats["types"],
            "goa_source_url": PROTEOME2TAXID_URL,
            "proteome_count": stats["total"],
            "reference_count": stats["reference"],
            "goa_resolved_count": stats["resolved"],
            "goa_taxa_count": stats["goa_taxa"],
            "is_fallback": False,
        }
        print("\n=== Summary ===")
        print(f"  proteomes:     {stats['total']}  (tiers {stats['types']})")
        print(f"    reference:   {stats['reference']}")
        print(f"  GOA resolved:  {stats['resolved']}  ({stats['goa_taxa']} distinct taxa)")
        print(f"  UniProt:       {stats['release']} ({stats['release_date']})")
        print("\n=== Write outputs ===")
        write_files(catalogue, manifest)
        # Full run complete → clear the resume sidecars.
        for p in (JSONL_PATH, CURSOR_PATH):
            try:
                os.remove(p)
            except OSError:
                pass
        print("\nDone. Review the summary, then publish proteomes_list.json.gz as a release asset.")
        return 0

    # REFRESH mode
    print("=== Fetch EBI proteome2taxid ===")
    taxid_map = parse_taxid_map(fetch_proteome2taxid())
    if not taxid_map:
        print("ERROR: proteome2taxid parsed to 0 entries — aborting.")
        return 1

    print("\n=== Load current catalogue ===")
    catalogue = load_current_catalogue()
    print(f"  {len(catalogue)} entries")

    print("\n=== Refresh file_url by taxid join ===")
    stats = refresh(catalogue, taxid_map)
    print(f"  total entries:    {stats['total']}")
    print(f"  GOA resolved:     {stats['resolved']}")
    print(f"  changed:          {stats['changed']}")
    print(f"    ↳ newly resolved (NA→url): {stats['newly_resolved']}")
    print(f"    ↳ newly NA (url→NA):       {stats['newly_na']}")
    print(f"  unchanged:        {stats['unchanged']}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    now = _now_iso()
    manifest = {
        "version": now[:10], "release_tag": None, "downloaded_at": now, "refreshed_at": now,
        "source_url": PROTEOME2TAXID_URL, "proteome_count": stats["total"],
        "goa_resolved_count": stats["resolved"], "is_fallback": False,
    }
    print("\n=== Write outputs ===")
    write_files(catalogue, manifest)
    print("\nDone. Review the diff above, then publish proteomes_list.json.gz as a release asset.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
