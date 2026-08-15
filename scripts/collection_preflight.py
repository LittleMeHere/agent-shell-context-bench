"""Zero-quota qualification audit over the real collection execution paths.

This script never invokes an agent model.  It asks each selected environment
adapter to fingerprint the environment and to run only ``<agent> --version``.
That distinction is deliberate: the checks exercise the same WSL/SSH/local
transport and PATH resolution used by collection without consuming a
subscription call or creating a benchmark trial.

Examples (run from an external control directory with the repository on
``PYTHONPATH``):

    python C:/path/to/repo/scripts/collection_preflight.py \
      --env windows_powershell --env windows_pwsh7 --env windows_wsl2 \
      --matrix C:/path/to/repo/config/v2-runtime-matrix.candidate.json \
      --output C:/tmp/pstax-preflight/windows.json

    python C:/path/to/repo/scripts/collection_preflight.py \
      --env linux_native \
      --matrix C:/path/to/repo/config/v2-runtime-matrix.candidate.json \
      --output C:/tmp/pstax-preflight/linux.json

The output is an operational artifact.  It may contain environment-version
details and therefore must receive the normal redaction review before it is
published.  Environment-variable values and executable paths are never
recorded; only set/unset booleans are retained.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.registry import make_agent, make_environment  # noqa: E402
from harness.scheduler import (  # noqa: E402
    AGY_CONFIG_SPECS,
    CLAUDE_CONFIGS,
    CODEX_CONFIGS,
    ENVIRONMENTS,
    REQUIRED_CLAUDE_ENV_VARS,
)
from scripts.configuration_matrix import RuntimeMatrix, load_matrix  # noqa: E402

SCHEMA_VERSION = "1.1.0"
V1_PWSH_VERSION = "7.6.2"
V1_UBUNTU_RELEASE = "Ubuntu 24.04"
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Check:
    check_id: str
    status: str
    expected: str | None = None
    observed: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class EnvironmentAudit:
    env_id: str
    checks: tuple[Check, ...]
    probe: Mapping[str, str]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(
            check.status == STATUS_PASS for check in self.checks
        )


@dataclass(frozen=True)
class PreflightAudit:
    schema_version: str
    created_at: str
    zero_quota: bool
    matrix_status: str | None
    matrix_digest: str | None
    environments: tuple[EnvironmentAudit, ...]
    controller_checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return bool(self.environments) and all(
            environment.passed for environment in self.environments
        ) and all(check.status == STATUS_PASS for check in self.controller_checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "zero_quota": self.zero_quota,
            "matrix_status": self.matrix_status,
            "matrix_digest": self.matrix_digest,
            "passed": self.passed,
            "controller_checks": [
                dataclasses.asdict(check) for check in self.controller_checks
            ],
            "environments": [
                {
                    "env_id": environment.env_id,
                    "passed": environment.passed,
                    "checks": [
                        dataclasses.asdict(check) for check in environment.checks
                    ],
                    "probe": dict(environment.probe),
                }
                for environment in self.environments
            ],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _version_token_present(observed: str, expected: str) -> bool:
    """Match a dotted version as a token, not as a prefix of another build."""
    return re.search(
        rf"(?<![0-9.]){re.escape(expected)}(?![0-9.])", observed
    ) is not None


def _safe_error(exc: BaseException) -> str:
    """Return a bounded error string without local absolute paths."""
    text = str(exc).replace(str(Path.home()), "<HOME>")
    text = text.replace(str(REPO_ROOT), "<REPO>")
    return text[-1000:]


def _agent_specs(
    agy_cli_version: str | None,
    matrix: RuntimeMatrix | None,
) -> tuple[tuple[str, str, str | None], ...]:
    if matrix is not None:
        first_by_agent = {}
        for config in matrix.configurations:
            first_by_agent.setdefault(config.agent_id, config)
        return tuple(
            (
                first_by_agent[agent_id].agent_id,
                first_by_agent[agent_id].model_id,
                first_by_agent[agent_id].expected_cli_version,
            )
            for agent_id in ("claude_code", "codex", "agy")
        )
    return (
        (
            CLAUDE_CONFIGS[0].agent_id,
            CLAUDE_CONFIGS[0].model_id,
            CLAUDE_CONFIGS[0].expected_cli_version,
        ),
        (
            CODEX_CONFIGS[0].agent_id,
            CODEX_CONFIGS[0].model_id,
            CODEX_CONFIGS[0].expected_cli_version,
        ),
        ("agy", AGY_CONFIG_SPECS[0][1], agy_cli_version),
    )


def _environment_probe_checks(
    env_id: str,
    probe: Mapping[str, str],
    *,
    pwsh_version: str,
    ubuntu_release: str,
    windows_release: str | None,
    macos_runner: str | None,
    node_version: str | None,
) -> list[Check]:
    checks: list[Check] = []
    observed_id = probe.get("env_id")
    checks.append(
        Check(
            "environment_identity",
            STATUS_PASS if observed_id == env_id else STATUS_FAIL,
            expected=env_id,
            observed=observed_id,
        )
    )
    if "probe_error" in probe:
        checks.append(
            Check(
                "environment_probe",
                STATUS_FAIL,
                expected="parseable environment fingerprint",
                detail=str(probe["probe_error"])[-1000:],
            )
        )
        return checks

    checks.append(Check("environment_probe", STATUS_PASS))
    if node_version is not None:
        observed_node = probe.get("node", "")
        checks.append(
            Check(
                "node_version",
                STATUS_PASS
                if _version_token_present(observed_node, node_version)
                else STATUS_FAIL,
                expected=node_version,
                observed=observed_node,
            )
        )
    if env_id == "windows_powershell":
        if windows_release is not None:
            observed_os = probe.get("os", "")
            checks.append(
                Check(
                    "windows_release",
                    STATUS_PASS
                    if windows_release.casefold() in observed_os.casefold()
                    else STATUS_FAIL,
                    expected=windows_release,
                    observed=observed_os,
                )
            )
        observed = probe.get("ps_version", "")
        checks.append(
            Check(
                "powershell_version",
                STATUS_PASS if observed.startswith("5.1") else STATUS_FAIL,
                expected="5.1.x",
                observed=observed,
            )
        )
    elif env_id == "windows_pwsh7":
        if windows_release is not None:
            observed_os = probe.get("os", "")
            checks.append(
                Check(
                    "windows_release",
                    STATUS_PASS
                    if windows_release.casefold() in observed_os.casefold()
                    else STATUS_FAIL,
                    expected=windows_release,
                    observed=observed_os,
                )
            )
        observed = probe.get("ps_version", "")
        checks.append(
            Check(
                "pwsh_version",
                STATUS_PASS if observed == pwsh_version else STATUS_FAIL,
                expected=pwsh_version,
                observed=observed,
            )
        )
    elif env_id in {"windows_wsl2", "linux_native"}:
        observed = probe.get("os_release", "")
        checks.append(
            Check(
                "ubuntu_release",
                STATUS_PASS if ubuntu_release in observed else STATUS_FAIL,
                expected=ubuntu_release,
                observed=observed,
            )
        )
    elif env_id == "macos_actions":
        observed = probe.get("os", "")
        checks.append(
            Check(
                "macos_identity",
                STATUS_PASS if observed == "Darwin" else STATUS_FAIL,
                expected="Darwin",
                observed=observed,
            )
        )
        if macos_runner is not None:
            observed_runner = probe.get("runner_image", "")

            def normalize(value: str) -> str:
                return re.sub(r"[^a-z0-9]", "", value.casefold())

            checks.append(
                Check(
                    "macos_runner",
                    STATUS_PASS
                    if normalize(observed_runner) == normalize(macos_runner)
                    else STATUS_FAIL,
                    expected=macos_runner,
                    observed=observed_runner,
                )
            )
    return checks


def _hygiene_checks(environ: Mapping[str, str]) -> list[Check]:
    return [
        Check(
            f"env_var:{name}",
            STATUS_PASS if bool(environ.get(name)) else STATUS_FAIL,
            expected="set",
            observed="set" if environ.get(name) else "unset",
        )
        for name in REQUIRED_CLAUDE_ENV_VARS
    ]


def audit_environment(
    env_id: str,
    *,
    agy_cli_version: str | None,
    matrix: RuntimeMatrix | None = None,
    environment_factory: Callable[[str], Any] = make_environment,
    agent_factory: Callable[[str, str], Any] = make_agent,
) -> EnvironmentAudit:
    checks: list[Check] = []
    probe: dict[str, str] = {"env_id": env_id}
    try:
        environment = environment_factory(env_id)
    except Exception as exc:  # noqa: BLE001 - failure must become evidence
        checks.append(
            Check(
                "environment_constructed",
                STATUS_FAIL,
                expected="adapter constructed",
                detail=_safe_error(exc),
            )
        )
        return EnvironmentAudit(env_id, tuple(checks), probe)

    checks.append(Check("environment_constructed", STATUS_PASS))
    try:
        raw_probe = environment.probe()
        probe = {str(key): str(value) for key, value in raw_probe.items()}
        checks.extend(
            _environment_probe_checks(
                env_id,
                probe,
                pwsh_version=(matrix.pwsh_version if matrix else V1_PWSH_VERSION),
                ubuntu_release=(
                    matrix.ubuntu_release if matrix else V1_UBUNTU_RELEASE
                ),
                windows_release=matrix.windows_release if matrix else None,
                macos_runner=matrix.macos_runner if matrix else None,
                node_version=matrix.node_version if matrix else None,
            )
        )
    except Exception as exc:  # noqa: BLE001 - report, do not abort other paths
        checks.append(
            Check(
                "environment_probe",
                STATUS_FAIL,
                expected="probe completed",
                detail=_safe_error(exc),
            )
        )

    for agent_id, model_id, expected_version in _agent_specs(
        agy_cli_version, matrix
    ):
        check_id = f"agent_cli:{agent_id}"
        if expected_version is None:
            checks.append(
                Check(
                    check_id,
                    STATUS_BLOCKED,
                    expected="day-one agy version supplied with --agy-cli-version",
                    detail="agy is pin-at-collection-start; no implicit pin is allowed",
                )
            )
            continue
        try:
            agent = agent_factory(agent_id, model_id)
            observed = str(agent.cli_version(environment)).strip()
        except Exception as exc:  # noqa: BLE001 - report, do not abort matrix
            checks.append(
                Check(
                    check_id,
                    STATUS_FAIL,
                    expected=expected_version,
                    detail=_safe_error(exc),
                )
            )
            continue
        checks.append(
            Check(
                check_id,
                STATUS_PASS
                if _version_token_present(observed, expected_version)
                else STATUS_FAIL,
                expected=expected_version,
                observed=observed[:500],
            )
        )

    return EnvironmentAudit(env_id, tuple(checks), probe)


def run_audit(
    env_ids: Sequence[str],
    *,
    agy_cli_version: str | None,
    matrix: RuntimeMatrix | None = None,
    environ: Mapping[str, str] | None = None,
    environment_factory: Callable[[str], Any] = make_environment,
    agent_factory: Callable[[str, str], Any] = make_agent,
    created_at: str | None = None,
    observed_python_version: str | None = None,
) -> PreflightAudit:
    if matrix is not None and agy_cli_version is not None:
        raise ValueError("supply matrix or agy_cli_version, not both")
    unknown = set(env_ids) - set(ENVIRONMENTS)
    if unknown:
        raise ValueError(
            f"unknown environment(s) {sorted(unknown)}; expected {list(ENVIRONMENTS)}"
        )
    if not env_ids:
        raise ValueError("at least one --env is required")
    if len(set(env_ids)) != len(env_ids):
        raise ValueError("duplicate --env values are not allowed")

    effective_environ = os.environ if environ is None else environ
    audits = tuple(
        audit_environment(
            env_id,
            agy_cli_version=agy_cli_version,
            matrix=matrix,
            environment_factory=environment_factory,
            agent_factory=agent_factory,
        )
        for env_id in env_ids
    )
    controller_checks = _hygiene_checks(effective_environ)
    if matrix is not None:
        observed_python = observed_python_version or platform.python_version()
        controller_checks.append(
            Check(
                "python_version",
                STATUS_PASS
                if observed_python == matrix.python_version
                else STATUS_FAIL,
                expected=matrix.python_version,
                observed=observed_python,
            )
        )
    return PreflightAudit(
        schema_version=SCHEMA_VERSION,
        created_at=created_at or _utc_now(),
        zero_quota=True,
        matrix_status=matrix.status if matrix else None,
        matrix_digest=matrix.digest if matrix else None,
        environments=audits,
        controller_checks=tuple(controller_checks),
    )


def write_audit(audit: PreflightAudit, output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(audit.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite existing audit: {output}") from exc


def _print_summary(audit: PreflightAudit) -> None:
    print(f"zero-quota collection preflight: {'PASS' if audit.passed else 'NOT READY'}")
    for check in audit.controller_checks:
        print(f"  {check.status:7} controller/{check.check_id}")
    for environment in audit.environments:
        print(f"  {environment.env_id}: {'PASS' if environment.passed else 'NOT READY'}")
        for check in environment.checks:
            suffix = ""
            if check.observed is not None:
                suffix = f" observed={check.observed!r}"
            elif check.detail is not None:
                suffix = f" detail={check.detail!r}"
            print(f"    {check.status:7} {check.check_id}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--env",
        action="append",
        dest="env_ids",
        choices=ENVIRONMENTS,
        required=True,
        help="collection path to audit; repeat for multiple paths",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        help="candidate or frozen runtime-matrix JSON (required for V2)",
    )
    parser.add_argument(
        "--agy-cli-version",
        help="legacy V1 diagnostic mode; omission blocks agy unless --matrix is used",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="new JSON artifact path (existing files are never overwritten)",
    )
    args = parser.parse_args(argv)
    if args.matrix is not None and args.agy_cli_version is not None:
        parser.error("supply --matrix or --agy-cli-version, not both")
    audit = run_audit(
        args.env_ids,
        agy_cli_version=args.agy_cli_version,
        matrix=load_matrix(args.matrix) if args.matrix is not None else None,
    )
    _print_summary(audit)
    if args.output is not None:
        write_audit(audit, args.output)
        print(f"artifact: {args.output.resolve()}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
