/* ============================================================================
   OrthoGather — shared frontend utilities
   Replaces the legacy ui.js. Loaded by every page (deferred).
   ============================================================================ */

(function (global) {
  'use strict';

  const ICONS = {
    success: 'fa-circle-check',
    warning: 'fa-triangle-exclamation',
    error:   'fa-circle-exclamation',
    info:    'fa-circle-info',
  };

  /**
   * Render a status alert inside a container.
   * @param {string} targetId  The id of the container element.
   * @param {'success'|'warning'|'error'|'info'} type
   * @param {string} text      Plain text (no HTML).
   * @param {{title?:string}} [opts]
   */
  function showStatus(targetId, type, text, opts) {
    const el = document.getElementById(targetId);
    if (!el) return;

    const variant = type in ICONS ? type : 'info';
    const iconClass = ICONS[variant];

    el.innerHTML = '';

    const alert = document.createElement('div');
    alert.className = `alert alert-${variant}`;
    alert.setAttribute('role', variant === 'error' ? 'alert' : 'status');

    const icon = document.createElement('i');
    icon.className = `fa-solid ${iconClass} alert-icon`;
    icon.setAttribute('aria-hidden', 'true');
    alert.appendChild(icon);

    const message = document.createElement('div');
    message.className = 'alert-message';

    if (opts && opts.title) {
      const title = document.createElement('div');
      title.className = 'alert-title';
      title.textContent = opts.title;
      message.appendChild(title);
    }

    const body = document.createElement('div');
    body.textContent = String(text || '');
    message.appendChild(body);

    alert.appendChild(message);
    el.appendChild(alert);
    el.style.display = 'block';
  }

  /**
   * Hide a status container previously populated by showStatus().
   * @param {string} targetId
   */
  function clearStatus(targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.innerHTML = '';
    el.style.display = 'none';
  }

  /**
   * Toggle the loading state of a button. Adds the `.is-loading` class which
   * the design system styles to show a spinner overlay; the original text is
   * preserved via the `data-text-idle` attribute.
   *
   * @param {string} buttonId
   * @param {boolean} isLoading
   * @param {{textLoading?:string, textIdle?:string}} [opts]
   */
  function setButtonLoading(buttonId, isLoading, opts) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    const options = opts || {};

    if (!btn.dataset.textIdle) {
      btn.dataset.textIdle = options.textIdle || btn.textContent.trim();
    }

    btn.disabled = !!isLoading;
    btn.classList.toggle('is-loading', !!isLoading);

    if (isLoading && options.textLoading) {
      btn.dataset.textLoading = options.textLoading;
    }
  }

  /**
   * Global page-level loading overlay (full-screen spinner).
   */
  function showSpinner() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('is-visible');
  }

  function hideSpinner() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('is-visible');
  }

  /* ---- Public API ---- */
  global.OG = global.OG || {};
  global.OG.showStatus = showStatus;
  global.OG.clearStatus = clearStatus;
  global.OG.setButtonLoading = setButtonLoading;
  global.OG.showSpinner = showSpinner;
  global.OG.hideSpinner = hideSpinner;

  /* ---- Backward-compatibility shims (kept until all templates migrate) ---- */
  global.showStatus = showStatus;
  global.setButtonLoading = setButtonLoading;
  global.showSpinner = showSpinner;
  global.hideSpinner = hideSpinner;
})(window);

/* Ensure overlay starts hidden on every load */
window.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.classList.remove('is-visible');
});
