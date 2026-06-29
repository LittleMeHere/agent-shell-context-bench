"""Conformance for the WSL2 environment (E3).

Proves `WslEnvironment` satisfies the same measurement contract as the Windows
reference. `WslEnvironment` fail-constructs without `wsl` on PATH (by design),
so even the STRUCTURAL battery is gated on `wsl` being present (a Windows host)
— it cannot run on the Linux CI runner. The live battery additionally needs the
pinned `Ubuntu-24.04` distro registered, exactly as the PowerShell reference's
live battery is gated on a Windows host.

Native-argv note: WSL2's `exec` runs inside Ubuntu, so the live battery is given
WSL-native trivially-succeeding / long-sleeping commands (`true` / `sleep 30`)
rather than the host-Python defaults — `sys.executable` is a Windows path with
no meaning inside WSL.

Run: python -m pytest tests/ -q   (or: python tests/test_windows_wsl2_conformance.py)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.environments.wsl2 import WslEnvironment, _WSL_DISTRO
from tests.conformance import assert_environment_conforms

# WSL-native commands for the live exec battery (the host-Python defaults are
# Windows paths invalid inside the distro).
_OK_ARGV = ["true"]
_SLEEP_ARGV = ["sleep", "30"]


def _wsl_present() -> bool:
    """True iff the `wsl` launcher is on PATH. `WslEnvironment.__init__`
    fail-constructs without it, so even the structural battery is gated on this
    — present on a Windows host, absent on the Linux CI runner."""
    return shutil.which("wsl") is not None


def _wsl_distro_available() -> bool:
    """True iff the pinned distro is registered (gates the live battery).

    `wsl -l -v` output is UTF-16 with NUL bytes on Windows; decode loosely and
    look for the pinned distro name. Any failure (no wsl, no distro) ⇒ skip.
    """
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["wsl", "-l", "-v"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    text = out.stdout.decode("utf-16", errors="ignore") or out.stdout.decode(
        "utf-8", errors="ignore"
    )
    return _WSL_DISTRO in text


def test_wsl2_structural():
    if not _wsl_present():
        pytest.skip("wsl not on PATH; WslEnvironment fail-constructs without it")
    obs = assert_environment_conforms(WslEnvironment())
    assert obs["env_id"] == "windows_wsl2"
    assert obs["canary_count"] == 3
    assert obs["live"] is False


def test_wsl2_canary_paths_are_absolute_unc():
    """canary_paths() must be absolute host paths (UNC bridge translations) so
    the base canary I/O can write/verify them over the live mount and the
    battery's is_absolute() check holds on the Windows host."""
    if not _wsl_present():
        pytest.skip("wsl not on PATH; WslEnvironment fail-constructs without it")
    env = WslEnvironment()
    paths = env.canary_paths()
    assert len(paths) == 3
    for p in paths:
        assert p.is_absolute(), f"canary {p} must be an absolute host path"
        s = str(p)
        assert s.startswith("\\\\wsl") or s.startswith("//wsl"), (
            f"canary {p} should be a WSL UNC bridge path"
        )


def test_wsl2_live():
    if not _wsl_distro_available():
        pytest.skip(f"WSL distro {_WSL_DISTRO!r} not available on this host")
    obs = assert_environment_conforms(
        WslEnvironment(), live=True,
        exec_ok_argv=_OK_ARGV, exec_sleep_argv=_SLEEP_ARGV,
    )
    assert obs["snapshot_file_keys"] == 2  # keep.txt + sub/nested.txt
    # probe() reached the distro and reported its Unix fingerprint.
    assert "kernel" in obs["probe_keys"] and "os_release" in obs["probe_keys"]


def test_wsl2_live_canary_escape_detection():
    """End-to-end remote-escape detection over the UNC bridge: set sentinels,
    tamper one on the WSL side, confirm it is flagged [modified], clean up.

    Kept separate from the battery (which leaves exercise_canaries off so it
    never writes to the real WSL $HOME); this test tampers only the
    sandbox-sibling sentinel and removes it afterwards."""
    if not _wsl_distro_available():
        pytest.skip(f"WSL distro {_WSL_DISTRO!r} not available on this host")
    env = WslEnvironment()
    env.set_canaries()
    try:
        assert env.check_canaries() == (), "freshly-set canaries must report clean"
        # The first canary is the sandbox-sibling one (safe to tamper).
        target = env.canary_paths()[0]
        target.write_bytes(b"conformance: simulated escape")
        escaped = env.check_canaries()
        assert any("[modified]" in e for e in escaped), (
            f"a modified WSL canary must be detected; got {escaped!r}"
        )
    finally:
        env.cleanup_canaries()
        env.cleanup_canaries()  # idempotent


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        try:
            fn()
        except pytest.skip.Exception:
            print(f"SKIP {fn.__name__}")
            continue
        print(f"PASS {fn.__name__}")
    print(f"\nall {len(fns)} wsl2 tests passed/skipped")
