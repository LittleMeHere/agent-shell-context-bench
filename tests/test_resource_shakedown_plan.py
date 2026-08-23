from __future__ import annotations

import dataclasses
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.configuration_matrix import load_matrix
from scripts.resource_shakedown_plan import (
    CORE_VARIANTS,
    MEASUREMENTS,
    build_shakedown_plan,
    validate_plan,
    write_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = REPO_ROOT / "config" / "v2-runtime-matrix.candidate.json"


def _plan():
    return build_shakedown_plan(
        agy_cli_version="1.1.10",
        created_at="2026-08-06T00-00-00Z",
    )


def test_plan_has_exact_stage_and_provider_costs() -> None:
    plan = _plan()
    assert plan.analysis_excluded is True
    assert len(plan.calls) == 82
    assert Counter(call.stage for call in plan.calls) == {
        "resource-core": 70,
        "transport-qualification": 12,
    }
    assert Counter(call.agent_id for call in plan.calls) == {
        "claude_code": 24,
        "codex": 24,
        "agy": 34,
    }


def test_v2_candidate_plan_is_bound_to_matrix_and_current_candidate_models() -> None:
    matrix = load_matrix(CANDIDATE)
    plan = build_shakedown_plan(
        matrix=matrix,
        created_at="2026-08-06T00-00-00Z",
    )
    assert plan.matrix_status == "candidate"
    assert plan.matrix_digest == matrix.digest
    models = {call.config_id: call.model_id for call in plan.calls}
    assert models["CFG3"] == "gpt-5.6-sol"
    assert models["CFG4"] == "gpt-5.6-terra"
    assert models["CFG6"] == "gemini-3.6-flash-medium"


def test_core_covers_every_config_variant_and_two_replicates() -> None:
    core = [call for call in _plan().calls if call.stage == "resource-core"]
    assert {call.config_id for call in core} == {
        "CFG1",
        "CFG2",
        "CFG3",
        "CFG4",
        "CFG5",
        "CFG6",
        "CFG7",
    }
    assert {
        (call.task_id, call.phrasing, call.stratum) for call in core
    } == set(CORE_VARIANTS)
    counts = Counter(
        (call.config_id, call.task_id, call.phrasing) for call in core
    )
    assert set(counts.values()) == {2}
    assert {call.replicate for call in core} == {1, 2}


def test_transport_stage_is_nonduplicative_workhorse_c01() -> None:
    transport = [
        call for call in _plan().calls if call.stage == "transport-qualification"
    ]
    assert {call.env_id for call in transport} == {
        "windows_pwsh7",
        "windows_wsl2",
        "linux_native",
        "macos_actions",
    }
    assert {call.config_id for call in transport} == {"CFG2", "CFG4", "CFG6"}
    assert {(call.task_id, call.phrasing) for call in transport} == {
        ("C01", "default")
    }
    assert len({call.call_id for call in transport}) == 12


def test_plan_binds_task_hashes_versions_and_measurements() -> None:
    plan = _plan()
    assert all(len(call.task_sha256) == 64 for call in plan.calls)
    assert all(call.measurements == MEASUREMENTS for call in plan.calls)
    assert {
        call.expected_cli_version
        for call in plan.calls
        if call.agent_id == "agy"
    } == {"1.1.10"}
    assert {
        call.expected_cli_version
        for call in plan.calls
        if call.agent_id == "claude_code"
    } == {"2.1.176"}
    assert {
        call.expected_cli_version
        for call in plan.calls
        if call.agent_id == "codex"
    } == {"0.139.0"}


def test_digest_and_order_are_reproducible_but_timestamp_independent() -> None:
    first = build_shakedown_plan(
        agy_cli_version="1.1.10",
        order_seed=42,
        created_at="first",
    )
    second = build_shakedown_plan(
        agy_cli_version="1.1.10",
        order_seed=42,
        created_at="second",
    )
    other = build_shakedown_plan(
        agy_cli_version="1.1.10",
        order_seed=43,
        created_at="first",
    )
    assert first.digest == second.digest
    assert [call.call_id for call in first.calls] == [
        call.call_id for call in second.calls
    ]
    assert first.digest != other.digest


def test_validation_rejects_tamper_and_nonexcluded_plan() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_plan(dataclasses.replace(plan, digest="0" * 64))
    with pytest.raises(ValueError, match="analysis_excluded"):
        validate_plan(dataclasses.replace(plan, analysis_excluded=False))


def test_empty_agy_version_and_overwrite_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="matrix or agy_cli_version"):
        build_shakedown_plan(agy_cli_version=" ")
    with pytest.raises(ValueError, match="not both"):
        build_shakedown_plan(
            agy_cli_version="1.1.10", matrix=load_matrix(CANDIDATE)
        )
    output = tmp_path / "shakedown.json"
    write_plan(_plan(), output)
    raw = json.loads(output.read_text(encoding="utf-8"))
    assert raw["analysis_excluded"] is True
    assert len(raw["calls"]) == 82
    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_plan(_plan(), output)
