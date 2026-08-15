"""Load and validate an explicit collection runtime matrix.

The matrix is deliberately separate from the frozen V1 scheduler constants.
It lets pre-data V2 qualification bind model labels, CLI versions, and the
version-sensitive environment pins before any paid benchmark call is made.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.scheduler import (
    CLAUDE_CONFIGS,
    CODEX_CONFIGS,
    ModelConfig,
    RuntimeBinding,
    _agy_configs,
)

SCHEMA_VERSION = "1.0.0"
VALID_STATUSES = {"candidate", "frozen", "legacy-diagnostic"}
EXPECTED_AGENT_BY_CONFIG = {
    "CFG1": "claude_code",
    "CFG2": "claude_code",
    "CFG3": "codex",
    "CFG4": "codex",
    "CFG5": "agy",
    "CFG6": "agy",
    "CFG7": "agy",
}


@dataclass(frozen=True)
class RuntimeConfiguration:
    config_id: str
    agent_id: str
    model_id: str
    nominal_model_id: str
    expected_cli_version: str


@dataclass(frozen=True)
class RuntimeMatrix:
    schema_version: str
    status: str
    as_of_date: str
    python_version: str
    node_version: str
    windows_release: str
    pwsh_version: str
    ubuntu_release: str
    macos_runner: str
    configurations: tuple[RuntimeConfiguration, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "as_of_date": self.as_of_date,
            "python_version": self.python_version,
            "node_version": self.node_version,
            "windows_release": self.windows_release,
            "pwsh_version": self.pwsh_version,
            "ubuntu_release": self.ubuntu_release,
            "macos_runner": self.macos_runner,
            "configurations": [
                dataclasses.asdict(config) for config in self.configurations
            ],
        }

    def pin_payload(self) -> dict[str, Any]:
        """Return scientific/runtime identity, excluding workflow state."""
        payload = self.as_dict()
        payload.pop("status")
        return payload

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.pin_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def model_configs(self) -> tuple[ModelConfig, ...]:
        return tuple(
            ModelConfig(
                config.config_id,
                config.agent_id,
                config.model_id,
                config.expected_cli_version,
            )
            for config in self.configurations
        )

    def scheduler_binding(self) -> RuntimeBinding:
        """Project a frozen matrix into the scheduler's signed plan payload."""
        if self.status != "frozen":
            raise ValueError("scheduler plans require a frozen runtime matrix")
        return RuntimeBinding(
            matrix_digest=self.digest,
            matrix_status=self.status,
            configurations=self.model_configs(),
        )


def validate_matrix(matrix: RuntimeMatrix) -> None:
    if matrix.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported runtime-matrix schema {matrix.schema_version!r}")
    if matrix.status not in VALID_STATUSES:
        raise ValueError(
            f"invalid runtime-matrix status {matrix.status!r}; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", matrix.as_of_date) is None:
        raise ValueError("runtime matrix as_of_date must use YYYY-MM-DD")
    for name, value in (
        ("python_version", matrix.python_version),
        ("node_version", matrix.node_version),
        ("windows_release", matrix.windows_release),
        ("pwsh_version", matrix.pwsh_version),
        ("ubuntu_release", matrix.ubuntu_release),
        ("macos_runner", matrix.macos_runner),
    ):
        if not value.strip():
            raise ValueError(f"runtime matrix {name} must be non-empty")

    ids = [config.config_id for config in matrix.configurations]
    if len(ids) != len(EXPECTED_AGENT_BY_CONFIG) or set(ids) != set(
        EXPECTED_AGENT_BY_CONFIG
    ):
        raise ValueError(
            "runtime matrix must contain exactly one of CFG1 through CFG7"
        )
    for config in matrix.configurations:
        expected_agent = EXPECTED_AGENT_BY_CONFIG[config.config_id]
        if config.agent_id != expected_agent:
            raise ValueError(
                f"{config.config_id} must use {expected_agent}, "
                f"found {config.agent_id}"
            )
        for name, value in (
            ("model_id", config.model_id),
            ("nominal_model_id", config.nominal_model_id),
            ("expected_cli_version", config.expected_cli_version),
        ):
            if not value.strip():
                raise ValueError(f"{config.config_id} {name} must be non-empty")

    versions_by_agent: dict[str, set[str]] = {}
    for config in matrix.configurations:
        versions_by_agent.setdefault(config.agent_id, set()).add(
            config.expected_cli_version
        )
    inconsistent = {
        agent: sorted(versions)
        for agent, versions in versions_by_agent.items()
        if len(versions) != 1
    }
    if inconsistent:
        raise ValueError(
            "one executable cannot have multiple expected versions per agent: "
            f"{inconsistent}"
        )

    by_id = {config.config_id: config for config in matrix.configurations}
    if by_id["CFG2"].nominal_model_id != by_id["CFG7"].nominal_model_id:
        raise ValueError(
            "CFG2 and CFG7 must share nominal_model_id for the S6 "
            "same-model harness-control contrast"
        )


def load_matrix(path: Path) -> RuntimeMatrix:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        matrix = RuntimeMatrix(
            schema_version=str(raw["schema_version"]),
            status=str(raw["status"]),
            as_of_date=str(raw["as_of_date"]),
            python_version=str(raw["python_version"]),
            node_version=str(raw["node_version"]),
            windows_release=str(raw["windows_release"]),
            pwsh_version=str(raw["pwsh_version"]),
            ubuntu_release=str(raw["ubuntu_release"]),
            macos_runner=str(raw["macos_runner"]),
            configurations=tuple(
                RuntimeConfiguration(**config) for config in raw["configurations"]
            ),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load runtime matrix {path}: {exc}") from exc
    validate_matrix(matrix)
    return matrix


def write_matrix(matrix: RuntimeMatrix, output: Path) -> None:
    validate_matrix(matrix)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(matrix.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite existing matrix: {output}") from exc


def legacy_v1_matrix(agy_cli_version: str) -> RuntimeMatrix:
    """Materialize the frozen V1 constants for an analysis-excluded diagnostic."""
    if not agy_cli_version.strip():
        raise ValueError("agy_cli_version must be the observed diagnostic build")
    configs = (*CLAUDE_CONFIGS, *CODEX_CONFIGS, *_agy_configs(agy_cli_version.strip()))
    nominal = {
        "CFG1": "claude-opus-4-8",
        "CFG2": "claude-sonnet-4-6",
        "CFG3": "gpt-5.5",
        "CFG4": "gpt-5.4-mini",
        "CFG5": "gemini-3.1-pro",
        "CFG6": "gemini-3.5-flash",
        "CFG7": "claude-sonnet-4-6",
    }
    matrix = RuntimeMatrix(
        schema_version=SCHEMA_VERSION,
        status="legacy-diagnostic",
        as_of_date="2026-06-12",
        python_version="3.11.9",
        node_version="not-pinned-v1",
        windows_release="Windows 11",
        pwsh_version="7.6.2",
        ubuntu_release="Ubuntu 24.04",
        macos_runner="macos-26",
        configurations=tuple(
            RuntimeConfiguration(
                config.config_id,
                config.agent_id,
                config.model_id,
                nominal[config.config_id],
                str(config.expected_cli_version),
            )
            for config in configs
        ),
    )
    validate_matrix(matrix)
    return matrix
