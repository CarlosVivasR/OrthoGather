/* ============================================================================
   OrthoGather — Home page (index.html)
   Hooks up the entry cards: file uploads + navigation + GO preselected flow.
   ============================================================================ */

(function () {
  'use strict';

  function handleProteinZipChange(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    document.getElementById('uploadForm').submit();
  }

  async function handleGOZipChange(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    try {
      OG.showSpinner();
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/cargar_carpeta?modo=upload', {
        method: 'POST',
        body: fd,
      });
      if (!res.ok) {
        OG.hideSpinner();
        OG.showStatus('status-message', 'error', 'Error uploading the ZIP file for the Gene Ontology analysis.');
        return;
      }
      window.location.href = '/resultado_goa';
    } catch (err) {
      OG.hideSpinner();
      OG.showStatus('status-message', 'error', 'Unexpected error: ' + err.message);
    }
  }

  async function runGeneOntologyPreselected() {
    try {
      OG.showSpinner();
      const prepResponse = await fetch('/cargar_carpeta?filename=Orthogroups.zip&modo=preselected');
      if (!prepResponse.ok) {
        OG.hideSpinner();
        OG.showStatus('status-message', 'error', 'Error preparing data for the Gene Ontology analysis.');
        return;
      }
      window.location.href = '/resultado_goa';
    } catch (err) {
      OG.hideSpinner();
      OG.showStatus('status-message', 'error', 'Unexpected error: ' + err.message);
    }
  }

  function wireUp() {
    /* File inputs */
    const zipInput   = document.getElementById('zipInput');
    const zipInputGO = document.getElementById('zipInputGO');
    if (zipInput)   zipInput.addEventListener('change', handleProteinZipChange);
    if (zipInputGO) zipInputGO.addEventListener('change', handleGOZipChange);

    /* Subaction buttons (data-action attributes) */
    document.querySelectorAll('[data-action]').forEach((el) => {
      el.addEventListener('click', (e) => {
        const action = el.dataset.action;
        switch (action) {
          case 'upload-protein-zip':
            e.preventDefault();
            zipInput && zipInput.click();
            break;
          case 'upload-go-zip':
            e.preventDefault();
            zipInputGO && zipInputGO.click();
            break;
          case 'preselected-protein':
            window.location.href = '/cargar_carpeta?filename=Orthogroups.zip&modo=preselected';
            break;
          case 'preselected-go':
            e.preventDefault();
            runGeneOntologyPreselected();
            break;
          case 'new-analysis':
            window.location.href = '/1-seleccion_especies';
            break;
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireUp);
  } else {
    wireUp();
  }
})();
