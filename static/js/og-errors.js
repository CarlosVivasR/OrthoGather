/**
 * OrthoGather unified error / warning system — frontend half.
 *
 * Counterpart to orthogather/utils/error_catalog.py + respond_error() on the
 * backend. The backend ships every error as a JSON object shaped like:
 *
 *   {
 *     "success":   false,
 *     "error_code": "ERR_FOREGROUND_MISSING",
 *     "message":   "Foreground proteins are missing from the session",
 *     "hint":      "Load a foreground (paste UniProt IDs + click 'Load …') before…",
 *     "where":     "gene_ontology_analysis",
 *     "category":  "state",
 *     "severity":  "error"
 *   }
 *
 * The frontend renders that as a toast/banner via OG.showError(payload).
 * It also provides OG.fetchJSON(url, opts) — a thin wrapper around fetch()
 * that auto-surfaces any backend error so per-page code never has to repeat
 * `if (!data.success) showError(data); return;` boilerplate.
 *
 * Auto-loaded on every page (see base.html / each template's <script> tag).
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------
  // Toast container — one per page, created on demand.
  // ---------------------------------------------------------------------
  function _ensureContainer() {
    let c = document.getElementById('og-toast-container');
    if (c) return c;
    c = document.createElement('div');
    c.id = 'og-toast-container';
    c.setAttribute('role', 'status');
    c.setAttribute('aria-live', 'polite');
    document.body.appendChild(c);
    return c;
  }

  const CATEGORY_ICONS = {
    'input':     'fa-pen-to-square',
    'state':     'fa-list-check',
    'data':      'fa-file-circle-xmark',
    'network':   'fa-wifi',
    'external':  'fa-globe',
    'not-found': 'fa-compass',
    'system':    'fa-circle-exclamation',
  };

  // Auto-dismiss only for info; errors and warnings stay until clicked.
  const AUTO_DISMISS_MS = {
    'info':    6000,
    'warning': 0,
    'error':   0,
  };

  /**
   * Render a structured error/warning/info banner.
   * @param {Object} payload - the JSON from respond_error() OR an ad-hoc
   *                           object { message, hint, severity, category, error_code }
   */
  function showError(payload) {
    if (!payload || typeof payload !== 'object') return;
    const severity = payload.severity || 'error';
    const category = payload.category || 'system';
    const icon     = CATEGORY_ICONS[category] || CATEGORY_ICONS.system;
    const code     = payload.error_code || '';
    const message  = payload.message    || 'Something went wrong.';
    const hint     = payload.hint       || '';

    // Dedupe — if a toast with the SAME error_code is already on screen, just
    // bump its counter instead of stacking N identical banners. This makes
    // repeat-action errors (e.g. clicking "add" past the species cap) sane.
    if (code) {
      const existing = document.querySelector(`.og-toast[data-code="${CSS.escape(code)}"]`);
      if (existing) {
        const counter = existing.querySelector('.og-toast-counter');
        const n = (parseInt(counter?.textContent || '1', 10) || 1) + 1;
        if (counter) {
          counter.textContent = String(n);
        } else {
          const body = existing.querySelector('.og-toast-body');
          const c = document.createElement('span');
          c.className = 'og-toast-counter';
          c.textContent = String(n);
          c.title = `Triggered ${n} times`;
          body.insertBefore(c, body.firstChild);
        }
        // Refresh the pulse so the user notices it's still happening
        existing.classList.remove('is-pulse');
        void existing.offsetWidth;  // force reflow
        existing.classList.add('is-pulse');
        return existing;
      }
    }

    const toast = document.createElement('div');
    toast.className = `og-toast og-toast--${severity}`;
    toast.dataset.code = code;
    toast.innerHTML = `
      <div class="og-toast-icon"><i class="fa-solid ${icon}" aria-hidden="true"></i></div>
      <div class="og-toast-body">
        ${code ? `<div class="og-toast-code">${code}</div>` : ''}
        <div class="og-toast-message">${_escape(message)}</div>
        ${hint ? `<div class="og-toast-hint">${_escape(hint)}</div>` : ''}
      </div>
      <button class="og-toast-dismiss" type="button" aria-label="Dismiss">
        <i class="fa-solid fa-xmark" aria-hidden="true"></i>
      </button>
    `;

    const container = _ensureContainer();
    container.appendChild(toast);

    // Animate in next frame
    requestAnimationFrame(() => toast.classList.add('is-visible'));

    const dismiss = () => {
      toast.classList.remove('is-visible');
      setTimeout(() => toast.remove(), 250);
    };
    toast.querySelector('.og-toast-dismiss').addEventListener('click', dismiss);

    const ttl = AUTO_DISMISS_MS[severity];
    if (ttl > 0) setTimeout(dismiss, ttl);

    // Echo to console for devs
    const consoleMethod = (severity === 'error')   ? console.error
                       : (severity === 'warning') ? console.warn
                       : console.info;
    consoleMethod(`[OG] ${code || severity.toUpperCase()}: ${message}` + (hint ? ` — hint: ${hint}` : ''));

    return toast;
  }

  /**
   * Convenience wrappers — same payload shape as showError().
   */
  function showWarning(payload) {
    return showError(Object.assign({severity: 'warning', category: 'system'}, payload));
  }
  function showInfo(payload) {
    return showError(Object.assign({severity: 'info', category: 'system'}, payload));
  }

  /**
   * fetch() wrapper that automatically surfaces backend errors.
   *
   *   const data = await OG.fetchJSON('/foreground_analysis', {
   *     method: 'POST',
   *     body: JSON.stringify({uniprot_ids: ids}),
   *   });
   *   if (!data) return;  // error already shown
   *   // ... use data
   *
   * Returns the parsed JSON on success, null on failure (after showing
   * the error toast). The caller almost never has to handle errors manually.
   */
  async function fetchJSON(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      {'Accept': 'application/json', 'Content-Type': 'application/json'},
      opts.headers || {}
    );
    try {
      const res = await fetch(url, opts);
      const data = await res.json().catch(() => null);
      if (!res.ok || (data && data.success === false)) {
        // Backend error — show the structured payload
        if (data) {
          showError(data);
        } else {
          showError({
            error_code: 'ERR_NETWORK',
            severity: 'error',
            category: 'network',
            message: `HTTP ${res.status} ${res.statusText}`,
            hint: 'Check your network connection and the server log.',
          });
        }
        return null;
      }
      return data;
    } catch (err) {
      showError({
        error_code: 'ERR_NETWORK',
        severity: 'error',
        category: 'network',
        message: 'Could not reach the OrthoGather server',
        hint: 'Is the Flask app running on the expected port? Check the terminal.',
      });
      console.error('[OG] fetchJSON failed:', err);
      return null;
    }
  }

  function _escape(s) {
    const d = document.createElement('div');
    d.textContent = String(s == null ? '' : s);
    return d.innerHTML;
  }

  // Expose on window so every page can use it
  window.OG = window.OG || {};
  window.OG.showError   = showError;
  window.OG.showWarning = showWarning;
  window.OG.showInfo    = showInfo;
  window.OG.fetchJSON   = fetchJSON;
})();
