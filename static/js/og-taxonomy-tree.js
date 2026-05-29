/* ============================================================================
   OrthoGather taxonomic tree — minimalist renderer (Point 11, v2 reset).

   Design principles after the aesthetic reset (2026-05-26):
     - No live updates. The tree builds only when the user explicitly clicks
       a "Generate / refresh tree" button. No debounce, no live fetch on
       species add/remove — the user controls when to spend the lookup.
     - No modal, no Expand, no summary stat cards, no iTOL handoff button.
     - Only one export: Download Newick.
     - Compact (~600 px wide). Looks like a small scientific-figure dendrogram,
       not a dashboard widget.
     - Internal nodes are unlabeled circles. Only species names render at
       leaves. Hover the species circle for a native title tooltip with
       taxon id + full lineage (lightweight).

   Public API on `window.OGTaxonomyTree`:
     - render(opts)            → draws the dendrogram into a container
     - fetchTree(speciesArr)   → POST to /api/taxonomy_tree
     - downloadNewick(nwk, n)  → triggers .nwk file download
   ============================================================================ */
(function () {
  "use strict";

  function _render({ containerId, treeData, perLeaf = 36, width = 600 }) {
    if (!treeData || !window.d3) return;
    const root = d3.hierarchy(treeData);
    const nLeaves = root.leaves().length || 1;

    // Generous right margin so even long species names ("Mycobacterium
    // tuberculosis H37Rv") fit without clipping.
    const margin = { top: 12, right: 240, bottom: 12, left: 12 };
    const innerW = width - margin.left - margin.right;
    const innerH = Math.max(120, nLeaves * perLeaf);
    const height = innerH + margin.top + margin.bottom;

    const container = d3.select("#" + containerId);
    container.selectAll("*").remove();

    const svg = container.append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMinYMin meet")
      .attr("width", width)
      .attr("height", height)
      .style("cursor", "grab");

    // ── Pan + zoom (Google-Maps style) ─────────────────────────────────
    // Drag the SVG to pan; scroll to zoom. Useful when species names are
    // long and would otherwise be clipped by the right margin: the user
    // can drag left to read them. We zoom-in modestly (0.5×–4×) so users
    // can't accidentally lose the tree off-screen.
    const g = svg.append("g");

    const zoom = d3.zoom()
      .scaleExtent([0.5, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });

    const initialTransform = d3.zoomIdentity.translate(margin.left, margin.top);
    svg.call(zoom)
      .call(zoom.transform, initialTransform)
      .on("mousedown.cursor", () => svg.style("cursor", "grabbing"))
      .on("mouseup.cursor",   () => svg.style("cursor", "grab"));

    // Expose a reset handler on the container so the host page can wire
    // a "reset view" button if it wants one.
    container.node().__resetZoom = () => {
      svg.transition().duration(220).call(zoom.transform, initialTransform);
    };

    d3.cluster().size([innerH, innerW])(root);

    // Branches — thin subtle gray
    g.selectAll("path.link").data(root.links()).join("path")
      .attr("class", "link")
      .attr("d", d => `M${d.source.y},${d.source.x} V${d.target.x} H${d.target.y}`);

    // ── Custom HTML tooltip ────────────────────────────────────────────
    // Native SVG <title> tooltips have a ~1 s browser delay → feels broken.
    // A floating div on mouseover is the standard D3 pattern: instant
    // feedback, styled to match the rest of OrthoGather.
    let tip = document.getElementById("og-tax-tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "og-tax-tooltip";
      tip.className = "og-tax-tooltip";
      document.body.appendChild(tip);
    }
    function showTip(html, evt) {
      tip.innerHTML = html;
      tip.style.display = "block";
      tip.style.left = (evt.pageX + 12) + "px";
      tip.style.top  = (evt.pageY + 12) + "px";
    }
    function hideTip() { tip.style.display = "none"; }
    function moveTip(evt) {
      tip.style.left = (evt.pageX + 12) + "px";
      tip.style.top  = (evt.pageY + 12) + "px";
    }

    // Internal nodes — small unlabeled circles. Hover reveals rank + name.
    const internalG = g.selectAll("g.internal")
      .data(root.descendants().filter(d => d.children))
      .join("g")
      .attr("class", "internal")
      .attr("transform", d => `translate(${d.y}, ${d.x})`);
    internalG.append("circle").attr("r", 3.5);
    internalG
      .on("mouseover", function (event, d) {
        const rank = d.data.rank ? `<span class="og-tax-tip-rank">${d.data.rank}</span>` : "";
        showTip(`${rank}<b>${d.data.name}</b>`, event);
      })
      .on("mousemove", function (event) { moveTip(event); })
      .on("mouseout", hideTip);

    // Leaves — species circle + name
    const leaf = g.selectAll("g.leaf")
      .data(root.leaves())
      .join("g").attr("class", "leaf")
      .attr("transform", d => `translate(${d.y}, ${d.x})`);
    leaf.append("circle").attr("r", 3.5);
    leaf.append("text").attr("class", "leaf-name")
      .attr("dx", 8)
      .attr("dominant-baseline", "middle")
      .text(d => d.data.name);
    leaf
      .on("mouseover", function (event, d) {
        const tid = d.data.taxon_id ? `<span class="og-tax-tip-rank">taxon ${d.data.taxon_id}</span>` : "";
        showTip(`${tid}<b>${d.data.name}</b>`, event);
      })
      .on("mousemove", function (event) { moveTip(event); })
      .on("mouseout", hideTip);

    return svg;
  }

  // ── Lightbox / expand modal ─────────────────────────────────────────
  // Mirrors the figure-modal pattern that resultado.html uses for
  // Figures 1–4: same structure (head with title + close, body with the
  // re-rendered visualization), same backdrop click + Esc to close.
  function _ensureModal() {
    let modal = document.getElementById("og-tax-figure-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "og-tax-figure-modal";
    modal.className = "tax-figure-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.hidden = true;
    modal.innerHTML = `
      <div class="tax-figure-modal-inner">
        <div class="tax-figure-modal-head">
          <div>
            <h3 id="og-tax-modal-title">Taxonomic tree</h3>
            <div class="sub" id="og-tax-modal-sub">Drag to pan · scroll to zoom · double-click to reset</div>
          </div>
          <button type="button" class="tax-figure-modal-close" aria-label="Close">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </div>
        <div class="tax-figure-modal-body">
          <div id="og-tax-modal-plot"></div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    // Close handlers
    modal.querySelector(".tax-figure-modal-close").addEventListener("click", _closeLightbox);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) _closeLightbox();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !modal.hidden) _closeLightbox();
    });
    return modal;
  }

  function _openLightbox(treeData, opts) {
    const modal = _ensureModal();
    const title = document.getElementById("og-tax-modal-title");
    if (title) title.textContent = (opts && opts.title) || "Taxonomic tree";
    modal.hidden = false;
    requestAnimationFrame(() => {
      // Larger canvas for the modal: more perLeaf, wider, fits available width.
      _render({
        containerId: "og-tax-modal-plot",
        treeData,
        perLeaf: 48,
        width: Math.min(1320, window.innerWidth - 120),
      });
    });
  }
  function _closeLightbox() {
    const modal = document.getElementById("og-tax-figure-modal");
    if (modal) modal.hidden = true;
    const host = document.getElementById("og-tax-modal-plot");
    if (host) host.innerHTML = "";
  }

  function _downloadNewick(newick, nSpecies) {
    if (!newick) return;
    const today = new Date().toISOString().slice(0, 10);
    const stem = (typeof descriptiveFilename === "function")
      ? descriptiveFilename("taxonomy-tree", "newick", [`${nSpecies}sp`])
      : `taxonomy-tree_${nSpecies}sp_${today}`;
    const blob = new Blob([newick + "\n"], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${stem}.nwk`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  async function fetchTree(speciesArr) {
    if (!Array.isArray(speciesArr) || speciesArr.length === 0) {
      return { success: false, message: "No species provided" };
    }
    const res = await fetch("/api/taxonomy_tree", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ species: speciesArr }),
    });
    return res.json();
  }

  window.OGTaxonomyTree = {
    render: _render,
    fetchTree,
    downloadNewick: _downloadNewick,
    openLightbox: _openLightbox,
    closeLightbox: _closeLightbox,
  };
})();
