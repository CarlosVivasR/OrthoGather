"""
OrthoGather tutorial screenshot capture script.

Drives the running Flask app (default http://127.0.0.1:5001) via headless Chrome
and saves PNGs under static/images/tutorial/. Re-run any subset of steps with
the --only argument; everything else is fresh on every run.

Usage
-----
    # Capture all "cheap" screenshots that don't require a GOA download
    python tools/capture_tutorial_screenshots.py --skip-go-results

    # Capture everything (assumes GOA files have already been downloaded
    # and a foreground/background loaded in a previous session)
    python tools/capture_tutorial_screenshots.py

    # Just one shot
    python tools/capture_tutorial_screenshots.py --only home

Requires (in the conda env)
---------------------------
    pip install selenium webdriver-manager

The script is idempotent and tolerant: failure of one shot doesn't stop the rest.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "static" / "images" / "tutorial"
DEFAULT_URL = "http://127.0.0.1:5001"

# Viewport: a single common size keeps the tutorial figures visually consistent.
# 1280 x 800 mirrors a typical mid-size laptop; 1.5x device pixel ratio gives
# crisp screenshots without the file size of full retina.
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
DEVICE_PIXEL_RATIO = 1.5


def make_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver with sensible defaults for screenshots."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}")
    opts.add_argument(f"--force-device-scale-factor={DEVICE_PIXEL_RATIO}")
    opts.add_argument("--hide-scrollbars")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    # Pretend to be a normal-sized desktop so layout doesn't go mobile-first
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(VIEWPORT_WIDTH, VIEWPORT_HEIGHT)
    # The full GO flow (foreground -> background -> enrichment) can take ~60s
    # with 47 species; bump the async-script ceiling to 4 minutes so the flow
    # has plenty of room without changing per-page timeouts.
    driver.set_script_timeout(240)
    return driver


def _wait_ready(driver, timeout=10) -> None:
    """Block until document.readyState is 'complete'."""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def _scroll_to(driver, y: int) -> None:
    driver.execute_script(f"window.scrollTo(0, {y});")
    time.sleep(0.25)


def _scroll_to_selector(driver, selector: str, block: str = "start") -> None:
    driver.execute_script(
        f"document.querySelector({selector!r}).scrollIntoView({{block: {block!r}}});"
    )
    time.sleep(0.25)


def _save(driver, name: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.png"
    driver.save_screenshot(str(out))
    print(f"  saved {out.relative_to(REPO_ROOT)}  ({out.stat().st_size // 1024} KB)")
    return out


# ----------------------------------------------------------------------------
# Individual capture steps
# ----------------------------------------------------------------------------
def shot_home(driver, base: str) -> None:
    """Home page — the three entry-point cards visible."""
    driver.get(base + "/")
    _wait_ready(driver)
    # The home page has a fullscreen splash hero. Scroll past it to the
    # "Pick your starting point" cards.
    _scroll_to(driver, 750)
    _save(driver, "tut_00_home")


def shot_tutorial_top(driver, base: str) -> None:
    """Tutorial page — TOC + hero visible."""
    driver.get(base + "/tutorial")
    _wait_ready(driver)
    _scroll_to(driver, 0)
    _save(driver, "tut_tutorial_top")


def _enter_preselected(driver, base: str) -> None:
    """Set up the preselected dataset in the session, then land on /resultado."""
    # The /cargar_carpeta route both initialises the session AND renders
    # resultado.html. So one navigation does it all.
    driver.get(base + "/cargar_carpeta?filename=Orthogroups.zip&modo=preselected")
    _wait_ready(driver)
    # Give Plotly a beat to render the figures
    time.sleep(2.0)


def shot_protein_figures(driver, base: str) -> None:
    """Protein Analysis — Figures 1 + 2 (orthogroup distribution + sharing)."""
    _enter_preselected(driver, base)
    _scroll_to(driver, 400)
    _save(driver, "tut_01_protein_figures")


def shot_protein_species_picker(driver, base: str) -> None:
    """Protein Analysis — species chips picker (Compare specific species section)."""
    _enter_preselected(driver, base)
    _scroll_to_selector(driver, "#upset-heading", block="start")
    time.sleep(0.5)
    _save(driver, "tut_02_protein_species_picker")


def _run_upset(driver) -> bool:
    """Pick 3 species chips and click Generate UpSet. Returns True on success."""
    # Wait for chips to be populated by the page's JS
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script(
                "return document.querySelectorAll('#upset-picker-chips [data-species]').length > 0"
            )
        )
    except Exception:
        return False

    # Pick the first 3 chips
    driver.execute_script("""
        const chips = document.querySelectorAll('#upset-picker-chips [data-species]');
        for (let i = 0; i < Math.min(3, chips.length); i++) {
            chips[i].click();
        }
    """)
    time.sleep(0.4)

    # Click generate
    driver.execute_script("document.getElementById('upset-generate-btn')?.click();")

    # Wait for #upset-figures to become visible (no longer [hidden])
    try:
        WebDriverWait(driver, 45).until(
            lambda d: d.execute_script(
                "const el = document.getElementById('upset-figures');"
                "return el && !el.hasAttribute('hidden');"
            )
        )
        time.sleep(1.5)  # let SVGs paint
        return True
    except Exception:
        return False


def shot_protein_upset(driver, base: str) -> None:
    """Protein Analysis — UpSet plots (Fig 3 + 4). Generates them via JS click."""
    _enter_preselected(driver, base)
    if not _run_upset(driver):
        print("  SKIP tut_03_protein_upset — UpSet didn't render in time.")
        return
    _scroll_to_selector(driver, "#upset-card-3", block="start")
    time.sleep(0.4)
    _save(driver, "tut_03_protein_upset")


def shot_protein_uniprot_filter(driver, base: str) -> None:
    """Protein Analysis — UniProt filter for Figures 5 + 6.
    Reveals the filter section by force (it's hidden until UpSet runs)."""
    _enter_preselected(driver, base)
    # Force-reveal the filter section so the tutorial can show the layout
    driver.execute_script(
        "document.getElementById('upset-filter-section')?.removeAttribute('hidden');"
    )
    _scroll_to_selector(driver, "#upset-filter-section", block="start")
    time.sleep(0.4)
    _save(driver, "tut_04_protein_uniprot_filter")


def shot_go_match_table(driver, base: str) -> None:
    """GO page — species match table."""
    # Make sure we have a preselected session first
    _enter_preselected(driver, base)
    driver.get(base + "/resultado_goa")
    _wait_ready(driver)
    _scroll_to_selector(driver, "#species-table", block="start")
    time.sleep(0.4)
    _save(driver, "tut_05_go_match_table")


def shot_go_explainers(driver, base: str) -> None:
    """GO page — Foreground + Background explainer cards."""
    _enter_preselected(driver, base)
    driver.get(base + "/resultado_goa")
    _wait_ready(driver)
    # Reveal the hidden GO analysis block so explainers are visible without
    # going through the slow GOA download.
    driver.execute_script(
        "document.getElementById('go-analysis-block')?.removeAttribute('hidden');"
    )
    _scroll_to_selector(driver, ".goa-explainer", block="start")
    time.sleep(0.3)
    _save(driver, "tut_06_go_explainers")


def shot_go_settings(driver, base: str) -> None:
    """GO page — Analysis settings card with a help popover open."""
    _enter_preselected(driver, base)
    driver.get(base + "/resultado_goa")
    _wait_ready(driver)
    driver.execute_script(
        "document.getElementById('go-analysis-block')?.removeAttribute('hidden');"
    )
    # Force the Evidence-quality popover visible (the document click handler
    # would otherwise close it before the screenshot is taken).
    driver.execute_script(
        "document.querySelector('.figure-help-popover[data-help-for=\"evidence\"]')?"
        ".removeAttribute('hidden');"
    )
    _scroll_to_selector(driver, ".goa-settings", block="center")
    time.sleep(0.4)
    _save(driver, "tut_07_go_settings")


def _drive_full_go_flow(driver, base: str) -> bool:
    """Run the full GO enrichment flow from within the Selenium browser so the
    session cookies match. Assumes /download_goa_files has already populated
    GOAfiles/ and Gene_Ontology_Analysis.xlsx — those live on disk and are
    re-used."""
    # 1. Initialise session via /cargar_carpeta
    driver.get(base + "/cargar_carpeta?filename=Orthogroups.zip&modo=preselected")
    _wait_ready(driver)
    # 2. Visit /resultado_goa to load species_matches into session
    driver.get(base + "/resultado_goa")
    _wait_ready(driver)
    # 3-5. Submit foreground, background, run enrichment — via in-page fetch()
    result = driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        (async () => {
          // Pull 20 E. coli K12 UniProt IDs by parsing the Initial Groups via
          // a small server roundtrip. Easier: just hardcode some that we know
          // are present (they came from the catalogue we just downloaded).
          const ids = ['P05827','P07109','P08368','P09833','P0A9P9','P0A9Q1',
                       'P0A9R7','P0A9T8','P0AA16','P0AAF6','P0AAG3','P0AAI1',
                       'P0ACQ4','P0ACR4','P0ACR7','P0ACZ8','P0AE88','P0AEK2',
                       'P0AET8','P0AFJ5'];
          // Foreground
          let r = await fetch('/foreground_analysis', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({uniprot_ids: ids, use_orthogroups: true,
                                   single_copy_only: false})
          });
          if (!r.ok) return done({step:'fg', http: r.status});
          // Background = all GOA
          r = await fetch('/background_analysis', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({background_choice: '5', use_orthogroups: false,
                                   single_copy_only: false, custom_uniprot_ids: []})
          });
          if (!r.ok) return done({step:'bg', http: r.status});
          // Run enrichment
          r = await fetch('/gene_ontology_analysis', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({p_value: 0.05, min_depth: 2,
                                   evidence_preset: 'all',
                                   counting_mode: 'per_protein'})
          });
          if (!r.ok) return done({step:'go', http: r.status});
          const data = await r.json();
          done({step:'ok', counts:{
            bp: (data.bp_results||[]).length,
            cc: (data.cc_results||[]).length,
            mf: (data.mf_results||[]).length
          }});
        })();
    """)
    if not result or result.get("step") != "ok":
        print(f"  Drive failed: {result}")
        return False
    total = sum(result["counts"].values())
    print(f"  GO terms returned: BP={result['counts']['bp']} "
          f"CC={result['counts']['cc']} MF={result['counts']['mf']} "
          f"(total {total})")
    if total == 0:
        return False

    # Reload the GO page and trigger the in-page render of the cached results.
    # The page's runAnalysisBtn handler is the simplest path: clicking it
    # re-runs the analysis (now fast thanks to GAF cache) and renders the
    # Plotly chart + table.
    driver.get(base + "/resultado_goa")
    _wait_ready(driver)
    # Unhide the GO analysis block and enable the run button (which the page's
    # own handlers would normally enable after foreground/background loads —
    # we already loaded both via fetch() above, so we bypass those handlers).
    driver.execute_script("""
        document.getElementById('go-analysis-block')?.removeAttribute('hidden');
        const btn = document.getElementById('run-full-go-analysis');
        if (btn) { btn.disabled = false; }
    """)
    driver.execute_script(
        "document.getElementById('run-full-go-analysis')?.click();"
    )
    # Wait for #go-results-container to become visible. The page's JS uses
    # `el.hidden = false` which also removes the attribute, so the same check
    # works.
    try:
        WebDriverWait(driver, 180).until(
            lambda d: d.execute_script(
                "const el = document.getElementById('go-results-container');"
                "return el && !el.hasAttribute('hidden') && el.style.display !== 'none';"
            )
        )
    except Exception:
        # Fall back: check if at least the Plotly host has children (we may
        # have missed the visibility transition due to the dual-attr mechanism)
        children = driver.execute_script(
            "return document.querySelector('#go-plot')?.children?.length || 0;"
        )
        if children > 0:
            print("  Results visible via fallback check (Plotly populated).")
        else:
            print("  GO results container never showed up.")
            return False
    time.sleep(1.5)  # let Plotly paint
    return True


# Module-level guard so we only drive the flow once per script run even if
# multiple result-dependent shots are requested.
_flow_done = False


def _ensure_results(driver, base: str) -> bool:
    global _flow_done
    if _flow_done:
        return True
    print("  Driving full GO flow inside the browser session...")
    _flow_done = _drive_full_go_flow(driver, base)
    return _flow_done


def shot_go_results_plot(driver, base: str) -> None:
    """GO page — interactive Plotly chart. Drives the flow if needed."""
    if not _ensure_results(driver, base):
        print("  SKIP tut_08_go_results_plot — GO flow didn't produce results.")
        return
    # Click the "Cellular Component" namespace tab — far fewer terms (~34)
    # than BP (~400), so the chart fits in one viewport without per-bar clipping.
    driver.execute_script("""
        const btn = [...document.querySelectorAll('.go-ns-btn')]
                       .find(b => b.dataset.ns === 'cellular_component');
        btn?.click();
    """)
    time.sleep(1.2)
    _scroll_to_selector(driver, "#go-plot", block="start")
    time.sleep(0.6)
    _save(driver, "tut_08_go_results_plot")


def shot_go_results_table(driver, base: str) -> None:
    """GO page — interactive table with evidence chips."""
    if not _ensure_results(driver, base):
        print("  SKIP tut_09_go_results_table — GO flow didn't produce results.")
        return
    _scroll_to_selector(driver, "#go-table", block="start")
    time.sleep(0.5)
    _save(driver, "tut_09_go_results_table")


def shot_history(driver, base: str) -> None:
    """History page — past runs."""
    driver.get(base + "/history")
    _wait_ready(driver)
    _scroll_to(driver, 0)
    time.sleep(0.4)
    _save(driver, "tut_10_history")


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
ALL_STEPS: Dict[str, Callable] = {
    "home":                shot_home,
    "tutorial_top":        shot_tutorial_top,
    "protein_figures":     shot_protein_figures,
    "protein_picker":      shot_protein_species_picker,
    "protein_upset":       shot_protein_upset,
    "protein_uniprot":     shot_protein_uniprot_filter,
    "go_match_table":      shot_go_match_table,
    "go_explainers":       shot_go_explainers,
    "go_settings":         shot_go_settings,
    "go_results_plot":     shot_go_results_plot,
    "go_results_table":    shot_go_results_table,
    "history":             shot_history,
}

# Anything that needs the GO enrichment to have been run already
GO_RESULT_STEPS = {"go_results_plot", "go_results_table"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=DEFAULT_URL)
    ap.add_argument("--skip-go-results", action="store_true",
                    help="Skip steps that require a finished GO enrichment.")
    ap.add_argument("--only", nargs="*", choices=list(ALL_STEPS),
                    help="Run only these named steps.")
    args = ap.parse_args()

    steps = args.only or list(ALL_STEPS)
    if args.skip_go_results:
        steps = [s for s in steps if s not in GO_RESULT_STEPS]

    print(f"Capturing into {OUT_DIR}")
    print(f"Steps: {', '.join(steps)}")

    driver = make_driver()
    try:
        for step in steps:
            print(f"\n=== {step} ===")
            try:
                ALL_STEPS[step](driver, args.base_url)
            except Exception as e:
                print(f"  FAILED: {e}")
    finally:
        driver.quit()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
