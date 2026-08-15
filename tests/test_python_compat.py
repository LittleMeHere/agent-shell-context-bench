from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path


_SITECUSTOMIZE = (
    Path(__file__).resolve().parents[1]
    / "harness"
    / "python_compat"
    / "sitecustomize.py"
)


def _execute_sitecustomize(module_name: str) -> None:
    spec = importlib.util.spec_from_file_location(module_name, _SITECUSTOMIZE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def test_macos_service_once_skips_only_loopback_fqdn(monkeypatch):
    calls = []

    def original(name=""):
        calls.append(name)
        return f"resolved:{name}"

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "argv", ["/fixture/service.py", "12345", "--once"])
    monkeypatch.setattr(socket, "getfqdn", original)
    _execute_sitecustomize("_test_service_sitecustomize")

    assert socket.getfqdn("127.0.0.1") == "127.0.0.1"
    assert socket.getfqdn("example.test") == "resolved:example.test"
    assert calls == ["example.test"]


def test_compat_does_not_patch_other_python_processes(monkeypatch):
    def original(name=""):
        return f"resolved:{name}"

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "argv", ["-c"])
    monkeypatch.setattr(socket, "getfqdn", original)
    _execute_sitecustomize("_test_other_sitecustomize")

    assert socket.getfqdn("127.0.0.1") == "resolved:127.0.0.1"
