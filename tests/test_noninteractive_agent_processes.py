from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from harness.environments.linux_native import LinuxNativeEnvironment
from harness.environments.macos_actions import MacOSActionsEnvironment
from harness.environments.powershell import PowerShellEnvironment


@pytest.mark.parametrize("environment", ["powershell", "remote", "macos"])
def test_agent_processes_close_inherited_stdin(monkeypatch, environment) -> None:
    observed: dict[str, object] = {}

    def completed(*args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", completed)
    if environment == "powershell":
        PowerShellEnvironment._spawn(
            ["python"], cwd=".", timeout=1, env=None
        )
    elif environment == "remote":
        LinuxNativeEnvironment(ssh_target="example.invalid")._spawn(
            ["ssh"], timeout=1
        )
    else:
        MacOSActionsEnvironment._spawn(
            ["python"], cwd=".", timeout=1, env=None
        )

    assert observed["stdin"] is subprocess.DEVNULL
