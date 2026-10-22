"""Build docs/Installation_guide.pdf from docs/INSTALL.html.

The PDF is the web guide printed by headless Chrome, with a cover, a table of
contents and a footer carrying the version from orthogather/config.py. Run it
after changing the guide or the version (see installers/README.md, Releasing).

Usage:  python tools/build_installation_guide.py [--chrome PATH]
"""
from __future__ import annotations

import argparse
import datetime
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]
AUTHORS = ("Carlos Vivas-Rodríguez, David Gomez Matallanas, Colm J. Ryan,<br>"
           "Siobhán McClean, Olivier Dennler and Joanna Drabińska")


def version():
    text = (REPO / "orthogather" / "config.py").read_text()
    return re.search(r'ORTHOGATHER_VERSION = "([^"]+)"', text).group(1)


def print_html(ver):
    html = (DOCS / "INSTALL.html").read_text()
    sections = re.findall(r'<div class="section-title">([^<]+)</div>', html)
    month = datetime.date.today().strftime("%B %Y")
    css = f"""
<style>
  @page {{ size: A4; margin: 22mm 18mm 20mm;
    @bottom-left {{ content: "OrthoGather installation guide · v{ver}"; font: 11px Inter, sans-serif; color: #6b7280; }}
    @bottom-right {{ content: counter(page); font: 11px Inter, sans-serif; color: #6b7280; }} }}
  @page cover {{ margin: 0; @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
  @media print {{
    header.hero, body > footer {{ display: none; }}
    body {{ background: #fff; }}
    main.wrap {{ padding-top: 0; }}
    .section-title {{ font-family: 'Fraunces', Georgia, serif; font-size: 24px; font-weight: 700;
      letter-spacing: 0; text-transform: none; color: var(--navy); margin: 34px 0 16px; }}
    .section-title:first-of-type {{ margin-top: 0; }}
  }}
  .guide-cover {{ page: cover; position: relative; width: 210mm; height: 297mm; overflow: hidden;
    break-after: page; text-align: center; font-family: Inter, sans-serif; }}
  .guide-cover .bg {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: .32; }}
  .guide-cover .inner {{ position: relative; padding-top: 30mm; }}
  .guide-cover h1 {{ font-family: 'Fraunces', Georgia, serif; font-size: 36px; color: #003366; margin: 0 0 8mm; }}
  .guide-cover .logo {{ width: 62mm; }}
  .guide-cover .sub {{ font-size: 16px; color: #374151; margin: 8mm 0 4mm; line-height: 1.6; }}
  .guide-cover .ver {{ font-weight: 700; color: #003366; font-size: 14px; }}
  .guide-cover .authors {{ font-size: 14px; margin: 9mm 0 3mm; line-height: 1.6; }}
  .guide-cover .links {{ font-size: 12px; color: #6b7280; }}
  .guide-cover .logos {{ position: absolute; bottom: 18mm; left: 0; right: 0; display: flex;
    justify-content: center; align-items: center; gap: 22mm; }}
  .guide-cover .logos img {{ height: 20mm; }}
  .guide-contents {{ break-after: page; font-family: Inter, sans-serif; }}
  .guide-contents h2 {{ font-family: 'Fraunces', Georgia, serif; font-size: 28px; color: #003366; margin: 0 0 8mm; }}
  .guide-contents ol {{ font-size: 16px; line-height: 2.1; padding-left: 7mm; margin: 0 0 10mm; }}
  .guide-contents p {{ font-size: 13px; color: #374151; }}
</style>
"""
    items = "".join(f"<li>{s}</li>" for s in sections)
    front = f"""
<section class="guide-cover">
  <img class="bg" src="assets/guide/cover-background.jpg" alt="">
  <div class="inner">
    <h1>Installation guide</h1>
    <img class="logo" src="assets/guide/logo.png" alt="OrthoGather">
    <p class="sub">A local platform for orthology-based proteome comparisons<br>and Gene Ontology enrichment</p>
    <p class="ver">Version {ver} · {month}</p>
    <p class="authors">{AUTHORS}</p>
    <p class="links">github.com/CarlosVivasR/OrthoGather · doi.org/10.5281/zenodo.18510910</p>
  </div>
  <div class="logos">
    <img src="assets/guide/ucd-cancer-data-lab.png" alt="UCD Cancer Data Lab">
    <img src="assets/guide/ucd.png" alt="University College Dublin">
  </div>
</section>
<section class="guide-contents">
  <h2>Contents</h2>
  <ol>{items}</ol>
  <p>This guide covers installation only. How to use OrthoGather is described in the README, the
  tutorial inside the application and the paper: Vivas-Rodríguez C, Gomez Matallanas D, Ryan CJ,
  McClean S, Dennler O, Drabinska J. OrthoGather: a local platform for orthology-based proteome
  comparisons and Gene Ontology enrichment. bioRxiv (2026), doi.org/10.64898/2026.01.30.702851.</p>
  <p>Questions and problems: github.com/CarlosVivasR/OrthoGather/issues</p>
</section>
"""
    # Print the troubleshooting answers too: <details> prints closed otherwise.
    css += "<script>addEventListener('DOMContentLoaded', () => " \
           "document.querySelectorAll('details').forEach(d => d.open = true));</script>\n"
    html = html.replace("</head>", css + "</head>", 1)
    return re.sub(r"(<body[^>]*>)", r"\1" + front, html, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome")
    args = ap.parse_args()
    chrome = args.chrome or next((c for c in CHROME_CANDIDATES
                                  if Path(c).exists() or shutil.which(c)), None)
    if not chrome:
        sys.exit("Google Chrome or Chromium not found; pass --chrome PATH.")
    ver = version()
    # Written next to INSTALL.html so that the relative image paths resolve.
    src = DOCS / "_installation_guide_print.html"
    src.write_text(print_html(ver))
    out = DOCS / "Installation_guide.pdf"
    try:
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            "--virtual-time-budget=10000", f"--user-data-dir={profile}",
                            f"--print-to-pdf={out}", src.as_uri()],
                           check=True, capture_output=True)
    finally:
        src.unlink(missing_ok=True)
    print(f"Wrote {out} (version {ver})")


if __name__ == "__main__":
    main()
