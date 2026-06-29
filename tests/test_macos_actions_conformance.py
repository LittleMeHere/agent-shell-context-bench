"""Conformance battery for the macOS-on-Actions environment (E5).

The structural battery (no infrastructure) runs on ANY host, so CI verifies
the contract even on the Windows/Linux machines that can't be a macOS
runner. The live battery is gated on `sys.platform == 'darwin'`, exactly as
the Windows reference env's live battery is gated on a Windows host — it
exercises the real sandbox / snapshot / exec / probe path and so only runs
on a Mac or the `macos-26` Actions runner itself.

Run: python -m pytest tests/ -q   (or: python tests/test_macos_actions_conformance.py)
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

from harness.environments.macos_actions import MacOSActionsEnvironment
from tests.conformance import assert_environment_conforms


def _on_macos() -> bool:
    return sys.platform == "darwin"


def test_macos_actions_structural():
    """Structural mode needs no macOS, so it runs on any host."""
    tmp = Path(tempfile.mkdtemp(prefix="macos_struct_"))
    try:
        obs = assert_environment_conforms(MacOSActionsEnvironment(sandbox_root=tmp))
        assert obs["env_id"] == "macos_actions"
        assert obs["canary_count"] == 3  # sandbox-sibling + $HOME + $TMPDIR
        assert obs["live"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_macos_actions_registered():
    """The id moved from _PLANNED_ENVIRONMENTS into the live map and resolves
    to this class (the registry edit every new env makes)."""
    from harness.registry import make_environment

    env = make_environment("macos_actions")
    assert isinstance(env, MacOSActionsEnvironment)
    assert env.env_id == "macos_actions"


def test_macos_actions_live():
    """Full live battery: real sandbox lifecycle, POSIX snapshot keys,
    timeout-is-data, missing-tool-raises, and an env_id-tagged probe.

    Gated on macOS (a Mac dev host or the macos-26 runner). The
    `exercise_canaries` path is left at its default off here: it would write
    sentinels into the real $HOME / $TMPDIR; canary write/detect semantics
    are already covered OS-independently by tests/test_canary_detection.py
    against the inherited base-class implementation this env does not
    override.
    """
    if not _on_macos():
        pytest.skip("macOS env runs on darwin only (a Mac or the macos-26 runner)")
    tmp = Path(tempfile.mkdtemp(prefix="macos_live_"))
    try:
        env = MacOSActionsEnvironment(sandbox_root=tmp)
        obs = assert_environment_conforms(env, live=True)
        assert obs["snapshot_file_keys"] == 2  # keep.txt + sub/nested.txt
        # The probe must fingerprint the runner and report a real macOS.
        info = env.probe()
        assert info.get("env_id") == "macos_actions"
        assert info.get("os") == "Darwin", (
            f"expected uname -s == 'Darwin' on a macOS runner; "
            f"probe reported os={info.get('os')!r}"
        )
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
    print(f"\nall {len(fns)} macos_actions tests passed/skipped")
