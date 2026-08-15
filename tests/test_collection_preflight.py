from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.configuration_matrix import load_matrix
from scripts.collection_preflight import (
    STATUS_BLOCKED,
    STATUS_FAIL,
    STATUS_PASS,
    audit_environment,
    run_audit,
    write_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = REPO_ROOT / "config" / "v2-runtime-matrix.candidate.json"


class FakeEnvironment:
    def __init__(self, env_id: str, probe: dict[str, str] | None = None) -> None:
        self.env_id = env_id
        self._probe = probe or {"env_id": env_id, "ps_version": "5.1.22621.1"}

    def probe(self) -> dict[str, str]:
        return dict(self._probe)


def _environment_factory(env_id: str) -> FakeEnvironment:
    return FakeEnvironment(env_id)


def _agent_factory(agent_id: str, model_id: str):
    versions = {
        "claude_code": "2.1.176 (Claude Code)",
        "codex": "codex-cli 0.139.0",
        "agy": "1.1.8",
    }
    return SimpleNamespace(cli_version=lambda environment: versions[agent_id])


def _hygiene() -> dict[str, str]:
    return {
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_FEEDBACK_COMMAND": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
    }


def test_exact_versions_and_hygiene_pass() -> None:
    audit = run_audit(
        ["windows_powershell"],
        agy_cli_version="1.1.8",
        environ=_hygiene(),
        environment_factory=_environment_factory,
        agent_factory=_agent_factory,
        created_at="2026-08-06T00-00-00Z",
    )
    assert audit.passed
    assert audit.zero_quota is True
    assert audit.as_dict()["passed"] is True


def test_explicit_v2_matrix_controls_cli_and_environment_pins() -> None:
    matrix = load_matrix(CANDIDATE)

    def current_agent_factory(agent_id: str, model_id: str):
        versions = {
            "claude_code": "2.1.231 (Claude Code)",
            "codex": "codex-cli 0.147.0",
            "agy": "1.1.13",
        }
        return SimpleNamespace(cli_version=lambda environment: versions[agent_id])

    audit = run_audit(
        ["windows_pwsh7"],
        agy_cli_version=None,
        matrix=matrix,
        environ=_hygiene(),
        environment_factory=lambda env_id: FakeEnvironment(
            env_id,
            {
                "env_id": env_id,
                "node": "v24.12.0",
                "os": "Microsoft Windows 11 Home",
                "ps_version": "7.6.4",
            },
        ),
        agent_factory=current_agent_factory,
        created_at="2026-08-06T00-00-00Z",
        observed_python_version="3.11.9",
    )
    assert audit.passed
    assert audit.matrix_status == "candidate"
    assert audit.matrix_digest == matrix.digest


def test_explicit_matrix_and_legacy_agy_pin_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="supply matrix or agy_cli_version"):
        run_audit(
            ["windows_powershell"],
            agy_cli_version="1.1.10",
            matrix=load_matrix(CANDIDATE),
        )


def test_version_prefix_collision_fails_closed() -> None:
    def bad_agent_factory(agent_id: str, model_id: str):
        versions = {
            "claude_code": "2.1.1760",
            "codex": "0.139.00",
            "agy": "1.1.80",
        }
        return SimpleNamespace(cli_version=lambda environment: versions[agent_id])

    audit = run_audit(
        ["windows_powershell"],
        agy_cli_version="1.1.8",
        environ=_hygiene(),
        environment_factory=_environment_factory,
        agent_factory=bad_agent_factory,
    )
    statuses = {
        check.check_id: check.status for check in audit.environments[0].checks
    }
    assert statuses["agent_cli:claude_code"] == STATUS_FAIL
    assert statuses["agent_cli:codex"] == STATUS_FAIL
    assert statuses["agent_cli:agy"] == STATUS_FAIL
    assert not audit.passed


def test_missing_agy_day_one_pin_is_blocked_without_invocation() -> None:
    invoked: list[str] = []

    def tracking_agent_factory(agent_id: str, model_id: str):
        invoked.append(agent_id)
        return _agent_factory(agent_id, model_id)

    audit = run_audit(
        ["windows_powershell"],
        agy_cli_version=None,
        environ=_hygiene(),
        environment_factory=_environment_factory,
        agent_factory=tracking_agent_factory,
    )
    agy = next(
        check
        for check in audit.environments[0].checks
        if check.check_id == "agent_cli:agy"
    )
    assert agy.status == STATUS_BLOCKED
    assert invoked == ["claude_code", "codex"]
    assert not audit.passed


def test_environment_exception_becomes_failure_and_other_paths_continue() -> None:
    def mixed_factory(env_id: str):
        if env_id == "windows_pwsh7":
            raise RuntimeError(r"C:\Users\private\cannot connect")
        return _environment_factory(env_id)

    audit = run_audit(
        ["windows_powershell", "windows_pwsh7"],
        agy_cli_version="1.1.8",
        environ=_hygiene(),
        environment_factory=mixed_factory,
        agent_factory=_agent_factory,
    )
    assert audit.environments[0].passed
    failed = audit.environments[1]
    assert failed.checks[0].status == STATUS_FAIL
    assert str(Path.home()) not in (failed.checks[0].detail or "")
    assert not audit.passed


@pytest.mark.parametrize(
    ("env_id", "probe", "check_id", "status"),
    [
        (
            "windows_pwsh7",
            {"env_id": "windows_pwsh7", "ps_version": "7.6.2"},
            "pwsh_version",
            STATUS_PASS,
        ),
        (
            "windows_pwsh7",
            {"env_id": "windows_pwsh7", "ps_version": "7.6.4"},
            "pwsh_version",
            STATUS_FAIL,
        ),
        (
            "windows_wsl2",
            {"env_id": "windows_wsl2", "os_release": "Ubuntu 24.04.3 LTS"},
            "ubuntu_release",
            STATUS_PASS,
        ),
        (
            "linux_native",
            {"env_id": "linux_native", "os_release": "Ubuntu 22.04.5 LTS"},
            "ubuntu_release",
            STATUS_FAIL,
        ),
        (
            "macos_actions",
            {"env_id": "macos_actions", "os": "Darwin"},
            "macos_identity",
            STATUS_PASS,
        ),
    ],
)
def test_environment_pin_checks(
    env_id: str,
    probe: dict[str, str],
    check_id: str,
    status: str,
) -> None:
    audit = audit_environment(
        env_id,
        agy_cli_version="1.1.8",
        environment_factory=lambda _: FakeEnvironment(env_id, probe),
        agent_factory=_agent_factory,
    )
    assert next(check for check in audit.checks if check.check_id == check_id).status == status


def test_explicit_matrix_checks_macos_runner_identity() -> None:
    matrix = load_matrix(CANDIDATE)
    versions = {
        "claude_code": "2.1.231",
        "codex": "0.147.0",
        "agy": "1.1.13",
    }
    audit = audit_environment(
        "macos_actions",
        agy_cli_version=None,
        matrix=matrix,
        environment_factory=lambda _: FakeEnvironment(
            "macos_actions",
            {
                "env_id": "macos_actions",
                "node": "v24.12.0",
                "os": "Darwin",
                "runner_image": "macos26",
            },
        ),
        agent_factory=lambda agent_id, model_id: SimpleNamespace(
            cli_version=lambda environment: versions[agent_id]
        ),
    )
    assert audit.passed
    assert next(
        check for check in audit.checks if check.check_id == "macos_runner"
    ).status == STATUS_PASS

    drift = audit_environment(
        "macos_actions",
        agy_cli_version=None,
        matrix=matrix,
        environment_factory=lambda _: FakeEnvironment(
            "macos_actions",
            {
                "env_id": "macos_actions",
                "node": "v24.12.0",
                "os": "Darwin",
                "runner_image": "macos15",
            },
        ),
        agent_factory=lambda agent_id, model_id: SimpleNamespace(
            cli_version=lambda environment: versions[agent_id]
        ),
    )
    assert next(
        check for check in drift.checks if check.check_id == "macos_runner"
    ).status == STATUS_FAIL
    assert not drift.passed


def test_unset_hygiene_values_are_boolean_only_and_fail() -> None:
    secret = "do-not-emit-this-value"
    audit = run_audit(
        ["windows_powershell"],
        agy_cli_version="1.1.8",
        environ={"DISABLE_TELEMETRY": secret},
        environment_factory=_environment_factory,
        agent_factory=_agent_factory,
    )
    encoded = json.dumps(audit.as_dict())
    assert secret not in encoded
    assert '"observed": "set"' in encoded
    assert not audit.passed


def test_unknown_and_duplicate_environments_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown environment"):
        run_audit(["invented"], agy_cli_version="1.1.8")
    with pytest.raises(ValueError, match="duplicate"):
        run_audit(
            ["windows_powershell", "windows_powershell"],
            agy_cli_version="1.1.8",
        )


def test_write_audit_refuses_overwrite(tmp_path: Path) -> None:
    audit = run_audit(
        ["windows_powershell"],
        agy_cli_version="1.1.8",
        environ=_hygiene(),
        environment_factory=_environment_factory,
        agent_factory=_agent_factory,
        created_at="2026-08-06T00-00-00Z",
    )
    output = tmp_path / "audit.json"
    write_audit(audit, output)
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_audit(audit, output)
