function showStatus(targetId, type, text) {
  var el = document.getElementById(targetId);
  if (!el) return;
  var cls = "alert";
  if (type === "success") cls += " alert-success";
  else if (type === "error") cls += " alert-error";
  else if (type === "info") cls += " alert-info";
  var div = document.createElement("div");
  div.className = cls;
  div.textContent = String(text || "");
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
  el.appendChild(div);
  el.style.display = "block";
}

function setButtonLoading(buttonId, isLoading, opts) {
  var btn = document.getElementById(buttonId);
  if (!btn) return;
  var options = opts || {};
  var textLoading = options.textLoading || "Loading...";
  var textIdle = options.textIdle || btn.dataset.textIdle || btn.textContent;

  if (!btn.dataset.textIdle) {
    btn.dataset.textIdle = textIdle;
  }

  btn.disabled = !!isLoading;
  btn.textContent = isLoading ? textLoading : btn.dataset.textIdle;
}
