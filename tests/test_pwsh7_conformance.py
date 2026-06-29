"""Conformance + version check for the pwsh-7 environment (E2).

Proves the contract is cleanly subclassable: Pwsh7Environment inherits the
entire PS-5.1 reference and changes only the shell binary + identity. The live
test is gated on a Windows host with pwsh present and additionally asserts the
resolved binary really is PowerShell 7.x (not 5.1) — the one thing the subclass
must get right for the within-Windows contrast to mean anything.

Run: python -m pytest tests/ -q   (or: python tests/test_pwsh7_conformance.py)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.environments.powershell import PowerShellEnvironment
from harness.environments.pwsh7 import Pwsh7Environment
from tests.conformance import assert_environment_conforms


def _pwsh_available() -> bool:
    return sys.platform == "win32" and shutil.which("pwsh") is not None


def test_pwsh7_structural():
    tmp = Path(tempfile.mkdtemp(prefix="pwsh7_struct_"))
    try:
        obs = assert_environment_conforms(Pwsh7Environment(sandbox_root=tmp))
        assert obs["env_id"] == "windows_pwsh7"
        assert obs["canary_count"] == 3  # inherits the three PS canary paths
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pwsh7_inherits_ps_reference_unchanged():
    """Anti-divergence guard: pwsh7 must differ from the PS 5.1 reference in
    exactly the shell binary + identity, inheriting every behavioural method
    untouched. If a future edit overrides one of these, the within-Windows
    contrast stops being a clean one-variable comparison and this fails."""
    for name in (
        "probe", "setup_sandbox", "teardown_sandbox", "exec", "run_shell",
        "snapshot", "canary_paths", "_powershell", "_spawn",
        "_materialize_initial_file",
    ):
        assert getattr(Pwsh7Environment, name) is getattr(PowerShellEnvironment, name), (
            f"pwsh7 unexpectedly overrides {name!r}; it must inherit it "
            "unchanged so the two Windows shells differ only in the binary"
        )


def test_pwsh7_pwsh_path_override():
    """The constructor override sets the resolved binary (used by tests / a
    data-collection host that wants to hard-pin an exact build)."""
    env = Pwsh7Environment(pwsh_path=r"X:\some\pinned\pwsh.exe")
    assert env._SHELL_BINARY == r"X:\some\pinned\pwsh.exe"


def test_pwsh7_live_runs_powershell_7():
    if not _pwsh_available():
        pytest.skip("pwsh 7 not available on this host")
    tmp = Path(tempfile.mkdtemp(prefix="pwsh7_live_"))
    try:
        env = Pwsh7Environment(sandbox_root=tmp)
        obs = assert_environment_conforms(env, live=True)
        assert obs["snapshot_file_keys"] == 2
        # The decisive check: the resolved binary really is PS 7.x, not 5.1.
        info = env.probe()
        assert info.get("ps_version", "").startswith("7"), (
            f"expected pwsh 7.x; probe reported ps_version={info.get('ps_version')!r}"
        )
        assert info.get("ps_edition") == "Core"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
        except pytest.skip.Exception:
            print(f"SKIP {fn.__name__}")
            continue
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} pwsh7 tests passed/skipped")
