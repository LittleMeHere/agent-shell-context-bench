"""Exercises the shared conformance batteries (tests/conformance.py).

Three things are proven here:

  1. The reference adapters (ClaudeCodeAdapter, PowerShellEnvironment) pass
     their batteries — i.e. the batteries encode the contract the references
     already satisfy, so a new adapter that passes them is equivalent to the
     references by construction.
  2. The environment `live=True` path works on ANY OS, via a minimal local
     subprocess env — so CI on a Linux/macOS runner still verifies the
     battery itself even though it can't run the Windows reference.
  3. The registry stays consistent (the edit every new adapter makes).

The Windows PS 5.1 reference env's live battery is gated on a Windows host,
mirroring how it is only fully exercised where it can actually run.

Run: python -m pytest tests/ -q   (or: python tests/test_adapter_conformance.py)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

import pytest

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.adapters.claude_code import ClaudeCodeAdapter
from harness.environments.base import EnvironmentAdapter
from harness.environments.powershell import PowerShellEnvironment
from harness.fs import local_snapshot
from harness.types import FilesystemSnapshot, ProcessResult, SandboxHandle
from tests.conformance import (
    assert_agent_adapter_conforms,
    assert_environment_conforms,
    assert_registry_consistency,
)


# ---------------------------------------------------------------------------
# A minimal, OS-independent conforming environment — lets the live battery be
# verified on any runner, and doubles as the smallest possible worked example
# of the contract for adapter authors.
# ---------------------------------------------------------------------------


class _LocalSubprocessEnv(EnvironmentAdapter):
    env_id: ClassVar[str] = "test_local_subprocess"
    description: ClassVar[str] = "tmp-rooted local subprocess env (conformance self-test)"

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def canary_paths(self) -> list[Path]:
        # Sibling of the per-trial sandboxes, i.e. outside any one sandbox.
        return [self._root / ".canary_outside_sandbox"]

    def probe(self) -> dict[str, str]:
        return {"env_id": self.env_id, "python": sys.version.split()[0]}

    def setup_sandbox(
        self, task_id: str, trial_index: int, preconditions: Mapping[str, object]
    ) -> SandboxHandle:
        path = self._root / f"{task_id}_t{trial_index}_{int(time.time() * 1e6)}"
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        for entry in preconditions.get("initial_files", []) or []:
            if isinstance(entry, Mapping):
                rel, content = str(entry["path"]), str(entry.get("content", ""))
            else:
                rel, content = str(entry), ""
            target = path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for tool in preconditions.get("required_tools", []) or []:
            if shutil.which(str(tool)) is None:
                shutil.rmtree(path, ignore_errors=True)
                raise EnvironmentError(f"required tool {tool!r} missing")
        return SandboxHandle(
            task_id=task_id, trial_index=trial_index, env_id=self.env_id,
            root=str(path), host_root=path,
        )

    def teardown_sandbox(self, sandbox: SandboxHandle) -> None:
        shutil.rmtree(sandbox.host_root, ignore_errors=True)

    def exec(self, argv, *, cwd, timeout, env=None) -> ProcessResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ProcessResult(
                argv=tuple(argv), returncode=None, stdout="", stderr="",
                duration_seconds=time.monotonic() - start, timed_out=True,
            )
        return ProcessResult(
            argv=tuple(argv), returncode=proc.returncode, stdout=proc.stdout,
            stderr=proc.stderr, duration_seconds=time.monotonic() - start,
        )

    def run_shell(self, sandbox: SandboxHandle, script: str, *, timeout: float) -> ProcessResult:
        return self.exec([sys.executable, "-c", script], cwd=sandbox.root, timeout=timeout)

    def snapshot(self, sandbox: SandboxHandle) -> FilesystemSnapshot:
        snap = local_snapshot(sandbox.host_root)
        return FilesystemSnapshot(
            files=snap.files, dirs=snap.dirs, escaped_paths=self.check_canaries(),
        )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_claude_code_agent_conforms():
    obs = assert_agent_adapter_conforms(ClaudeCodeAdapter("claude-sonnet-4-6"))
    assert obs["agent_id"] == "claude_code"
    # The 'mixed' robustness case carries exactly one shell command.
    assert obs["parse_transcript_total_commands"] >= 1


def test_registry_is_consistent():
    obs = assert_registry_consistency()
    assert "windows_powershell" in obs["implemented_envs"]
    assert "claude_code" in obs["implemented_agents"]


def test_local_subprocess_env_conforms_live():
    """Full live battery on an OS-independent env (verifies the battery on
    any runner, including the canary write/detect path)."""
    tmp = Path(tempfile.mkdtemp(prefix="conformance_localenv_"))
    try:
        obs = assert_environment_conforms(
            _LocalSubprocessEnv(tmp), live=True, exercise_canaries=True,
        )
        assert obs["live"] is True
        assert obs["snapshot_file_keys"] == 2  # keep.txt + sub/nested.txt
        assert obs["exercised_canaries"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reference_powershell_env_structural():
    # Structural mode needs no PowerShell, so it runs on any host.
    tmp = Path(tempfile.mkdtemp(prefix="conformance_ps_struct_"))
    try:
        obs = assert_environment_conforms(PowerShellEnvironment(sandbox_root=tmp))
        assert obs["env_id"] == "windows_powershell"
        assert obs["canary_count"] == 3
        assert obs["live"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reference_powershell_env_live():
    if sys.platform != "win32":
        pytest.skip("PowerShell 5.1 reference env runs on Windows only")
    tmp = Path(tempfile.mkdtemp(prefix="conformance_ps_live_"))
    try:
        # exercise_canaries left False: would write to the real %USERPROFILE%
        # / %TEMP% sentinels; canary IO is covered by test_canary_detection.
        obs = assert_environment_conforms(
            PowerShellEnvironment(sandbox_root=tmp), live=True,
        )
        assert obs["env_id"] == "windows_powershell"
        assert obs["snapshot_file_keys"] == 2
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
    print(f"\nall {len(fns)} conformance tests passed/skipped")
