"""
Tiny network/UI helpers used by app.py at startup time only.
"""
from __future__ import annotations

import socket
import webbrowser


def find_free_port(start: int = 5000, end: int = 5100) -> int:
    """Return the first available TCP port in ``[start, end]``.

    Raises ``RuntimeError`` if every port in the range is busy.
    """
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free ports in range {start}-{end}")


def open_browser(port: int) -> None:
    """Open the user's default browser pointing at the local Flask app."""
    webbrowser.open(f"http://127.0.0.1:{port}")
