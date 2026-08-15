"""Narrow Python compatibility shim for macOS loopback service oracles."""

from __future__ import annotations

import socket
import sys
from pathlib import Path


if (
    sys.platform == "darwin"
    and Path(sys.argv[0]).name == "service.py"
    and "--once" in sys.argv[1:]
):
    _original_getfqdn = socket.getfqdn

    def _loopback_getfqdn(name: str = "") -> str:
        if name in {"127.0.0.1", "localhost", "::1"}:
            return name
        return _original_getfqdn(name)

    socket.getfqdn = _loopback_getfqdn
