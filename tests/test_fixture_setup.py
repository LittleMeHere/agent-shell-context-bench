from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from harness.checks import evaluate_checks
from harness.fixture_setup import FixtureSetupError, prepare_fixture
from harness.fs import local_snapshot
from harness.types import ProcessResult, SandboxHandle


class LocalArgvEnvironment:
    def exec(self, argv, *, cwd, timeout, env=None):
        try:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                env=({**os.environ, **env} if env is not None else None),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return ProcessResult(
                argv=tuple(argv),
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_seconds=0.0,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessResult(
                argv=tuple(argv), returncode=None, stdout=exc.stdout or "",
                stderr=exc.stderr or "", duration_seconds=timeout, timed_out=True,
            )


def _sandbox(root: Path) -> SandboxHandle:
    return SandboxHandle("C07-I01", 0, "local", str(root), root)


def test_declarative_git_conflict_fixture_and_environment_oracle(tmp_path: Path):
    (tmp_path / "app.txt").write_text("mode=base\n", encoding="utf-8")
    env = LocalArgvEnvironment()
    setup = {
        "fixture_setup": [
            {"type": "git_init_commit", "message": "base"},
            {"type": "git_create_branch", "name": "feature"},
            {"type": "write_files", "files": {"app.txt": "mode=feature\n"}},
            {"type": "git_commit_all", "message": "feature"},
            {"type": "git_switch", "ref": "main"},
            {"type": "write_files", "files": {"app.txt": "mode=main\n"}},
            {"type": "git_commit_all", "message": "main"},
            {"type": "git_merge_conflict", "ref": "feature"},
        ]
    }
    prepare_fixture(env, _sandbox(tmp_path), setup)

    assert "<<<<<<<" in (tmp_path / "app.txt").read_text(encoding="utf-8")
    passed, results = evaluate_checks(
        local_snapshot(tmp_path),
        [
            {
                "type": "environment_command",
                "argv": ["git", "diff", "--name-only", "--diff-filter=U"],
                "stdout": "app.txt\n",
            }
        ],
        environment_exec=env.exec,
        environment_cwd=str(tmp_path),
    )
    assert passed, results


def test_fixture_setup_rejects_unknown_operations_before_agent(tmp_path: Path):
    with pytest.raises(FixtureSetupError, match="unsupported"):
        prepare_fixture(
            LocalArgvEnvironment(),
            _sandbox(tmp_path),
            {"fixture_setup": [{"type": "run_shell", "script": "anything"}]},
        )


def test_free_loopback_port_fixture_is_written_and_unoccupied(tmp_path: Path):
    import socket

    prepare_fixture(
        LocalArgvEnvironment(),
        _sandbox(tmp_path),
        {
            "fixture_setup": [
                {"type": "write_free_loopback_port", "path": "runtime/port.txt"}
            ]
        },
    )
    port = int((tmp_path / "runtime" / "port.txt").read_text(encoding="utf-8"))
    assert 10240 <= port < 32768
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_environment_command_fails_closed_without_execution_context(tmp_path: Path):
    passed, results = evaluate_checks(
        local_snapshot(tmp_path),
        [{"type": "environment_command", "argv": ["git", "status"]}],
    )
    assert not passed
    assert results[0].detail == "environment execution context unavailable"
