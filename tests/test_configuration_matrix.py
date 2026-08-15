from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from scripts.configuration_matrix import (
    RuntimeConfiguration,
    RuntimeMatrix,
    legacy_v1_matrix,
    load_matrix,
    validate_matrix,
    write_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = REPO_ROOT / "config" / "v2-runtime-matrix.candidate.json"


def test_candidate_is_valid_and_binds_same_model_control() -> None:
    matrix = load_matrix(CANDIDATE)
    assert matrix.status == "candidate"
    assert len(matrix.digest) == 64
    by_id = {config.config_id: config for config in matrix.configurations}
    assert by_id["CFG2"].nominal_model_id == by_id["CFG7"].nominal_model_id
    assert by_id["CFG3"].model_id == "gpt-5.6-sol"
    assert by_id["CFG4"].model_id == "gpt-5.6-terra"
    assert dataclasses.replace(matrix, status="frozen").digest == matrix.digest
    with pytest.raises(ValueError, match="require a frozen"):
        matrix.scheduler_binding()
    binding = dataclasses.replace(matrix, status="frozen").scheduler_binding()
    assert binding.matrix_digest == matrix.digest
    assert binding.matrix_status == "frozen"
    assert len(binding.configurations) == 7


def test_matrix_rejects_broken_s6_pair_and_agent_assignment() -> None:
    matrix = load_matrix(CANDIDATE)
    configs = list(matrix.configurations)
    cfg7_index = next(
        index for index, config in enumerate(configs) if config.config_id == "CFG7"
    )
    configs[cfg7_index] = dataclasses.replace(
        configs[cfg7_index], nominal_model_id="claude-sonnet-5"
    )
    with pytest.raises(ValueError, match="same-model harness-control"):
        validate_matrix(dataclasses.replace(matrix, configurations=tuple(configs)))

    configs = list(matrix.configurations)
    configs[0] = dataclasses.replace(configs[0], agent_id="codex")
    with pytest.raises(ValueError, match="CFG1 must use claude_code"):
        validate_matrix(dataclasses.replace(matrix, configurations=tuple(configs)))


def test_matrix_rejects_mixed_versions_within_one_cli() -> None:
    matrix = load_matrix(CANDIDATE)
    configs = list(matrix.configurations)
    configs[1] = dataclasses.replace(configs[1], expected_cli_version="different")
    with pytest.raises(ValueError, match="multiple expected versions"):
        validate_matrix(dataclasses.replace(matrix, configurations=tuple(configs)))


def test_legacy_matrix_is_explicitly_diagnostic() -> None:
    matrix = legacy_v1_matrix("1.1.10")
    assert matrix.status == "legacy-diagnostic"
    assert {config.expected_cli_version for config in matrix.configurations if config.agent_id == "agy"} == {"1.1.10"}


def test_load_and_write_fail_closed(tmp_path: Path) -> None:
    matrix = load_matrix(CANDIDATE)
    output = tmp_path / "matrix.json"
    write_matrix(matrix, output)
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "candidate"
    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_matrix(matrix, output)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot load runtime matrix"):
        load_matrix(malformed)
