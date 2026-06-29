"""Windows 11 PowerShell 7.x (pwsh) environment — E2, subclass of the PS 5.1 reference.

The pre-registered within-Windows shell contrast: "does upgrading PowerShell
close the gap?" (DECISIONS 2026-05-26 Q3 — 8 of 9 seeded-error tasks are
pre-registered to behave identically on PS 5.1 and pwsh 7; only T01's `&&`
chaining differs, since pwsh 7.0 added pipeline-chain operators). For that
contrast to be valid the two cells must differ in EXACTLY one thing — the shell
— so this class inherits the whole PowerShellEnvironment reference (sandbox,
snapshot, canary sentinels, exec, probe) and overrides only the shell binary
and the identity.

Binary pin — why this differs from PS 5.1's literal absolute pin:
PS 5.1 pins a stable, version-free path (`...\\WindowsPowerShell\\v1.0\\powershell.exe`).
pwsh's install path encodes its version
(`...\\WindowsApps\\Microsoft.PowerShell_7.6.3.0_x64__...\\pwsh.exe`), so a
literal absolute pin would self-break on every pwsh point release. Instead the
binary is resolved deterministically at import (overridable via the
`PSTAX_PWSH_PATH` env var, or the `pwsh_path` constructor arg for tests) and the
EXACT version is recorded every run by the inherited `probe()`
(`$PSVersionTable.PSVersion`). `docs/VERSIONS.md` pins the expected 7.6.x; a
different MAJOR version is a confound the researcher resolves, not the harness —
exactly the rule PS 5.1 states for its own major version.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import ClassVar

from .powershell import PowerShellEnvironment


def _resolve_pwsh() -> str:
    """Deterministically resolve the pwsh 7 binary at import time.

    Precedence: explicit `PSTAX_PWSH_PATH` override -> `pwsh` on PATH (the
    WindowsApps execution alias resolves to the installed build) -> the bare
    name as a last resort, so import never fails on a host without pwsh (such a
    host simply won't run this env's live path). Whatever it resolves to is
    auditable because probe() records the running version per trial.
    """
    explicit = os.environ.get("PSTAX_PWSH_PATH")
    if explicit:
        return explicit
    return shutil.which("pwsh") or "pwsh.exe"


_PWSH = _resolve_pwsh()


class Pwsh7Environment(PowerShellEnvironment):
    env_id: ClassVar[str] = "windows_pwsh7"
    description: ClassVar[str] = "Windows 11 native, PowerShell 7.x (pwsh.exe)"
    _SHELL_BINARY: ClassVar[str] = _PWSH

    def __init__(
        self, sandbox_root: Path | None = None, *, pwsh_path: str | None = None
    ) -> None:
        super().__init__(sandbox_root)
        if pwsh_path is not None:
            self._SHELL_BINARY = pwsh_path
