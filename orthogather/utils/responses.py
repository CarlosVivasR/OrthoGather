"""
Uniform JSON response helper used across every JSON-returning Flask route.
Originally defined inline in app.py; moved here so any blueprint can import
it without round-tripping through the Flask app module.

Two helpers live here:

  respond(ok, msg, ...)              — legacy free-form response.
  respond_error(code, ...)           — looks up the error catalogue and emits
                                        a structured response with stable code,
                                        message, hint, severity and HTTP code.

New code should prefer ``respond_error`` so every error in OrthoGather has a
catalogue entry and the frontend can render them consistently.
"""
from __future__ import annotations

import logging

from flask import jsonify

from orthogather.utils.error_catalog import ERRORS, lookup


def respond(ok: bool, msg: str, *, where=None, hint=None, payload=None, code=200):
    """
    Build a uniform JSON response.

    Parameters
    ----------
    ok : bool
        ``True`` for success, ``False`` for error. Drives both the
        ``success`` field in the payload and the log level.
    msg : str
        Human-readable message; rendered to the user.
    where : str, optional
        Workflow-step label (e.g. ``"foreground_analysis"``). Useful when
        the frontend has to surface different UI per step.
    hint : str, optional
        Suggested next action when ``ok=False``.
    payload : dict, optional
        Extra fields merged into the top level of the response (NOT nested
        under a ``payload`` key — callers historically depend on top-level
        access).
    code : int, default 200
        HTTP status code.
    """
    data = {"success": ok, "message": msg}
    if where:
        data["where"] = where
    if hint:
        data["hint"] = hint
    if payload:
        data.update(payload)

    if ok:
        logging.info(f"{where or 'GO'}: {msg}")
    else:
        logging.error(f"{where or 'GO'}: {msg} | hint={hint}")

    return jsonify(data), code


def respond_error(code: str, *, where: str = None,
                   extra: dict = None, http_code: int = None,
                   detail: str = None):
    """Look up an error in the catalogue and emit a structured JSON response.

    Parameters
    ----------
    code : str
        Stable code from :mod:`orthogather.utils.error_catalog` (e.g.
        ``"ERR_NO_UNIPROT_IDS"``). Unknown codes fall back to ERR_UNEXPECTED.
    where : str, optional
        Workflow-step label so the frontend can group / route the error
        (defaults to the lower-cased error code).
    extra : dict, optional
        Extra fields merged into the response payload. Use this to ship
        dynamic data (e.g. ``{"failed_files": [...]}``).
    http_code : int, optional
        Override the spec's default HTTP status code.
    detail : str, optional
        Free-text addendum appended to the catalogue message. Use sparingly —
        if you find yourself adding details often, add a new catalogue entry
        instead.

    Returns
    -------
    (Response, int)
        A Flask response + HTTP status code, matching :func:`respond`'s shape.
    """
    spec = lookup(code)
    msg = spec.message + (f": {detail}" if detail else "")
    payload = {
        "error_code": code,
        "category":   spec.category,
        "severity":   spec.severity,
    }
    if extra:
        payload.update(extra)
    return respond(
        False, msg,
        where=where or code.lower(),
        hint=spec.hint,
        payload=payload,
        code=http_code or spec.http_code,
    )
