/* ============================================================================
   OrthoGather — Species selection page
   - Loads the proteome catalogue
   - Live search with type-ahead results
   - Selected-species chips with removal
   - Download / Run OrthoFinder buttons with status feedback
   - SSE stream of OrthoFinder logs
   - Post-analysis subactions (Protein / GO)
   ============================================================================ */

(function () {
  'use strict';

  let proteomeData = [];
  let selectedTemp = [];

  // -------------------------------------------------------------------------
  // Species selection limit (Point 7 of the post-review plan).
  //
  // Reviewer 3 noted that checkbox-based selection scales poorly past ~100
  // entries. Rather than rebuild the picker as a taxonomic tree (weeks of
  // work), we set a sensible upper bound: OrthoFinder runs comfortably with
  // 5–30 species, and 50 is already past the realistic comparative-genomics
  // ceiling for a local desktop run.
  //
  //   MAX_SPECIES      → hard cap; the picker refuses to add beyond this.
  //   WARN_AT_PCT      → soft warning (toast) once the user reaches this %.
  // -------------------------------------------------------------------------
  const MAX_SPECIES  = 50;
  const WARN_AT_PCT  = 0.8;        // toast at 40/50

  const $ = (id) => document.getElementById(id);

  /** Attempt to add a species. Returns true on success, false when blocked
   *  by the limit or already in the list. Surfaces an OG.showError toast
   *  on hard-cap rejection so the user knows why. */
  function tryAddSpecies(entry) {
    if (selectedTemp.find((x) => x.id === entry.id)) return false; // dedupe
    if (selectedTemp.length >= MAX_SPECIES) {
      if (window.OG && OG.showError) {
        OG.showError({
          error_code: 'ERR_SPECIES_LIMIT_REACHED',
          severity: 'warning',
          category: 'input',
          message: `Species limit reached (${MAX_SPECIES} max)`,
          hint:    'OrthoGather is tuned for ≤ 50 species on a local desktop. ' +
                   'Remove a chip first, or split the analysis in two and use ' +
                   '/compare to view both side-by-side.',
        });
      }
      return false;
    }
    selectedTemp.push(entry);
    // Soft warning at 80% so the user knows the ceiling is coming.
    if (selectedTemp.length === Math.floor(MAX_SPECIES * WARN_AT_PCT)) {
      if (window.OG && OG.showInfo) {
        OG.showInfo({
          error_code: 'ERR_SPECIES_NEAR_LIMIT',
          severity: 'info',
          category: 'input',
          message: `${selectedTemp.length} of ${MAX_SPECIES} species selected`,
          hint:    `You're approaching the analysis limit. OrthoFinder runs ` +
                   `comfortably up to ~50 species — beyond that, expect long ` +
                   `runtimes and consider splitting the analysis.`,
        });
      }
    }
    return true;
  }

  function updateWorkflowStep(stepIndex) {
    // stepIndex: 0 = selecting, 1 = downloaded, 2 = orthofinder done
    document.querySelectorAll('.workflow-steps .step').forEach((el, i) => {
      el.classList.remove('is-active', 'is-done', 'is-pending', 'is-progress');
      if (i < stepIndex) el.classList.add('is-done');
      else if (i === stepIndex) el.classList.add('is-active');
      else el.classList.add('is-pending');
    });
  }

  /* Fine-grained: set per-step state explicitly (pending/active/progress/done) */
  function setWorkflowStates(states) {
    document.querySelectorAll('.workflow-steps .step').forEach((el, i) => {
      el.classList.remove('is-active', 'is-done', 'is-pending', 'is-progress');
      el.classList.add('is-' + (states[i] || 'pending'));
    });
  }

  function updateSelected() {
    const selectedDiv = $('selected');
    selectedDiv.innerHTML = selectedTemp.map((item, index) => {
      const isRef = item.type === 'reference';
      const proteomeId = item.id || '';
      const tooltip = `${item.label}${proteomeId ? '  ·  ' + proteomeId : ''}  ·  ${isRef ? 'Reference' : 'Non-reference'} proteome`;
      return `
        <div class="species-chip ${isRef ? '' : 'is-non-reference'}" role="listitem" title="${escapeHtml(tooltip)}">
          <span class="chip-dot" aria-hidden="true"></span>
          <span class="chip-name">${escapeHtml(item.label)}</span>
          <button type="button" class="chip-remove" data-index="${index}" aria-label="Remove ${escapeHtml(item.label)}">
            <i class="fa-solid fa-xmark" aria-hidden="true"></i>
          </button>
        </div>
      `;
    }).join('');

    // Wire remove buttons
    selectedDiv.querySelectorAll('.chip-remove').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedTemp.splice(Number(btn.dataset.index), 1);
        updateSelected();
      });
    });

    // Toggle "is-overflowing" so the fade-mask hint only shows when there's actually scroll
    requestAnimationFrame(() => {
      const overflow = selectedDiv.scrollHeight > selectedDiv.clientHeight + 1;
      selectedDiv.classList.toggle('is-overflowing', overflow);
    });

    // Update count + meta
    const meta = document.querySelector('.selected-meta');
    if (meta) {
      const count = $('selectedCount');
      if (count) count.textContent = String(selectedTemp.length);
      const max = $('selectedMax');
      if (max) max.textContent = String(MAX_SPECIES);
      meta.classList.toggle('is-empty',     selectedTemp.length < 2);
      meta.classList.toggle('is-near-limit', selectedTemp.length >= Math.floor(MAX_SPECIES * WARN_AT_PCT));
      meta.classList.toggle('is-at-limit',   selectedTemp.length >= MAX_SPECIES);
    }
    // Clear-all is only meaningful when there's something to clear
    const clearBtn = $('selectedClearBtn');
    if (clearBtn) clearBtn.hidden = selectedTemp.length === 0;

    // Drive the action bar state machine
    refreshActionBarFromSelection();

    // Point 11 (reset v2) — just update the Generate button's enabled state
    // and re-label it as "Refresh" if the user already generated a tree.
    _refreshTaxBtnState();
  }

  // ====================================================================
  // Point 11 (v2) — Simple "Generate tree" button. No debounce, no live
  // updates, no toggle panel. The user clicks once, sees the tree. If
  // they add/remove species afterwards, the button label changes to
  // "Refresh" so they know it's stale.
  // ====================================================================

  let taxGenerated = false;
  let taxLastSpeciesKey = "";

  function _speciesForTax() {
    return selectedTemp
      .filter(s => s && s.taxon_id && /^\d+$/.test(String(s.taxon_id)))
      .map(s => ({ name: s.label, taxon_id: String(s.taxon_id) }));
  }

  function _refreshTaxBtnState() {
    const btn = document.getElementById("taxGenerateBtn");
    const label = document.getElementById("taxGenerateBtnLabel");
    if (!btn || !label) return;
    const sp = _speciesForTax();
    if (sp.length < 2) {
      btn.disabled = true;
      label.textContent = "Generate tree (≥ 2 species)";
      return;
    }
    btn.disabled = false;
    const key = JSON.stringify(sp.map(s => s.taxon_id).sort());
    if (taxGenerated && key !== taxLastSpeciesKey) {
      // Species changed since last fetch — button regenerates with the new set.
      label.textContent = `Refresh tree (${sp.length} species)`;
    } else if (taxGenerated) {
      // Already generated with this exact set — clicking re-renders the
      // current cached tree (instant). Keep the label actionable so the
      // user knows the button still works.
      label.textContent = `Open tree (${sp.length} species)`;
    } else {
      label.textContent = `Generate tree (${sp.length} species)`;
    }
  }

  async function _generateTaxonomyTree() {
    if (!(window.OGTaxonomyTree && window.d3)) return;
    const sp = _speciesForTax();
    if (sp.length < 2) return;

    const btn = document.getElementById("taxGenerateBtn");
    const treeEl = document.getElementById("taxTree");
    const actions = document.getElementById("taxActions");

    if (btn) btn.disabled = true;
    if (treeEl) {
      treeEl.hidden = false;
      // Reset ONLY the inner SVG container — keep the expand button intact.
      const svgHost = document.getElementById("taxTreeSvg");
      if (svgHost) svgHost.innerHTML = `<div class="tax-tree-loading">Fetching lineages…</div>`;
      // Scroll the tree panel into view smoothly so the user actually sees
      // the result even when the section is below the viewport.
      requestAnimationFrame(() => {
        treeEl.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }

    let resp;
    try {
      resp = await OGTaxonomyTree.fetchTree(sp);
    } catch (err) {
      if (treeEl) treeEl.innerHTML = `<div class="tax-tree-empty">Network error. See console.</div>`;
      if (btn) btn.disabled = false;
      console.error(err);
      return;
    }

    if (!resp || !resp.success || !resp.tree) {
      if (treeEl) treeEl.innerHTML = `<div class="tax-tree-empty">${(resp && resp.message) || "Tree unavailable"}</div>`;
      if (btn) btn.disabled = false;
      return;
    }

    // Replace the loader inside #taxTreeSvg only (the expand button lives
    // as a sibling and must survive the rerender).
    const svgHost = document.getElementById("taxTreeSvg");
    if (svgHost) svgHost.innerHTML = "";
    OGTaxonomyTree.render({
      containerId: "taxTreeSvg",
      treeData: resp.tree,
    });

    // Wire the Expand button → lightbox modal (figure-modal pattern).
    const ex = document.getElementById("taxExpandBtn");
    if (ex) {
      const fresh = ex.cloneNode(true);
      ex.parentNode.replaceChild(fresh, ex);
      fresh.addEventListener("click", () => {
        OGTaxonomyTree.openLightbox(resp.tree, { title: `Taxonomic tree — ${sp.length} species` });
      });
    }

    // Wire the Download .nwk + Reset view buttons to this tree.
    if (actions) actions.hidden = false;
    const dl = document.getElementById("taxDownloadNewickBtn");
    if (dl) {
      // Replace listeners by cloning the node — keeps logic idempotent across regenerations.
      const fresh = dl.cloneNode(true);
      dl.parentNode.replaceChild(fresh, dl);
      fresh.addEventListener("click", () => {
        OGTaxonomyTree.downloadNewick(resp.newick, sp.length);
      });
    }
    const rv = document.getElementById("taxResetViewBtn");
    if (rv) {
      const fresh = rv.cloneNode(true);
      rv.parentNode.replaceChild(fresh, rv);
      fresh.addEventListener("click", () => {
        const tEl = document.getElementById("taxTreeSvg");
        if (tEl && typeof tEl.__resetZoom === "function") tEl.__resetZoom();
      });
    }

    taxGenerated = true;
    taxLastSpeciesKey = JSON.stringify(sp.map(s => s.taxon_id).sort());
    _refreshTaxBtnState();
    if (btn) btn.disabled = false;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("taxGenerateBtn");
    if (btn) btn.addEventListener("click", _generateTaxonomyTree);
    _refreshTaxBtnState();
  });

  /* ────────────────────────────────────────────────────────────────
     Action bar state machine
     Buttons: #downloadBtn  →  #runOrthofinderBtn
     States:  pending → ready → progress → done
     ──────────────────────────────────────────────────────────────── */
  function setActionState(btn, state, helperText) {
    if (!btn) return;
    btn.classList.remove('is-pending', 'is-ready', 'is-progress', 'is-done');
    btn.classList.add('is-' + state);
    btn.disabled = (state === 'pending' || state === 'progress' || state === 'done');
    const stateEl = btn.querySelector('.action-btn-state');
    if (stateEl && helperText !== undefined) stateEl.textContent = helperText;
  }

  function refreshActionBarFromSelection() {
    const dlBtn  = $('downloadBtn');
    const runBtn = $('runOrthofinderBtn');
    if (!dlBtn || !runBtn) return;
    // If we're past the Download stage, don't downgrade
    if (dlBtn.classList.contains('is-progress') ||
        dlBtn.classList.contains('is-done')) return;

    if (selectedTemp.length >= 2) {
      setActionState(dlBtn, 'ready', 'Ready');
    } else {
      setActionState(dlBtn, 'pending', 'Add at least 2 species');
    }
    if (!runBtn.classList.contains('is-done') &&
        !runBtn.classList.contains('is-progress')) {
      setActionState(runBtn, 'pending', 'After download');
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function postAndRedirect(url, params) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    Object.entries(params).forEach(([k, v]) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = k;
      input.value = v;
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
  }

  function goProteinAnalysisGenerated() {
    postAndRedirect('/cargar_carpeta', { modo: 'generated' });
  }

  async function goGeneOntologyGenerated() {
    try {
      OG.showSpinner();
      const res = await fetch('/cargar_carpeta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ modo: 'generated' }),
      });
      if (!res.ok) {
        OG.hideSpinner();
        OG.showStatus('downloadStatus', 'error', 'Error preparing data for the Gene Ontology analysis.');
        return;
      }
      window.location.href = '/resultado_goa';
    } catch (e) {
      OG.hideSpinner();
      OG.showStatus('downloadStatus', 'error', 'Unexpected error: ' + e.message);
    }
  }

  /* Expose for inline onclick fallbacks (templates may still use them) */
  window.goProteinAnalysisGenerated = goProteinAnalysisGenerated;
  window.goGeneOntologyGenerated = goGeneOntologyGenerated;

  /* ---- Catalogue metadata + update mechanism ---- */
  function formatAge(isoDate) {
    if (!isoDate) return '';
    const then = new Date(isoDate);
    const now = new Date();
    const diffMs = now - then;
    const day = 24 * 3600 * 1000;
    const days = Math.floor(diffMs / day);
    if (days < 0) return 'in the future';
    if (days === 0) return 'today';
    if (days === 1) return '1 day old';
    if (days < 30) return `${days} days old`;
    const months = Math.floor(days / 30);
    if (months < 12) return `about ${months} month${months === 1 ? '' : 's'} old`;
    const years = Math.floor(months / 12);
    const remMonths = months % 12;
    if (remMonths === 0) return `${years} year${years === 1 ? '' : 's'} old`;
    return `${years} year${years === 1 ? '' : 's'}, ${remMonths} month${remMonths === 1 ? '' : 's'} old`;
  }

  function formatBytes(n) {
    if (!n || n < 0) return '?';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function estimateDownloadTime(bytes) {
    // Assume 3-15 MB/s typical home connection
    const mb = bytes / (1024 * 1024);
    const fast = Math.ceil(mb / 15);
    const slow = Math.ceil(mb / 3);
    if (fast === slow) return `~${fast}s`;
    if (slow < 60) return `~${fast}-${slow}s`;
    return `~${Math.ceil(fast/60)}-${Math.ceil(slow/60)} min`;
  }

  let catalogueLocalInfo = null;

  function renderCatalogueMeta(info) {
    catalogueLocalInfo = info;
    // If the catalogue ready-hint was rendered BEFORE we knew the version
    // (the two fetches race), refresh it now so the version tail appears.
    const hint = document.getElementById('catalogue-hint');
    if (hint && hint.classList.contains('is-ready') && proteomeData.length) {
      setCatalogueLoading('ready');
    }
    const meta    = document.getElementById('catalogue-meta');
    const verEl   = document.getElementById('catalogue-version');
    const ageEl   = document.getElementById('catalogue-age');
    if (!meta || !verEl || !ageEl) return;

    if (info.is_fallback) {
      verEl.textContent = 'unknown (bundled)';
    } else {
      verEl.textContent = info.version || (info.downloaded_at || '').slice(0, 10) || '?';
    }
    const dateOnly = (info.downloaded_at || '').slice(0, 10);
    ageEl.textContent = (dateOnly ? dateOnly + ' · ' : '') + formatAge(info.downloaded_at);
    meta.hidden = false;
  }

  function clearUpdateArea() {
    const a = document.getElementById('catalogue-update-area');
    if (a) a.innerHTML = '';
  }

  function showUpdateMessage(kind, text) {
    const a = document.getElementById('catalogue-update-area');
    if (!a) return;
    const icons = { ok: 'fa-circle-check', info: 'fa-circle-info', error: 'fa-circle-exclamation' };
    const variants = { ok: 'success', info: 'info', error: 'error' };
    a.innerHTML = `<div class="alert alert-${variants[kind] || 'info'}" role="status">
      <i class="fa-solid ${icons[kind] || 'fa-circle-info'} alert-icon" aria-hidden="true"></i>
      <div class="alert-message">${text}</div>
    </div>`;
  }

  function showUpdateAvailable(remote) {
    const a = document.getElementById('catalogue-update-area');
    if (!a) return;
    const publishedDate = (remote.published_at || '').slice(0, 10);
    a.innerHTML = `
      <div class="catalogue-update-card">
        <div class="update-title">
          <i class="fa-solid fa-sparkles" aria-hidden="true"></i>
          A newer catalogue is available
        </div>
        <dl>
          <dt>Version</dt>          <dd>${remote.release_name || remote.release_tag || '—'}</dd>
          <dt>Published</dt>        <dd>${publishedDate}</dd>
          <dt>Asset</dt>            <dd>${remote.asset_name}</dd>
          <dt>Size</dt>             <dd>${formatBytes(remote.asset_size)}</dd>
          <dt>Estimated time</dt>   <dd>${estimateDownloadTime(remote.asset_size)}</dd>
        </dl>
        <div class="actions">
          <button type="button" class="btn btn-primary" id="catalogue-update-btn">
            <i class="fa-solid fa-download"></i> Update now
          </button>
          <button type="button" class="btn btn-ghost" id="catalogue-update-cancel-btn">
            Keep current
          </button>
          <span class="text-secondary">After updating, refresh the page to apply.</span>
        </div>
      </div>
    `;
    document.getElementById('catalogue-update-btn').addEventListener('click', () => {
      startCatalogueUpdate(remote);
    });
    document.getElementById('catalogue-update-cancel-btn').addEventListener('click', clearUpdateArea);
  }

  function startCatalogueUpdate(remote) {
    const a = document.getElementById('catalogue-update-area');
    a.innerHTML = `
      <div class="catalogue-update-progress">
        <strong>Downloading new catalogue...</strong>
        <div class="progress" role="progressbar" aria-label="Catalogue download" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-bar" id="cat-bar" style="width:0%"></div>
        </div>
        <div class="progress-text">
          <span id="cat-bytes">0 MB</span>
          <span id="cat-percent">0%</span>
        </div>
      </div>
    `;
    const bar = document.getElementById('cat-bar');
    const bytesEl = document.getElementById('cat-bytes');
    const percentEl = document.getElementById('cat-percent');

    const params = new URLSearchParams({
      url: remote.asset_url,
      version: remote.release_name || remote.release_tag || '',
      tag: remote.release_tag || '',
    });
    const es = new EventSource('/catalog/update?' + params.toString());

    es.onmessage = (ev) => {
      let data; try { data = JSON.parse(ev.data); } catch (e) { return; }
      switch (data.phase) {
        case 'start':
        case 'downloading':
          break;
        case 'progress':
          if (data.total_bytes > 0) {
            const pct = data.percent || 0;
            bar.style.width = pct + '%';
            percentEl.textContent = pct + '%';
            bytesEl.textContent = formatBytes(data.bytes_downloaded) + ' / ' + formatBytes(data.total_bytes);
          } else {
            bytesEl.textContent = formatBytes(data.bytes_downloaded) + ' downloaded';
            percentEl.textContent = '—';
          }
          break;
        case 'validating':
          bytesEl.textContent = 'Validating downloaded catalogue...';
          percentEl.textContent = '';
          break;
        case 'done':
          es.close();
          a.innerHTML = `<div class="alert alert-success" role="status">
            <i class="fa-solid fa-circle-check alert-icon" aria-hidden="true"></i>
            <div class="alert-message">
              <div class="alert-title">Catalogue updated successfully</div>
              <div>New version: <strong>${data.manifest.version}</strong> · ${(data.manifest.proteome_count || 0).toLocaleString()} proteomes.</div>
              <div style="margin-top: var(--space-2);">
                <button type="button" class="btn btn-primary btn-sm" onclick="location.reload()">
                  <i class="fa-solid fa-rotate"></i> Reload page to apply
                </button>
              </div>
            </div>
          </div>`;
          break;
        case 'error':
          es.close();
          a.innerHTML = `<div class="alert alert-error" role="alert">
            <i class="fa-solid fa-circle-exclamation alert-icon" aria-hidden="true"></i>
            <div class="alert-message">
              <div class="alert-title">Update failed</div>
              <div>${data.reason}</div>
            </div>
          </div>`;
          break;
      }
    };
    es.onerror = () => {
      es.close();
      a.innerHTML = `<div class="alert alert-error" role="alert">
        <i class="fa-solid fa-circle-exclamation alert-icon" aria-hidden="true"></i>
        <div class="alert-message">Connection lost while updating the catalogue.</div>
      </div>`;
    };
  }

  // Shared check routine. When `silent`, stay quiet unless a newer catalogue is
  // found (used by the auto-check on load); otherwise surface every outcome
  // (used by the manual "Check for updates" button).
  function runUpdateCheck(silent) {
    return fetch('/catalog/check_updates')
      .then(r => r.json())
      .then(res => {
        if (!res.ok) {
          if (!silent) showUpdateMessage('error', res.reason || 'Could not check for updates.');
          return;
        }
        if (!res.update_available) {
          if (!silent) showUpdateMessage('ok', res.reason || `You're on the latest available catalogue.`);
          return;
        }
        // A newer catalogue exists → show the 1-click update card.
        showUpdateAvailable(res.remote);
      })
      .catch(err => {
        if (!silent) showUpdateMessage('error', 'Network error: ' + err.message);
      });
  }

  function wireCatalogueUpdates() {
    // Load local info, then auto-detect a newer catalogue on page load
    // (detect + 1-click). The check is silent on errors/rate-limits so a flaky
    // network or GitHub throttle never nags the user — the manual button below
    // still reports those outcomes explicitly.
    fetch('/catalog/info')
      .then(r => r.ok ? r.json() : null)
      .then(info => {
        if (info) renderCatalogueMeta(info);
        runUpdateCheck(true);
      })
      .catch(() => {});

    const checkBtn = document.getElementById('catalogue-check-btn');
    if (!checkBtn) return;
    checkBtn.addEventListener('click', () => {
      checkBtn.disabled = true;
      checkBtn.classList.add('is-loading');
      showUpdateMessage('info', 'Checking GitHub for newer releases...');
      runUpdateCheck(false).finally(() => {
        checkBtn.disabled = false;
        checkBtn.classList.remove('is-loading');
      });
    });
  }

  /* ---- Catalogue loading ---- */
  function setCatalogueLoading(state, msg) {
    const input = document.getElementById('search');
    const hint  = document.getElementById('catalogue-hint');
    if (!input || !hint) return;
    // We never DISABLE the input — that can suppress the 'input' event in
    // some browsers. We just adjust placeholder + hint copy, and the search
    // handler short-circuits while proteomeData is empty.
    if (state === 'loading') {
      input.placeholder = 'Loading proteome catalogue...';
      hint.textContent = msg || 'Loading the catalogue (~250 MB). This can take 20-60 s the first time.';
      hint.className = 'label-helper is-loading';
    } else if (state === 'ready') {
      input.placeholder = 'e.g. Escherichia coli, Burkholderia, UP000000625...';
      // Bake the catalogue version into the ready-line if we have it — saves
      // the user from clicking the (almost invisible) kebab menu just to see
      // which snapshot they're searching against.
      let versionTail = '';
      if (catalogueLocalInfo) {
        if (catalogueLocalInfo.is_fallback) {
          versionTail = ' · bundled fallback';
        } else {
          const v = catalogueLocalInfo.version
            || (catalogueLocalInfo.downloaded_at || '').slice(0, 10);
          if (v) versionTail = ` · v${v}`;
        }
      }
      hint.innerHTML = msg
        ? msg
        : `Catalogue ready — <strong>${proteomeData.length.toLocaleString()}</strong> proteomes<span class="catalogue-version-tail">${versionTail}</span>`;
      hint.className = 'label-helper is-ready';
      // Trigger a fresh search in case the user already typed something
      const evt = new Event('input', { bubbles: true });
      input.dispatchEvent(evt);
    } else if (state === 'error') {
      hint.textContent = msg || 'Could not load catalogue.';
      hint.className = 'label-helper is-error';
    }
  }

  function applyPrefillFromHistory() {
    if (!proteomeData || proteomeData.length === 0) return;
    fetch('/api/prefill_species')
      .then((r) => (r.ok ? r.json() : { ids: [] }))
      .then((payload) => {
        const ids = (payload && payload.ids) || [];
        if (!ids.length) return;
        const byId = new Map();
        for (const p of proteomeData) byId.set(p['Proteome Id'], p);
        let added = 0;
        let truncated = false;
        for (const pid of ids) {
          const item = byId.get(pid);
          if (!item) continue;
          const wasAdded = tryAddSpecies({
            id: pid,
            label: item.label,
            type: item.type === 'reference' ? 'reference' : 'non-reference',
            taxon_id: item.taxon_id || '',
          });
          if (wasAdded) {
            added += 1;
          } else if (selectedTemp.length >= MAX_SPECIES) {
            truncated = true;
            break;        // hit the cap; stop pre-filling silently
          }
        }
        if (truncated && window.OG && OG.showWarning) {
          OG.showWarning({
            error_code: 'ERR_REPRODUCE_TRUNCATED',
            severity: 'warning',
            category: 'input',
            message: `Pre-fill truncated at ${MAX_SPECIES} species`,
            hint: `The saved run had more than ${MAX_SPECIES} species; OrthoGather only pre-filled the first ${added}. Remove any you don't need and add others manually.`,
          });
        }
        if (added > 0) {
          updateSelected();
          if (window.OG && OG.showStatus) {
            OG.showStatus('downloadStatus', 'success',
              `Pre-filled ${added} species from a past run — ready to re-run.`);
          }
        }
      })
      .catch(() => { /* silent — prefill is best-effort */ });
  }

  function loadCatalogue() {
    setCatalogueLoading('loading');
    // Slim, gzipped projection: the server sends a compact array of
    // [label, pid, isRef(0/1), taxon_id] tuples (~6 MB gzipped) instead of the
    // full ~246 MB catalogue. Far faster transfer + parse, and ~3× less memory
    // even at ~1 M proteomes. The browser transparently decompresses it.
    fetch('/catalog/species_index')
      .then((res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then((rows) => {
        // Rebuild the objects the rest of the page expects, and pre-compute the
        // lowercased label + proteome ID in the SAME pass. Pre-normalising here
        // means the search loop never calls .toLowerCase() per keystroke (which
        // on ~1 M strings would be real, perceptible typing lag).
        const data = new Array(rows.length);
        for (let i = 0; i < rows.length; i++) {
          const r = rows[i];
          const label = r[0] || '';
          const pid = r[1] || '';
          data[i] = {
            label,
            'Proteome Id': pid,
            type: r[2] ? 'reference' : 'non-reference',
            taxon_id: r[3] || '',
            _lc_label: label.toLowerCase(),
            _lc_pid: pid.toLowerCase(),
          };
        }
        proteomeData = data;
        setCatalogueLoading('ready');
        // After the catalogue is in memory, pre-fill chips if the user landed
        // here via /history/<id>/reproduce. The endpoint clears the session key
        // on read so a manual reload starts fresh.
        applyPrefillFromHistory();
      })
      .catch((err) => {
        const friendly = 'Error loading the proteome catalogue: ' + err.message +
          '. Try reloading the page.';
        setCatalogueLoading('error', friendly);
        OG.showStatus('downloadStatus', 'error', friendly);
      });
  }

  /* ---- Search ---- */
  // Remembers the last search term that matched nothing, so we can skip the
  // full-catalogue scan while the user keeps typing past a dead end.
  let _lastEmptyTerm = '';

  function runSearch(input, resultsDiv) {
    const searchTerm = input.value.toLowerCase().trim();
    resultsDiv.innerHTML = '';
    resultsDiv.classList.remove('is-empty-state');
    if (searchTerm.length < 2) return;
    if (!proteomeData || proteomeData.length === 0) return;

    // Early-exit loop instead of .filter().slice(20): stop scanning as soon
    // as we have 20 matches. With "ec" as searchTerm this typically scans a
    // few thousand entries instead of all ~1 M.
    const MAX_RESULTS = 20;
    const matches = [];
    // No-match memoization: if a shorter prefix already matched nothing, every
    // longer extension of it also matches nothing — so skip the full ~1 M scan
    // entirely. This is what keeps typing past a dead end from lagging.
    const skipScan = _lastEmptyTerm && searchTerm.startsWith(_lastEmptyTerm);
    if (!skipScan) {
      for (let i = 0; i < proteomeData.length; i++) {
        const item = proteomeData[i];
        // _lc_label / _lc_pid are precomputed at catalogue load — see
        // loadCatalogue(). No per-keystroke allocations here.
        if (item._lc_label.includes(searchTerm) || item._lc_pid.includes(searchTerm)) {
          matches.push(item);
          if (matches.length >= MAX_RESULTS) break;
        }
      }
    }
    // Remember a dead-end term (and clear it the moment we get hits again).
    _lastEmptyTerm = matches.length === 0 ? searchTerm : '';

    // ── Empty state: no matches found ──
    if (matches.length === 0) {
      resultsDiv.classList.add('is-empty-state');
      resultsDiv.innerHTML = `
        <div class="results-empty">
          <i class="fa-regular fa-folder-open" aria-hidden="true"></i>
          No matches for <strong>${escapeHtml(input.value.trim())}</strong>
          <span class="results-empty-hint">Try a different organism name or a UniProt proteome ID.</span>
        </div>
      `;
      return;
    }

    matches.forEach((item) => {
      const div = document.createElement('div');
      div.className = `option ${item.type}`;
      div.textContent = item.label;
      div.setAttribute('data-id', item['Proteome Id']);
      div.setAttribute('data-label', item.label);
      div.setAttribute('data-taxon-id', item.taxon_id || '');
      div.setAttribute('role', 'option');
      div.setAttribute('tabindex', '-1');     // not in tab order; keyboard nav via ↑/↓ in input

      div.addEventListener('click', function () { selectOption(this); });
      div.addEventListener('mouseenter', () => setHighlight(div));

      resultsDiv.appendChild(div);
    });

    // Auto-highlight the first item (so Enter selects it immediately)
    if (matches.length > 0) {
      setHighlight(resultsDiv.firstElementChild);
    }

    function selectOption(el) {
      const id = el.getAttribute('data-id');
      const added = tryAddSpecies({
        id,
        label: el.getAttribute('data-label'),
        type: el.classList.contains('reference') ? 'reference' : 'non-reference',
        taxon_id: el.getAttribute('data-taxon-id') || '',
      });
      if (added) updateSelected();
      input.value = '';
      resultsDiv.innerHTML = '';
      resultsDiv.classList.remove('is-empty-state');
      input.focus();
    }
  }

  /* Track which option is keyboard-highlighted */
  function setHighlight(el) {
    if (!el) return;
    const resultsDiv = el.parentElement;
    resultsDiv.querySelectorAll('.option.is-highlighted').forEach(o => o.classList.remove('is-highlighted'));
    el.classList.add('is-highlighted');
    // Ensure it's visible within the scrollable results
    el.scrollIntoView({ block: 'nearest' });
  }

  function moveHighlight(resultsDiv, delta) {
    const opts = Array.from(resultsDiv.querySelectorAll('.option'));
    if (opts.length === 0) return;
    const current = resultsDiv.querySelector('.option.is-highlighted');
    let idx = current ? opts.indexOf(current) : -1;
    idx = Math.max(0, Math.min(opts.length - 1, idx + delta));
    setHighlight(opts[idx]);
  }

  function wireSearch() {
    const input = $('search');
    const resultsDiv = $('results');
    if (!input || !resultsDiv) return;

    // Tiny debounce so a 5-letter burst doesn't kick off 5 full scans.
    // 50ms is below the perception threshold for "typing feels laggy" but
    // big enough to coalesce normal typing into a single search per pause.
    let searchTimer = null;
    const handler = () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runSearch(input, resultsDiv), 50);
    };
    input.addEventListener('input', handler);
    // NOTE: we used to also listen on `keyup`, which doubled the work on
    // every printable keystroke. The `input` event already fires for every
    // value change (typing, paste, IME) so `keyup` was strictly redundant.

    // ── Keyboard navigation: ↑ / ↓ / Enter / Esc ──
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveHighlight(resultsDiv, 1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveHighlight(resultsDiv, -1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const highlighted = resultsDiv.querySelector('.option.is-highlighted');
        if (highlighted) highlighted.click();
      } else if (e.key === 'Escape') {
        input.value = '';
        resultsDiv.innerHTML = '';
        resultsDiv.classList.remove('is-empty-state');
      }
    });
  }

  /* ---- Download proteomes (SSE-based, with retries) ---- */

  // Module-level state so the "Retry failed" button can re-issue the stream
  // with only the failed IDs without losing the rest of the page state.
  let lastDownloadFailed = [];      // list of {pid, reason}
  let lastDownloadedCount = 0;
  let lastDownloadedTotal = 0;

  function $progress() { return document.querySelector('.download-progress'); }

  function ensureProgressVisible() {
    const panel = $progress();
    if (panel) panel.classList.add('is-active');
  }

  function setProgressBar(current, total) {
    const bar = document.getElementById('download-bar');
    const label = document.getElementById('download-bar-label');
    if (bar) bar.style.width = total > 0 ? `${(current / total) * 100}%` : '0';
    if (label) label.textContent = `${current} / ${total}`;
  }

  function appendDownloadLog(text, level = 'info') {
    const log = document.getElementById('downloadLog');
    if (!log) return;
    const line = document.createElement('div');
    line.className = `log-line log-${level}`;
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function setCurrentPid(text) {
    const el = document.getElementById('download-current');
    if (el) el.textContent = text;
  }

  function renderDownloadSummary(payload) {
    const summary = document.getElementById('download-summary');
    if (!summary) return;

    const downloaded = (payload.downloaded || []).length;
    const failed = (payload.failed || []);
    const empty = (payload.empty || []);

    lastDownloadedCount = downloaded;
    lastDownloadFailed = failed;

    const total = lastDownloadedTotal;
    let html = '';

    if (downloaded === total && failed.length === 0 && empty.length === 0) {
      html = `<div class="alert alert-success" role="status">
        <i class="fa-solid fa-circle-check alert-icon" aria-hidden="true"></i>
        <div class="alert-message">
          <div class="alert-title">All ${downloaded} proteomes downloaded</div>
          <div>You can now run OrthoFinder.</div>
        </div>
      </div>`;
    } else if (downloaded > 0 && failed.length > 0) {
      const failedList = failed.map(f => f.pid).join(', ');
      html = `<div class="alert alert-warning" role="status">
        <i class="fa-solid fa-triangle-exclamation alert-icon" aria-hidden="true"></i>
        <div class="alert-message">
          <div class="alert-title">Downloaded ${downloaded} of ${total}</div>
          <div>${failed.length} failed: <code>${failedList}</code></div>
        </div>
      </div>
      <div style="display: flex; gap: var(--space-3); margin-top: var(--space-3); flex-wrap: wrap;">
        <button type="button" class="btn btn-secondary" id="retry-failed-btn">
          <i class="fa-solid fa-rotate"></i> Retry failed (${failed.length})
        </button>
        <span class="text-secondary" style="font-size: var(--text-body-sm); align-self: center;">
          You can also proceed with the ${downloaded} already downloaded.
        </span>
      </div>`;
    } else if (downloaded === 0) {
      const failedList = failed.map(f => f.pid).join(', ');
      html = `<div class="alert alert-error" role="alert">
        <i class="fa-solid fa-circle-exclamation alert-icon" aria-hidden="true"></i>
        <div class="alert-message">
          <div class="alert-title">No proteomes were downloaded</div>
          <div>All ${total} attempts failed: <code>${failedList || '(see log above)'}</code></div>
        </div>
      </div>
      <div style="margin-top: var(--space-3);">
        <button type="button" class="btn btn-primary" id="retry-failed-btn">
          <i class="fa-solid fa-rotate"></i> Retry all
        </button>
      </div>`;
    } else if (empty.length > 0) {
      const emptyList = empty.map(e => e.pid).join(', ');
      html = `<div class="alert alert-warning" role="status">
        <i class="fa-solid fa-triangle-exclamation alert-icon" aria-hidden="true"></i>
        <div class="alert-message">
          <div class="alert-title">${downloaded} downloaded, ${empty.length} empty</div>
          <div>Empty proteomes (no data on UniProt): <code>${emptyList}</code></div>
        </div>
      </div>`;
    }

    summary.innerHTML = html;
    summary.style.display = 'block';

    // Wire retry button if present
    const retryBtn = document.getElementById('retry-failed-btn');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        const failedIds = lastDownloadFailed.map(f => f.pid);
        if (failedIds.length === 0) return;
        startDownloadStream(failedIds, /* isRetry */ true);
      });
    }

    // Enable Run OrthoFinder if we have at least 1 FASTA
    const runBtn = $('runOrthofinderBtn');
    if (runBtn && downloaded > 0) {
      runBtn.disabled = false;
      updateWorkflowStep(1);
    }
  }

  function startDownloadStream(ids, isRetry = false) {
    if (!ids || ids.length === 0) {
      OG.showStatus('downloadStatus', 'error', 'No proteome IDs to download.');
      return;
    }

    ensureProgressVisible();
    OG.setButtonLoading('downloadBtn', true, { textLoading: 'Downloading...' });

    // Reset progress UI
    lastDownloadedTotal = isRetry ? (lastDownloadedTotal) : ids.length;
    // When retrying, accumulate previous downloaded count separately.
    if (!isRetry) {
      lastDownloadedCount = 0;
      lastDownloadFailed = [];
      const log = document.getElementById('downloadLog');
      if (log) log.innerHTML = '';
      const summary = document.getElementById('download-summary');
      if (summary) { summary.innerHTML = ''; summary.style.display = 'none'; }
    } else {
      appendDownloadLog(`--- Retrying ${ids.length} failed proteome(s) ---`, 'warning');
    }

    setProgressBar(0, isRetry ? ids.length : lastDownloadedTotal);
    setCurrentPid(isRetry ? 'Retrying...' : 'Starting...');

    const params = new URLSearchParams({
      ids: ids.join(','),
      mode: isRetry ? 'retry' : 'all',
    });
    const es = new EventSource(`/stream_download?${params.toString()}`);

    let perPassTotal = ids.length;
    let perPassCurrent = 0;
    // Aggregate results across this pass
    const passResult = { downloaded: [], failed: [], empty: [] };

    es.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch (e) { return; }

      switch (data.phase) {
        case 'start':
          perPassTotal = data.total;
          appendDownloadLog(`Starting download of ${data.total} proteome(s)${data.mode === 'retry' ? ' (retry pass)' : ''}`, 'info');
          break;
        case 'proteome_start':
          perPassCurrent = data.current;
          setCurrentPid(data.pid);
          setProgressBar(data.current - 1, perPassTotal);
          appendDownloadLog(`[${data.current}/${data.total}] ${data.pid}`, 'info');
          break;
        case 'attempt':
          if (data.attempt > 1) {
            appendDownloadLog(`  attempt ${data.attempt}/${3} (${data.step})`, 'warning');
          }
          break;
        case 'metadata_ok':
          appendDownloadLog(`  ✓ ${data.species}`, 'success');
          break;
        case 'retry_wait':
          appendDownloadLog(`  waiting ${data.seconds}s before retry — ${data.reason}`, 'warning');
          break;
        case 'proteome_saved':
          appendDownloadLog(`  ✓ saved ${data.filename} (${Math.round(data.size_bytes / 1024)} KB)`, 'success');
          passResult.downloaded.push({ pid: data.pid, filename: data.filename, species: data.species, size_bytes: data.size_bytes });
          setProgressBar(perPassCurrent, perPassTotal);
          break;
        case 'proteome_empty':
          appendDownloadLog(`  ⚠️ empty file, skipped`, 'warning');
          passResult.empty.push({ pid: data.pid, filename: data.filename });
          setProgressBar(perPassCurrent, perPassTotal);
          break;
        case 'proteome_failed':
          appendDownloadLog(`  ✗ FAILED after ${data.attempts} attempts — ${data.reason}`, 'error');
          passResult.failed.push({ pid: data.pid, reason: data.reason });
          setProgressBar(perPassCurrent, perPassTotal);
          break;
        case 'done': {
          // Merge this pass with the accumulated previous state.
          // For "all" mode this IS the full result.
          // For "retry" mode, we add new downloads and remove just-recovered IDs
          // from the previous failed list.
          if (isRetry) {
            // Move recovered IDs from prev failures to downloads
            const recovered = new Set(passResult.downloaded.map(d => d.pid));
            const stillFailed = lastDownloadFailed.filter(f => !recovered.has(f.pid));
            const merged = {
              downloaded: passResult.downloaded,  // additional successes
              failed: passResult.failed.concat(stillFailed.filter(f => !passResult.failed.find(x => x.pid === f.pid))),
              empty: passResult.empty,
            };
            // Update accumulated counters
            lastDownloadedCount = lastDownloadedCount + passResult.downloaded.length;
            renderDownloadSummary(merged);
          } else {
            renderDownloadSummary(passResult);
          }
          es.close();
          OG.setButtonLoading('downloadBtn', false);
          // Mark download as done and Run OrthoFinder as ready
          {
            const dlBtn  = document.getElementById('downloadBtn');
            const runBtn = document.getElementById('runOrthofinderBtn');
            const someFailed = (typeof passResult !== 'undefined') &&
                               passResult.failed && passResult.failed.length > 0;
            if (someFailed) {
              // Keep download as "ready" so user can hit retry; do not advance yet
              setActionState(dlBtn, 'ready', 'Retry failed');
              setWorkflowStates(['done', 'active', 'pending']);
            } else {
              setActionState(dlBtn, 'done', 'Done');
              setActionState(runBtn, 'ready', 'Ready');
              setWorkflowStates(['done', 'done', 'active']);
            }
          }
          break;
        }
      }
    };

    es.onerror = (_e) => {
      appendDownloadLog('Connection lost while streaming download.', 'error');
      es.close();
      OG.setButtonLoading('downloadBtn', false);
      setActionState(document.getElementById('downloadBtn'), 'ready', 'Retry');
      // Show a generic failure summary so the user can retry
      renderDownloadSummary({
        downloaded: passResult.downloaded,
        failed: ids.filter(id => !passResult.downloaded.find(d => d.pid === id))
                   .map(id => ({ pid: id, reason: 'connection lost' })),
        empty: passResult.empty,
      });
    };
  }

  function wireDownload() {
    const btn = $('downloadBtn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      if (btn.disabled || btn.classList.contains('is-done')) return;
      const ids = selectedTemp.map((item) => item.id);
      if (ids.length === 0) {
        OG.showStatus('downloadStatus', 'error', 'Please select at least one species before downloading.');
        return;
      }
      setActionState(btn, 'progress', 'Downloading…');
      setWorkflowStates(['done', 'progress', 'pending']);
      startDownloadStream(ids, /* isRetry */ false);
    });
  }

  /* ---- Run OrthoFinder (SSE stream) ---- */
  function wireRunOrthofinder() {
    const btn = $('runOrthofinderBtn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      if (btn.disabled || btn.classList.contains('is-done')) return;
      const logPanel = $('logPanel');
      const gif = $('loadingGif');
      const postBtns = $('postAnalysisButtons');
      const logSection = document.querySelector('.species-log-section');

      OG.setButtonLoading('runOrthofinderBtn', true, { textLoading: 'Running OrthoFinder...' });
      setActionState(btn, 'progress', 'Running…');
      setWorkflowStates(['done', 'done', 'progress']);
      logSection.classList.add('is-active');
      logPanel.classList.add('is-visible');
      gif.classList.add('is-visible');
      logPanel.innerHTML = '<div class="log-line log-info">Starting OrthoFinder...</div>';

      const eventSource = new EventSource('/stream_orthofinder');

      eventSource.onmessage = (event) => {
        if (event.data === 'DONE') {
          logPanel.insertAdjacentHTML('beforeend', '<div class="log-line log-success">Analysis complete.</div>');
          gif.classList.remove('is-visible');
          postBtns.classList.add('is-visible');
          OG.setButtonLoading('runOrthofinderBtn', false);
          setActionState(btn, 'done', 'Done');
          eventSource.close();
          setWorkflowStates(['done', 'done', 'done']);
          renderRunSummary();
        } else {
          const cls = /error|fail|❌/i.test(event.data)
            ? 'log-error'
            : /warn|⚠️/i.test(event.data)
              ? 'log-warning'
              : 'log-info';
          const line = document.createElement('div');
          line.className = 'log-line ' + cls;
          line.textContent = event.data;
          logPanel.appendChild(line);
          logPanel.scrollTop = logPanel.scrollHeight;
        }
      };

      eventSource.onerror = () => {
        logPanel.insertAdjacentHTML('beforeend', '<div class="log-line log-error">Connection error while streaming OrthoFinder output.</div>');
        gif.classList.remove('is-visible');
        OG.setButtonLoading('runOrthofinderBtn', false);
        eventSource.close();
      };
    });
  }

  /* ---- Post-analysis subaction cards ---- */
  /* ────────────────────────────────────────────────────────────────
     Render the run-summary card (factual, no Excellent/Mixed labels)
     When called on init (opts.restore=true) it ALSO restores the
     workflow indicators + action bar + post-analysis CTAs, so a page
     refresh after a completed run doesn't lose the user's place.
     ──────────────────────────────────────────────────────────────── */
  async function renderRunSummary(opts) {
    opts = opts || {};
    let meta;
    try {
      const res = await fetch('/run_summary');
      if (!res.ok) return false;
      meta = await res.json();
    } catch (e) { return false; }

    const summary = meta.summary || {};
    const issues  = meta.issues  || [];
    if (!summary.ok) return;

    const container = document.getElementById('run-summary');
    if (!container) return;

    const fmt = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString());
    const fmtPct = (n) => (n === null || n === undefined ? '—' : `${n}%`);
    const durationMin = meta.duration_s ? Math.floor(meta.duration_s / 60) : 0;
    const durationSec = meta.duration_s ? Math.round(meta.duration_s % 60) : 0;
    const durationText = durationMin > 0
      ? `${durationMin} min ${durationSec} s`
      : `${durationSec} s`;

    const speciesRows = summary.species.map((sp) => {
      const issue = issues.find((i) => i.species === sp.name);
      const rowClass = issue ? 'is-issue' : '';
      return `
        <tr class="${rowClass}">
          <td><span class="sp-name">${escapeHtml(sp.name)}</span></td>
          <td class="num">${fmt(sp.n_proteins)}</td>
          <td class="num">${fmtPct(sp.pct_in_og)}</td>
          <td class="num">${fmt(sp.n_in_og)}</td>
          ${issue ? `<td class="issue-cell"><i class="fa-solid fa-circle-exclamation"></i> ${escapeHtml(issue.detail)}</td>` : '<td></td>'}
        </tr>
      `;
    }).join('');

    // Coverage spread hint — only show if the spread is wide (informational, not a warning)
    const spreadHint = (
      summary.max_pct_in_og != null &&
      summary.min_pct_in_og != null &&
      (summary.max_pct_in_og - summary.min_pct_in_og) >= 20
    ) ? `<p class="run-summary-hint"><i class="fa-solid fa-lightbulb"></i> Variation in coverage is normal when species span distant taxonomic groups.</p>` : '';

    container.innerHTML = `
      <div class="run-summary-head">
        <h3><i class="fa-solid fa-flask"></i> Analysis complete</h3>
        <span class="run-summary-meta">${summary.species.length} species · ${durationText}</span>
      </div>

      <div class="run-summary-stats">
        <div class="stat-block">
          <span class="stat-value">${fmt(summary.total_orthogroups)}</span>
          <span class="stat-label">orthogroups</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">${fmt(summary.single_copy_orthogroups)}</span>
          <span class="stat-label">single-copy orthologs</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">${fmtPct(summary.mean_pct_in_og)}</span>
          <span class="stat-label">mean proteins in OG${summary.min_pct_in_og != null ? `<br><span class="stat-sub">(range ${summary.min_pct_in_og}–${summary.max_pct_in_og}%)</span>` : ''}</span>
        </div>
        <div class="stat-block">
          <span class="stat-value">${fmt(summary.species_specific_orthogroups)}</span>
          <span class="stat-label">species-specific OGs</span>
        </div>
      </div>

      <table class="run-summary-table">
        <thead>
          <tr>
            <th>Species</th>
            <th class="num">Proteins</th>
            <th class="num">% in OG</th>
            <th class="num">In OG</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${speciesRows}</tbody>
      </table>

      ${spreadHint}
      ${issues.length > 0 ? `<p class="run-summary-issue-note"><i class="fa-solid fa-triangle-exclamation"></i> ${issues.length} technical issue${issues.length>1?'s':''} detected — see rows above.</p>` : ''}
    `;
    container.classList.add('is-visible');
    container.removeAttribute('hidden');

    if (opts.restore) {
      // Recovered from previous run after page refresh — set the surrounding UI to "done" state
      setWorkflowStates(['done', 'done', 'done']);
      const dlBtn  = document.getElementById('downloadBtn');
      const runBtn = document.getElementById('runOrthofinderBtn');
      setActionState(dlBtn,  'done', 'Done');
      setActionState(runBtn, 'done', 'Done');
      const postBtns = document.getElementById('postAnalysisButtons');
      if (postBtns) postBtns.classList.add('is-visible');
    } else {
      container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    return true;
  }

  function wirePostAnalysis() {
    document.querySelectorAll('[data-action]').forEach((el) => {
      el.addEventListener('click', () => {
        switch (el.dataset.action) {
          case 'generated-protein': goProteinAnalysisGenerated(); break;
          case 'generated-go':      goGeneOntologyGenerated();    break;
        }
      });
    });
  }

  /* ---- Kebab menu (catalogue version + check for updates) ---- */
  function wireKebab() {
    const btn  = document.getElementById('catalogue-kebab');
    const menu = document.getElementById('catalogue-menu');
    if (!btn || !menu) return;

    const open  = () => { menu.hidden = false; btn.setAttribute('aria-expanded', 'true'); };
    const close = () => { menu.hidden = true;  btn.setAttribute('aria-expanded', 'false'); };

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      menu.hidden ? open() : close();
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (menu.hidden) return;
      if (!menu.contains(e.target) && e.target !== btn) close();
    });
    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !menu.hidden) close();
    });
  }

  /* ---- "Clear all" link on Selected species ---- */
  function wireClearAll() {
    const btn = document.getElementById('selectedClearBtn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      if (!selectedTemp.length) return;
      // No confirm dialog: the list is easy to rebuild and chips have
      // their own individual ✕; a modal here would feel disproportionate.
      selectedTemp.length = 0;
      updateSelected();
    });
  }

  /* ---- Init ---- */
  function init() {
    updateWorkflowStep(0);
    loadCatalogue();
    wireSearch();
    wireDownload();
    wireRunOrthofinder();
    wirePostAnalysis();
    wireCatalogueUpdates();
    wireKebab();
    wireClearAll();
    refreshActionBarFromSelection();   // initial state
    // Note: we no longer auto-restore the previous run on page load — that was
    // blocking the user from starting a fresh analysis. The previous run is
    // always available through the "View past analyses" link in the breadcrumb
    // and through the /history page.
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
