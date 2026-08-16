from __future__ import annotations

import copy
import hashlib

import pytest

from analysis.v2_analysis_dataset import (
    AnalysisDatasetError,
    accepted_family_domains,
    build_analysis_dataset,
    derive_analysis_trial,
    finite_roster_h1_point_estimate,
)
from analysis.v2_finite_roster import finite_roster_epoch_sensitivity
from harness.outcomes import construct_agy_outcome_evidence, construct_binary_outcome
from harness.scheduler import (
    AGY_MINI_PILOT_PHASE,
    V2_PILOT_PHASE,
    build_plan,
    schedule_identity_for_cell,
)


def _record(plan, cell, index: int, *, success: bool = True) -> dict:
    outcome = construct_binary_outcome(
        checks_passed=success,
        completed=True,
        timed_out=False,
    )
    attempt_id = hashlib.sha256(
        f"{cell.cell_id}:{index}".encode("utf-8")
    ).hexdigest()[:32]
    return {
        "schema_version": plan.trial_schema_version,
        "trial": {
            "task_id": cell.task_id,
            "family_id": cell.family_id,
            "instance_id": cell.instance_id,
            "instance_sha256": cell.instance_sha256,
            "task_category": (
                "capability" if cell.task_id.startswith("C") else "seeded_error"
            ),
            "agent_id": cell.agent_id,
            "model_id": cell.model_id,
            "env_id": cell.env_id,
            "phrasing": cell.phrasing,
            "trial_index": index,
        },
        "attempt": {"attempt_id": attempt_id},
        "schedule": schedule_identity_for_cell(
            plan, cell, valid_slot_index=index
        ).as_dict(),
        "environment_probe": {"env_id": cell.env_id},
        "agent": {
            "completed": True,
            "process": {"timed_out": False, "returncode": 0},
        },
        "outcome": {
            "success": outcome.success,
            "checks_passed": outcome.checks_passed,
            "decision_reason": outcome.decision_reason,
            "checks": [
                {
                    "check_type": "test",
                    "passed": success,
                    "detail": "synthetic",
                    "evidence": "",
                }
            ],
        },
        "validity": {"valid": True, "harness_error": None},
        "measurement": {"status": "complete"},
    }


@pytest.fixture(scope="module")
def v2_plan(frozen_runtime_binding):
    return build_plan(
        V2_PILOT_PHASE, runtime_binding=frozen_runtime_binding
    )


def test_derive_analysis_trial_reconstructs_common_outcome(v2_plan) -> None:
    cell = v2_plan.cells[0]
    row = derive_analysis_trial(_record(v2_plan, cell, 0, success=False))
    assert row.config_id == cell.config_id
    assert row.valid_analysis_trial
    assert not row.binary_success_final
    assert row.failed is True


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda raw: raw["outcome"].__setitem__("success", False),
            "outcome.success contradicts",
        ),
        (
            lambda raw: raw["agent"]["process"].__setitem__("timed_out", True),
            "completion contradicts",
        ),
        (
            lambda raw: raw["trial"].__setitem__("family_id", "C99"),
            "trial.family_id contradicts",
        ),
        (
            lambda raw: raw["schedule"].__setitem__("token_sha256", "0" * 64),
            "invalid schedule identity",
        ),
    ],
)
def test_analysis_reconstruction_rejects_forged_records(
    v2_plan, mutator, message
) -> None:
    raw = _record(v2_plan, v2_plan.cells[0], 0)
    mutator(raw)
    with pytest.raises(AnalysisDatasetError, match=message):
        derive_analysis_trial(raw)


def test_analysis_reconstruction_rejects_timeout_that_claims_success(v2_plan) -> None:
    raw = _record(v2_plan, v2_plan.cells[0], 0)
    raw["agent"]["completed"] = False
    raw["agent"]["process"] = {"timed_out": True, "returncode": None}
    with pytest.raises(AnalysisDatasetError, match="outcome.success contradicts"):
        derive_analysis_trial(raw)


def test_agy_d011_is_reconstructed_from_raw_cwd_evidence() -> None:
    plan = build_plan(AGY_MINI_PILOT_PHASE, agy_cli_version="0.2.6")
    cell = plan.cells[0]
    raw = _record(plan, cell, 0)
    evidence = construct_agy_outcome_evidence(
        checks_passed=True,
        completed=True,
        timed_out=False,
        brain_status="present",
        cwd_tags=["cwd_in_sandbox"],
    )
    raw["agy"] = {
        "brain_transcript_located": True,
        "brain_conversation_candidates": 1,
        "brain_parse_status": "present",
        "brain_valid_event_count": 2,
        "brain_malformed_line_count": 0,
        "brain_shell_call_count": 1,
        "brain_outcome_event_count": 1,
        "cwd_compliance": {
            "commands": 1,
            "cwd_in_sandbox": 1,
            "cwd_in_agy_scratch": 0,
            "cwd_elsewhere": 0,
            "sandbox_compliance_rate": 1.0,
        },
        "cwd_tags": [
            {"index": 0, "cwd": "/work/sandbox", "tag": "cwd_in_sandbox"}
        ],
        "v2_outcome_evidence": evidence.as_log_dict(),
    }
    row = derive_analysis_trial(raw)
    assert row.transcript_analysis_eligible is True
    assert row.agy_cwd_status == "all_in_sandbox"

    forged = copy.deepcopy(raw)
    forged["agy"]["v2_outcome_evidence"]["cwd_status"] = "mixed"
    with pytest.raises(AnalysisDatasetError, match="D-011 evidence contradicts"):
        derive_analysis_trial(forged)


def test_complete_v2_plan_builds_and_equal_weight_point_estimator_recovers(v2_plan) -> None:
    records = []
    for cell in v2_plan.cells:
        for index in range(cell.target_valid_trials):
            failure = (
                cell.task_id.startswith("C")
                and cell.env_id == "windows_powershell"
            )
            records.append(_record(v2_plan, cell, index, success=not failure))
    rows = build_analysis_dataset(v2_plan, records)
    assert len(rows) == 720
    assert [row.execution_position for row in rows] == list(range(720))
    assert [sum(row.collection_epoch == epoch for row in rows) for epoch in range(4)] == [
        180,
        180,
        180,
        180,
    ]
    estimate = finite_roster_h1_point_estimate(rows)
    assert estimate.windows_failure_rate == pytest.approx(1.0)
    assert estimate.linux_failure_rate == pytest.approx(0.0)
    assert estimate.risk_difference == pytest.approx(1.0)
    assert estimate.risk_ratio == float("inf")
    assert (
        estimate.domains,
        estimate.families,
        estimate.instances,
        estimate.configurations,
        estimate.trials,
    ) == (6, 12, 3, 2, 144)


def test_complete_v2_plan_epoch_sensitivity_matches_frozen_composition(v2_plan) -> None:
    records = []
    for cell in v2_plan.cells:
        for index in range(cell.target_valid_trials):
            failure = (
                cell.task_id.startswith("C")
                and cell.env_id == "windows_powershell"
            )
            records.append(_record(v2_plan, cell, index, success=not failure))
    rows = build_analysis_dataset(v2_plan, records)
    reports = finite_roster_epoch_sensitivity(rows)

    assert [report.status for report in reports] == [
        "estimated",
        "estimated",
        "estimated",
        "not_applicable_no_capability_trials",
    ]
    for report in reports[:3]:
        assert report.result is not None
        assert report.result.fallback_used
        assert report.result.risk_difference == pytest.approx(1.0)
    assert reports[3].capability_trials == 0


def test_finite_roster_estimator_equal_weights_domains_and_families(v2_plan) -> None:
    rows = []
    for cell in v2_plan.cells:
        if not cell.task_id.startswith("C"):
            continue
        if cell.env_id not in {"windows_powershell", "linux_native"}:
            continue
        failure = cell.env_id == "windows_powershell" and cell.family_id == "C01"
        rows.append(
            derive_analysis_trial(_record(v2_plan, cell, 0, success=not failure))
        )
    estimate = finite_roster_h1_point_estimate(rows)
    assert estimate.windows_failure_rate == pytest.approx(1 / 12)
    assert estimate.linux_failure_rate == 0.0
    assert estimate.risk_difference == pytest.approx(1 / 12)


def test_dataset_builder_fails_on_incomplete_duplicate_and_excess_slots(v2_plan) -> None:
    first = _record(v2_plan, v2_plan.cells[0], 0)
    with pytest.raises(AnalysisDatasetError, match="incomplete valid slots"):
        build_analysis_dataset(v2_plan, [first])

    with pytest.raises(AnalysisDatasetError, match="duplicate analysis-trial"):
        build_analysis_dataset(v2_plan, [first, copy.deepcopy(first)])

    cell = next(cell for cell in v2_plan.cells if cell.target_valid_trials == 1)
    duplicate_slot = [_record(v2_plan, cell, 0), _record(v2_plan, cell, 0)]
    duplicate_slot[1]["trial"]["trial_index"] = 1
    duplicate_slot[1]["attempt"]["attempt_id"] = "f" * 32
    with pytest.raises(AnalysisDatasetError, match="duplicate valid slot"):
        build_analysis_dataset(v2_plan, duplicate_slot)

    first_cell, second_cell = v2_plan.cells[:2]
    first_attempt = _record(v2_plan, first_cell, 0)
    repeated_attempt = _record(v2_plan, second_cell, 0)
    repeated_attempt["attempt"]["attempt_id"] = first_attempt["attempt"]["attempt_id"]
    with pytest.raises(AnalysisDatasetError, match="duplicate attempt_id"):
        build_analysis_dataset(v2_plan, [first_attempt, repeated_attempt])


def test_family_domain_mapping_is_the_accepted_six_by_two_roster() -> None:
    mapping = accepted_family_domains()
    assert len(mapping) == 12
    assert sorted(mapping.values()).count("A") == 2
    assert set(mapping.values()) == set("ABCDEF")
