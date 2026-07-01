"""
Tiny network/UI helpers used by app.py at startup time only.
"""
from __future__ import annotations

import os
import socket
import urllib.request
import webbrowser
from pathlib import Path

# Where the running app advertises the TCP port it actually bound to.
# The Windows launcher reads this (via \\wsl.localhost\Ubuntu\root\.orthogather\port.txt)
# so it opens the *real* port even when app.py had to fall back off 5000.
# ~/.orthogather/ is the app's existing per-user state dir (see orthogather/config.py).
PORT_FILE = Path.home() / ".orthogather" / "port.txt"


def write_port_file(port: int, path: Path = PORT_FILE) -> None:
    """Atomically record the port the app is about to serve on.

    Must be called BEFORE ``app.run()`` (which blocks forever) so the launcher
    can discover the port. Written atomically (tmp + os.replace) so a poller on
    the Windows side never reads a half-written file. Best-effort: a failure
    here must never stop the app from starting.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".txt.tmp")
        tmp.write_text(str(port), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is already listening on ``host:port``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_orthogather_running(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if the service on ``host:port`` looks like OrthoGather itself.

    Used so that double-clicking the launcher while it's already running opens
    the existing instance instead of crashing on a port clash — but without
    hijacking some *other* program that happens to hold the port.

    Retries a few times with a generous timeout: at startup the machine can be
    under load (two processes spinning up at once), and a single short probe
    can time out on a perfectly healthy instance. We only conclude "not
    OrthoGather" after several attempts all fail or return non-matching HTML.
    """
    import time

    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/", timeout=2.5) as r:
                body = r.read(8192).decode("utf-8", "replace")
                if "OrthoGather" in body:
                    return True
        except Exception:
            pass
        if attempt < 2:
            time.sleep(0.4)
    return False


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
