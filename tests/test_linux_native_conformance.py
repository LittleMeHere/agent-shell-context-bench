"""Conformance for the Linux-native environment (E4).

Proves `LinuxNativeEnvironment` satisfies the same measurement contract as the
Windows reference — critically, that its no-shared-mount sync produces a
locally-readable, sandbox-relative-POSIX-keyed `host_root` byte-comparable to
the Windows cell (this is the other half of the primary H1a Windows-vs-Linux
comparison).

Structural mode runs anywhere (no infra). The live battery is gated on a
configured GCP SSH target (`PSTAX_GCP_SSH`); without it the live tests skip,
exactly as the Windows reference's live battery is gated on a Windows host.

Native-argv note: the live battery is given Linux-native trivially-succeeding /
long-sleeping commands (`true` / `sleep 30`); the host-Python defaults are
local-OS paths invalid on the remote box. `exercise_canaries` is left OFF: the
Linux sentinels live on the remote filesystem and are not locally writable, so
the battery's local-write canary exercise does not apply — remote escape
detection is covered by its own test below (mirroring how the Windows reference
defers canary IO to a dedicated test).

Run: python -m pytest tests/ -q   (or: python tests/test_linux_native_conformance.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.environments.linux_native import (
    LinuxNativeEnvironment,
    _ssh_configured,
)
from tests.conformance import assert_environment_conforms

# Linux-native commands for the live exec battery.
_OK_ARGV = ["true"]
_SLEEP_ARGV = ["sleep", "30"]


def test_linux_native_structural():
    obs = assert_environment_conforms(LinuxNativeEnvironment())
    assert obs["env_id"] == "linux_native"
    assert obs["canary_count"] == 3
    assert obs["live"] is False


def test_linux_native_canary_handles_absolute_and_mapped():
    """canary_paths() returns host-absolute handles (so the battery's
    is_absolute()/outside-sandbox checks hold on any host) each mapped to the
    remote POSIX sentinel it stands for."""
    env = LinuxNativeEnvironment()
    paths = env.canary_paths()
    assert len(paths) == 3
    for p in paths:
        assert p.is_absolute(), f"canary handle {p} must be an absolute host path"
        assert str(p) in env._canary_remote, "each handle must map to a remote target"
    remotes = list(env._canary_remote.values())
    assert any(r.endswith("/.pstax_canary_user_profile") for r in remotes)
    assert "/tmp/.pstax_canary_temp_dir" in remotes


def test_linux_native_requires_ssh_target_for_exec():
    """With no target configured, the transport refuses loudly rather than
    silently doing nothing (a benchmark that skips a cell corrupts the matrix);
    exec surfaces this as a harness-side EnvironmentError before any spawn."""
    env = LinuxNativeEnvironment(ssh_target=None)
    with pytest.raises(EnvironmentError):
        env._wrap_argv(["true"])


def test_linux_native_live():
    if not _ssh_configured():
        pytest.skip("no GCP SSH target configured (set PSTAX_GCP_SSH)")
    obs = assert_environment_conforms(
        LinuxNativeEnvironment(), live=True,
        exec_ok_argv=_OK_ARGV, exec_sleep_argv=_SLEEP_ARGV,
    )
    assert obs["snapshot_file_keys"] == 2  # keep.txt + sub/nested.txt synced back
    assert "kernel" in obs["probe_keys"] and "os_release" in obs["probe_keys"]


def test_linux_native_live_canary_escape_detection():
    """Remote escape detection over SSH: set sentinels, tamper the
    sandbox-sibling one on the remote box, confirm [modified], clean up.

    Only the sandbox-sibling sentinel is tampered (not the real remote $HOME)."""
    if not _ssh_configured():
        pytest.skip("no GCP SSH target configured (set PSTAX_GCP_SSH)")
    import shlex
    import subprocess

    env = LinuxNativeEnvironment()
    env.set_canaries()
    try:
        assert env.check_canaries() == (), "freshly-set canaries must report clean"
        # Tamper the sandbox-sibling sentinel on the remote, over the same wrapper.
        target_remote = env._canary_remote[str(env.canary_paths()[0])]
        subprocess.run(
            env._wrap_argv(
                ["bash", "-c", f"printf TAMPERED > {shlex.quote(target_remote)}"]
            ),
            capture_output=True, timeout=60,
        )
        escaped = env.check_canaries()
        assert any("[modified]" in e for e in escaped), (
            f"a modified remote canary must be detected; got {escaped!r}"
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
    print(f"\nall {len(fns)} linux_native tests passed/skipped")
