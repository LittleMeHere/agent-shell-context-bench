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
import subprocess
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1]
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from harness.environments.linux_native import (
    LinuxNativeEnvironment,
    _ssh_configured,
)
from harness.fs import SandboxUnreadableError
from harness.types import ProcessResult, SandboxHandle
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


def test_linux_native_requires_ssh_target_for_exec(monkeypatch):
    """With no target configured, the transport refuses loudly rather than
    silently doing nothing (a benchmark that skips a cell corrupts the matrix);
    exec surfaces this as a harness-side EnvironmentError before any spawn.

    The constructor falls back to the module-level PSTAX_GCP_SSH pin, so that
    fallback is neutralised here — otherwise this test can only pass on hosts
    where E4 is UNconfigured, and fails on the actual collection host."""
    import harness.environments.linux_native as ln
    monkeypatch.setattr(ln, "_GCP_SSH_TARGET", None)
    env = LinuxNativeEnvironment(ssh_target=None)
    with pytest.raises(EnvironmentError):
        env._wrap_argv(["true"])


def test_linux_native_pinned_known_hosts_fails_closed():
    env = LinuxNativeEnvironment(
        ssh_target="bench@example.invalid",
        ssh_key="bench-key",
        ssh_port="2200",
        ssh_known_hosts="bench-known-hosts",
    )
    wrapped = env._wrap_argv(["true"])
    assert "UserKnownHostsFile=bench-known-hosts" in wrapped
    assert "StrictHostKeyChecking=yes" in wrapped
    assert "StrictHostKeyChecking=accept-new" not in wrapped
    assert wrapped[-3:] == ["bench@example.invalid", "--", "true"]


def test_linux_native_without_known_hosts_accepts_first_seen_key(monkeypatch):
    import harness.environments.linux_native as ln
    monkeypatch.setattr(ln, "_GCP_SSH_KNOWN_HOSTS", None)
    env = LinuxNativeEnvironment(
        ssh_target="bench@example.invalid",
        ssh_known_hosts=None,
    )
    opts = env._ssh_opts()
    assert "StrictHostKeyChecking=accept-new" in opts
    assert not any(opt.startswith("UserKnownHostsFile=") for opt in opts)


def _fake_remote_sandbox(
    env: LinuxNativeEnvironment,
) -> SandboxHandle:
    root = "/tmp/pstax/X01_0"
    return SandboxHandle(
        task_id="X01",
        trial_index=0,
        env_id=env.env_id,
        root=root,
        host_root=env._host_root_for(root),
    )


@pytest.mark.parametrize(
    "producer",
    [
        subprocess.CompletedProcess(
            ["ssh"],
            255,
            stdout=b"",
            stderr=b"ssh: connection reset",
        ),
        subprocess.CompletedProcess(
            ["ssh"],
            255,
            stdout=b"",
            stderr=b"Permission denied (publickey)",
        ),
        subprocess.CompletedProcess(
            ["ssh"],
            255,
            stdout=b"",
            stderr=b"Identity file key.pem: No such file or directory",
        ),
        subprocess.CompletedProcess(
            ["ssh"],
            0,
            stdout=b"",
            stderr=b"",
        ),
    ],
)
def test_linux_native_sync_transport_failure_never_becomes_empty_snapshot(
    tmp_path: Path,
    monkeypatch,
    producer,
):
    import harness.environments.linux_native as ln

    env = LinuxNativeEnvironment(ssh_target="fake")
    monkeypatch.setattr(env, "_local_mirror_root", lambda: tmp_path)
    sandbox = _fake_remote_sandbox(env)
    monkeypatch.setattr(ln.subprocess, "run", lambda *args, **kwargs: producer)
    with pytest.raises(EnvironmentError) as caught:
        env._sync_back(sandbox)
    assert not isinstance(caught.value, SandboxUnreadableError)


def test_linux_native_missing_remote_sandbox_is_explicit_unreadability(
    tmp_path: Path,
    monkeypatch,
):
    import harness.environments.linux_native as ln

    env = LinuxNativeEnvironment(ssh_target="fake")
    monkeypatch.setattr(env, "_local_mirror_root", lambda: tmp_path)
    sandbox = _fake_remote_sandbox(env)
    producer = subprocess.CompletedProcess(
        ["ssh"],
        2,
        stdout=b"",
        stderr=(
            b"tar: /tmp/pstax/X01_0: Cannot open: "
            b"No such file or directory"
        ),
    )
    monkeypatch.setattr(ln.subprocess, "run", lambda *args, **kwargs: producer)
    with pytest.raises(SandboxUnreadableError) as caught:
        env._sync_back(sandbox)
    assert caught.value.agent_attributable is True


def test_linux_native_extract_failure_is_infrastructure_not_empty_snapshot(
    tmp_path: Path,
    monkeypatch,
):
    import harness.environments.linux_native as ln

    env = LinuxNativeEnvironment(ssh_target="fake")
    monkeypatch.setattr(env, "_local_mirror_root", lambda: tmp_path)
    sandbox = _fake_remote_sandbox(env)
    responses = iter(
        [
            subprocess.CompletedProcess(
                ["ssh"],
                0,
                stdout=b"tar-bytes",
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                ["tar"],
                2,
                stdout=b"",
                stderr=b"corrupt archive",
            ),
        ]
    )
    monkeypatch.setattr(
        ln.subprocess,
        "run",
        lambda *args, **kwargs: next(responses),
    )
    with pytest.raises(EnvironmentError) as caught:
        env._sync_back(sandbox)
    assert not isinstance(caught.value, SandboxUnreadableError)


def test_linux_native_exec_transport_255_without_remote_marker_is_infrastructure(
    monkeypatch,
):
    env = LinuxNativeEnvironment(ssh_target="fake")
    monkeypatch.setattr(
        env,
        "_spawn",
        lambda *args, **kwargs: ProcessResult(
            argv=("ssh",),
            returncode=255,
            stdout="",
            stderr="Permission denied (publickey)",
            duration_seconds=0.01,
        ),
    )
    with pytest.raises(EnvironmentError, match="before the remote agent start"):
        env.exec(["agent"], cwd="/tmp/pstax/X01_0", timeout=30)


def test_linux_native_remote_agent_exit_255_with_marker_remains_agent_result(
    monkeypatch,
):
    import harness.environments._remote as remote_mod

    env = LinuxNativeEnvironment(ssh_target="fake")
    token = "a" * 32
    monkeypatch.setattr(
        remote_mod.uuid,
        "uuid4",
        lambda: type("FixedUuid", (), {"hex": token})(),
    )

    def marked_spawn(wrapped_argv, *, timeout, env=None):
        return ProcessResult(
            argv=tuple(wrapped_argv),
            returncode=255,
            stdout="agent output",
            stderr=(
                f"\n__PSTAX_REMOTE_START_{token}__\n"
                f"agent warning\n"
                f"__PSTAX_REMOTE_EXIT_{token}__=255\n"
            ),
            duration_seconds=0.01,
        )

    monkeypatch.setattr(env, "_spawn", marked_spawn)
    result = env.exec(["agent"], cwd="/tmp/pstax/X01_0", timeout=30)
    assert result.returncode == 255
    assert result.stdout == "agent output"
    assert result.stderr == "agent warning"


@pytest.mark.parametrize("start_observed", [False, True])
def test_linux_native_timeout_requires_remote_agent_start_marker(
    monkeypatch,
    start_observed: bool,
):
    import harness.environments._remote as remote_mod

    env = LinuxNativeEnvironment(ssh_target="fake")
    token = "b" * 32
    monkeypatch.setattr(
        remote_mod.uuid,
        "uuid4",
        lambda: type("FixedUuid", (), {"hex": token})(),
    )

    def timed_spawn(wrapped_argv, *, timeout, env=None):
        stderr = "transport stalled"
        if start_observed:
            stderr = (
                f"\n__PSTAX_REMOTE_START_{token}__\n"
                "agent still running"
            )
        return ProcessResult(
            argv=tuple(wrapped_argv),
            returncode=None,
            stdout="partial",
            stderr=stderr,
            duration_seconds=30,
            timed_out=True,
        )

    monkeypatch.setattr(env, "_spawn", timed_spawn)
    if not start_observed:
        with pytest.raises(
            EnvironmentError,
            match="before the remote agent start",
        ):
            env.exec(["agent"], cwd="/tmp/pstax/X01_0", timeout=30)
        return
    result = env.exec(["agent"], cwd="/tmp/pstax/X01_0", timeout=30)
    assert result.timed_out is True
    assert result.stdout == "partial"
    assert result.stderr == "agent still running"


def test_remote_spawn_normalizes_timeout_bytes_to_text(monkeypatch):
    import harness.environments._remote as remote_mod

    env = LinuxNativeEnvironment(ssh_target="fake")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["ssh"],
            timeout=30,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr(remote_mod.subprocess, "run", raise_timeout)
    result = env._spawn(["ssh"], timeout=30)
    assert result.timed_out is True
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"


def test_linux_native_live():
    if not _ssh_configured():
        pytest.skip("no GCP SSH target configured (set PSTAX_GCP_SSH)")
    obs = assert_environment_conforms(
        LinuxNativeEnvironment(), live=True,
        exec_ok_argv=_OK_ARGV, exec_sleep_argv=_SLEEP_ARGV,
        # Permit SSH to authenticate and emit the start marker before timing
        # out the deliberately sleeping command. The benchmark timeout is
        # 180 s; 5 s is still far below the conformance command's 30 s sleep.
        exec_timeout_seconds=5,
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
